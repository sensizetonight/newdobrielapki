# app.py
from flask import Flask, render_template, request, flash, redirect, url_for, jsonify, Response
import sqlite3
import os
import csv
import io
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
import json

from analytics_engine import (
    METHOD_DESCRIPTIONS,
    build_forecast_series,
    compute_kpis,
    forecast_ensemble,
    future_month_labels,
)
from db_migrate import migrate_database, seed_if_empty
from economic_engine import (
    BUDGET_CATEGORIES,
    get_full_economic_dashboard,
    set_setting,
)
from economic_engine import current_year_month

app = Flask(__name__)
app.secret_key = 'dobrye_lapki_secret_2025'
app.config['UPLOAD_FOLDER'] = 'static/uploads'

if not os.path.exists(app.config['UPLOAD_FOLDER']):
    os.makedirs(app.config['UPLOAD_FOLDER'])

DATABASE = 'shelter.db'
migrate_database(DATABASE)
if seed_if_empty(DATABASE):
    print('Database was empty — default users and animals restored.')

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

class User(UserMixin):
    def __init__(self, id, username, role):
        self.id = id
        self.username = username
        self.role = role

@login_manager.user_loader
def load_user(user_id):
    with get_db() as conn:
        cursor = conn.execute('SELECT id, username, role FROM users WHERE id = ?', (user_id,))
        user = cursor.fetchone()
        if user:
            return User(user['id'], user['username'], user['role'])
        return None

def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

def get_news():
    with get_db() as conn:
        cursor = conn.execute('SELECT * FROM news ORDER BY date DESC')
        return [dict(row) for row in cursor.fetchall()]

def get_animals():
    with get_db() as conn:
        cursor = conn.execute('SELECT * FROM animals')
        return [dict(row) for row in cursor.fetchall()]

def get_stray_animals():
    with get_db() as conn:
        cursor = conn.execute('SELECT * FROM stray_animals')
        return [dict(row) for row in cursor.fetchall()]

def get_adoption_requests():
    with get_db() as conn:
        cursor = conn.execute('''
            SELECT ar.id, ar.animal_id, a.name AS animal_name, ar.user_name, ar.phone, ar.email, ar.submitted_at, ar.status
            FROM adoption_requests ar
            JOIN animals a ON ar.animal_id = a.id
            ORDER BY ar.submitted_at DESC
        ''')
        return [dict(row) for row in cursor.fetchall()]

def get_donations():
    with get_db() as conn:
        cursor = conn.execute('''
            SELECT d.id, d.user_name, d.amount, d.donation_type, d.animal_id, a.name AS animal_name, d.donated_at
            FROM donations d
            LEFT JOIN animals a ON d.animal_id = a.id
            ORDER BY d.donated_at DESC
        ''')
        return [dict(row) for row in cursor.fetchall()]

def get_inventory(search=None, category=None):
    with get_db() as conn:
        query = '''
            SELECT id, item_name, category, quantity, unit, unit_price, quantity * unit_price AS total_price, added_at
            FROM inventory
        '''
        params = []
        conditions = []
        if search:
            conditions.append('item_name LIKE ?')
            params.append(f'%{search}%')
        if category and category in ['food', 'medicine', 'supplies', 'other']:
            conditions.append('category = ?')
            params.append(category)
        if conditions:
            query += ' WHERE ' + ' AND '.join(conditions)
        query += ' ORDER BY added_at DESC'
        cursor = conn.execute(query, params)
        return [dict(row) for row in cursor.fetchall()]

def get_inventory_stats():
    with get_db() as conn:
        cursor = conn.execute('''
            SELECT 
                SUM(quantity * unit_price) AS total_value,
                COUNT(*) AS item_count
            FROM inventory
        ''')
        stats = cursor.fetchone()
        return {
            'total_value': round(stats['total_value'], 2) if stats['total_value'] else 0,
            'item_count': stats['item_count'] or 0
        }

def get_donation_stats():
    with get_db() as conn:
        cursor = conn.execute('''
            SELECT 
                SUM(amount) as total_amount,
                COUNT(*) as donation_count,
                AVG(amount) as avg_donation
            FROM donations
        ''')
        stats = cursor.fetchone()
        return {
            'total_amount': stats['total_amount'] or 0,
            'donation_count': stats['donation_count'] or 0,
            'avg_donation': round(stats['avg_donation'], 2) if stats['avg_donation'] else 0
        }

def log_action(action, description, user_id):
    with get_db() as conn:
        conn.execute('''
            INSERT INTO logs (action, description, user_id, created_at)
            VALUES (?, ?, ?, ?)
        ''', (action, description, user_id, datetime.now().isoformat()))
        conn.commit()

# ========== АНАЛИТИЧЕСКИЕ ФУНКЦИИ ==========

def get_donations_timeline(days=30):
    """Получить данные о пожертвованиях за период"""
    with get_db() as conn:
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)
        cursor = conn.execute('''
            SELECT DATE(donated_at) as date, SUM(amount) as total, COUNT(*) as count
            FROM donations
            WHERE datetime(donated_at) >= datetime(?)
            GROUP BY DATE(donated_at)
            ORDER BY date ASC
        ''', (start_date.isoformat(),))
        return [dict(row) for row in cursor.fetchall()]

def get_adoption_trends(days=30):
    """Получить тренды усыновлений"""
    with get_db() as conn:
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)
        cursor = conn.execute('''
            SELECT DATE(submitted_at) as date, 
                   COUNT(*) as total,
                   SUM(CASE WHEN status = 'approved' THEN 1 ELSE 0 END) as approved,
                   SUM(CASE WHEN status = 'pending' THEN 1 ELSE 0 END) as pending,
                   SUM(CASE WHEN status = 'rejected' THEN 1 ELSE 0 END) as rejected
            FROM adoption_requests
            WHERE datetime(submitted_at) >= datetime(?)
            GROUP BY DATE(submitted_at)
            ORDER BY date ASC
        ''', (start_date.isoformat(),))
        return [dict(row) for row in cursor.fetchall()]

def get_inventory_analysis():
    """Анализ инвентаря по категориям"""
    with get_db() as conn:
        cursor = conn.execute('''
            SELECT 
                category,
                COUNT(*) as item_count,
                SUM(quantity) as total_quantity,
                SUM(quantity * unit_price) as total_value,
                AVG(unit_price) as avg_price
            FROM inventory
            GROUP BY category
        ''')
        return [dict(row) for row in cursor.fetchall()]

def get_animal_statistics():
    """Статистика по животным"""
    with get_db() as conn:
        cursor = conn.execute('''
            SELECT 
                status,
                COUNT(*) as count
            FROM animals
            GROUP BY status
        ''')
        return [dict(row) for row in cursor.fetchall()]

def get_monthly_series(table: str, date_col: str, value_expr: str, months: int = 12):
    """Агрегация по месяцам (YYYY-MM) за последние months месяцев."""
    with get_db() as conn:
        cursor = conn.execute(
            f'''
            SELECT strftime('%Y-%m', {date_col}) AS month,
                   {value_expr} AS total
            FROM {table}
            WHERE datetime({date_col}) >= datetime('now', ?)
            GROUP BY month
            ORDER BY month ASC
            ''',
            (f'-{months * 31} days',),
        )
        return [dict(row) for row in cursor.fetchall()]


def get_monthly_donations(months=12):
    return get_monthly_series(
        'donations', 'donated_at', 'SUM(amount)', months
    )


def get_monthly_expenses(months=12):
    return get_monthly_series(
        'inventory', 'added_at', 'SUM(quantity * unit_price)', months
    )


def get_monthly_adoptions(months=12):
    with get_db() as conn:
        cursor = conn.execute(
            '''
            SELECT strftime('%Y-%m', submitted_at) AS month,
                   COUNT(*) AS total,
                   SUM(CASE WHEN status = 'approved' THEN 1 ELSE 0 END) AS approved,
                   SUM(CASE WHEN status = 'pending' THEN 1 ELSE 0 END) AS pending,
                   SUM(CASE WHEN status = 'rejected' THEN 1 ELSE 0 END) AS rejected
            FROM adoption_requests
            WHERE datetime(submitted_at) >= datetime('now', ?)
            GROUP BY month
            ORDER BY month ASC
            ''',
            (f'-{months * 31} days',),
        )
        return [dict(row) for row in cursor.fetchall()]


def get_analytics_forecasts(horizon=3):
    """Полный набор прогнозов для дашборда."""
    donations_m = get_monthly_donations(12)
    expenses_m = get_monthly_expenses(12)
    adoptions_m = get_monthly_adoptions(12)

    donations_fc = build_forecast_series(donations_m, 'total', 'month', horizon)
    expenses_fc = build_forecast_series(expenses_m, 'total', 'month', horizon)

    adoption_values = [float(r.get('approved', 0) or 0) for r in adoptions_m]
    adoption_ensemble = forecast_ensemble(adoption_values, horizon)
    last_adoption_month = adoptions_m[-1]['month'] if adoptions_m else datetime.now().strftime('%Y-%m')

    adoption_forecast = []
    for i, month in enumerate(future_month_labels(last_adoption_month, horizon)):
        adoption_forecast.append(
            {
                'month': month,
                'value': adoption_ensemble['predictions'][i],
                'lower': adoption_ensemble['lower'][i],
                'upper': adoption_ensemble['upper'][i],
            }
        )

    # Баланс по месяцам (доход − расход) и прогноз
    months_set = sorted(
        set([r['month'] for r in donations_m] + [r['month'] for r in expenses_m])
    )
    don_map = {r['month']: float(r['total'] or 0) for r in donations_m}
    exp_map = {r['month']: float(r['total'] or 0) for r in expenses_m}
    balance_rows = [
        {'month': m, 'total': round(don_map.get(m, 0) - exp_map.get(m, 0), 2)}
        for m in months_set
    ]
    balance_fc = build_forecast_series(balance_rows, 'total', 'month', horizon)

    # Обратная совместимость: прогноз расходов для шаблона
    legacy_forecast = [
        {'month': f['month'], 'predicted_cost': f['value']}
        for f in expenses_fc['forecast']
    ]

    return {
        'donations': donations_fc,
        'expenses': expenses_fc,
        'adoptions': {
            'historical': [
                {
                    'month': r['month'],
                    'value': int(r.get('approved', 0) or 0),
                    'total': int(r.get('total', 0) or 0),
                }
                for r in adoptions_m
            ],
            'forecast': adoption_forecast,
        },
        'balance': balance_fc,
        'legacy_expense_forecast': legacy_forecast,
        'methods': METHOD_DESCRIPTIONS,
    }


def forecast_costs(months=3):
    """Прогноз расходов (обёртка над ансамблевой моделью)."""
    return get_analytics_forecasts(months)['legacy_expense_forecast']

def get_financial_summary():
    """Финансовая сводка"""
    with get_db() as conn:
        # Доходы (пожертвования)
        cursor = conn.execute('SELECT SUM(amount) as total FROM donations')
        total_donations = cursor.fetchone()['total'] or 0
        
        # Расходы (инвентарь)
        cursor = conn.execute('SELECT SUM(quantity * unit_price) as total FROM inventory')
        total_expenses = cursor.fetchone()['total'] or 0
        
        # Пожертвования за последние 30 дней
        cursor = conn.execute('''
            SELECT SUM(amount) as total 
            FROM donations 
            WHERE datetime(donated_at) >= datetime('now', '-30 days')
        ''')
        monthly_donations = cursor.fetchone()['total'] or 0
        
        # Расходы за последние 30 дней
        cursor = conn.execute('''
            SELECT SUM(quantity * unit_price) as total 
            FROM inventory 
            WHERE datetime(added_at) >= datetime('now', '-30 days')
        ''')
        monthly_expenses = cursor.fetchone()['total'] or 0
        
        return {
            'total_donations': round(total_donations, 2),
            'total_expenses': round(total_expenses, 2),
            'balance': round(total_donations - total_expenses, 2),
            'monthly_donations': round(monthly_donations, 2),
            'monthly_expenses': round(monthly_expenses, 2),
            'monthly_balance': round(monthly_donations - monthly_expenses, 2)
        }

def get_donation_categories():
    """Анализ пожертвований по типам"""
    with get_db() as conn:
        cursor = conn.execute('''
            SELECT 
                donation_type,
                COUNT(*) as count,
                SUM(amount) as total,
                AVG(amount) as avg
            FROM donations
            GROUP BY donation_type
        ''')
        return [dict(row) for row in cursor.fetchall()]

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        if not username or not password:
            flash('Username and password are required!', 'error')
        else:
            with get_db() as conn:
                try:
                    conn.execute('INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)',
                                 (username, generate_password_hash(password), 'guest'))
                    conn.commit()
                    flash('Registration successful! Please log in.', 'success')
                    return redirect(url_for('login'))
                except sqlite3.IntegrityError:
                    flash('Username already exists!', 'error')
    return render_template('register.html', title='Registration')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        with get_db() as conn:
            cursor = conn.execute('SELECT * FROM users WHERE username = ?', (username,))
            user = cursor.fetchone()
            if user and check_password_hash(user['password_hash'], password):
                user_obj = User(user['id'], user['username'], user['role'])
                login_user(user_obj)
                flash('Login successful!', 'success')
                return redirect(url_for('index'))
            else:
                flash('Invalid username or password!', 'error')
    return render_template('login.html', title='Login')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('You have been logged out!', 'success')
    return redirect(url_for('index'))

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST' and current_user.is_authenticated and current_user.role == 'admin':
        title = request.form.get('title')
        content = request.form.get('content')
        date = request.form.get('date')
        if not all([title, content, date]):
            flash("All fields are required!", "error")
        else:
            with get_db() as conn:
                conn.execute('INSERT INTO news (title, content, date) VALUES (?, ?, ?)',
                             (title, content, date))
                conn.commit()
                log_action('add_news', f'Added news: {title}', current_user.id)
            flash("News added!", "success")
    news_list = get_news()
    return render_template('index.html', title="Dobrye Lapki - Home", news=news_list)

@app.route('/delete_news/<int:id>', methods=['POST'])
@login_required
def delete_news(id):
    if current_user.role != 'admin':
        flash('Only admins can delete news!', 'error')
        return redirect(url_for('index'))
    with get_db() as conn:
        cursor = conn.execute('SELECT title FROM news WHERE id = ?', (id,))
        news = cursor.fetchone()
        if news:
            conn.execute('DELETE FROM news WHERE id = ?', (id,))
            conn.commit()
            log_action('delete_news', f'Deleted news: {news["title"]}', current_user.id)
            flash("News deleted!", "success")
        else:
            flash("News not found!", "error")
    return redirect(url_for('index'))

@app.route('/animals', methods=['GET', 'POST'])
def animals():
    if request.method == 'POST':
        if not current_user.is_authenticated:
            flash("Please log in to perform this action!", "error")
            return redirect(url_for('login'))
        
        action = request.form.get('action')
        if action == 'add' and current_user.role in ['admin', 'volunteer']:
            name = request.form.get('name')
            description = request.form.get('description')
            status = request.form.get('status')
            age = request.form.get('age')
            gender = request.form.get('gender')
            vaccinated = request.form.get('vaccinated')
            sterilized = request.form.get('sterilized')
            photo = request.files.get('photo')
            photo_url = None
            if not name or not status:
                flash("Name and status are required!", "error")
            else:
                if photo and photo.filename:
                    photo_url = f"uploads/{photo.filename}"
                    photo.save(os.path.join(app.config['UPLOAD_FOLDER'], photo.filename))
                with get_db() as conn:
                    conn.execute('INSERT INTO animals (name, description, status, photo_url, age, gender, vaccinated, sterilized) VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
                                 (name, description, status, photo_url, age, gender, vaccinated, sterilized))
                    conn.commit()
                    log_action('add_animal', f'Added animal: {name}', current_user.id)
                flash("Animal added!", "success")
        elif action == 'edit' and current_user.role in ['admin', 'volunteer']:
            animal_id = request.form.get('animal_id')
            name = request.form.get('name')
            description = request.form.get('description')
            status = request.form.get('status')
            age = request.form.get('age')
            gender = request.form.get('gender')
            vaccinated = request.form.get('vaccinated')
            sterilized = request.form.get('sterilized')
            photo = request.files.get('photo')
            photo_url = request.form.get('existing_photo_url')
            if not name or not status:
                flash("Name and status are required!", "error")
            else:
                if photo and photo.filename:
                    photo_url = f"uploads/{photo.filename}"
                    photo.save(os.path.join(app.config['UPLOAD_FOLDER'], photo.filename))
                with get_db() as conn:
                    conn.execute('UPDATE animals SET name = ?, description = ?, status = ?, photo_url = ?, age = ?, gender = ?, vaccinated = ?, sterilized = ? WHERE id = ?',
                                 (name, description, status, photo_url, age, gender, vaccinated, sterilized, animal_id))
                    conn.commit()
                    log_action('edit_animal', f'Edited animal ID {animal_id}: {name}', current_user.id)
                flash("Animal updated!", "success")
        elif action == 'adopt':
            animal_id = request.form.get('animal_id')
            user_name = request.form.get('user_name')
            phone = request.form.get('phone')
            email = request.form.get('email')
            if not all([animal_id, user_name, phone, email]):
                flash("All fields are required!", "error")
            else:
                with get_db() as conn:
                    conn.execute('INSERT INTO adoption_requests (animal_id, user_name, phone, email, submitted_at) VALUES (?, ?, ?, ?, ?)',
                                 (animal_id, user_name, phone, email, datetime.now().isoformat()))
                    conn.commit()
                    log_action('adoption_request', f'Adoption request for animal ID {animal_id} by {user_name}', current_user.id if current_user.is_authenticated else 0)
                flash("Adoption request submitted! We'll contact you soon.", "success")
    animals_list = get_animals()
    return render_template('animals.html', title="Dobrye Lapki - Animals", animals=animals_list)

@app.route('/delete_animal/<int:id>', methods=['POST'])
@login_required
def delete_animal(id):
    if current_user.role not in ['admin', 'volunteer']:
        flash('Only admins or volunteers can delete animals!', 'error')
        return redirect(url_for('animals'))
    with get_db() as conn:
        cursor = conn.execute('SELECT name FROM animals WHERE id = ?', (id,))
        animal = cursor.fetchone()
        if animal:
            conn.execute('DELETE FROM animals WHERE id = ?', (id,))
            conn.commit()
            log_action('delete_animal', f'Deleted animal: {animal["name"]}', current_user.id)
            flash("Animal deleted!", "success")
        else:
            flash("Animal not found!", "error")
    return redirect(url_for('animals'))

@app.route('/map', methods=['GET', 'POST'])
def map():
    stray_animals = get_stray_animals()
    if request.method == 'POST' and current_user.is_authenticated and current_user.role in ['admin', 'volunteer']:
        description = request.form.get('description')
        lat = request.form.get('lat')
        lon = request.form.get('lon')
        if not all([description, lat, lon]):
            flash("All fields are required!", "error")
            return redirect(url_for('map'))
        try:
            lat = float(lat)
            lon = float(lon)
        except ValueError:
            flash("Coordinates must be numbers!", "error")
            return redirect(url_for('map'))
        photo = request.files.get('photo')
        photo_url = None
        if photo and photo.filename:
            photo_url = f"uploads/{photo.filename}"
            photo.save(os.path.join(app.config['UPLOAD_FOLDER'], photo.filename))
        with get_db() as conn:
            conn.execute('INSERT INTO stray_animals (description, lat, lon, photo_url) VALUES (?, ?, ?, ?)',
                         (description, lat, lon, photo_url))
            conn.commit()
            log_action('add_stray_animal', f'Added stray animal marker: {description}', current_user.id)
        flash("Marker added!", "success")
        return redirect(url_for('map'))
    return render_template('map.html', title="Dobrye Lapki - Map", stray_animals=stray_animals)

@app.route('/delete_mark/<int:id>', methods=['POST'])
@login_required
def delete_mark(id):
    if current_user.role not in ['admin', 'volunteer']:
        flash('Only admins or volunteers can delete markers!', 'error')
        return redirect(url_for('map'))
    with get_db() as conn:
        cursor = conn.execute('SELECT description FROM stray_animals WHERE id = ?', (id,))
        marker = cursor.fetchone()
        if marker:
            conn.execute('DELETE FROM stray_animals WHERE id = ?', (id,))
            conn.commit()
            log_action('delete_stray_animal', f'Deleted stray animal marker: {marker["description"]}', current_user.id)
            flash("Marker deleted!", "success")
        else:
            flash("Marker not found!", "error")
    return redirect(url_for('map'))

@app.route('/admin/dashboard', methods=['GET', 'POST'])
@login_required
def admin_dashboard():
    if current_user.role != 'admin':
        flash('Access restricted to administrators only!', 'error')
        return redirect(url_for('index'))
    
    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'update_request':
            request_id = request.form.get('request_id')
            new_status = request.form.get('status')
            if request_id and new_status in ['pending', 'approved', 'rejected']:
                with get_db() as conn:
                    processed = datetime.now().isoformat() if new_status != 'pending' else None
                    conn.execute(
                        'UPDATE adoption_requests SET status = ?, processed_at = COALESCE(processed_at, ?) WHERE id = ?',
                        (new_status, processed, request_id),
                    )
                    conn.commit()
                    log_action('update_adoption_request', f'Updated adoption request ID {request_id} to {new_status}', current_user.id)
                flash(f"Request #{request_id} status updated to {new_status}!", "success")
            else:
                flash("Invalid request or status!", "error")
        elif action == 'add_inventory':
            item_name = request.form.get('item_name')
            category = request.form.get('category')
            quantity = request.form.get('quantity')
            unit = request.form.get('unit')
            unit_price = request.form.get('unit_price')
            if not all([item_name, category, quantity, unit, unit_price]):
                flash("All fields are required!", "error")
            else:
                try:
                    quantity = float(quantity)
                    unit_price = float(unit_price)
                    if quantity < 0 or unit_price < 0:
                        flash("Quantity and unit price cannot be negative!", "error")
                    else:
                        with get_db() as conn:
                            conn.execute('''
                                INSERT INTO inventory (item_name, category, quantity, unit, unit_price, added_at)
                                VALUES (?, ?, ?, ?, ?, ?)
                            ''', (item_name, category, quantity, unit, unit_price, datetime.now().isoformat()))
                            conn.commit()
                            log_action('add_inventory', f'Added inventory item: {item_name}', current_user.id)
                        flash("Inventory item added!", "success")
                except ValueError:
                    flash("Quantity and unit price must be numbers!", "error")
        elif action == 'edit_inventory':
            item_id = request.form.get('item_id')
            item_name = request.form.get('item_name')
            category = request.form.get('category')
            quantity = request.form.get('quantity')
            unit = request.form.get('unit')
            unit_price = request.form.get('unit_price')
            if not all([item_id, item_name, category, quantity, unit, unit_price]):
                flash("All fields are required!", "error")
            else:
                try:
                    quantity = float(quantity)
                    unit_price = float(unit_price)
                    if quantity < 0 or unit_price < 0:
                        flash("Quantity and unit price cannot be negative!", "error")
                    else:
                        with get_db() as conn:
                            conn.execute('''
                                UPDATE inventory 
                                SET item_name = ?, category = ?, quantity = ?, unit = ?, unit_price = ?
                                WHERE id = ?
                            ''', (item_name, category, quantity, unit, unit_price, item_id))
                            conn.commit()
                            log_action('edit_inventory', f'Edited inventory item ID {item_id}: {item_name}', current_user.id)
                        flash("Inventory item updated!", "success")
                except ValueError:
                    flash("Quantity and unit price must be numbers!", "error")
        elif action == 'delete_inventory':
            item_id = request.form.get('item_id')
            with get_db() as conn:
                cursor = conn.execute('SELECT item_name FROM inventory WHERE id = ?', (item_id,))
                item = cursor.fetchone()
                if item:
                    conn.execute('DELETE FROM inventory WHERE id = ?', (item_id,))
                    conn.commit()
                    log_action('delete_inventory', f'Deleted inventory item: {item["item_name"]}', current_user.id)
                    flash("Inventory item deleted!", "success")
                else:
                    flash("Item not found!", "error")
    
    search = request.args.get('search')
    category = request.args.get('category')
    adoption_requests = get_adoption_requests()
    donations = get_donations()
    donation_stats = get_donation_stats()
    inventory = get_inventory(search, category)
    inventory_stats = get_inventory_stats()
    return render_template('admin_dashboard.html', title="Admin Dashboard", 
                         requests=adoption_requests, donations=donations, 
                         donation_stats=donation_stats, inventory=inventory,
                         inventory_stats=inventory_stats, search=search, category=category)

@app.route('/contact', methods=['GET', 'POST'])
def contact():
    if request.method == 'POST':
        name = request.form.get('name')
        phone = request.form.get('phone')
        if not all([name, phone]):
            flash("All fields are required!", "error")
        else:
            # Здесь можно добавить логику для обработки формы, например, отправка email
            log_action('contact_form', f'Contact form submitted by {name}', current_user.id if current_user.is_authenticated else 0)
            flash("Thank you for contacting us! We'll get back to you soon.", "success")
            return redirect(url_for('contact'))
    return render_template('contact.html', title="Dobrye Lapki - Contact Us")

@app.route('/donate', methods=['GET', 'POST'])
def donate():
    from economic_engine import get_campaigns_with_progress, get_cost_per_animal, get_setting

    animals_list = [a for a in get_animals() if a.get('status') != 'Adopted']
    campaigns = get_campaigns_with_progress()
    cost_info = get_cost_per_animal()
    suggested = {
        'month': int(cost_info['monthly_per_animal']),
        'week': int(cost_info['daily_cost'] * 7),
        'day': int(cost_info['daily_cost']),
    }

    if request.method == 'POST':
        user_name = request.form.get('user_name')
        amount = request.form.get('amount')
        donation_type = request.form.get('donation_type')
        animal_id = request.form.get('animal_id') if donation_type == 'animal' else None
        campaign_id = request.form.get('campaign_id') or None
        is_recurring = 1 if request.form.get('is_recurring') else 0

        if not all([user_name, amount, donation_type]):
            flash("Заполните все обязательные поля!", "error")
        else:
            try:
                amount = float(amount)
                if amount <= 0:
                    flash("Сумма должна быть больше нуля!", "error")
                else:
                    with get_db() as conn:
                        conn.execute(
                            '''INSERT INTO donations (user_name, amount, donation_type, animal_id, campaign_id, is_recurring, donated_at)
                               VALUES (?, ?, ?, ?, ?, ?, ?)''',
                            (user_name, amount, donation_type, animal_id, campaign_id, is_recurring,
                             datetime.now().isoformat()),
                        )
                        if is_recurring:
                            conn.execute(
                                '''INSERT INTO recurring_donations (user_name, amount, frequency, next_date, active, created_at)
                                   VALUES (?, ?, 'monthly', ?, 1, ?)''',
                                (user_name, amount,
                                 (datetime.now() + timedelta(days=30)).isoformat(),
                                 datetime.now().isoformat()),
                            )
                        conn.commit()
                    log_action('donation', f'Donation {amount} by {user_name}',
                               current_user.id if current_user.is_authenticated else 0)
                    flash("Спасибо за пожертвование!", "success")
                    return redirect(url_for('donate'))
            except ValueError:
                flash("Укажите корректную сумму!", "error")
    return render_template(
        'donate.html',
        title="Пожертвовать — Добрые Лапки",
        animals=animals_list,
        campaigns=campaigns,
        suggested=suggested,
        cost_info=cost_info,
    )

@app.route('/admin/analytics')
@login_required
def analytics_dashboard():
    """Аналитический дашборд"""
    if current_user.role != 'admin':
        flash('Access restricted to administrators only!', 'error')
        return redirect(url_for('index'))

    financial_summary = get_financial_summary()
    animal_stats = get_animal_statistics()
    inventory_analysis = get_inventory_analysis()
    donation_categories = get_donation_categories()
    forecast = forecast_costs(3)
    kpis = compute_kpis(
        financial_summary, animal_stats, get_monthly_adoptions(6)
    )

    return render_template(
        'analytics.html',
        title='Аналитика — Добрые Лапки',
        financial_summary=financial_summary,
        animal_stats=animal_stats,
        inventory_analysis=inventory_analysis,
        donation_categories=donation_categories,
        forecast=forecast,
        kpis=kpis,
    )

@app.route('/api/analytics/donations-timeline')
@login_required
def api_donations_timeline():
    """API для графика пожертвований"""
    if current_user.role != 'admin':
        return jsonify({'error': 'Access denied'}), 403
    days = request.args.get('days', 30, type=int)
    data = get_donations_timeline(days)
    return jsonify(data)

@app.route('/api/analytics/adoption-trends')
@login_required
def api_adoption_trends():
    """API для графика усыновлений"""
    if current_user.role != 'admin':
        return jsonify({'error': 'Access denied'}), 403
    days = request.args.get('days', 30, type=int)
    data = get_adoption_trends(days)
    return jsonify(data)

@app.route('/api/analytics/inventory')
@login_required
def api_inventory_analysis():
    """API для анализа инвентаря"""
    if current_user.role != 'admin':
        return jsonify({'error': 'Access denied'}), 403
    data = get_inventory_analysis()
    return jsonify(data)


def _admin_api_guard():
    if current_user.role != 'admin':
        return jsonify({'error': 'Access denied'}), 403
    return None


@app.route('/api/analytics/forecasts')
@login_required
def api_analytics_forecasts():
    """Прогнозы по доходам, расходам, усыновлениям и балансу."""
    denied = _admin_api_guard()
    if denied:
        return denied
    horizon = request.args.get('horizon', 3, type=int)
    horizon = max(1, min(horizon, 6))
    return jsonify(get_analytics_forecasts(horizon))


@app.route('/api/analytics/dashboard')
@login_required
def api_analytics_dashboard():
    """Сводка KPI и справочник методов прогнозирования."""
    denied = _admin_api_guard()
    if denied:
        return denied
    financial = get_financial_summary()
    animal_stats = get_animal_statistics()
    adoption_monthly = get_monthly_adoptions(6)
    kpis = compute_kpis(financial, animal_stats, adoption_monthly)
    return jsonify(
        {
            'kpis': kpis,
            'financial': financial,
            'animal_stats': animal_stats,
            'donation_categories': get_donation_categories(),
            'inventory': get_inventory_analysis(),
        }
    )


@app.route('/admin/economics', methods=['GET', 'POST'])
@login_required
def economics_dashboard():
    if current_user.role != 'admin':
        flash('Доступ только для администраторов!', 'error')
        return redirect(url_for('index'))

    if request.method == 'POST':
        action = request.form.get('action')
        ym = current_year_month()
        try:
            if action == 'add_budget':
                with get_db() as conn:
                    conn.execute(
                        '''INSERT OR REPLACE INTO budget_plans (year_month, category, planned_amount)
                           VALUES (?, ?, ?)''',
                        (ym, request.form.get('category'), float(request.form.get('planned_amount'))),
                    )
                    conn.commit()
                flash('Статья бюджета сохранена', 'success')
            elif action == 'add_campaign':
                with get_db() as conn:
                    aid = request.form.get('animal_id') or None
                    conn.execute(
                        '''INSERT INTO fundraising_campaigns (title, description, target_amount, animal_id, start_date, status)
                           VALUES (?, '', ?, ?, ?, 'active')''',
                        (request.form.get('title'), float(request.form.get('target_amount')),
                         aid, datetime.now().isoformat()),
                    )
                    conn.commit()
                flash('Сбор создан', 'success')
            elif action == 'add_partner':
                with get_db() as conn:
                    conn.execute(
                        'INSERT INTO partners (name, amount, partner_type, start_date) VALUES (?, ?, ?, ?)',
                        (request.form.get('name'), float(request.form.get('amount')),
                         'sponsor', datetime.now().isoformat()),
                    )
                    conn.commit()
                flash('Партнёр добавлен', 'success')
            elif action == 'add_event':
                with get_db() as conn:
                    conn.execute(
                        'INSERT INTO events (name, event_date, cost, revenue) VALUES (?, ?, ?, ?)',
                        (request.form.get('name'), datetime.now().isoformat(),
                         float(request.form.get('cost')), float(request.form.get('revenue'))),
                    )
                    conn.commit()
                flash('Мероприятие добавлено', 'success')
            elif action == 'add_recurring':
                with get_db() as conn:
                    conn.execute(
                        '''INSERT INTO recurring_donations (user_name, amount, frequency, next_date, active, created_at)
                           VALUES (?, ?, 'monthly', ?, 1, ?)''',
                        (request.form.get('user_name'), float(request.form.get('amount')),
                         (datetime.now() + timedelta(days=30)).isoformat(), datetime.now().isoformat()),
                    )
                    conn.commit()
                flash('Регулярное пожертвование добавлено', 'success')
            elif action == 'add_vet':
                d = request.form.get('scheduled_date')
                scheduled = f'{d}T10:00:00'
                with get_db() as conn:
                    conn.execute(
                        '''INSERT INTO vet_appointments (animal_id, scheduled_at, service_type, estimated_cost, status)
                           VALUES (?, ?, ?, ?, 'planned')''',
                        (request.form.get('animal_id'), scheduled, request.form.get('service_type'),
                         float(request.form.get('estimated_cost'))),
                    )
                    conn.commit()
                flash('Визит добавлен', 'success')
            elif action == 'save_settings':
                set_setting('kennel_capacity', request.form.get('kennel_capacity', '25'))
                set_setting('daily_cost_per_animal', request.form.get('daily_cost_per_animal', '150'))
                set_setting('monthly_fixed_costs', request.form.get('monthly_fixed_costs', '45000'))
                flash('Настройки сохранены', 'success')
        except (ValueError, TypeError):
            flash('Проверьте введённые числа', 'error')
        return redirect(url_for('economics_dashboard'))

    eco = get_full_economic_dashboard()
    animals = get_animals()
    return render_template(
        'economics.html',
        title='Экономика — Добрые Лапки',
        eco=eco,
        animals=animals,
        budget_categories=BUDGET_CATEGORIES,
    )


@app.route('/admin/economics/export')
@login_required
def export_economics_csv():
    if current_user.role != 'admin':
        flash('Доступ запрещён', 'error')
        return redirect(url_for('index'))
    eco = get_full_economic_dashboard()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Отчёт экономики приюта', datetime.now().isoformat()])
    writer.writerow([])
    writer.writerow(['Показатель', 'Значение'])
    writer.writerow(['Баланс', eco['financial']['balance']])
    writer.writerow(['Доходы всего', eco['financial']['total_income']])
    writer.writerow(['Расходы всего', eco['financial']['total_expenses']])
    writer.writerow(['Запас прочности (мес)', eco['sustainability']['index_months']])
    writer.writerow(['Стоимость содержания/мес', eco['cost_per_animal']['monthly_per_animal']])
    writer.writerow([])
    writer.writerow(['Бюджет', eco['budget']['year_month'], 'План', 'Факт'])
    for row in eco['budget']['rows']:
        writer.writerow([row['label'], '', row['planned'], row['actual']])
    writer.writerow([])
    writer.writerow(['Сценарий', 'Доход', 'Расход', 'Баланс'])
    for s in eco['scenarios']:
        writer.writerow([s['name'], s['income'], s['expenses'], s['balance']])
    return Response(
        '\ufeff' + output.getvalue(),
        mimetype='text/csv; charset=utf-8',
        headers={'Content-Disposition': 'attachment; filename=economics_report.csv'},
    )


@app.route('/api/economics/dashboard')
@login_required
def api_economics_dashboard():
    denied = _admin_api_guard()
    if denied:
        return denied
    return jsonify(get_full_economic_dashboard())


@app.route('/api/analytics/monthly-overview')
@login_required
def api_monthly_overview():
    """Помесячные ряды для комбинированных графиков."""
    denied = _admin_api_guard()
    if denied:
        return denied
    months = request.args.get('months', 12, type=int)
    return jsonify(
        {
            'donations': get_monthly_donations(months),
            'expenses': get_monthly_expenses(months),
            'adoptions': get_monthly_adoptions(months),
        }
    )


if __name__ == '__main__':
    app.run(debug=True, host='127.0.0.1', port=5000)