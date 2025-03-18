CREATE TABLE IF NOT EXISTS content_sources
(
    id             SERIAL PRIMARY KEY,
    name           TEXT UNIQUE NOT NULL,
    source_handler TEXT,
    domain         TEXT,
    aliases        TEXT,
    old_domains    TEXT,
    categories     TEXT,
    locale         TEXT      DEFAULT 'RU',
    geo            TEXT      DEFAULT 'RU',
    description    TEXT,
    created_at     TIMESTAMP DEFAULT NOW(),
    updated_at     TIMESTAMP DEFAULT NOW(),
    is_active      BOOLEAN   DEFAULT TRUE
);

CREATE TABLE IF NOT EXISTS external_articles_links
(
    id           SERIAL PRIMARY KEY,
    source_id    INTEGER NOT NULL,
    link         TEXT    NOT NULL,
    categories   TEXT,
    created_at   TIMESTAMP DEFAULT NOW(),
    updated_at   TIMESTAMP DEFAULT NOW(),
    is_processed BOOLEAN   DEFAULT FALSE,
    UNIQUE (source_id, link)
);

CREATE TABLE IF NOT EXISTS external_articles_previews
(
    id           SERIAL PRIMARY KEY,
    link_id      INTEGER NOT NULL,
    title        TEXT,
    text         TEXT,
    image_link   TEXT,
    created_at   TIMESTAMP DEFAULT NOW(),
    updated_at   TIMESTAMP DEFAULT NOW(),
    is_processed BOOLEAN   DEFAULT FALSE
);

CREATE TABLE IF NOT EXISTS external_articles
(
    id           SERIAL PRIMARY KEY,
    link_id      INTEGER NOT NULL,
    title        TEXT,
    text         TEXT,
    sources      TEXT,
    created_at   TIMESTAMP DEFAULT NOW(),
    updated_at   TIMESTAMP DEFAULT NOW(),
    is_processed BOOLEAN   DEFAULT FALSE
);

CREATE TABLE IF NOT EXISTS visual_content
(
    id         SERIAL PRIMARY KEY,
    link       TEXT,
    data       BYTEA,
    name       TEXT,
    extension  TEXT,
    width      INTEGER,
    height     INTEGER,
    categories TEXT,
    tags       TEXT,
    parent     INTEGER,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS articles_previews
(
    id         SERIAL PRIMARY KEY,
    article_id INTEGER NOT NULL,
    title      TEXT,
    text       TEXT,
    image      TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS articles
(
    id              SERIAL PRIMARY KEY,
    title           TEXT,
    text            TEXT,
    sources         TEXT,
    categories      TEXT,
    tags            TEXT,
    parent          INTEGER,
    locale          TEXT      DEFAULT 'RU',
    geo             TEXT      DEFAULT 'RU',
    created_at      TIMESTAMP DEFAULT NOW(),
    updated_at      TIMESTAMP DEFAULT NOW(),
    source_datetime TIMESTAMP
);

CREATE TABLE IF NOT EXISTS categories
(
    id          SERIAL PRIMARY KEY,
    name        TEXT NOT NULL UNIQUE,
    description TEXT
);

CREATE TABLE IF NOT EXISTS categories_labels
(
    id          SERIAL PRIMARY KEY,
    category_id INTEGER NOT NULL,
    locale      TEXT DEFAULT 'RU',
    clause      TEXT
);

ALTER TABLE external_articles_previews
ADD CONSTRAINT external_articles_previews_unique_key
UNIQUE (link_id, title, image_link);

ALTER TABLE visual_content
ADD CONSTRAINT visual_content_link_key
UNIQUE (link);