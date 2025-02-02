import psycopg2
import psycopg2.extras
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

CREATE TABLE IF NOT EXISTS external_articles_links (
    id SERIAL PRIMARY KEY,
    source_id INTEGER NOT NULL,
    link TEXT NOT NULL,
    categories TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    is_processed BOOLEAN DEFAULT FALSE,
    UNIQUE (source_id, link)
);

CREATE TABLE IF NOT EXISTS external_articles_previews (
    id SERIAL PRIMARY KEY,
    link_id INTEGER NOT NULL,
    title TEXT,
    text TEXT,
    image_link TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    is_processed BOOLEAN DEFAULT FALSE
);

CREATE TABLE IF NOT EXISTS external_articles (
    id SERIAL PRIMARY KEY,
    link_id INTEGER NOT NULL,
    title TEXT,
    text TEXT,
    sources TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    is_processed BOOLEAN DEFAULT FALSE
);

CREATE TABLE IF NOT EXISTS visual_content (
    id SERIAL PRIMARY KEY,
    link TEXT,
    data BYTEA,
    name TEXT,
    extension TEXT,
    width INTEGER,
    height INTEGER,
    categories TEXT,
    tags TEXT,
    parent INTEGER,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS articles_previews (
    id SERIAL PRIMARY KEY,
    article_id INTEGER NOT NULL,
    title TEXT,
    text TEXT,
    image TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS articles (
    id SERIAL PRIMARY KEY,
    title TEXT,
    text TEXT,
    sources TEXT,
    categories TEXT,
    tags TEXT,
    parent INTEGER,
    locale TEXT DEFAULT 'RU',
    geo TEXT DEFAULT 'RU',
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    source_datetime TIMESTAMP
);

CREATE TABLE IF NOT EXISTS categories (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    description TEXT
);

CREATE TABLE IF NOT EXISTS categories_labels (
    id SERIAL PRIMARY KEY,
    category_id INTEGER NOT NULL,
    locale TEXT DEFAULT 'RU',
    clause TEXT
);
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
