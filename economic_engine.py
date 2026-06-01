"""
Экономический модуль приюта «Добрые Лапки».
Расчёты: бюджет, устойчивость, кассовый разрыв, ABC, воронка доноров и др.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from statistics import mean

from analytics_engine import forecast_ensemble

DATABASE = 'shelter.db'

BUDGET_CATEGORIES = {
    'food': 'Корм',
    'medicine': 'Лекарства',
    'supplies': 'Принадлежности',
    'rent': 'Аренда',
    'salaries': 'ФОТ',
    'marketing': 'Маркетинг',
    'other': 'Прочее',
}

INV_TO_BUDGET = {
    'food': 'food',
    'medicine': 'medicine',
    'supplies': 'supplies',
    'other': 'other',
}


def _conn():
    import sqlite3
    c = sqlite3.connect(DATABASE)
    c.row_factory = sqlite3.Row
    return c


def get_setting(key: str, default: str = '0') -> str:
    with _conn() as conn:
        row = conn.execute(
            'SELECT value FROM shelter_settings WHERE key = ?', (key,)
        ).fetchone()
        return row['value'] if row else default


def set_setting(key: str, value: str):
    with _conn() as conn:
        conn.execute(
            'INSERT OR REPLACE INTO shelter_settings (key, value) VALUES (?, ?)',
            (key, value),
        )
        conn.commit()


def current_year_month() -> str:
    return datetime.now().strftime('%Y-%m')


def get_financial_totals():
    with _conn() as conn:
        don = conn.execute('SELECT COALESCE(SUM(amount), 0) AS t FROM donations').fetchone()['t']
        exp = conn.execute(
            'SELECT COALESCE(SUM(quantity * unit_price), 0) AS t FROM inventory'
        ).fetchone()['t']
        svc = conn.execute(
            "SELECT COALESCE(SUM(amount), 0) AS t FROM service_orders WHERE status = 'completed'"
        ).fetchone()['t']
        partners = conn.execute(
            'SELECT COALESCE(SUM(amount), 0) AS t FROM partners'
        ).fetchone()['t']
        monthly_don = conn.execute(
            '''SELECT COALESCE(SUM(amount), 0) AS t FROM donations
               WHERE datetime(donated_at) >= datetime('now', '-30 days')'''
        ).fetchone()['t']
        monthly_exp = conn.execute(
            '''SELECT COALESCE(SUM(quantity * unit_price), 0) AS t FROM inventory
               WHERE datetime(added_at) >= datetime('now', '-30 days')'''
        ).fetchone()['t']
    balance = don + svc + partners - exp
    monthly_balance = monthly_don - monthly_exp
    return {
        'total_income': round(don + svc + partners, 2),
        'total_donations': round(don, 2),
        'total_services': round(svc, 2),
        'total_partners': round(partners, 2),
        'total_expenses': round(exp, 2),
        'balance': round(balance, 2),
        'monthly_donations': round(monthly_don, 2),
        'monthly_expenses': round(monthly_exp, 2),
        'monthly_balance': round(monthly_balance, 2),
    }


def get_budget_plan_vs_fact(year_month: str | None = None):
    ym = year_month or current_year_month()
    with _conn() as conn:
        plans = {
            r['category']: r['planned_amount']
            for r in conn.execute(
                'SELECT category, planned_amount FROM budget_plans WHERE year_month = ?',
                (ym,),
            ).fetchall()
        }
        fact_rows = conn.execute(
            '''SELECT category, SUM(quantity * unit_price) AS fact
               FROM inventory
               WHERE strftime('%Y-%m', added_at) = ?
               GROUP BY category''',
            (ym,),
        ).fetchall()
        fixed = float(get_setting('monthly_fixed_costs', '45000'))
    fact_by_budget = {cat: 0.0 for cat in BUDGET_CATEGORIES}
    for row in fact_rows:
        bc = INV_TO_BUDGET.get(row['category'], 'other')
        fact_by_budget[bc] += float(row['fact'] or 0)
    fact_by_budget['rent'] = fixed * 0.4
    fact_by_budget['salaries'] = fixed * 0.5
    fact_by_budget['marketing'] = fixed * 0.1

    items = []
    for cat, label in BUDGET_CATEGORIES.items():
        plan = float(plans.get(cat, 0))
        fact = round(fact_by_budget.get(cat, 0), 2)
        if plan == 0 and cat in ('rent', 'salaries', 'marketing') and fixed > 0:
            plan = round(fact_by_budget[cat], 2)
        variance = round(fact - plan, 2)
        items.append({
            'category': cat,
            'label': label,
            'planned': round(plan, 2),
            'actual': fact,
            'variance': variance,
            'pct': round((fact / plan * 100) if plan else 0, 1),
        })
    return {'year_month': ym, 'items': items, 'total_planned': sum(i['planned'] for i in items),
            'total_actual': sum(i['actual'] for i in items)}


def get_cost_per_animal():
    daily = float(get_setting('daily_cost_per_animal', '150'))
    monthly = round(daily * 30, 2)
    with _conn() as conn:
        active = conn.execute(
            '''SELECT COUNT(*) AS c FROM animals
               WHERE status NOT IN ('Adopted')'''
        ).fetchone()['c']
        total_monthly = round(monthly * active, 2) if active else 0
    return {
        'daily_cost': daily,
        'monthly_per_animal': monthly,
        'active_animals': active,
        'total_monthly_herd_cost': total_monthly,
    }


def get_cash_runway():
    fin = get_financial_totals()
    balance = fin['balance']
    monthly_exp = fin['monthly_expenses'] or 1
    monthly_inc = fin['monthly_donations']
    net_burn = monthly_exp - monthly_inc
    if net_burn <= 0:
        days = 999
        gap_date = None
    else:
        days = int(max(0, balance / (net_burn / 30)))
        gap_date = (datetime.now() + timedelta(days=days)).strftime('%Y-%m-%d')
    return {
        'current_balance': balance,
        'monthly_net': round(monthly_inc - monthly_exp, 2),
        'days_until_gap': days if days < 999 else None,
        'gap_date': gap_date,
        'alert': days < 60 and net_burn > 0,
    }


def get_campaigns_with_progress():
    with _conn() as conn:
        campaigns = [dict(r) for r in conn.execute(
            '''SELECT c.*, a.name AS animal_name,
                      COALESCE((SELECT SUM(d.amount) FROM donations d WHERE d.campaign_id = c.id), 0) AS raised
               FROM fundraising_campaigns c
               LEFT JOIN animals a ON c.animal_id = a.id
               ORDER BY c.start_date DESC'''
        ).fetchall()]
    for c in campaigns:
        target = float(c['target_amount'] or 1)
        raised = float(c['raised'] or 0)
        c['raised'] = round(raised, 2)
        c['progress_pct'] = round(min(100, raised / target * 100), 1)
    return campaigns


def get_abc_inventory():
    with _conn() as conn:
        rows = conn.execute(
            '''SELECT item_name, category, SUM(quantity * unit_price) AS value
               FROM inventory GROUP BY item_name, category ORDER BY value DESC'''
        ).fetchall()
    items = [{'name': r['item_name'], 'category': r['category'], 'value': round(r['value'], 2)}
             for r in rows]
    total = sum(i['value'] for i in items) or 1
    cum = 0
    for i in items:
        cum += i['value']
        pct = cum / total * 100
        i['share_pct'] = round(i['value'] / total * 100, 1)
        i['class'] = 'A' if pct <= 80 else ('B' if pct <= 95 else 'C')
    return items


def get_stock_alerts():
    alerts = []
    with _conn() as conn:
        norms = {r['category']: dict(r) for r in conn.execute('SELECT * FROM stock_norms').fetchall()}
        stock = conn.execute(
            '''SELECT category, SUM(quantity) AS qty FROM inventory GROUP BY category'''
        ).fetchall()
        prices = conn.execute(
            '''SELECT category, AVG(unit_price) AS avg_p FROM inventory GROUP BY category'''
        ).fetchall()
    price_map = {r['category']: r['avg_p'] for r in prices}
    for row in stock:
        cat = row['category']
        norm = norms.get(cat)
        if not norm:
            continue
        daily = float(norm['daily_consumption'])
        min_days = int(norm['min_days_stock'])
        days_left = float(row['qty']) / daily if daily > 0 else 999
        if days_left < min_days:
            alerts.append({
                'category': cat,
                'label': BUDGET_CATEGORIES.get(INV_TO_BUDGET.get(cat, cat), cat),
                'quantity': round(row['qty'], 1),
                'unit': norm['unit'],
                'days_left': round(days_left, 1),
                'min_days': min_days,
                'reorder_estimate': round(daily * min_days * float(price_map.get(cat, 0)), 2),
            })
    return alerts


def get_supplier_comparison():
    with _conn() as conn:
        rows = conn.execute(
            '''SELECT i.item_name, s.name AS supplier, i.unit_price, i.added_at
               FROM inventory i
               LEFT JOIN suppliers s ON i.supplier_id = s.id
               ORDER BY i.item_name, i.added_at DESC'''
        ).fetchall()
    by_item = {}
    for r in rows:
        name = r['item_name']
        if name not in by_item:
            by_item[name] = []
        by_item[name].append({
            'supplier': r['supplier'] or 'Не указан',
            'price': round(r['unit_price'], 2),
            'date': r['added_at'][:10],
        })
    result = []
    for name, history in by_item.items():
        prices = [h['price'] for h in history]
        result.append({
            'item_name': name,
            'min_price': min(prices),
            'max_price': max(prices),
            'avg_price': round(mean(prices), 2),
            'history': history[:5],
        })
    return sorted(result, key=lambda x: x['max_price'] - x['min_price'], reverse=True)[:15]


def get_events_roi():
    with _conn() as conn:
        events = [dict(r) for r in conn.execute(
            'SELECT * FROM events ORDER BY event_date DESC'
        ).fetchall()]
    for e in events:
        cost = float(e['cost'] or 0)
        rev = float(e['revenue'] or 0)
        e['roi_pct'] = round(((rev - cost) / cost * 100) if cost else 0, 1)
        e['profit'] = round(rev - cost, 2)
    return events


def get_recurring_stats():
    with _conn() as conn:
        active = conn.execute(
            'SELECT COUNT(*) AS c, COALESCE(SUM(amount), 0) AS s FROM recurring_donations WHERE active = 1'
        ).fetchone()
    return {
        'active_count': active['c'],
        'monthly_recurring_total': round(active['s'], 2),
        'annual_forecast': round(active['s'] * 12, 2),
    }


def get_partners_summary():
    with _conn() as conn:
        rows = [dict(r) for r in conn.execute(
            'SELECT * FROM partners ORDER BY start_date DESC'
        ).fetchall()]
    return {
        'partners': rows,
        'total_amount': round(sum(float(p['amount']) for p in rows), 2),
        'active_count': sum(1 for p in rows if not p.get('end_date')),
    }


def get_services_summary():
    with _conn() as conn:
        services = [dict(r) for r in conn.execute(
            'SELECT * FROM paid_services WHERE active = 1'
        ).fetchall()]
        revenue = conn.execute(
            '''SELECT service_id, SUM(amount) AS total, COUNT(*) AS orders
               FROM service_orders WHERE status = 'completed' GROUP BY service_id'''
        ).fetchall()
    rev_map = {r['service_id']: dict(r) for r in revenue}
    for s in services:
        r = rev_map.get(s['id'], {})
        s['revenue'] = round(float(r.get('total') or 0), 2)
        s['orders'] = r.get('orders') or 0
    total_rev = sum(s['revenue'] for s in services)
    return {'services': services, 'total_revenue': round(total_rev, 2)}


def get_donor_funnel():
    with _conn() as conn:
        total_donors = conn.execute(
            'SELECT COUNT(DISTINCT user_name) AS c FROM donations'
        ).fetchone()['c']
        repeat = conn.execute(
            '''SELECT COUNT(*) AS c FROM (
                 SELECT user_name FROM donations GROUP BY user_name HAVING COUNT(*) > 1
               )'''
        ).fetchone()['c']
        recurring = conn.execute(
            'SELECT COUNT(*) AS c FROM recurring_donations WHERE active = 1'
        ).fetchone()['c']
        animal_specific = conn.execute(
            "SELECT COUNT(*) AS c FROM donations WHERE donation_type = 'animal'"
        ).fetchone()['c']
        total_d = conn.execute('SELECT COUNT(*) AS c FROM donations').fetchone()['c']
        avg_d = conn.execute('SELECT AVG(amount) AS a FROM donations').fetchone()['a']
    return {
        'unique_donors': total_donors,
        'repeat_donors': repeat,
        'repeat_rate_pct': round(repeat / total_donors * 100, 1) if total_donors else 0,
        'recurring_donors': recurring,
        'animal_targeted_donations': animal_specific,
        'animal_targeted_pct': round(animal_specific / total_d * 100, 1) if total_d else 0,
        'avg_donation': round(avg_d or 0, 2) if total_d else 0,
    }


def get_adoption_efficiency():
    with _conn() as conn:
        rows = conn.execute(
            '''SELECT submitted_at, processed_at, status FROM adoption_requests
               WHERE status = 'approved' AND processed_at IS NOT NULL'''
        ).fetchall()
        pending = conn.execute(
            "SELECT COUNT(*) AS c FROM adoption_requests WHERE status = 'pending'"
        ).fetchone()['c']
    days_list = []
    for r in rows:
        try:
            s = datetime.fromisoformat(r['submitted_at'][:19])
            p = datetime.fromisoformat(r['processed_at'][:19])
            days_list.append((p - s).days)
        except (ValueError, TypeError):
            pass
    daily_cost = float(get_setting('daily_cost_per_animal', '150'))
    avg_days = round(mean(days_list), 1) if days_list else 0
    return {
        'avg_processing_days': avg_days,
        'pending_queue': pending,
        'cost_per_pending_day': round(pending * daily_cost, 2),
        'processed_count': len(days_list),
    }


def get_kennel_occupancy():
    capacity = int(get_setting('kennel_capacity', '25'))
    with _conn() as conn:
        occupied = conn.execute(
            '''SELECT COUNT(*) AS c FROM animals WHERE status NOT IN ('Adopted')'''
        ).fetchone()['c']
    pct = round(occupied / capacity * 100, 1) if capacity else 0
    return {
        'capacity': capacity,
        'occupied': occupied,
        'free_slots': max(0, capacity - occupied),
        'occupancy_pct': pct,
        'can_accept': occupied < capacity,
    }


def get_vet_calendar(limit=10):
    with _conn() as conn:
        rows = [dict(r) for r in conn.execute(
            '''SELECT v.*, a.name AS animal_name FROM vet_appointments v
               JOIN animals a ON v.animal_id = a.id
               ORDER BY v.scheduled_at ASC LIMIT ?''',
            (limit,),
        ).fetchall()]
    total_planned = sum(float(r['estimated_cost'] or 0) for r in rows if r['status'] == 'planned')
    return {'appointments': rows, 'planned_cost_total': round(total_planned, 2)}


def get_break_even():
    fixed = float(get_setting('monthly_fixed_costs', '45000'))
    fin = get_financial_totals()
    variable_monthly = fin['monthly_expenses']
    monthly_income = fin['monthly_donations'] + get_recurring_stats()['monthly_recurring_total']
    total_cost = fixed + variable_monthly
    surplus = monthly_income - total_cost
    be_donations = max(0, total_cost - get_services_summary()['total_revenue'] - get_partners_summary()['total_amount'] / 12)
    return {
        'monthly_fixed': fixed,
        'monthly_variable': round(variable_monthly, 2),
        'monthly_total_cost': round(total_cost, 2),
        'monthly_income': round(monthly_income, 2),
        'surplus': round(surplus, 2),
        'break_even_donations_needed': round(be_donations, 2),
        'is_profitable': surplus >= 0,
    }


def get_scenario_analysis():
    fin = get_financial_totals()
    base_inc = fin['monthly_donations']
    base_exp = fin['monthly_expenses'] + float(get_setting('monthly_fixed_costs', '45000'))
    scenarios = []
    for name, inc_pct, exp_pct in [
        ('Базовый', 0, 0),
        ('Оптимистичный', 15, -5),
        ('Пессимистичный', -20, 10),
    ]:
        inc = base_inc * (1 + inc_pct / 100)
        exp = base_exp * (1 + exp_pct / 100)
        scenarios.append({
            'name': name,
            'income': round(inc, 2),
            'expenses': round(exp, 2),
            'balance': round(inc - exp, 2),
        })
    return scenarios


def get_sustainability_index():
    fin = get_financial_totals()
    balance = fin['balance']
    monthly_cost = fin['monthly_expenses'] + float(get_setting('monthly_fixed_costs', '45000')) / 12
    monthly_cost = fin['monthly_expenses'] + float(get_setting('monthly_fixed_costs', '45000'))
    index = round(balance / monthly_cost, 2) if monthly_cost > 0 else 0
    label = 'Высокая' if index >= 3 else ('Средняя' if index >= 1 else 'Низкая')
    return {
        'index_months': index,
        'label': label,
        'balance': balance,
        'monthly_burn': round(monthly_cost - fin['monthly_donations'], 2),
    }


def get_adoption_savings():
    daily = float(get_setting('daily_cost_per_animal', '150'))
    with _conn() as conn:
        adopted = conn.execute(
            "SELECT COUNT(*) AS c FROM animals WHERE status = 'Adopted'"
        ).fetchone()['c']
        avg_days = 45
    saved = round(adopted * avg_days * daily, 2)
    return {
        'adopted_count': adopted,
        'assumed_days_in_shelter': avg_days,
        'economic_effect': saved,
        'description': 'Условная экономия затрат после усыновления',
    }


def get_monthly_income_series(months=6):
    with _conn() as conn:
        don = conn.execute(
            '''SELECT strftime('%Y-%m', donated_at) AS m, SUM(amount) AS t
               FROM donations GROUP BY m ORDER BY m DESC LIMIT ?''',
            (months,),
        ).fetchall()
    values = [float(r['t']) for r in reversed(don)]
    if len(values) < 2:
        return None
    fc = forecast_ensemble(values, 3)
    return {'historical': values, 'forecast': fc['predictions']}


def get_full_economic_dashboard():
    return {
        'financial': get_financial_totals(),
        'budget': get_budget_plan_vs_fact(),
        'cost_per_animal': get_cost_per_animal(),
        'cash_runway': get_cash_runway(),
        'campaigns': get_campaigns_with_progress(),
        'abc_inventory': get_abc_inventory()[:20],
        'stock_alerts': get_stock_alerts(),
        'supplier_comparison': get_supplier_comparison()[:10],
        'events_roi': get_events_roi(),
        'recurring': get_recurring_stats(),
        'partners': get_partners_summary(),
        'services': get_services_summary(),
        'donor_funnel': get_donor_funnel(),
        'adoption_efficiency': get_adoption_efficiency(),
        'kennel': get_kennel_occupancy(),
        'vet_calendar': get_vet_calendar(),
        'break_even': get_break_even(),
        'scenarios': get_scenario_analysis(),
        'sustainability': get_sustainability_index(),
        'adoption_savings': get_adoption_savings(),
        'settings': {
            'kennel_capacity': get_setting('kennel_capacity'),
            'daily_cost_per_animal': get_setting('daily_cost_per_animal'),
            'monthly_fixed_costs': get_setting('monthly_fixed_costs'),
        },
    }
