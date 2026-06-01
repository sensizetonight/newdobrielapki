# Технические детали проекта "Добрые Лапки"

## 1. СХЕМА БАЗЫ ДАННЫХ

### 1.1. ER-диаграмма (текстовое представление)

```
┌─────────────┐         ┌──────────────────┐
│    users    │         │     animals      │
├─────────────┤         ├──────────────────┤
│ id (PK)     │         │ id (PK)          │
│ username    │         │ name             │
│ password_   │         │ description       │
│   hash      │         │ status           │
│ role        │         │ photo_url        │
└─────────────┘         │ age, gender      │
                         │ vaccinated      │
                         │ sterilized      │
                         └────────┬────────┘
                                  │
                    ┌─────────────┼─────────────┐
                    │             │             │
         ┌──────────▼──────┐  ┌──▼──────────┐  │
         │adoption_requests│  │  donations   │  │
         ├─────────────────┤  ├──────────────┤  │
         │ id (PK)         │  │ id (PK)      │  │
         │ animal_id (FK)  │  │ user_name    │  │
         │ user_name       │  │ amount       │  │
         │ phone           │  │ donation_    │  │
         │ email           │  │   type       │  │
         │ submitted_at    │  │ animal_id    │  │
         │ status          │  │   (FK)       │  │
         └─────────────────┘  │ donated_at  │  │
                               └──────────────┘  │
                                                 │
┌─────────────┐  ┌──────────────┐  ┌───────────┐
│   news      │  │  inventory   │  │   logs    │
├─────────────┤  ├──────────────┤  ├───────────┤
│ id (PK)     │  │ id (PK)      │  │ id (PK)   │
│ title       │  │ item_name    │  │ action    │
│ content     │  │ category     │  │ descrip-  │
│ date        │  │ quantity     │  │   tion    │
└─────────────┘  │ unit         │  │ user_id   │
                 │ unit_price   │  │   (FK)    │
┌─────────────┐  │ added_at     │  │ created_  │
│stray_animals│  └──────────────┘  │   at      │
├─────────────┤                   └───────────┘
│ id (PK)     │
│ description │
│ lat, lon    │
│ photo_url   │
└─────────────┘
```

### 1.2. Описание связей

- **users → logs**: Один ко многим (один пользователь - много логов)
- **animals → adoption_requests**: Один ко многим (одно животное - много заявок)
- **animals → donations**: Один ко многим (одно животное - много пожертвований, опционально)

## 2. АРХИТЕКТУРА ПРИЛОЖЕНИЯ

### 2.1. Схема взаимодействия компонентов

```
┌─────────────┐
│   Browser   │
│  (Client)   │
└──────┬──────┘
       │ HTTP Request
       │
┌──────▼──────────────────────────────────────┐
│           Flask Application (app.py)           │
│  ┌──────────────────────────────────────────┐ │
│  │         Routing Layer                     │ │
│  │  @app.route('/...')                      │ │
│  └──────┬───────────────────────────────────┘ │
│         │                                      │
│  ┌──────▼───────────────────────────────────┐ │
│  │      Business Logic Layer                 │ │
│  │  - get_animals()                          │ │
│  │  - get_donations()                        │ │
│  │  - forecast_costs()                       │ │
│  │  - get_financial_summary()                │ │
│  └──────┬───────────────────────────────────┘ │
│         │                                      │
│  ┌──────▼───────────────────────────────────┐ │
│  │      Data Access Layer                    │ │
│  │  - get_db()                               │ │
│  │  - SQL queries                            │ │
│  └──────┬───────────────────────────────────┘ │
└─────────┼────────────────────────────────────┘
          │
          │ SQL
          │
┌─────────▼─────────┐
│   SQLite Database │
│    (shelter.db)   │
└───────────────────┘
```

### 2.2. Поток обработки запроса

```
1. HTTP Request → Flask Router
2. Проверка аутентификации (@login_required)
3. Проверка прав доступа (role check)
4. Вызов бизнес-логики
5. Запрос к БД
6. Обработка данных
7. Рендеринг шаблона (Jinja2)
8. HTTP Response → Browser
```

## 3. МАРШРУТЫ ПРИЛОЖЕНИЯ

### 3.1. Публичные маршруты

| Маршрут | Метод | Описание | Доступ |
|---------|-------|----------|--------|
| `/` | GET, POST | Главная страница, новости | Все |
| `/animals` | GET, POST | Каталог животных | Все |
| `/map` | GET, POST | Карта бездомных животных | Все |
| `/donate` | GET, POST | Пожертвования | Все |
| `/contact` | GET, POST | Контакты | Все |
| `/register` | GET, POST | Регистрация | Все |
| `/login` | GET, POST | Вход | Все |

### 3.2. Защищенные маршруты

| Маршрут | Метод | Описание | Роль |
|---------|-------|----------|------|
| `/logout` | GET | Выход | Авторизованные |
| `/delete_news/<id>` | POST | Удаление новости | admin |
| `/delete_animal/<id>` | POST | Удаление животного | admin, volunteer |
| `/delete_mark/<id>` | POST | Удаление метки на карте | admin, volunteer |
| `/admin/dashboard` | GET, POST | Админ-панель | admin |
| `/admin/analytics` | GET | Аналитический дашборд | admin |

### 3.3. API маршруты

| Маршрут | Метод | Описание | Роль |
|---------|-------|----------|------|
| `/api/analytics/donations-timeline` | GET | Данные пожертвований | admin |
| `/api/analytics/adoption-trends` | GET | Тренды усыновлений | admin |
| `/api/analytics/inventory` | GET | Анализ инвентаря | admin |

## 4. АЛГОРИТМЫ И МЕТОДЫ

### 4.1. Алгоритм прогнозирования затрат

```python
def forecast_costs(months=3):
    """
    Алгоритм:
    1. Получить исторические данные за 90 дней
    2. Вычислить среднее дневное значение расходов
    3. Рассчитать тренд методом линейной регрессии
    4. Спрогнозировать на N месяцев вперед
    """
    
    # Шаг 1: Получение данных
    historical_data = get_inventory_data(last_90_days)
    
    # Шаг 2: Расчет среднего
    avg_daily = mean(historical_costs)
    
    # Шаг 3: Линейная регрессия
    # Формула: y = ax + b
    # где a = (n*Σxy - Σx*Σy) / (n*Σx² - (Σx)²)
    trend = calculate_trend(historical_costs)
    
    # Шаг 4: Прогноз
    for month in range(1, months + 1):
        predicted = avg_daily * 30 + (trend * 30 * month)
        forecast.append(predicted)
    
    return forecast
```

**Сложность алгоритма:** O(n), где n - количество исторических записей

### 4.2. Метод расчета финансовой сводки

```python
def get_financial_summary():
    """
    Расчет финансовых показателей:
    - Доходы: сумма всех пожертвований
    - Расходы: стоимость всего инвентаря
    - Баланс: доходы - расходы
    - Месячные показатели: за последние 30 дней
    """
    
    total_donations = SUM(donations.amount)
    total_expenses = SUM(inventory.quantity * inventory.unit_price)
    balance = total_donations - total_expenses
    
    monthly_donations = SUM(donations WHERE date >= now - 30 days)
    monthly_expenses = SUM(inventory WHERE date >= now - 30 days)
    monthly_balance = monthly_donations - monthly_expenses
    
    return {
        'total_donations': total_donations,
        'total_expenses': total_expenses,
        'balance': balance,
        'monthly_donations': monthly_donations,
        'monthly_expenses': monthly_expenses,
        'monthly_balance': monthly_balance
    }
```

### 4.3. Метод фильтрации инвентаря

```python
def get_inventory(search=None, category=None):
    """
    Динамическое построение SQL-запроса с фильтрами
    """
    query = "SELECT * FROM inventory"
    conditions = []
    params = []
    
    if search:
        conditions.append("item_name LIKE ?")
        params.append(f'%{search}%')
    
    if category:
        conditions.append("category = ?")
        params.append(category)
    
    if conditions:
        query += " WHERE " + " AND ".join(conditions)
    
    query += " ORDER BY added_at DESC"
    
    return execute_query(query, params)
```

## 5. СТРУКТУРА ШАБЛОНОВ

### 5.1. Иерархия шаблонов

```
base.html (базовый шаблон)
├── header (навигация, аутентификация)
├── main (основной контент)
└── footer

Наследуемые шаблоны:
├── index.html (главная)
├── animals.html (каталог)
├── admin_dashboard.html (админ-панель)
├── analytics.html (аналитика)
├── donate.html (пожертвования)
├── map.html (карта)
├── contact.html (контакты)
├── login.html (вход)
└── register.html (регистрация)
```

### 5.2. Использование Jinja2

**Переменные:**
```jinja2
{{ variable_name }}
{{ current_user.username }}
```

**Условия:**
```jinja2
{% if current_user.role == 'admin' %}
    <!-- Админ-контент -->
{% endif %}
```

**Циклы:**
```jinja2
{% for animal in animals %}
    <div>{{ animal.name }}</div>
{% endfor %}
```

**Наследование:**
```jinja2
{% extends "base.html" %}
{% block content %}
    <!-- Контент -->
{% endblock %}
```

## 6. БЕЗОПАСНОСТЬ

### 6.1. Хеширование паролей

```python
# При регистрации
password_hash = generate_password_hash(password)

# При входе
if check_password_hash(user.password_hash, password):
    login_user(user)
```

**Алгоритм:** PBKDF2 с SHA-256 (через Werkzeug)

### 6.2. Защита от SQL-инъекций

**Неправильно:**
```python
query = f"SELECT * FROM users WHERE username = '{username}'"
```

**Правильно:**
```python
cursor.execute('SELECT * FROM users WHERE username = ?', (username,))
```

### 6.3. Валидация данных

```python
# Проверка типов
try:
    amount = float(amount)
    if amount <= 0:
        raise ValueError
except ValueError:
    flash("Invalid amount", "error")
```

## 7. ПРОИЗВОДИТЕЛЬНОСТЬ

### 7.1. Оптимизация запросов

- Использование индексов в БД
- Параметризованные запросы
- Выборка только необходимых полей

### 7.2. Кэширование

- Статические файлы (CSS, JS, изображения)
- Возможность добавления Redis для кэширования данных

### 7.3. Асинхронность

- Chart.js загружает данные через AJAX
- Обновление графиков без перезагрузки страницы

## 8. ТЕСТИРОВАНИЕ

### 8.1. Типы тестирования

1. **Unit-тесты** - тестирование отдельных функций
2. **Integration-тесты** - тестирование взаимодействия компонентов
3. **E2E-тесты** - тестирование пользовательских сценариев

### 8.2. Примеры тестовых сценариев

1. Регистрация нового пользователя
2. Вход в систему
3. Добавление животного (admin/volunteer)
4. Подача заявки на усыновление
5. Внесение пожертвования
6. Просмотр аналитики (admin)
7. Прогнозирование затрат

## 9. РАЗВЕРТЫВАНИЕ

### 9.1. Development (разработка)

```bash
python app.py
# Запуск на http://127.0.0.1:5000
```

### 9.2. Production (продакшн)

**Рекомендуемая конфигурация:**

1. **WSGI-сервер:** Gunicorn
```bash
gunicorn -w 4 -b 0.0.0.0:8000 app:app
```

2. **Обратный прокси:** Nginx
```nginx
server {
    listen 80;
    server_name shelter.example.com;
    
    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
    
    location /static {
        alias /path/to/static;
    }
}
```

3. **База данных:** PostgreSQL (для масштабирования)

4. **Кэширование:** Redis

## 10. МЕТРИКИ И МОНИТОРИНГ

### 10.1. Ключевые метрики

- Количество активных пользователей
- Количество животных в приюте
- Количество заявок на усыновление
- Объем пожертвований
- Использование инвентаря

### 10.2. Логирование

- Все действия пользователей логируются
- Таблица `logs` хранит историю
- Возможность анализа активности

## 11. ДОКУМЕНТАЦИЯ КОДА

### 11.1. Комментарии

- Docstrings для функций
- Inline-комментарии для сложной логики
- Описание алгоритмов

### 11.2. Соглашения

- PEP 8 для Python
- Именование: snake_case для функций, PascalCase для классов
- Максимальная длина строки: 100 символов

## 12. ЗАКЛЮЧЕНИЕ

Проект демонстрирует:
- Использование современных веб-технологий
- Правильную архитектуру приложения
- Реализацию аналитических функций
- Безопасность и валидацию данных
- Адаптивный дизайн
- RESTful API

Система готова к использованию и может быть расширена дополнительным функционалом.

