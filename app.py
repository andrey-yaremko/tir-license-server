from flask import Flask, request, jsonify, render_template, session, redirect, url_for
from datetime import datetime, timedelta
import sqlite3
import hashlib
import uuid
import os
import secrets
import boto3
from botocore.config import Config

app = Flask(__name__)
app.secret_key = secrets.token_hex(32)

# === ЗМІННІ ОТОЧЕННЯ (Ті самі, що ти вже налаштував) ===
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD")
B2_KEY_ID = os.environ.get("B2_KEY_ID")
B2_APP_KEY = os.environ.get("B2_APP_KEY")
B2_BUCKET_NAME = os.environ.get("B2_BUCKET_NAME")
B2_ENDPOINT = os.environ.get("B2_ENDPOINT", "https://s3.us-west-004.backblazeb2.com")

# === B2 CLIENT ===
s3_client = None
try:
    if B2_KEY_ID and B2_APP_KEY:
        s3_client = boto3.client(
            's3', endpoint_url=B2_ENDPOINT,
            aws_access_key_id=B2_KEY_ID, aws_secret_access_key=B2_APP_KEY,
            config=Config(signature_version='s3v4')
        )
        print("✅ B2 Client Connected")
except Exception as e:
    print(f"⚠️ B2 Error: {e}")

# === БАЗА ДАНИХ (Адаптивна) ===

def get_db_connection():
    """Підключення до БД (Postgres на Railway або SQLite локально)"""
    database_url = os.environ.get('DATABASE_URL')
    if database_url:
        try:
            import psycopg2
            from urllib.parse import urlparse
            r = urlparse(database_url)
            return psycopg2.connect(
                database=r.path[1:], user=r.username, password=r.password,
                host=r.hostname, port=r.port
            )
        except ImportError: pass
    return sqlite3.connect('licenses.db')

def execute_query(query, params=(), fetch_one=False, fetch_all=False, commit=False):
    """
    Головна функція-фіксер:
    Якщо це Postgres, вона сама замінить '?' на '%s'.
    Це виправить помилку 'Error creating license'.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Перевірка типу бази
    is_pg = 'psycopg2' in str(type(cursor)) or 'psycopg2' in str(type(conn))
    
    if is_pg:
        query = query.replace('?', '%s')
    
    try:
        cursor.execute(query, params)
        
        result = None
        if fetch_one: result = cursor.fetchone()
        elif fetch_all: result = cursor.fetchall()
            
        if commit: conn.commit()
        return result
    except Exception as e:
        print(f"🔥 SQL Error: {e}")
        if commit: conn.rollback()
        raise e
    finally:
        conn.close()

def init_database():
    """Створення таблиць (якщо їх ще немає)"""
    conn = get_db_connection()
    cursor = conn.cursor()
    is_pg = 'psycopg2' in str(type(cursor)) or 'psycopg2' in str(type(conn))
    
    try:
        if is_pg:
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
        else:
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
    except Exception as e:
        print(f"⚠️ Init DB: {e}")
    finally:
        conn.close()

# === ROUTES (АДМІНКА) ===

@app.route('/')
def home():
    return jsonify({"message": "Server Running", "status": "ok"})

@app.route('/admin')
def admin_panel():
    return render_template('admin.html')

@app.route('/admin/login', methods=['POST'])
def admin_login():
    data = request.json
    # Якщо пароль не заданий в змінних, пускаємо зі старим (fallback для тестів)
    server_pass = ADMIN_PASSWORD if ADMIN_PASSWORD else "Karnaval3e"
    
    if data.get('password') == server_pass:
        session['admin_logged_in'] = True
        return jsonify({"success": True})
    return jsonify({"success": False, "message": "Невірний пароль"}), 401

@app.route('/admin/logout', methods=['POST'])
def admin_logout():
    session.pop('admin_logged_in', None)
    return jsonify({"success": True})

@app.route('/admin/check_auth', methods=['GET'])
def check_auth_status():
    return jsonify({"authenticated": session.get('admin_logged_in') == True})

@app.route('/admin/licenses', methods=['GET'])
def get_all_licenses():
    if not session.get('admin_logged_in'): return jsonify({"error": "Auth failed"}), 401
    try:
        rows = execute_query('SELECT * FROM licenses ORDER BY created_at DESC', fetch_all=True)
        result = []
        for r in rows:
            result.append({
                'id': r[0], 'license_key': r[1], 'hwid': r[2], 'days': r[3],
                'activated_at': r[4], 'expires_at': r[5], 'status': r[6],
                'last_check': r[7], 'created_at': r[8]
            })
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/admin/create_license', methods=['POST'])
def create_license():
    if not session.get('admin_logged_in'): return jsonify({"error": "Auth failed"}), 401
    data = request.json
    days = data.get('days', 30)
    key = f"TIR-{uuid.uuid4().hex[:8].upper()}-{uuid.uuid4().hex[:8].upper()}"
    
    try:
        execute_query(
            'INSERT INTO licenses (license_key, days, status) VALUES (?, ?, ?)',
            (key, days, 'active'), commit=True
        )
        return jsonify({"success": True, "license_key": key, "days": days})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

@app.route('/admin/delete_license/<int:id>', methods=['DELETE'])
def delete_license(id):
    if not session.get('admin_logged_in'): return jsonify({"error": "Auth failed"}), 401
    execute_query('DELETE FROM licenses WHERE id = ?', (id,), commit=True)
    return jsonify({"success": True})

@app.route('/admin/stats', methods=['GET'])
def get_stats():
    if not session.get('admin_logged_in'): return jsonify({"error": "Auth failed"}), 401
    try:
        total = execute_query('SELECT COUNT(*) FROM licenses', fetch_one=True)[0]
        active = execute_query("SELECT COUNT(*) FROM licenses WHERE status = 'active'", fetch_one=True)[0]
        activated = execute_query('SELECT COUNT(*) FROM licenses WHERE hwid IS NOT NULL', fetch_one=True)[0]
        return jsonify({"total_licenses": total, "active_licenses": active, "activated_licenses": activated})
    except:
        return jsonify({"total_licenses": 0, "active_licenses": 0, "activated_licenses": 0})

# === CLIENT API (LAUNCHER) ===

@app.route('/get_download_link', methods=['POST'])
def get_download_link():
    data = request.json
    key, hwid = data.get('license_key'), data.get('hwid')
    
    row = execute_query('SELECT hwid, status, expires_at FROM licenses WHERE license_key = ?', (key,), fetch_one=True)
    if not row: return jsonify({"message": "Ліцензія не знайдена"}), 403
    
    stored_hwid, status, expires_at = row
    
    if status != 'active': return jsonify({"message": "Ліцензія неактивна"}), 403
    if stored_hwid != hwid: return jsonify({"message": "HWID не співпадає"}), 403
    
    if expires_at and datetime.now() > (expires_at if isinstance(expires_at, datetime) else datetime.fromisoformat(str(expires_at))):
        return jsonify({"message": "Термін дії вийшов"}), 403

    if not s3_client: return jsonify({"message": "Server S3 config error"}), 500
    
    try:
        # Генеруємо посилання на завантаження
        url = s3_client.generate_presigned_url(
            ClientMethod='get_object',
            Params={'Bucket': B2_BUCKET_NAME, 'Key': 'TIR_Bot_Full.zip'},
            ExpiresIn=300
        )
        return jsonify({"download_url": url})
    except Exception as e:
        return jsonify({"message": f"B2 Error: {e}"}), 500

@app.route('/check_license', methods=['POST'])
def check_license():
    data = request.json
    key, hwid = data.get('license_key'), data.get('hwid')
    
    row = execute_query('SELECT id, hwid, days, expires_at, status FROM licenses WHERE license_key = ?', (key,), fetch_one=True)
    if not row: return jsonify({"valid": False, "message": "Не знайдено"})
    
    lid, stored_hwid, days, expires_at, status = row
    
    if status != 'active': return jsonify({"valid": False, "message": "Неактивна"})
    if stored_hwid and stored_hwid != hwid: return jsonify({"valid": False, "message": "Інший HWID"})
    
    is_expired = False
    if expires_at:
        exp_dt = expires_at if isinstance(expires_at, datetime) else datetime.fromisoformat(str(expires_at))
        if datetime.now() > exp_dt: is_expired = True

    if is_expired:
        execute_query("UPDATE licenses SET status = 'expired' WHERE id = ?", (lid,), commit=True)
        return jsonify({"valid": False, "message": "Протермінована"})
    
    execute_query("UPDATE licenses SET last_check = ? WHERE id = ?", (datetime.now(), lid), commit=True)
    days_left = (exp_dt - datetime.now()).days if expires_at else days
    return jsonify({"valid": True, "message": "Активна", "expires_at": expires_at, "days_left": days_left})

@app.route('/activate', methods=['POST'])
def activate_license():
    data = request.json
    key, hwid = data.get('license_key'), data.get('hwid')
    
    row = execute_query('SELECT id, hwid, days, status, expires_at FROM licenses WHERE license_key = ?', (key,), fetch_one=True)
    if not row: return jsonify({"success": False, "message": "Невірний ключ"})
    
    lid, stored_hwid, days, status, expires_at = row
    
    if status != 'active': return jsonify({"success": False, "message": "Неактивна"})
    if stored_hwid and stored_hwid != hwid: return jsonify({"success": False, "message": "Вже активовано"})
    
    now = datetime.now()
    exp = now + timedelta(days=days)
    
    if not expires_at:
        execute_query(
            "UPDATE licenses SET hwid = ?, activated_at = ?, expires_at = ?, status = 'active' WHERE id = ?",
            (hwid, now, exp, lid), commit=True
        )
    else:
        execute_query("UPDATE licenses SET hwid = ? WHERE id = ?", (hwid, lid), commit=True)
        exp = expires_at
        
    return jsonify({"success": True, "expires_at": exp.isoformat(), "days": days})

def create_app():
    init_database()
    return app

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
