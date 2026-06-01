# app.py
from flask import Flask, render_template, request, flash, redirect, url_for, jsonify
import sqlite3
import os
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
import json

app = Flask(__name__)
app.secret_key = 'dobrye_lapki_secret_2025'
app.config['UPLOAD_FOLDER'] = 'static/uploads'

if not os.path.exists(app.config['UPLOAD_FOLDER']):
    os.makedirs(app.config['UPLOAD_FOLDER'])

DATABASE = 'shelter.db'

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

def forecast_costs(months=3):
    """Прогнозирование затрат на основе исторических данных"""
    with get_db() as conn:
        # Получаем исторические данные о расходах (инвентарь)
        cursor = conn.execute('''
            SELECT DATE(added_at) as date, SUM(quantity * unit_price) as daily_cost
            FROM inventory
            WHERE datetime(added_at) >= datetime('now', '-90 days')
            GROUP BY DATE(added_at)
            ORDER BY date ASC
        ''')
        historical = [dict(row) for row in cursor.fetchall()]
        
        if len(historical) < 3:
            # Недостаточно данных для прогноза - используем среднее значение
            avg_daily = 0
            if historical:
                avg_daily = sum(h['daily_cost'] for h in historical) / len(historical)
            trend = 0
        else:
            costs = [h['daily_cost'] for h in historical]
            avg_daily = sum(costs) / len(costs)
            # Простой расчет тренда (линейная регрессия без numpy)
            n = len(costs)
            x_sum = sum(range(n))
            y_sum = sum(costs)
            xy_sum = sum(i * costs[i] for i in range(n))
            x2_sum = sum(i * i for i in range(n))
            
            if n * x2_sum - x_sum * x_sum != 0:
                trend = (n * xy_sum - x_sum * y_sum) / (n * x2_sum - x_sum * x_sum)
            else:
                trend = 0
        
        # Прогноз на следующие месяцы
        forecast = []
        start_date = datetime.now()
        for i in range(months):
            month_date = start_date + timedelta(days=30 * (i + 1))
            # Простое линейное прогнозирование
            predicted_cost = max(0, avg_daily * 30 + (trend * 30 * (i + 1)))
            forecast.append({
                'month': month_date.strftime('%Y-%m'),
                'predicted_cost': round(predicted_cost, 2)
            })
        
        return forecast

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
                    conn.execute('UPDATE adoption_requests SET status = ? WHERE id = ?', (new_status, request_id))
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
    animals_list = get_animals()
    if request.method == 'POST':
        user_name = request.form.get('user_name')
        amount = request.form.get('amount')
        donation_type = request.form.get('donation_type')
        animal_id = request.form.get('animal_id') if donation_type == 'animal' else None

        if not all([user_name, amount, donation_type]):
            flash("All required fields must be filled!", "error")
        else:
            try:
                amount = float(amount)
                if amount <= 0:
                    flash("Amount must be greater than zero!", "error")
                else:
                    with get_db() as conn:
                        conn.execute('''
                            INSERT INTO donations (user_name, amount, donation_type, animal_id, donated_at)
                            VALUES (?, ?, ?, ?, ?)
                        ''', (user_name, amount, donation_type, animal_id, datetime.now().isoformat()))
                        conn.commit()
                        log_action('donation', f'Donation of {amount} by {user_name}', current_user.id if current_user.is_authenticated else 0)
                    flash("Thank you for your donation!", "success")
                    return redirect(url_for('donate'))
            except ValueError:
                flash("Amount must be a valid number!", "error")
    return render_template('donate.html', title="Dobrye Lapki - Donate", animals=animals_list)

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
    
    return render_template('analytics.html', 
                         title="Analytics Dashboard",
                         financial_summary=financial_summary,
                         animal_stats=animal_stats,
                         inventory_analysis=inventory_analysis,
                         donation_categories=donation_categories,
                         forecast=forecast)

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

if __name__ == '__main__':
    app.run(debug=True, host='127.0.0.1', port=5000)