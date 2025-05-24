from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, ForeignKey, LargeBinary
from sqlalchemy.orm import relationship, declarative_base
from sqlalchemy.sql import func

Base = declarative_base()


class ContentSource(Base):
    __tablename__ = "content_sources"
    id = Column(Integer, primary_key=True)
    name = Column(String(256), unique=True, nullable=False)
    source_handler = Column(String(128))
    domain = Column(String(256))
    aliases = Column(Text)
    old_domains = Column(Text)
    description = Column(Text)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now())
    is_active = Column(Boolean, default=True)
    external_articles_links = relationship("ExternalArticleLink", back_populates="content_source")


class ExternalArticleLink(Base):
    __tablename__ = "external_articles_links"
    id = Column(Integer, primary_key=True)
    source_id = Column(Integer, ForeignKey("content_sources.id", ondelete="CASCADE"), nullable=False)
    link = Column(Text, nullable=False)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now())
    is_processed = Column(Boolean, default=False)
    content_source = relationship("ContentSource", back_populates="external_articles_links")
    external_articles = relationship("ExternalArticle", back_populates="link")
    external_article_previews = relationship("ExternalArticlePreview", back_populates="link")
    categories = relationship("Category", secondary="external_article_link_categories")


class ExternalArticlePreview(Base):
    __tablename__ = "external_articles_previews"
    id = Column(Integer, primary_key=True)
    link_id = Column(Integer, ForeignKey("external_articles_links.id", ondelete="CASCADE"), nullable=False)
    title = Column(String(512))
    text = Column(Text)
    image_link = Column(Text)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now())
    is_processed = Column(Boolean, default=False)
    link = relationship("ExternalArticleLink", back_populates="external_article_previews")


class ExternalArticle(Base):
    __tablename__ = "external_articles"
    id = Column(Integer, primary_key=True)
    link_id = Column(Integer, ForeignKey("external_articles_links.id", ondelete="CASCADE"), nullable=False)
    title = Column(String(512))
    text = Column(Text)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now())
    is_processed = Column(Boolean, default=False)
    link = relationship("ExternalArticleLink", back_populates="external_articles")


class VisualContent(Base):
    __tablename__ = "visual_content"
    id = Column(Integer, primary_key=True)
    link = Column(Text)
    data = Column(LargeBinary)
    name = Column(String(128))
    extension = Column(String(16))
    width = Column(Integer)
    height = Column(Integer)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now())
    categories = relationship("Category", secondary="visual_content_categories")
    tags = relationship("Tag", secondary="visual_content_tags")


class Article(Base):
    __tablename__ = "articles"
    id = Column(Integer, primary_key=True)
    title = Column(String(512))
    text = Column(Text)
    parent = Column(Integer)
    locale = Column(String(8), default="ru")
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now())
    source_datetime = Column(DateTime)
    previews = relationship("ArticlePreview", back_populates="article")
    categories = relationship("Category", secondary="article_categories")
    geo = relationship("Geo", secondary="article_geo")
    tags = relationship("Tag", secondary="article_tags")


class ArticlePreview(Base):
    __tablename__ = "articles_previews"
    id = Column(Integer, primary_key=True)
    article_id = Column(Integer, ForeignKey("articles.id", ondelete="CASCADE"), nullable=False)
    title = Column(String(512))
    text = Column(Text)
    image = Column(Text)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now())
    article = relationship("Article", back_populates="previews")


class Category(Base):
    __tablename__ = "categories"
    id = Column(Integer, primary_key=True)
    code = Column(String(64), unique=True, nullable=False)
    description = Column(Text)
    labels = relationship("CategoryLabel", back_populates="category")


class CategoryLabel(Base):
    __tablename__ = "category_labels"
    id = Column(Integer, primary_key=True)
    category_id = Column(Integer, ForeignKey("categories.id", ondelete="CASCADE"), nullable=False)
    locale = Column(String(8), default="ru")
    label = Column(String(128), nullable=False)
    category = relationship("Category", back_populates="labels")


class Geo(Base):
    __tablename__ = "geo"
    id = Column(Integer, primary_key=True)
    code = Column(String(8), unique=True, nullable=False)
    description = Column(Text)
    labels = relationship("GeoLabel", back_populates="geo")


class GeoLabel(Base):
    __tablename__ = "geo_labels"
    id = Column(Integer, primary_key=True)
    geo_id = Column(Integer, ForeignKey("geo.id", ondelete="CASCADE"), nullable=False)
    locale = Column(String(8), default="ru")
    label = Column(String(128), nullable=False)
    geo = relationship("Geo", back_populates="labels")


class Tag(Base):
    __tablename__ = "tags"
    id = Column(Integer, primary_key=True)
    code = Column(String(64), unique=True, nullable=False)


# Many-to-many association tables
class ArticleCategory(Base):
    __tablename__ = "article_categories"
    article_id = Column(Integer, ForeignKey("articles.id", ondelete="CASCADE"), primary_key=True)
    category_id = Column(Integer, ForeignKey("categories.id", ondelete="CASCADE"), primary_key=True)


class ArticleGeo(Base):
    __tablename__ = "article_geo"
    article_id = Column(Integer, ForeignKey("articles.id", ondelete="CASCADE"), primary_key=True)
    geo_id = Column(Integer, ForeignKey("geo.id", ondelete="CASCADE"), primary_key=True)


class ArticleTag(Base):
    __tablename__ = "article_tags"
    article_id = Column(Integer, ForeignKey("articles.id", ondelete="CASCADE"), primary_key=True)
    tag_id = Column(Integer, ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True)


class ExternalArticleLinkCategory(Base):
    __tablename__ = "external_article_link_categories"
    link_id = Column(Integer, ForeignKey("external_articles_links.id", ondelete="CASCADE"), primary_key=True)
    category_id = Column(Integer, ForeignKey("categories.id", ondelete="CASCADE"), primary_key=True)


class VisualContentCategory(Base):
    __tablename__ = "visual_content_categories"
    visual_content_id = Column(Integer, ForeignKey("visual_content.id", ondelete="CASCADE"), primary_key=True)
    category_id = Column(Integer, ForeignKey("categories.id", ondelete="CASCADE"), primary_key=True)


class VisualContentTag(Base):
    __tablename__ = "visual_content_tags"
    visual_content_id = Column(Integer, ForeignKey("visual_content.id", ondelete="CASCADE"), primary_key=True)
    tag_id = Column(Integer, ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True)
