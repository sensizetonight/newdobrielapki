# create_db.py
import sqlite3
import os
from werkzeug.security import generate_password_hash
from datetime import datetime, timedelta
import random

DATABASE = 'shelter.db'

def create_db():
    if os.path.exists(DATABASE):
        os.remove(DATABASE)

    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS news (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            content TEXT NOT NULL,
            date TEXT NOT NULL
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS animals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            description TEXT,
            status TEXT,
            photo_url TEXT,
            age TEXT,
            gender TEXT,
            vaccinated TEXT,
            sterilized TEXT
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS stray_animals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            description TEXT NOT NULL,
            lat REAL NOT NULL,
            lon REAL NOT NULL,
            photo_url TEXT
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL CHECK(role IN ('admin', 'volunteer', 'guest')) DEFAULT 'guest'
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS adoption_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            animal_id INTEGER NOT NULL,
            user_name TEXT NOT NULL,
            phone TEXT NOT NULL,
            email TEXT NOT NULL,
            submitted_at TEXT NOT NULL,
            processed_at TEXT,
            status TEXT NOT NULL DEFAULT 'pending',
            FOREIGN KEY (animal_id) REFERENCES animals(id)
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS donations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_name TEXT NOT NULL,
            amount REAL NOT NULL,
            donation_type TEXT NOT NULL CHECK(donation_type IN ('shelter', 'animal')),
            animal_id INTEGER,
            campaign_id INTEGER,
            is_recurring INTEGER DEFAULT 0,
            donated_at TEXT NOT NULL,
            FOREIGN KEY (animal_id) REFERENCES animals(id)
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS inventory (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            item_name TEXT NOT NULL,
            category TEXT NOT NULL CHECK(category IN ('food', 'medicine', 'supplies', 'other')),
            quantity REAL NOT NULL,
            unit TEXT NOT NULL,
            unit_price REAL NOT NULL DEFAULT 0,
            supplier_id INTEGER,
            added_at TEXT NOT NULL
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            action TEXT NOT NULL,
            description TEXT NOT NULL,
            user_id INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    ''')

    cursor.execute('INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)',
                   ('admin', generate_password_hash('admin123'), 'admin'))
    cursor.execute('INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)',
                   ('volunteer1', generate_password_hash('volunteer123'), 'volunteer'))
    cursor.execute('INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)',
                   ('guest1', generate_password_hash('guest123'), 'guest'))

    # Добавляем новости
    news_data = [
        ('Открытие приюта', 'Мы открыли новый приют для животных!', '2025-01-15'),
        ('День открытых дверей', 'Присоединяйтесь к нам на день открытых дверей 25 марта!', '2025-01-20'),
        ('Новые питомцы', 'К нам поступили новые животные, ищущие дом', '2025-02-01'),
        ('Акция по стерилизации', 'Проводим бесплатную стерилизацию бездомных животных', '2025-02-15'),
        ('Благотворительный концерт', 'Организуем концерт в поддержку приюта', '2025-03-01'),
        ('Успешные усыновления', 'За этот месяц нашли дом для 15 животных!', '2025-03-10'),
    ]
    
    for news in news_data:
        cursor.execute('INSERT INTO news (title, content, date) VALUES (?, ?, ?)', news)

    # Добавляем больше животных с разными статусами
    animals_data = [
        ('Murzik', 'Friendly cat looking for a home', 'Looking for a home', '2 years', 'Male', 'Yes', 'Yes', 'images/murzik.jpg'),
        ('Barsik', 'Playful kitten', 'Looking for a home', '6 months', 'Male', 'No', 'No', 'images/barsik.jpg'),
        ('Sharik', 'Cheerful dog', 'Looking for a home', '3 years', 'Male', 'Yes', 'No', 'images/sharik.jpg'),
        ('Мурка', 'Ласковая кошка', 'Looking for a home', '1 year', 'Female', 'Yes', 'Yes', None),
        ('Рекс', 'Верный друг', 'Adopted', '4 years', 'Male', 'Yes', 'Yes', None),
        ('Белка', 'Активная собака', 'Looking for a home', '2 years', 'Female', 'Yes', 'No', None),
        ('Васька', 'Спокойный кот', 'In treatment', '5 years', 'Male', 'Yes', 'Yes', None),
        ('Джесси', 'Игривая собака', 'Looking for a home', '1 year', 'Female', 'Yes', 'Yes', None),
        ('Том', 'Дружелюбный кот', 'Adopted', '3 years', 'Male', 'Yes', 'Yes', None),
        ('Луна', 'Нежная кошка', 'Looking for a home', '2 years', 'Female', 'Yes', 'Yes', None),
        ('Макс', 'Энергичный пес', 'Looking for a home', '1 year', 'Male', 'No', 'No', None),
        ('Снежка', 'Белая кошка', 'In treatment', '4 years', 'Female', 'Yes', 'Yes', None),
        ('Барон', 'Большой друг', 'Adopted', '5 years', 'Male', 'Yes', 'Yes', None),
        ('Зефир', 'Мягкий котенок', 'Looking for a home', '3 months', 'Male', 'No', 'No', None),
        ('Лаки', 'Счастливая собака', 'Looking for a home', '2 years', 'Female', 'Yes', 'No', None),
    ]
    
    for animal in animals_data:
        cursor.execute('INSERT INTO animals (name, description, status, age, gender, vaccinated, sterilized, photo_url) VALUES (?, ?, ?, ?, ?, ?, ?, ?)', animal)
    
    # Получаем ID животных для связей
    cursor.execute('SELECT id FROM animals')
    animal_ids = [row[0] for row in cursor.fetchall()]

    cursor.execute('INSERT INTO stray_animals (description, lat, lon, photo_url) VALUES (?, ?, ?, ?)',
                   ('Stray dog near the park', 55.7558, 37.6173, 'uploads/stray_dog.jpg'))
    cursor.execute('INSERT INTO stray_animals (description, lat, lon, photo_url) VALUES (?, ?, ?, ?)',
                   ('Kitten near the shop', 55.7512, 37.6231, 'uploads/stray_kitten.jpg'))
    
    # Генерируем пожертвования за последние 90 дней
    donor_names = ['Иван Петров', 'Мария Сидорова', 'Алексей Иванов', 'Елена Козлова', 
                   'Дмитрий Смирнов', 'Анна Волкова', 'Сергей Лебедев', 'Ольга Новикова',
                   'Павел Морозов', 'Татьяна Федорова', 'Андрей Соколов', 'Наталья Орлова']
    
    base_date = datetime.now() - timedelta(days=365)
    donation_amounts = [500, 1000, 1500, 2000, 2500, 3000, 5000, 10000]
    
    for i in range(180):  # пожертвования за год (для помесячной аналитики)
        date = base_date + timedelta(days=random.randint(0, 365), hours=random.randint(8, 20))
        donor = random.choice(donor_names)
        amount = random.choice(donation_amounts)
        donation_type = random.choice(['shelter', 'animal'])
        animal_id = random.choice(animal_ids) if donation_type == 'animal' else None
        
        cursor.execute('INSERT INTO donations (user_name, amount, donation_type, animal_id, donated_at) VALUES (?, ?, ?, ?, ?)',
                       (donor, amount, donation_type, animal_id, date.isoformat()))
    
    # Генерируем заявки на усыновление за последние 90 дней
    applicant_names = ['Петр Иванов', 'Светлана Петрова', 'Михаил Сидоров', 'Екатерина Козлова',
                      'Александр Смирнов', 'Юлия Волкова', 'Игорь Лебедев', 'Марина Новикова',
                      'Владимир Морозов', 'Людмила Федорова', 'Николай Соколов', 'Елена Орлова']
    
    statuses = ['pending', 'approved', 'rejected']
    status_weights = [0.3, 0.5, 0.2]  # 30% pending, 50% approved, 20% rejected
    
    for i in range(80):  # заявки за год
        date = base_date + timedelta(days=random.randint(0, 365), hours=random.randint(9, 18))
        applicant = random.choice(applicant_names)
        animal_id = random.choice(animal_ids)
        status = random.choices(statuses, weights=status_weights)[0]
        phone = f'+7{random.randint(900, 999)}{random.randint(1000000, 9999999)}'
        email = f'{applicant.lower().replace(" ", ".")}@example.com'
        
        processed = (date + timedelta(days=random.randint(2, 14))).isoformat() if status != 'pending' else None
        cursor.execute(
            'INSERT INTO adoption_requests (animal_id, user_name, phone, email, submitted_at, processed_at, status) VALUES (?, ?, ?, ?, ?, ?, ?)',
            (animal_id, applicant, phone, email, date.isoformat(), processed, status),
        )

    # Добавляем много записей инвентаря за последние 90 дней для прогноза
    inventory_items = [
        ('Сухой корм для собак', 'food', 50, 'kg', 200),
        ('Сухой корм для кошек', 'food', 40, 'kg', 180),
        ('Влажный корм', 'food', 100, 'банок', 50),
        ('Ошейник от блох', 'medicine', 20, 'шт', 500),
        ('Вакцина', 'medicine', 30, 'доз', 800),
        ('Антибиотики', 'medicine', 15, 'упак', 1200),
        ('Одеяла', 'supplies', 15, 'шт', 300),
        ('Миски', 'supplies', 25, 'шт', 150),
        ('Игрушки', 'supplies', 50, 'шт', 100),
        ('Поводки', 'supplies', 20, 'шт', 200),
        ('Наполнитель для кошачьего туалета', 'supplies', 30, 'кг', 250),
        ('Шампунь для животных', 'supplies', 10, 'шт', 350),
    ]
    
    # Генерируем записи инвентаря за последний год
    inv_base = datetime.now() - timedelta(days=365)
    for i in range(120):
        date = inv_base + timedelta(days=random.randint(0, 365))
        item = random.choice(inventory_items)
        quantity = random.uniform(10, 100) if item[2] > 20 else random.uniform(5, 30)
        cursor.execute('INSERT INTO inventory (item_name, category, quantity, unit, unit_price, added_at) VALUES (?, ?, ?, ?, ?, ?)',
                       (item[0], item[1], round(quantity, 2), item[3], item[4], date.isoformat()))

    from db_migrate import migrate_database
    migrate_database(DATABASE)

    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    ym = datetime.now().strftime('%Y-%m')

    budget_seed = [
        ('food', 85000), ('medicine', 45000), ('supplies', 35000),
        ('rent', 60000), ('salaries', 120000), ('marketing', 15000), ('other', 10000),
    ]
    for cat, amt in budget_seed:
        cursor.execute(
            'INSERT OR IGNORE INTO budget_plans (year_month, category, planned_amount) VALUES (?, ?, ?)',
            (ym, cat, amt),
        )

    cursor.execute(
        '''INSERT INTO fundraising_campaigns (title, description, target_amount, animal_id, start_date, end_date, status)
           VALUES (?, ?, ?, ?, ?, ?, 'active')''',
        ('Корм на зиму', 'Закупка корма для всех питомцев', 150000, animal_ids[0],
         (datetime.now() - timedelta(days=30)).isoformat(), (datetime.now() + timedelta(days=60)).isoformat()),
    )
    cursor.execute(
        '''INSERT INTO fundraising_campaigns (title, description, target_amount, animal_id, start_date, status)
           VALUES (?, ?, ?, ?, ?, 'active')''',
        ('Операция для Васьки', 'Срочная ветеринарная помощь', 35000, animal_ids[6],
         datetime.now().isoformat()),
    )

    for name, amt in [('Зоомагазин «Лапки»', 50000), ('Ветклиника Партнёр', 30000)]:
        cursor.execute(
            'INSERT INTO partners (name, amount, partner_type, start_date) VALUES (?, ?, ?, ?)',
            (name, amt, 'sponsor', datetime.now().isoformat()),
        )

    cursor.execute(
        'INSERT INTO events (name, event_date, cost, revenue, notes) VALUES (?, ?, ?, ?, ?)',
        ('День открытых дверей', (datetime.now() - timedelta(days=45)).isoformat(), 12000, 45000, 'Успешная акция'),
    )
    cursor.execute(
        'INSERT INTO events (name, event_date, cost, revenue, notes) VALUES (?, ?, ?, ?, ?)',
        ('Благотворительный концерт', (datetime.now() - timedelta(days=90)).isoformat(), 35000, 82000, 'Высокий ROI'),
    )

    for donor, amt in [('Мария С.', 1000), ('Алексей И.', 1500)]:
        cursor.execute(
            '''INSERT INTO recurring_donations (user_name, amount, frequency, next_date, active, created_at)
               VALUES (?, ?, 'monthly', ?, 1, ?)''',
            (donor, amt, (datetime.now() + timedelta(days=30)).isoformat(), datetime.now().isoformat()),
        )

    cursor.execute(
        '''INSERT INTO service_orders (service_id, client_name, amount, ordered_at, status)
           VALUES (1, ?, ?, ?, 'completed')''',
        ('Ирина К.', 5000, (datetime.now() - timedelta(days=10)).isoformat()),
    )

    for aid in animal_ids[:3]:
        cursor.execute(
            '''INSERT INTO vet_appointments (animal_id, scheduled_at, service_type, estimated_cost, status)
               VALUES (?, ?, ?, ?, 'planned')''',
            (aid, (datetime.now() + timedelta(days=7 + aid)).isoformat(), 'Осмотр / вакцинация', 2500 + aid * 500),
        )

    conn.commit()
    conn.close()
    print(f"Database '{DATABASE}' successfully created.")
    
if __name__ == '__main__':
    create_db()