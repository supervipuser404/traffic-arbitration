# tests/test_scraper.py
import pytest
import requests

from scrapper.scraper_factory import ScraperHandlerFactory
from db.connection import get_connection
from db.queries import get_active_content_sources
from scrapper.commons import CATEGORIES

# Количество тестируемых источников
MAX_SOURCES = 3  # Можно увеличить, если нужно больше тестов


# Фикстура для загрузки списка активных источников
@pytest.fixture(scope="module")
def active_sources():
    """ Получаем список активных источников из базы """
    with get_connection() as conn:
        sources = get_active_content_sources(conn)
    return sources[:MAX_SOURCES]  # Ограничиваем количество источников


@pytest.fixture(scope="function")
def scraper(active_sources):
    """ Фикстура, создающая скраппер для каждого источника """
    source = active_sources[0]  # Берём первый источник
    return ScraperHandlerFactory.create(source), source


def test_scrape_one_category(scraper):
    """ Проверяем, что скраппер может загрузить хотя бы одну категорию """
    scraper_instance, source = scraper

    # Если categories пустой или None, используем дефолтный список
    categories = source.get("categories")
    if not categories:
        categories = list(CATEGORIES.keys())  # Берём ключи из словаря CATEGORIES
    else:
        categories = categories.split(";")

    category = categories[0]  # Берём первую категорию
    results = scraper_instance.scrape_category_previews(category)

    assert isinstance(results, list), "scrape_category_previews не вернул список!"
    assert len(results) > 0, f"Категория {category} пуста для {source['name']}!"

    print(f"Источник {source['name']}, категория {category}: найдено {len(results)} превью.")


def test_scrape_one_preview(scraper):
    """ Проверяем, что хотя бы одно превью содержит валидные данные """
    scraper_instance, source = scraper

    categories = source.get("categories")
    if not categories:
        categories = list(CATEGORIES.keys())  # Дефолтные категории
    else:
        categories = categories.split(";")

    category = categories[0]
    results = scraper_instance.scrape_category_previews(category)

    assert len(results) > 0, f"Нет превью в категории {category} для {source['name']}!"

    preview = results[0]  # Берём одно превью

    assert "link" in preview and preview["link"], "Нет ссылки на статью!"
    assert "image_link" in preview and preview["image_link"], "Нет ссылки на изображение!"
    assert "title" in preview and preview["title"], "Нет заголовка статьи!"

    print(f"Проверено превью: {preview}")


@pytest.mark.parametrize("key", ["link", "image_link"])
def test_check_links(scraper, key):
    """ Проверяем, что ссылки рабочие (возвращают 200) """
    scraper_instance, source = scraper

    categories = source.get("categories")
    if not categories:
        categories = list(CATEGORIES.keys())  # Дефолтные категории
    else:
        categories = categories.split(";")

    category = categories[0]
    results = scraper_instance.scrape_category_previews(category)

    assert len(results) > 0, f"Нет превью в категории {category} для {source['name']}!"

    url = results[0][key]
    assert url.startswith("http"), f"Некорректная ссылка {url}!"

    try:
        response = requests.head(url, allow_redirects=True, timeout=5)
        assert response.status_code == 200, f"Ссылка {url} недоступна!"
    except requests.RequestException as e:
        pytest.fail(f"Ошибка при проверке {key}: {e}")
