from flask import Flask, request, jsonify, render_template, session
from datetime import datetime, timedelta
import sqlite3
import hashlib
import uuid
import os
import secrets

app = Flask(__name__)
app.secret_key = secrets.token_hex(32)  # Випадковий ключ для сесій

# Налаштування бази даних
DATABASE = 'licenses.db'

# 🔐 ПАРОЛЬ ДЛЯ АДМІНКИ
ADMIN_PASSWORD = "Karnaval3e"  # ⚠️ ЗМІНІТЬ ЦЕЙ ПАРОЛЬ!

def get_db_connection():
    """Підключення до бази даних"""
    database_url = os.environ.get('DATABASE_URL')
    
    if database_url:
        # Спроба підключитися до PostgreSQL
        try:
            import psycopg2
            from urllib.parse import urlparse
            result = urlparse(database_url)
            conn = psycopg2.connect(
                database=result.path[1:],
                user=result.username,
                password=result.password,
                host=result.hostname,
                port=result.port
            )
            return conn
        except ImportError:
            # Якщо psycopg2 не встановлений, використовуємо SQLite
            pass
    
    # SQLite для локальної розробки або як запасний варіант
    import sqlite3
    conn = sqlite3.connect(DATABASE)
    return conn

def init_database():
    """Ініціалізація бази даних"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Для SQLite
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS licenses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            license_key TEXT UNIQUE NOT NULL,
            hwid TEXT,
            days INTEGER DEFAULT 30,
            activated_at DATETIME,
            expires_at DATETIME,
            status TEXT DEFAULT 'active',
            last_check DATETIME,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    conn.commit()
    conn.close()
    print("✅ База даних ініціалізована!")

def check_admin_auth():
    """Перевірка чи користувач авторизований"""
    return session.get('admin_logged_in') == True

@app.route('/')
def home():
    return jsonify({"message": "TIR Bot License Server", "status": "running"})

@app.route('/admin')
def admin_panel():
    """Веб-адмінка"""
    return render_template('admin.html')

@app.route('/admin/login', methods=['POST'])
def admin_login():
    """Логін в адмінку"""
    data = request.json
    password = data.get('password')
    
    if password == ADMIN_PASSWORD:
        session['admin_logged_in'] = True
        return jsonify({"success": True, "message": "Успішний вхід"})
    else:
        return jsonify({"success": False, "message": "Невірний пароль"}), 401

@app.route('/admin/logout', methods=['POST'])
def admin_logout():
    """Вийти з адмінки"""
    session.pop('admin_logged_in', None)
    return jsonify({"success": True, "message": "Вихід успішний"})

@app.route('/admin/check_auth', methods=['GET'])
def check_auth_status():
    """Перевірити статус авторизації"""
    if check_admin_auth():
        return jsonify({"authenticated": True})
    else:
        return jsonify({"authenticated": False}), 401

@app.route('/check_license', methods=['POST'])
def check_license():
    """Перевірка ліцензії"""
    data = request.json
    license_key = data.get('license_key')
    hwid = data.get('hwid')
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT * FROM licenses 
        WHERE license_key = ? AND status = 'active'
    ''', (license_key,))
    
    license_data = cursor.fetchone()
    
    if not license_data:
        conn.close()
        return jsonify({"valid": False, "message": "Ліцензія не знайдена або неактивна"})
    
    # Перевіряємо HWID
    license_id, _, stored_hwid, days, activated_at, expires_at, status, last_check, created_at = license_data
    
    if stored_hwid and stored_hwid != hwid:
        conn.close()
        return jsonify({"valid": False, "message": "HWID не співпадає"})
    
    # Перевіряємо термін дії
    if expires_at and datetime.now() > datetime.fromisoformat(expires_at):
        cursor.execute('UPDATE licenses SET status = "expired" WHERE id = ?', (license_id,))
        conn.commit()
        conn.close()
        return jsonify({"valid": False, "message": "Ліцензія протермінована"})
    
    # Оновлюємо останню перевірку
    cursor.execute('UPDATE licenses SET last_check = ? WHERE id = ?', (datetime.now(), license_id))
    conn.commit()
    conn.close()
    
    return jsonify({
        "valid": True,
        "message": "Ліцензія активна",
        "expires_at": expires_at,
        "days_left": (datetime.fromisoformat(expires_at) - datetime.now()).days if expires_at else days
    })

@app.route('/activate', methods=['POST'])
def activate_license():
    """Активація ліцензії"""
    data = request.json
    license_key = data.get('license_key')
    hwid = data.get('hwid')
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('SELECT * FROM licenses WHERE license_key = ?', (license_key,))
    license_data = cursor.fetchone()
    
    if not license_data:
        conn.close()
        return jsonify({"success": False, "message": "Невірний ключ ліцензії"})
    
    license_id, _, stored_hwid, days, activated_at, expires_at, status, last_check, created_at = license_data
    
    if status != 'active':
        conn.close()
        return jsonify({"success": False, "message": "Ліцензія неактивна"})
    
    if stored_hwid and stored_hwid != hwid:
        conn.close()
        return jsonify({"success": False, "message": "Ліцензія вже активована на іншому пристрої"})
    
    # Активація ліцензії
    activated_time = datetime.now()
    expires_time = activated_time + timedelta(days=days)
    
    cursor.execute('''
        UPDATE licenses 
        SET hwid = ?, activated_at = ?, expires_at = ?, status = 'active'
        WHERE id = ?
    ''', (hwid, activated_time, expires_time, license_id))
    
    conn.commit()
    conn.close()
    
    return jsonify({
        "success": True,
        "message": "Ліцензія успішно активована!",
        "expires_at": expires_time.isoformat(),
        "days": days
    })

@app.route('/admin/licenses', methods=['GET'])
def get_all_licenses():
    """Отримати всі ліцензії"""
    if not check_admin_auth():
        return jsonify({"error": "Не авторизовано"}), 401
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('SELECT * FROM licenses ORDER BY created_at DESC')
    licenses = cursor.fetchall()
    
    conn.close()
    
    # Форматуємо результат
    result = []
    for license in licenses:
        result.append({
            'id': license[0],
            'license_key': license[1],
            'hwid': license[2],
            'days': license[3],
            'activated_at': license[4],
            'expires_at': license[5],
            'status': license[6],
            'last_check': license[7],
            'created_at': license[8]
        })
    
    return jsonify(result)

@app.route('/admin/create_license', methods=['POST'])
def create_license():
    """Створити нову ліцензію"""
    if not check_admin_auth():
        return jsonify({"error": "Не авторизовано"}), 401
    
    data = request.json
    days = data.get('days', 30)
    
    # Генерація унікального ключа
    license_key = f"TIR-{uuid.uuid4().hex[:8].upper()}-{uuid.uuid4().hex[:8].upper()}"
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        INSERT INTO licenses (license_key, days, status)
        VALUES (?, ?, 'active')
    ''', (license_key, days))
    
    conn.commit()
    conn.close()
    
    return jsonify({
        "success": True,
        "message": "Ліцензія створена",
        "license_key": license_key,
        "days": days
    })

@app.route('/admin/delete_license/<int:license_id>', methods=['DELETE'])
def delete_license(license_id):
    """Видалити ліцензію"""
    if not check_admin_auth():
        return jsonify({"error": "Не авторизовано"}), 401
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('DELETE FROM licenses WHERE id = ?', (license_id,))
    conn.commit()
    conn.close()
    
    return jsonify({"success": True, "message": "Ліцензія видалена"})

@app.route('/admin/stats', methods=['GET'])
def get_stats():
    """Отримати статистику"""
    if not check_admin_auth():
        return jsonify({"error": "Не авторизовано"}), 401
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Загальна кількість ліцензій
    cursor.execute('SELECT COUNT(*) FROM licenses')
    total = cursor.fetchone()[0]
    
    # Активні ліцензії
    cursor.execute('SELECT COUNT(*) FROM licenses WHERE status = "active"')
    active = cursor.fetchone()[0]
    
    # Активовані ліцензії
    cursor.execute('SELECT COUNT(*) FROM licenses WHERE hwid IS NOT NULL')
    activated = cursor.fetchone()[0]
    
    conn.close()
    
    return jsonify({
        "total_licenses": total,
        "active_licenses": active,
        "activated_licenses": activated
    })

def create_app():
    init_database()
    return app

if __name__ == '__main__':
    init_database()
    print("🚀 Сервер запускається на http://localhost:5000")
    print("📊 Доступні endpoints:")
    print("   GET  / - перевірка сервера")
    print("   GET  /admin - веб-адмінка")
    print("   POST /check_license - перевірка ліцензії")
    print("   POST /activate - активація ліцензії")
    print("   GET  /admin/licenses - список ліцензій")
    print("   POST /admin/create_license - створити ліцензію")
    print("   DELETE /admin/delete_license/<id> - видалити ліцензію")
    print("   GET  /admin/stats - статистика")
    
    # Для хмарного хостингу
    port = int(os.environ.get('PORT', 5000))
    app.run(debug=False, host='0.0.0.0', port=port)
