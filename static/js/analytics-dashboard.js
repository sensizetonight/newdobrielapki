/**
 * Дашборд аналитики «Добрые Лапки»
 */
(function () {
    'use strict';

    const CHART_ANIM = false;

    const CHART_DEFAULTS = {
        responsive: true,
        maintainAspectRatio: false,
        animation: CHART_ANIM,
        plugins: {
            legend: {
                labels: { color: '#94a3b8', font: { family: 'Inter', size: 11 } },
            },
            tooltip: {
                backgroundColor: 'rgba(15, 20, 25, 0.95)',
                titleColor: '#f1f5f9',
                bodyColor: '#cbd5e1',
                borderColor: 'rgba(255,255,255,0.1)',
                borderWidth: 1,
                padding: 12,
                cornerRadius: 10,
            },
        },
        scales: {
            x: {
                grid: { color: 'rgba(255,255,255,0.05)' },
                ticks: { color: '#94a3b8', maxRotation: 45 },
            },
            y: {
                grid: { color: 'rgba(255,255,255,0.06)' },
                ticks: { color: '#94a3b8' },
                beginAtZero: true,
            },
        },
    };

    let charts = {};
    let currentDays = 30;
    let forecastHorizon = 3;
    let chartsReady = false;

    function fmtMoney(n) {
        return (
            new Intl.NumberFormat('ru-RU', {
                style: 'decimal',
                maximumFractionDigits: 0,
            }).format(n) + ' ₽'
        );
    }

    function destroyChart(id) {
        if (charts[id]) {
            charts[id].destroy();
            delete charts[id];
        }
    }

    function chartUpdate(id) {
        if (charts[id]) charts[id].update('none');
    }

    function buildForecastChart(canvasId, series, color) {
        const canvas = document.getElementById(canvasId);
        if (!canvas) return;

        destroyChart(canvasId);
        const ctx = canvas.getContext('2d');
        const hist = series.historical || [];
        const fc = series.forecast || [];
        const labels = [...hist.map((h) => h.month), ...fc.map((f) => f.month)];
        const histData = [...hist.map((h) => h.value), ...fc.map(() => null)];
        const predData = [...hist.map(() => null), ...fc.map((f) => f.value)];

        const g = ctx.createLinearGradient(0, 0, 0, 280);
        g.addColorStop(0, 'rgba(129, 140, 248, 0.3)');
        g.addColorStop(1, 'rgba(129, 140, 248, 0)');

        charts[canvasId] = new Chart(ctx, {
            type: 'line',
            data: {
                labels,
                datasets: [
                    {
                        label: 'Факт',
                        data: histData,
                        borderColor: color,
                        backgroundColor: g,
                        borderWidth: 2,
                        pointRadius: 3,
                        tension: 0.35,
                        fill: true,
                        spanGaps: false,
                    },
                    {
                        label: 'Прогноз',
                        data: predData,
                        borderColor: '#f472b6',
                        borderWidth: 2,
                        borderDash: [6, 4],
                        pointRadius: 3,
                        tension: 0.35,
                        spanGaps: false,
                    },
                ],
            },
            options: CHART_DEFAULTS,
        });
    }

    async function loadForecasts() {
        try {
            const res = await fetch(
                `/api/analytics/forecasts?horizon=${forecastHorizon}`
            );
            const forecasts = await res.json();

            buildForecastChart(
                'chartDonationsForecast',
                forecasts.donations,
                '#818cf8'
            );
            buildForecastChart(
                'chartExpensesForecast',
                forecasts.expenses,
                '#fb923c'
            );
            buildForecastChart(
                'chartBalanceForecast',
                forecasts.balance,
                '#34d399'
            );
            buildAdoptionForecast(forecasts.adoptions);
            renderInsights(forecasts);
        } catch (e) {
            console.error('Forecast load error', e);
        }
    }

    function renderInsights(forecasts) {
        const strip = document.getElementById('insightStrip');
        if (!strip) return;

        const chips = [];
        const finEl = document.getElementById('kpi-balance-value');
        const monthlyBal = finEl
            ? parseFloat(finEl.dataset.monthly || '0')
            : 0;

        if (monthlyBal < 0) {
            chips.push({
                text: 'Месячный баланс отрицательный — рекомендуем усилить сбор',
                warn: true,
            });
        }

        const nextExp = forecasts.expenses?.forecast?.[0]?.value;
        if (nextExp != null) {
            chips.push({
                text: `Прогноз расходов: ${fmtMoney(nextExp)}`,
                warn: false,
            });
        }

        const nextDon = forecasts.donations?.forecast?.[0]?.value;
        if (nextDon != null) {
            chips.push({
                text: `Прогноз пожертвований: ${fmtMoney(nextDon)}`,
                warn: false,
            });
        }

        strip.innerHTML = chips.length
            ? chips
                  .map(
                      (c) =>
                          `<div class="insight-chip ${c.warn ? 'warn' : ''}">${c.text}</div>`
                  )
                  .join('')
            : '';
        strip.classList.toggle('is-empty', chips.length === 0);
    }

    function buildAdoptionForecast(adoptions) {
        const canvas = document.getElementById('chartAdoptionsForecast');
        if (!canvas) return;

        destroyChart('chartAdoptionsForecast');
        const ctx = canvas.getContext('2d');
        const hist = adoptions.historical || [];
        const fc = adoptions.forecast || [];
        const labels = [...hist.map((h) => h.month), ...fc.map((f) => f.month)];

        charts.chartAdoptionsForecast = new Chart(ctx, {
            type: 'bar',
            data: {
                labels,
                datasets: [
                    {
                        label: 'Одобрено (факт)',
                        data: [...hist.map((h) => h.value), ...fc.map(() => null)],
                        backgroundColor: 'rgba(52, 211, 153, 0.75)',
                        borderRadius: 6,
                    },
                    {
                        label: 'Прогноз',
                        data: [...hist.map(() => null), ...fc.map((f) => f.value)],
                        backgroundColor: 'rgba(244, 114, 182, 0.75)',
                        borderRadius: 6,
                    },
                ],
            },
            options: CHART_DEFAULTS,
        });
    }

    function initTimelineCharts() {
        const donationsCtx = document.getElementById('donationsChart');
        if (!donationsCtx) return;

        charts.donationsChart = new Chart(donationsCtx.getContext('2d'), {
            type: 'line',
            data: {
                labels: [],
                datasets: [
                    {
                        label: 'Сумма (₽)',
                        data: [],
                        borderColor: '#818cf8',
                        backgroundColor: 'rgba(129, 140, 248, 0.12)',
                        fill: true,
                        tension: 0.35,
                    },
                ],
            },
            options: CHART_DEFAULTS,
        });

        charts.adoptionsChart = new Chart(
            document.getElementById('adoptionsChart').getContext('2d'),
            {
                type: 'bar',
                data: {
                    labels: [],
                    datasets: [
                        {
                            label: 'Одобрено',
                            data: [],
                            backgroundColor: 'rgba(52, 211, 153, 0.8)',
                            borderRadius: 6,
                        },
                        {
                            label: 'Ожидание',
                            data: [],
                            backgroundColor: 'rgba(251, 191, 36, 0.8)',
                            borderRadius: 6,
                        },
                        {
                            label: 'Отклонено',
                            data: [],
                            backgroundColor: 'rgba(248, 113, 113, 0.8)',
                            borderRadius: 6,
                        },
                    ],
                },
                options: {
                    ...CHART_DEFAULTS,
                    scales: {
                        x: { ...CHART_DEFAULTS.scales.x, stacked: true },
                        y: { ...CHART_DEFAULTS.scales.y, stacked: true },
                    },
                },
            }
        );

        charts.inventoryChart = new Chart(
            document.getElementById('inventoryChart').getContext('2d'),
            {
                type: 'doughnut',
                data: {
                    labels: [],
                    datasets: [
                        {
                            data: [],
                            backgroundColor: [
                                '#818cf8',
                                '#34d399',
                                '#fbbf24',
                                '#f472b6',
                            ],
                            borderWidth: 0,
                        },
                    ],
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    animation: CHART_ANIM,
                    cutout: '68%',
                    plugins: {
                        legend: {
                            position: 'right',
                            labels: { color: '#94a3b8', boxWidth: 12 },
                        },
                    },
                },
            }
        );

        charts.animalChart = new Chart(
            document.getElementById('animalChart').getContext('2d'),
            {
                type: 'doughnut',
                data: {
                    labels: [],
                    datasets: [
                        {
                            data: [],
                            backgroundColor: [
                                'rgba(129,140,248,0.75)',
                                'rgba(52,211,153,0.75)',
                                'rgba(251,191,36,0.75)',
                                'rgba(244,114,182,0.75)',
                            ],
                            borderWidth: 0,
                        },
                    ],
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    animation: CHART_ANIM,
                    cutout: '55%',
                    plugins: {
                        legend: {
                            position: 'bottom',
                            labels: { color: '#94a3b8', boxWidth: 12 },
                        },
                    },
                },
            }
        );

        chartsReady = true;
        updateTimeline(currentDays);
        initAnimalChartFromDom();
        loadInventoryOnce();
    }

    function loadInventoryOnce() {
        fetch('/api/analytics/inventory')
            .then((r) => r.json())
            .then((data) => {
                const cat = {
                    food: 'Корм',
                    medicine: 'Лекарства',
                    supplies: 'Принадлежности',
                    other: 'Прочее',
                };
                if (!charts.inventoryChart) return;
                charts.inventoryChart.data.labels = (data || []).map(
                    (d) => cat[d.category] || d.category
                );
                charts.inventoryChart.data.datasets[0].data = (data || []).map(
                    (d) => d.total_value || 0
                );
                chartUpdate('inventoryChart');
            });
    }

    function updateTimeline(days) {
        if (!chartsReady) return;
        currentDays = days;
        document.querySelectorAll('[data-days]').forEach((btn) => {
            btn.classList.toggle(
                'active',
                parseInt(btn.dataset.days, 10) === days
            );
        });

        fetch(`/api/analytics/donations-timeline?days=${days}`)
            .then((r) => r.json())
            .then((data) => {
                if (!charts.donationsChart) return;
                charts.donationsChart.data.labels = (data || []).map(
                    (d) => d.date
                );
                charts.donationsChart.data.datasets[0].data = (data || []).map(
                    (d) => d.total || 0
                );
                chartUpdate('donationsChart');
            });

        fetch(`/api/analytics/adoption-trends?days=${days}`)
            .then((r) => r.json())
            .then((data) => {
                if (!charts.adoptionsChart) return;
                charts.adoptionsChart.data.labels = (data || []).map(
                    (d) => d.date
                );
                charts.adoptionsChart.data.datasets[0].data = (data || []).map(
                    (d) => d.approved || 0
                );
                charts.adoptionsChart.data.datasets[1].data = (data || []).map(
                    (d) => d.pending || 0
                );
                charts.adoptionsChart.data.datasets[2].data = (data || []).map(
                    (d) => d.rejected || 0
                );
                chartUpdate('adoptionsChart');
            });
    }

    function initAnimalChartFromDom() {
        const el = document.getElementById('animal-stats-data');
        if (!el || !charts.animalChart) return;
        try {
            const stats = JSON.parse(el.textContent);
            charts.animalChart.data.labels = stats.map((s) => s.status);
            charts.animalChart.data.datasets[0].data = stats.map(
                (s) => s.count
            );
            chartUpdate('animalChart');
        } catch (_) {}
    }

    window.setForecastHorizon = function (h) {
        forecastHorizon = h;
        document.querySelectorAll('[data-horizon]').forEach((btn) => {
            btn.classList.toggle(
                'active',
                parseInt(btn.dataset.horizon, 10) === h
            );
        });
        loadForecasts();
    };

    document.addEventListener('DOMContentLoaded', () => {
        initTimelineCharts();
        loadForecasts();

        document.querySelectorAll('[data-days]').forEach((btn) => {
            btn.addEventListener('click', () =>
                updateTimeline(parseInt(btn.dataset.days, 10))
            );
        });
        document.querySelectorAll('[data-horizon]').forEach((btn) => {
            btn.addEventListener('click', () =>
                window.setForecastHorizon(parseInt(btn.dataset.horizon, 10))
            );
        });
    });
})();
