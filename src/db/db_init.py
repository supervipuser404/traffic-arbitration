import psycopg2
import sys
import os

# Импортируем модуль config
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
from utils.config import load_config

TABLES_SQL = """ 
CREATE TABLE IF NOT EXISTS content_sources (
    id SERIAL PRIMARY KEY,
    name TEXT UNIQUE NOT NULL,
    source_handler TEXT,
    domain TEXT,
    aliases TEXT,
    old_domains TEXT,
    categories TEXT,
    locale TEXT DEFAULT 'RU',
    geo TEXT DEFAULT 'RU',
    description TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    is_active BOOLEAN DEFAULT TRUE
);

-- Добавьте другие CREATE TABLE запросы здесь
"""

def create_tables():
    config = load_config()
    db_conf = config['database']
    
    conn = None
    try:
        conn = psycopg2.connect(
            host=db_conf['host'],
            port=db_conf['port'],
            user=db_conf['user'],
            password=db_conf['password'],
            dbname=db_conf['db_name']
        )
        with conn.cursor() as cur:
            cur.execute(TABLES_SQL)
            conn.commit()
        print("[INFO] Tables created or verified successfully.")
    except Exception as e:
        print("[ERROR] Unable to create tables:", e)
    finally:
        if conn:
            conn.close()

if __name__ == "__main__":
    create_tables()
