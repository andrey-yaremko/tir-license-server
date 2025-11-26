from flask import Flask, request, jsonify, render_template
from datetime import datetime, timedelta
import psycopg2
import hashlib
import uuid
import os
import base64
from urllib.parse import urlparse

app = Flask(__name__)

# 🔐 НАЛАШТУВАННЯ ДОСТУПУ ДО АДМІНКИ
ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "Karnaval3e"  # ⚠️ ЗМІНІТЬ ЦЕЙ ПАРОЛЬ!

def get_db_connection():
    """Підключення до PostgreSQL"""
    database_url = os.environ.get('DATABASE_URL')
    
    if database_url:
        # Для Railway PostgreSQL
        result = urlparse(database_url)
        conn = psycopg2.connect(
            database=result.path[1:],
            user=result.username,
            password=result.password,
            host=result.hostname,
            port=result.port
        )
    else:
        # Для локальної розробки (SQLite)
        import sqlite3
        conn = sqlite3.connect('licenses.db')
    
    return conn

def init_database():
    """Ініціалізація бази даних"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Для PostgreSQL
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS licenses (
            id SERIAL PRIMARY KEY,
            license_key TEXT UNIQUE NOT NULL,
            hwid TEXT,
            days INTEGER DEFAULT 30,
            activated_at TIMESTAMP,
            expires_at TIMESTAMP,
            status TEXT DEFAULT 'active',
            last_check TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    conn.commit()
    conn.close()
    print("✅ База даних ініціалізована!")

def check_auth(auth_header):
    """Перевірка авторизації"""
    if not auth_header:
        return False
    
    try:
        auth_type, credentials = auth_header.split(' ', 1)
        if auth_type.lower() != 'basic':
            return False
        
        decoded = base64.b64decode(credentials).decode('utf-8')
        username, password = decoded.split(':', 1)
        
        return username == ADMIN_USERNAME and password == ADMIN_PASSWORD
    except:
        return False

@app.route('/')
def home():
    return jsonify({"message": "TIR Bot License Server", "status": "running"})

@app.route('/admin')
def admin_panel():
    """Веб-адмінка з паролем"""
    # Перевірка авторизації через URL параметр (для простоти)
    auth_param = request.args.get('auth')
    if auth_param:
        try:
            decoded = base64.b64decode(auth_param).decode('utf-8')
            username, password = decoded.split(':', 1)
            if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
                return render_template('admin.html')
        except:
            pass
    
    # Якщо не авторизований - показуємо форму входу
    return '''
    <!DOCTYPE html>
    <html>
    <head>
        <title>TIR Bot - Вхід в адмінку</title>
        <style>
            body { font-family: Arial; margin: 50px; background: #f5f5f5; }
            .login-box { background: white; padding: 30px; border-radius: 10px; max-width: 400px; margin: 0 auto; box-shadow: 0 0 10px rgba(0,0,0,0.1); }
            h1 { color: #2c3e50; text-align: center; }
            input { width: 100%; padding: 10px; margin: 10px 0; border: 1px solid #ddd; border-radius: 5px; }
            button { background: #3498db; color: white; border: none; padding: 10px 20px; border-radius: 5px; width: 100%; cursor: pointer; }
            button:hover { background: #2980b9; }
            .error { color: red; text-align: center; margin-top: 10px; }
        </style>
    </head>
    <body>
        <div class="login-box">
            <h1>🔐 Вхід в адмінку</h1>
            <form onsubmit="login(event)">
                <input type="text" id="username" placeholder="Логін" value="admin" required>
                <input type="password" id="password" placeholder="Пароль" required>
                <button type="submit">Увійти</button>
            </form>
            <div id="error" class="error"></div>
        </div>
        
        <script>
            function login(event) {
                event.preventDefault();
                const username = document.getElementById('username').value;
                const password = document.getElementById('password').value;
                const auth = btoa(username + ':' + password);
                window.location.href = '/admin?auth=' + auth;
            }
            
            // Показуємо помилку якщо була невдала спроба
            const urlParams = new URLSearchParams(window.location.search);
            if (urlParams.get('error')) {
                document.getElementById('error').textContent = 'Невірний логін або пароль!';
            }
        </script>
    </body>
    </html>
    '''

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
        WHERE license_key = %s AND status = 'active'
    ''', (license_key,))
    
    license_data = cursor.fetchone()
    
    if not license_data:
        conn.close()
        return jsonify({"valid": False, "message": "Ліцензія не знайдена або неактивна"})
    
    # Перевіряємо HWID
    license_id, license_key, stored_hwid, days, activated_at, expires_at, status, last_check, created_at = license_data
    
    if stored_hwid and stored_hwid != hwid:
        conn.close()
        return jsonify({"valid": False, "message": "HWID не співпадає"})
    
    # Перевіряємо термін дії
    if expires_at and datetime.now() > expires_at:
        cursor.execute('UPDATE licenses SET status = %s WHERE id = %s', ('expired', license_id))
        conn.commit()
        conn.close()
        return jsonify({"valid": False, "message": "Ліцензія протермінована"})
    
    # Оновлюємо останню перевірку
    cursor.execute('UPDATE licenses SET last_check = %s WHERE id = %s', (datetime.now(), license_id))
    conn.commit()
    conn.close()
    
    return jsonify({
        "valid": True,
        "message": "Ліцензія активна",
        "expires_at": expires_at.isoformat() if expires_at else None,
        "days_left": (expires_at - datetime.now()).days if expires_at else days
    })

@app.route('/activate', methods=['POST'])
def activate_license():
    """Активація ліцензії"""
    data = request.json
    license_key = data.get('license_key')
    hwid = data.get('hwid')
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('SELECT * FROM licenses WHERE license_key = %s', (license_key,))
    license_data = cursor.fetchone()
    
    if not license_data:
        conn.close()
        return jsonify({"success": False, "message": "Невірний ключ ліцензії"})
    
    license_id, license_key, stored_hwid, days, activated_at, expires_at, status, last_check, created_at = license_data
    
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
        SET hwid = %s, activated_at = %s, expires_at = %s, status = 'active'
        WHERE id = %s
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
    """Отримати всі ліцензії (для адмінки)"""
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
            'activated_at': license[4].isoformat() if license[4] else None,
            'expires_at': license[5].isoformat() if license[5] else None,
            'status': license[6],
            'last_check': license[7].isoformat() if license[7] else None,
            'created_at': license[8].isoformat() if license[8] else None
        })
    
    return jsonify(result)

@app.route('/admin/create_license', methods=['POST'])
def create_license():
    """Створити нову ліцензію"""
    data = request.json
    days = data.get('days', 30)
    
    # Генерація унікального ключа
    license_key = f"TIR-{uuid.uuid4().hex[:8].upper()}-{uuid.uuid4().hex[:8].upper()}"
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        INSERT INTO licenses (license_key, days, status)
        VALUES (%s, %s, 'active')
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
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('DELETE FROM licenses WHERE id = %s', (license_id,))
    conn.commit()
    conn.close()
    
    return jsonify({"success": True, "message": "Ліцензія видалена"})

@app.route('/admin/stats', methods=['GET'])
def get_stats():
    """Отримати статистику"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Загальна кількість ліцензій
    cursor.execute('SELECT COUNT(*) FROM licenses')
    total = cursor.fetchone()[0]
    
    # Активні ліцензії
    cursor.execute('SELECT COUNT(*) FROM licenses WHERE status = %s', ('active',))
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
