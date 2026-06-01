"""Миграции схемы БД для экономического модуля."""

import sqlite3

DATABASE = 'shelter.db'

ECONOMIC_TABLES = '''
CREATE TABLE IF NOT EXISTS budget_plans (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    year_month TEXT NOT NULL,
    category TEXT NOT NULL,
    planned_amount REAL NOT NULL DEFAULT 0,
    UNIQUE(year_month, category)
);

CREATE TABLE IF NOT EXISTS fundraising_campaigns (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    description TEXT,
    target_amount REAL NOT NULL,
    animal_id INTEGER,
    start_date TEXT NOT NULL,
    end_date TEXT,
    status TEXT NOT NULL DEFAULT 'active',
    FOREIGN KEY (animal_id) REFERENCES animals(id)
);

CREATE TABLE IF NOT EXISTS recurring_donations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_name TEXT NOT NULL,
    email TEXT,
    amount REAL NOT NULL,
    frequency TEXT NOT NULL DEFAULT 'monthly',
    next_date TEXT NOT NULL,
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS partners (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    contact TEXT,
    amount REAL NOT NULL DEFAULT 0,
    partner_type TEXT NOT NULL DEFAULT 'sponsor',
    start_date TEXT NOT NULL,
    end_date TEXT,
    notes TEXT
);

CREATE TABLE IF NOT EXISTS paid_services (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    description TEXT,
    price REAL NOT NULL,
    active INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS service_orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    service_id INTEGER NOT NULL,
    client_name TEXT NOT NULL,
    phone TEXT,
    amount REAL NOT NULL,
    ordered_at TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'completed',
    FOREIGN KEY (service_id) REFERENCES paid_services(id)
);

CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    event_date TEXT NOT NULL,
    cost REAL NOT NULL DEFAULT 0,
    revenue REAL NOT NULL DEFAULT 0,
    notes TEXT
);

CREATE TABLE IF NOT EXISTS suppliers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    contact TEXT
);

CREATE TABLE IF NOT EXISTS stock_norms (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    category TEXT NOT NULL UNIQUE,
    daily_consumption REAL NOT NULL,
    unit TEXT NOT NULL,
    min_days_stock INTEGER NOT NULL DEFAULT 7
);

CREATE TABLE IF NOT EXISTS shelter_settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS vet_appointments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    animal_id INTEGER NOT NULL,
    scheduled_at TEXT NOT NULL,
    service_type TEXT NOT NULL,
    estimated_cost REAL NOT NULL DEFAULT 0,
    actual_cost REAL,
    status TEXT NOT NULL DEFAULT 'planned',
    FOREIGN KEY (animal_id) REFERENCES animals(id)
);
'''

DEFAULT_SETTINGS = {
    'kennel_capacity': '25',
    'daily_cost_per_animal': '150',
    'monthly_fixed_costs': '45000',
}


def _column_exists(cursor, table, column):
    cursor.execute(f'PRAGMA table_info({table})')
    return any(row[1] == column for row in cursor.fetchall())


def migrate_database(db_path=DATABASE):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.executescript(ECONOMIC_TABLES)

    alters = [
        ('donations', 'campaign_id', 'INTEGER'),
        ('donations', 'is_recurring', 'INTEGER DEFAULT 0'),
        ('inventory', 'supplier_id', 'INTEGER'),
        ('adoption_requests', 'processed_at', 'TEXT'),
    ]
    for table, col, col_type in alters:
        if not _column_exists(cursor, table, col):
            try:
                cursor.execute(f'ALTER TABLE {table} ADD COLUMN {col} {col_type}')
            except sqlite3.OperationalError:
                pass

    for key, value in DEFAULT_SETTINGS.items():
        cursor.execute(
            'INSERT OR IGNORE INTO shelter_settings (key, value) VALUES (?, ?)',
            (key, value),
        )

    cursor.execute('SELECT COUNT(*) FROM stock_norms')
    if cursor.fetchone()[0] == 0:
        norms = [
            ('food', 12.0, 'kg', 7),
            ('medicine', 2.0, 'доз', 14),
            ('supplies', 5.0, 'шт', 10),
            ('other', 1.0, 'шт', 30),
        ]
        for cat, daily, unit, days in norms:
            cursor.execute(
                'INSERT INTO stock_norms (category, daily_consumption, unit, min_days_stock) VALUES (?, ?, ?, ?)',
                (cat, daily, unit, days),
            )

    cursor.execute('SELECT COUNT(*) FROM suppliers')
    if cursor.fetchone()[0] == 0:
        for name in ['ЗооОпт', 'ВетФарм', 'Питомец+']:
            cursor.execute('INSERT INTO suppliers (name) VALUES (?)', (name,))

    cursor.execute('SELECT COUNT(*) FROM paid_services')
    if cursor.fetchone()[0] == 0:
        services = [
            ('Передержка', 'Временное содержание животного', 500),
            ('Гостиница для животных', 'Сутки в комфортных условиях', 800),
            ('Платная стерилизация', 'Стерилизация по записи', 3500),
            ('Груминг', 'Уход за шерстью', 1200),
        ]
        for n, d, p in services:
            cursor.execute(
                'INSERT INTO paid_services (name, description, price, active) VALUES (?, ?, ?, 1)',
                (n, d, p),
            )

    conn.commit()
    conn.close()
