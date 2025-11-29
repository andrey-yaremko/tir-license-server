from flask import Flask, request, jsonify, render_template, session
from datetime import datetime, timedelta
import sqlite3
import hashlib
import uuid
import os
import secrets
import boto3
from botocore.config import Config

app = Flask(__name__)
app.secret_key = secrets.token_hex(32)  # Випадковий ключ для сесій

# Налаштування бази даних
DATABASE = 'licenses.db'

# 🔐 ОТРИМУЄМО ПАРОЛЬ ЛИШЕ ЗІ ЗМІННИХ ОТОЧЕННЯ
# В коді більше немає "запасного" пароля. Якщо змінна не задана на сервері - вхід неможливий.
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD")

if not ADMIN_PASSWORD:
    print("⚠️ УВАГА: Змінна ADMIN_PASSWORD не знайдена! Вхід в адмінку буде неможливий.")

# ☁️ НАЛАШТУВАННЯ BACKBLAZE B2
B2_KEY_ID = os.environ.get("B2_KEY_ID")
B2_APP_KEY = os.environ.get("B2_APP_KEY")
B2_BUCKET_NAME = os.environ.get("B2_BUCKET_NAME")
# Endpoint залежить від регіону вашого бакету (наприклад: https://s3.us-west-004.backblazeb2.com)
B2_ENDPOINT = os.environ.get("B2_ENDPOINT", "https://s3.us-west-004.backblazeb2.com")

# Ініціалізація клієнта S3 (Backblaze)
try:
    s3_client = boto3.client(
        's3',
        endpoint_url=B2_ENDPOINT,
        aws_access_key_id=B2_KEY_ID,
        aws_secret_access_key=B2_APP_KEY,
        config=Config(signature_version='s3v4')
    )
    print("✅ B2 Client ініціалізовано")
except Exception as e:
    print(f"⚠️ Помилка ініціалізації B2: {e}")
    s3_client = None


def get_db_connection():
    """Підключення до бази даних"""
    database_url = os.environ.get('DATABASE_URL')
    
    if database_url:
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
            pass
    
    import sqlite3
    conn = sqlite3.connect(DATABASE)
    return conn

def init_database():
    """Ініціалізація бази даних"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS licenses (
                id INTEGER PRIMARY KEY,
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
    except Exception as e:
        print(f"⚠️ Інфо по БД: {e}")
        conn.rollback()
    finally:
        conn.close()

def check_admin_auth():
    """Перевірка чи користувач авторизований"""
    return session.get('admin_logged_in') == True

@app.route('/')
def home():
    return jsonify({"message": "TIR Bot License Server", "status": "running"})

@app.route('/admin')
def admin_panel():
    return render_template('admin.html')

@app.route('/admin/login', methods=['POST'])
def admin_login():
    data = request.json
    password = data.get('password')
    
    # Якщо пароль не налаштований на сервері, вхід заборонено завжди
    if not ADMIN_PASSWORD:
        return jsonify({"success": False, "message": "Сервер не налаштований (немає пароля)"}), 500

    if password == ADMIN_PASSWORD:
        session['admin_logged_in'] = True
        return jsonify({"success": True, "message": "Успішний вхід"})
    else:
        return jsonify({"success": False, "message": "Невірний пароль"}), 401

@app.route('/admin/logout', methods=['POST'])
def admin_logout():
    session.pop('admin_logged_in', None)
    return jsonify({"success": True, "message": "Вихід успішний"})

@app.route('/admin/check_auth', methods=['GET'])
def check_auth_status():
    if check_admin_auth():
        return jsonify({"authenticated": True})
    else:
        return jsonify({"authenticated": False}), 401

# ==========================================
# 🔥 НОВИЙ ЕНДПОІНТ ДЛЯ ЗАВАНТАЖЕННЯ 🔥
# ==========================================
@app.route('/get_download_link', methods=['POST'])
def get_download_link():
    """Генерує безпечне тимчасове посилання на файл"""
    data = request.json
    license_key = data.get('license_key')
    hwid = data.get('hwid')

    if not s3_client:
        return jsonify({"message": "Сервер не налаштований для завантажень (B2 Error)"}), 500

    conn = get_db_connection()
    cursor = conn.cursor()

    # 1. Перевіряємо чи валідна ліцензія
    cursor.execute('SELECT hwid, status, expires_at FROM licenses WHERE license_key = ?', (license_key,))
    row = cursor.fetchone()
    conn.close()

    if not row:
        return jsonify({"message": "Ліцензія не знайдена"}), 403
    
    stored_hwid, status, expires_at = row

    # 2. Перевірки безпеки
    if status != 'active':
        return jsonify({"message": "Ліцензія неактивна"}), 403
    
    if stored_hwid != hwid:
        return jsonify({"message": "HWID не співпадає! Скачування заборонено."}), 403
        
    if expires_at and datetime.now() > datetime.fromisoformat(str(expires_at)):
        return jsonify({"message": "Термін дії ліцензії закінчився"}), 403

    # 3. Генеруємо посилання (діє 5 хвилин)
    try:
        url = s3_client.generate_presigned_url(
            ClientMethod='get_object',
            Params={
                'Bucket': B2_BUCKET_NAME,
                'Key': 'TIR_Bot_Full.zip' # ⚠️ Файл має називатись саме так в бакеті
            },
            ExpiresIn=300 # 300 секунд = 5 хвилин
        )
        return jsonify({"download_url": url})
    except Exception as e:
        print(f"B2 Error: {e}")
        return jsonify({"message": "Помилка генерації посилання"}), 500


@app.route('/check_license', methods=['POST'])
def check_license():
    data = request.json
    license_key = data.get('license_key')
    hwid = data.get('hwid')
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('SELECT id, hwid, days, expires_at, status FROM licenses WHERE license_key = ?', (license_key,))
    license_data = cursor.fetchone()
    
    if not license_data:
        conn.close()
        return jsonify({"valid": False, "message": "Ліцензія не знайдена"})
    
    lic_id, stored_hwid, days, expires_at, status = license_data

    if status != 'active':
        conn.close()
        return jsonify({"valid": False, "message": "Ліцензія неактивна"})
    
    if stored_hwid and stored_hwid != hwid:
        conn.close()
        return jsonify({"valid": False, "message": "HWID не співпадає"})
    
    if expires_at and datetime.now() > datetime.fromisoformat(str(expires_at)):
        cursor.execute("UPDATE licenses SET status = 'expired' WHERE id = ?", (lic_id,))
        conn.commit()
        conn.close()
        return jsonify({"valid": False, "message": "Ліцензія протермінована"})
    
    cursor.execute("UPDATE licenses SET last_check = ? WHERE id = ?", (datetime.now(), lic_id))
    conn.commit()
    conn.close()
    
    days_left = 0
    if expires_at:
        days_left = (datetime.fromisoformat(str(expires_at)) - datetime.now()).days
    else:
        days_left = days

    return jsonify({
        "valid": True,
        "message": "Ліцензія активна",
        "expires_at": expires_at,
        "days_left": days_left
    })

@app.route('/activate', methods=['POST'])
def activate_license():
    data = request.json
    license_key = data.get('license_key')
    hwid = data.get('hwid')
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('SELECT id, hwid, days, status, expires_at FROM licenses WHERE license_key = ?', (license_key,))
    license_data = cursor.fetchone()
    
    if not license_data:
        conn.close()
        return jsonify({"success": False, "message": "Невірний ключ"})
    
    lic_id, stored_hwid, days, status, expires_at = license_data
    
    if status != 'active':
        conn.close()
        return jsonify({"success": False, "message": "Ліцензія неактивна"})
    
    if stored_hwid and stored_hwid != hwid:
        conn.close()
        return jsonify({"success": False, "message": "Вже активовано на іншому ПК"})
    
    activated_time = datetime.now()
    expires_time = activated_time + timedelta(days=days)
    
    if not expires_at: 
        cursor.execute('''
            UPDATE licenses 
            SET hwid = ?, activated_at = ?, expires_at = ?, status = 'active'
            WHERE id = ?
        ''', (hwid, activated_time, expires_time, lic_id))
    else:
        cursor.execute('UPDATE licenses SET hwid = ? WHERE id = ?', (hwid, lic_id))
        expires_time = datetime.fromisoformat(str(expires_at))
    
    conn.commit()
    conn.close()
    
    return jsonify({
        "success": True,
        "message": "Активовано успішно!",
        "expires_at": expires_time.isoformat(),
        "days": days
    })

@app.route('/admin/licenses', methods=['GET'])
def get_all_licenses():
    if not check_admin_auth(): return jsonify({"error": "Auth failed"}), 401
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM licenses ORDER BY created_at DESC')
    rows = cursor.fetchall()
    conn.close()
    return jsonify(rows)

@app.route('/admin/create_license', methods=['POST'])
def create_license():
    if not check_admin_auth(): return jsonify({"error": "Auth failed"}), 401
    data = request.json
    days = data.get('days', 30)
    license_key = f"TIR-{uuid.uuid4().hex[:8].upper()}-{uuid.uuid4().hex[:8].upper()}"
    
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('INSERT INTO licenses (license_key, days, status) VALUES (?, ?, ?)', (license_key, days, 'active'))
    conn.commit()
    conn.close()
    return jsonify({"success": True, "license_key": license_key, "days": days})

@app.route('/admin/delete_license/<int:license_id>', methods=['DELETE'])
def delete_license(license_id):
    if not check_admin_auth(): return jsonify({"error": "Auth failed"}), 401
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM licenses WHERE id = ?', (license_id,))
    conn.commit()
    conn.close()
    return jsonify({"success": True})

@app.route('/admin/stats', methods=['GET'])
def get_stats():
    if not check_admin_auth(): return jsonify({"error": "Auth failed"}), 401
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT COUNT(*) FROM licenses')
    total = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM licenses WHERE status = 'active'")
    active = cursor.fetchone()[0]
    cursor.execute('SELECT COUNT(*) FROM licenses WHERE hwid IS NOT NULL')
    activated = cursor.fetchone()[0]
    conn.close()
    return jsonify({"total_licenses": total, "active_licenses": active, "activated_licenses": activated})

def create_app():
    init_database()
    return app

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(debug=False, host='0.0.0.0', port=port)
