import sqlite3
import os

def init_database():
    """Ініціалізація бази даних для хмарного хостингу"""
    conn = sqlite3.connect('licenses.db')
    cursor = conn.cursor()
    
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
    
    # Додаємо тестову ліцензію
    cursor.execute('''
        INSERT OR IGNORE INTO licenses (license_key, days, status)
        VALUES (?, 30, 'active')
    ''', ('TEST-KEY-12345',))
    
    conn.commit()
    conn.close()
    print("✅ База даних ініціалізована для хмари!")

if __name__ == '__main__':
    init_database()