-- Источники контента
CREATE TABLE IF NOT EXISTS content_sources (
    id             SERIAL PRIMARY KEY,
    name           VARCHAR(256) UNIQUE NOT NULL,
    source_handler VARCHAR(128),
    domain         VARCHAR(256),
    aliases        TEXT,
    old_domains    TEXT,
    description    TEXT,
    created_at     TIMESTAMP DEFAULT NOW(),
    updated_at     TIMESTAMP DEFAULT NOW(),
    is_active      BOOLEAN   DEFAULT TRUE
);

CREATE TABLE IF NOT EXISTS external_articles_links (
    id           SERIAL PRIMARY KEY,
    source_id    INTEGER NOT NULL REFERENCES content_sources(id) ON DELETE CASCADE,
    link         TEXT    NOT NULL,
    created_at   TIMESTAMP DEFAULT NOW(),
    updated_at   TIMESTAMP DEFAULT NOW(),
    is_processed BOOLEAN   DEFAULT FALSE,
    UNIQUE (source_id, link)
);

CREATE TABLE IF NOT EXISTS external_articles_previews (
    id           SERIAL PRIMARY KEY,
    link_id      INTEGER NOT NULL REFERENCES external_articles_links(id) ON DELETE CASCADE,
    title        VARCHAR(512),
    text         TEXT,
    image_link   TEXT,
    created_at   TIMESTAMP DEFAULT NOW(),
    updated_at   TIMESTAMP DEFAULT NOW(),
    is_processed BOOLEAN   DEFAULT FALSE,
    UNIQUE (link_id, title, image_link)
);

CREATE TABLE IF NOT EXISTS external_articles (
    id           SERIAL PRIMARY KEY,
    link_id      INTEGER NOT NULL REFERENCES external_articles_links(id) ON DELETE CASCADE,
    title        VARCHAR(512),
    text         TEXT,
    created_at   TIMESTAMP DEFAULT NOW(),
    updated_at   TIMESTAMP DEFAULT NOW(),
    is_processed BOOLEAN   DEFAULT FALSE,
    UNIQUE (link_id)
);

CREATE TABLE IF NOT EXISTS visual_content (
    id         SERIAL PRIMARY KEY,
    link       TEXT,
    data       BYTEA,
    name       VARCHAR(128),
    extension  VARCHAR(16),
    width      INTEGER,
    height     INTEGER,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Основные статьи
CREATE TABLE IF NOT EXISTS articles (
    id              SERIAL PRIMARY KEY,
    title           VARCHAR(512),
    text            TEXT,
    parent          INTEGER,
    locale          VARCHAR(8) DEFAULT 'ru',
    created_at      TIMESTAMP DEFAULT NOW(),
    updated_at      TIMESTAMP DEFAULT NOW(),
    source_datetime TIMESTAMP
);

CREATE TABLE IF NOT EXISTS articles_previews (
    id         SERIAL PRIMARY KEY,
    article_id INTEGER NOT NULL REFERENCES articles(id) ON DELETE CASCADE,
    title      VARCHAR(512),
    text       TEXT,
    image      TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS categories (
    id          SERIAL PRIMARY KEY,
    code        VARCHAR(64) NOT NULL UNIQUE,
    description TEXT
);

CREATE TABLE IF NOT EXISTS category_labels (
    id          SERIAL PRIMARY KEY,
    category_id INTEGER NOT NULL REFERENCES categories(id) ON DELETE CASCADE,
    locale      VARCHAR(8) DEFAULT 'ru',
    label       VARCHAR(128) NOT NULL
);

CREATE TABLE IF NOT EXISTS geo (
    id          SERIAL PRIMARY KEY,
    code        VARCHAR(8) NOT NULL UNIQUE,
    description TEXT
);

CREATE TABLE IF NOT EXISTS geo_labels (
    id      SERIAL PRIMARY KEY,
    geo_id  INTEGER NOT NULL REFERENCES geo(id) ON DELETE CASCADE,
    locale  VARCHAR(8) DEFAULT 'ru',
    label   VARCHAR(128) NOT NULL
);

CREATE TABLE IF NOT EXISTS tags (
    id   SERIAL PRIMARY KEY,
    code VARCHAR(64) NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS article_categories (
    article_id   INTEGER NOT NULL REFERENCES articles(id) ON DELETE CASCADE,
    category_id  INTEGER NOT NULL REFERENCES categories(id) ON DELETE CASCADE,
    PRIMARY KEY (article_id, category_id)
);

CREATE TABLE IF NOT EXISTS article_geo (
    article_id INTEGER NOT NULL REFERENCES articles(id) ON DELETE CASCADE,
    geo_id     INTEGER NOT NULL REFERENCES geo(id) ON DELETE CASCADE,
    PRIMARY KEY (article_id, geo_id)
);

CREATE TABLE IF NOT EXISTS article_tags (
    article_id INTEGER NOT NULL REFERENCES articles(id) ON DELETE CASCADE,
    tag_id     INTEGER NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
    PRIMARY KEY (article_id, tag_id)
);

-- Связи для external_articles_links <-> categories
CREATE TABLE IF NOT EXISTS external_article_link_categories (
    link_id     INTEGER NOT NULL REFERENCES external_articles_links(id) ON DELETE CASCADE,
    category_id INTEGER NOT NULL REFERENCES categories(id) ON DELETE CASCADE,
    PRIMARY KEY (link_id, category_id)
);

-- Для visual_content связи
CREATE TABLE IF NOT EXISTS visual_content_categories (
    visual_content_id INTEGER NOT NULL REFERENCES visual_content(id) ON DELETE CASCADE,
    category_id       INTEGER NOT NULL REFERENCES categories(id) ON DELETE CASCADE,
    PRIMARY KEY (visual_content_id, category_id)
);

CREATE TABLE IF NOT EXISTS visual_content_tags (
    visual_content_id INTEGER NOT NULL REFERENCES visual_content(id) ON DELETE CASCADE,
    tag_id            INTEGER NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
    PRIMARY KEY (visual_content_id, tag_id)
);

-- Индексы для быстрого поиска (по нужным связям)
CREATE INDEX IF NOT EXISTS idx_article_categories_article_id ON article_categories(article_id);
CREATE INDEX IF NOT EXISTS idx_article_categories_category_id ON article_categories(category_id);
CREATE INDEX IF NOT EXISTS idx_article_geo_article_id ON article_geo(article_id);
CREATE INDEX IF NOT EXISTS idx_article_geo_geo_id ON article_geo(geo_id);
CREATE INDEX IF NOT EXISTS idx_article_tags_article_id ON article_tags(article_id);
CREATE INDEX IF NOT EXISTS idx_article_tags_tag_id ON article_tags(tag_id);
CREATE INDEX IF NOT EXISTS idx_external_article_link_categories_link_id ON external_article_link_categories(link_id);
CREATE INDEX IF NOT EXISTS idx_visual_content_categories_visual_content_id ON visual_content_categories(visual_content_id);
CREATE INDEX IF NOT EXISTS idx_visual_content_tags_visual_content_id ON visual_content_tags(visual_content_id);
