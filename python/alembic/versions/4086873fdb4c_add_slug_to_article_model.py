"""Add slug to Article model

Revision ID: 4086873fdb4c
Revises: d2f5bc19f971
Create Date: 2025-08-15 19:22:45.035921

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.sql import table, column
from slugify import slugify


# revision identifiers, used by Alembic.
revision: str = '4086873fdb4c'
down_revision: Union[str, None] = 'd2f5bc19f971'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('articles', sa.Column('slug', sa.String(length=128), nullable=True, comment="Человекочитаемый идентификатор для URL. Генерируется из транслитерированного заголовка (title). Максимальная длина 128 символов. Правила генерации: 1. Берется 120 символов из транслитерированного заголовка. 2. При нарушении уникальности добавляется числовой суффикс (например, '-2')."))
    
    articles_table = table('articles',
        column('id', sa.Integer),
        column('title', sa.String),
        column('slug', sa.String)
    )
    
    connection = op.get_bind()
    articles = connection.execute(sa.select(articles_table.c.id, articles_table.c.title)).fetchall()
    
    for article_id, title in articles:
        slug = slugify(title, max_length=120)
        
        while True:
            existing_article = connection.execute(
                sa.select(articles_table.c.id).where(articles_table.c.slug == slug)
            ).fetchone()
            
            if not existing_article:
                break
            
            slug = f"{slug}-{article_id}"

        connection.execute(
            articles_table.update().where(articles_table.c.id == article_id).values(slug=slug)
        )

    op.alter_column('articles', 'slug', nullable=False)
    op.create_unique_constraint('uq_articles_slug', 'articles', ['slug'])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint('uq_articles_slug', 'articles', type_='unique')
    op.drop_column('articles', 'slug')
