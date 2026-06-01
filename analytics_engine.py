"""
Модуль аналитики и прогнозирования для приюта «Добрые Лапки».

Методы прогноза (без внешних ML-библиотек — чистая математика на Python):
- OLS — линейная регрессия (метод наименьших квадратов)
- SES — простое экспоненциальное сглаживание
- Holt — линейный тренд (двойное экспоненциальное сглаживание)
- SMA / WMA — скользящее и взвешенное скользящее среднее
- Ensemble — усреднение прогнозов с доверительным интервалом
"""

from __future__ import annotations

from datetime import datetime, timedelta
from statistics import mean, pstdev
from typing import Any


def _ols_slope_intercept(y: list[float]) -> tuple[float, float]:
    """МНК: y = intercept + slope * x, x = 0..n-1."""
    n = len(y)
    if n < 2:
        return y[0] if y else 0.0, 0.0
    x_sum = sum(range(n))
    y_sum = sum(y)
    xy_sum = sum(i * y[i] for i in range(n))
    x2_sum = sum(i * i for i in range(n))
    denom = n * x2_sum - x_sum * x_sum
    if denom == 0:
        return mean(y), 0.0
    slope = (n * xy_sum - x_sum * y_sum) / denom
    intercept = (y_sum - slope * x_sum) / n
    return intercept, slope


def forecast_linear_regression(values: list[float], horizon: int) -> list[float]:
    """Прогноз линейной регрессией (экстраполяция тренда)."""
    if not values:
        return [0.0] * horizon
    if len(values) == 1:
        return [max(0.0, values[0])] * horizon
    intercept, slope = _ols_slope_intercept(values)
    n = len(values)
    return [max(0.0, intercept + slope * (n + i)) for i in range(horizon)]


def forecast_ses(values: list[float], horizon: int, alpha: float = 0.35) -> list[float]:
    """Простое экспоненциальное сглаживание (SES)."""
    if not values:
        return [0.0] * horizon
    level = values[0]
    for v in values[1:]:
        level = alpha * v + (1 - alpha) * level
    return [max(0.0, level)] * horizon


def forecast_holt(
    values: list[float], horizon: int, alpha: float = 0.35, beta: float = 0.15
) -> list[float]:
    """Метод Хольта: уровень + линейный тренд (двойное эксп. сглаживание)."""
    if not values:
        return [0.0] * horizon
    if len(values) == 1:
        return [max(0.0, values[0])] * horizon

    level = values[0]
    trend = values[1] - values[0]
    for v in values[1:]:
        prev_level = level
        level = alpha * v + (1 - alpha) * (level + trend)
        trend = beta * (level - prev_level) + (1 - beta) * trend

    return [max(0.0, level + trend * (i + 1)) for i in range(horizon)]


def forecast_sma(values: list[float], horizon: int, window: int = 3) -> list[float]:
    """Прогноз скользящим средним последних window точек."""
    if not values:
        return [0.0] * horizon
    w = min(window, len(values))
    avg = mean(values[-w:])
    return [max(0.0, avg)] * horizon


def forecast_wma(values: list[float], horizon: int, window: int = 3) -> list[float]:
    """Взвешенное скользящее среднее (больший вес у свежих данных)."""
    if not values:
        return [0.0] * horizon
    w = min(window, len(values))
    chunk = values[-w:]
    weights = list(range(1, w + 1))
    weighted = sum(c * wt for c, wt in zip(chunk, weights)) / sum(weights)
    return [max(0.0, weighted)] * horizon


def forecast_ensemble(values: list[float], horizon: int) -> dict[str, Any]:
    """
    Ансамблевый прогноз: среднее по методам + 95% интервал (эвристика по разбросу).
    """
    if not values:
        zeros = [0.0] * horizon
        return {
            "predictions": zeros,
            "lower": zeros,
            "upper": zeros,
            "methods": {},
            "method_used": "none",
        }

    methods = {
        "linear_regression": forecast_linear_regression(values, horizon),
        "ses": forecast_ses(values, horizon),
        "holt": forecast_holt(values, horizon),
        "sma": forecast_sma(values, horizon),
        "wma": forecast_wma(values, horizon),
    }

    predictions = []
    lowers = []
    uppers = []
    for i in range(horizon):
        pts = [m[i] for m in methods.values()]
        avg = mean(pts)
        spread = pstdev(pts) if len(pts) > 1 else (avg * 0.1 or 1.0)
        predictions.append(round(avg, 2))
        lowers.append(round(max(0, avg - 1.96 * spread), 2))
        uppers.append(round(avg + 1.96 * spread, 2))

    return {
        "predictions": predictions,
        "lower": lowers,
        "upper": uppers,
        "methods": {k: [round(v, 2) for v in vals] for k, vals in methods.items()},
        "method_used": "ensemble",
        "historical_count": len(values),
    }


def future_month_labels(last_month: str, count: int) -> list[str]:
    """Следующие count месяцев после last_month (YYYY-MM)."""
    y, m = map(int, last_month.split("-"))
    labels = []
    for _ in range(count):
        m += 1
        if m > 12:
            m = 1
            y += 1
        labels.append(f"{y:04d}-{m:02d}")
    return labels


def build_forecast_series(
    monthly_rows: list[dict],
    value_key: str = "total",
    month_key: str = "month",
    horizon: int = 3,
) -> dict[str, Any]:
    """Собрать историю + прогноз для одной метрики."""
    if not monthly_rows:
        now = datetime.now()
        labels = [
            (now - timedelta(days=30 * (horizon - i))).strftime("%Y-%m")
            for i in range(horizon)
        ]
        empty = forecast_ensemble([], horizon)
        return {
            "historical": [],
            "forecast": [
                {"month": labels[i], "value": empty["predictions"][i], **empty}
                for i in range(horizon)
            ],
            "labels": labels,
            "ensemble": empty,
        }

    historical = [
        {"month": r[month_key], "value": round(float(r[value_key] or 0), 2)}
        for r in monthly_rows
    ]
    values = [h["value"] for h in historical]
    last_month = historical[-1]["month"]
    future_months = future_month_labels(last_month, horizon)
    ensemble = forecast_ensemble(values, horizon)

    forecast = []
    for i, month in enumerate(future_months):
        forecast.append(
            {
                "month": month,
                "value": ensemble["predictions"][i],
                "lower": ensemble["lower"][i],
                "upper": ensemble["upper"][i],
                "methods": {k: v[i] for k, v in ensemble["methods"].items()},
            }
        )

    return {
        "historical": historical,
        "forecast": forecast,
        "ensemble": ensemble,
    }


def compute_kpis(
    financial: dict,
    animal_stats: list[dict],
    adoption_monthly: list[dict],
) -> list[dict]:
    """KPI-карточки для дашборда."""
    total_animals = sum(s.get("count", 0) for s in animal_stats)
    adopted = next(
        (s["count"] for s in animal_stats if s.get("status") == "Adopted"), 0
    )
    adoption_rate = round((adopted / total_animals * 100), 1) if total_animals else 0

    recent_adoptions = sum(r.get("approved", 0) for r in adoption_monthly[-3:])

    return [
        {
            "id": "donations",
            "label": "Доходы (всего)",
            "value": financial.get("total_donations", 0),
            "sub": f"+{financial.get('monthly_donations', 0)} ₽ за 30 дней",
            "icon": "fa-hand-holding-heart",
            "trend": "up",
        },
        {
            "id": "expenses",
            "label": "Расходы (всего)",
            "value": financial.get("total_expenses", 0),
            "sub": f"{financial.get('monthly_expenses', 0)} ₽ за 30 дней",
            "icon": "fa-cart-shopping",
            "trend": "neutral",
        },
        {
            "id": "balance",
            "label": "Баланс",
            "value": financial.get("balance", 0),
            "sub": f"Месяц: {financial.get('monthly_balance', 0)} ₽",
            "icon": "fa-scale-balanced",
            "trend": "up" if financial.get("balance", 0) >= 0 else "down",
        },
        {
            "id": "adoption_rate",
            "label": "Усыновлено",
            "value": adopted,
            "sub": f"{adoption_rate}% от {total_animals} питомцев",
            "icon": "fa-paw",
            "trend": "up",
        },
        {
            "id": "adoptions_forecast",
            "label": "Заявки (одобрено, 3 мес.)",
            "value": recent_adoptions,
            "sub": "по факту за последние месяцы",
            "icon": "fa-chart-line",
            "trend": "up",
        },
    ]


METHOD_DESCRIPTIONS = [
    {
        "id": "linear_regression",
        "name": "Линейная регрессия (МНК)",
        "formula": "ŷ = a + b·t",
        "description": "Аппроксимация тренда методом наименьших квадратов; экстраполяция на будущие периоды.",
    },
    {
        "id": "ses",
        "name": "Простое эксп. сглаживание (SES)",
        "formula": "L_t = α·y_t + (1−α)·L_{t−1}",
        "description": "Сглаживание уровня ряда; прогноз — последний сглаженный уровень (α=0.35).",
    },
    {
        "id": "holt",
        "name": "Метод Хольта",
        "formula": "ŷ_{t+h} = L_t + h·T_t",
        "description": "Двойное сглаживание: уровень + тренд; подходит при устойчивом росте/падении.",
    },
    {
        "id": "sma",
        "name": "Скользящее среднее (SMA)",
        "formula": "ŷ = mean(y_{t−k}, …, y_t)",
        "description": "Среднее за последние k месяцев (k=3); устойчив к выбросам.",
    },
    {
        "id": "wma",
        "name": "Взвешенное скользящее (WMA)",
        "formula": "ŷ = Σ w_i·y_i",
        "description": "Больший вес у недавних месяцев; быстрее реагирует на изменения.",
    },
    {
        "id": "ensemble",
        "name": "Ансамбль + доверительный интервал",
        "formula": "ŷ = mean(методов); CI ≈ ±1.96·σ",
        "description": "Итоговый прогноз — среднее пяти методов; полоса — разброс между ними.",
    },
]
