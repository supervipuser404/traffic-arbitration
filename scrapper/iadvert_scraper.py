import re
import time
from typing import List, Dict, Any
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed

from bs4 import BeautifulSoup
from selenium.webdriver.common.by import By

from scrapper.base_scraper import BaseScraperHandler
from scrapper.commons import CATEGORIES

logger = logging.getLogger(__name__)


class IAdvertScraper(BaseScraperHandler):
    """
    Пример конкретного скрапера для source_handler='iadvert'.
    Параллелим категории в scrape_all_categories.
    """

    def scrape_category_previews(self, category_slug: str) -> List[Dict[str, Any]]:
        domain = self.source_info.get("domain", "")
        if not domain.endswith("/"):
            domain += "/"

        url = f"https://{domain}{category_slug}"
        logger.info(f"[iadvert:{self.source_info['name']}] Парсинг категории {category_slug} => {url}")

        driver = self.driver_pool.get_driver()
        driver.get(url)
        unique_map = {}
        try:
            # Прокрутка
            for i in range(10):
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(1)
                logger.debug(f"[iadvert:{category_slug}] Прокрутка {i + 1}/10")
            time.sleep(5)

            elements = driver.find_elements(By.CLASS_NAME, "item-container")
            logger.debug(f"[iadvert:{category_slug}] Найдено элементов: {len(elements)}")

            slugs = {v: k for k, v in CATEGORIES.items()}
            for el in elements:
                link = el.get_attribute("href")
                # Имя категории неважно для показа страницы, но оно нужно.
                # Поэтому, для унификации, все названия категорий заменяем на 'general'
                link = link.split('/')
                # название категории
                link[3] = 'general'
                link = '/'.join(link) + "full/"
                img_link = el.find_element(By.XPATH, ".//img").get_attribute("src")
                cat_txt = el.find_element(By.XPATH, ".//div[@class='item-category']").text.strip()
                title = el.find_element(By.XPATH, ".//span[@class='item-link']").text

                key = (link, img_link, title)
                if key not in unique_map:
                    unique_map[key] = set()
                unique_map[key].add(slugs.get(cat_txt, "other"))
        except Exception as ex:
            logger.debug(f"Ошибка: {ex}", exc_info=True)
        finally:
            self.driver_pool.release_driver(driver)

        # Превращаем в список
        results = []
        categories = set()
        for (lk, im, ttl), cat_set in unique_map.items():
            categories.update(cat_set)
            merged_cats = ";".join(sorted(cat_set))
            results.append({
                "link": lk,
                "image_link": im,
                "category_text": merged_cats,
                "title": ttl,
            })
        logger.info(f"[iadvert:{category_slug}] Уникальных превью: {len(results)}")
        logger.info(f"[iadvert:{category_slug}] Категории: {sorted(categories)}")
        return results

    def scrape_all_categories(self, categories: List[str]) -> List[Dict[str, Any]]:
        """
        Переопределение: обрабатываем категории в пуле потоков -> каждый поток создаёт свой драйвер
        """
        logger.info(f"[iadvert:{self.source_info['name']}] Параллельный парсинг {len(categories)} категорий")
        all_data = []

        # Можно задать количество воркеров из config или настроек
        from config import config
        max_workers = config.get("parallel_categories_workers", 5)

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            fut_map = {}
            for cat in categories:
                f = executor.submit(self.scrape_category_previews, cat)
                fut_map[f] = cat

            # Собираем
            for f in as_completed(fut_map):
                cat_slug = fut_map[f]
                try:
                    data = f.result()
                    all_data.extend(data)
                except Exception as e:
                    logger.error(f"[iadvert:{cat_slug}] Ошибка в парсинге: {e}", exc_info=True)

        # Доп. шаг: объединить по ключу (link, image_link, title) (вдруг пересечения?)
        final_map = {}
        for item in all_data:
            key = (item["link"], item["image_link"], item["title"])
            cat_list = item["category_text"].split(";") if item["category_text"] else []
            if key not in final_map:
                final_map[key] = set()
            final_map[key].update(cat_list)

        final_results = []
        for (lk, im, ttl), catset in final_map.items():
            final_results.append({
                "link": lk,
                "image_link": im,
                "title": ttl,
                "category_text": ";".join(sorted(catset))
            })
        logger.info(f"[iadvert:{self.source_info['name']}] Всего обработано превью: {len(all_data)}")
        logger.info(f"[iadvert:{self.source_info['name']}] Всего итоговых превью: {len(final_results)}")
        return final_results

    def scrape_article(self, link: str) -> dict | None:
        """
        Обрабатывает одну статью и возвращает словарь с результатами:
        {link, title, text, sources}
        """
        driver = self.driver_pool.get_driver()
        try:
            driver.get(link)
            title = driver.find_element(By.CLASS_NAME, "item-title").text
            text = driver.find_element(By.CLASS_NAME, "item-body").text
            text = self.clean_html(text)
            return {
                "link": link,
                "title": title,
                "text": text,
                "sources": None
            }
        except Exception as e:
            logging.error(f"❌ Ошибка при обработке статьи {link}: {e}")
        finally:
            self.driver_pool.release_driver(driver)

    @staticmethod
    def clean_html(text):
        # Парсим HTML
        soup = BeautifulSoup(text, "html.parser")

        # Удаляем все <div> и их содержимое
        for div in soup.find_all("div"):
            div.decompose()

        # Преобразуем HTML обратно в строку
        cleaned_text = str(soup)

        # Удаляем лишние пробельные символы вокруг тегов <br> и <br/>
        cleaned_text = re.sub(r'\s*<br\s*/?>\s*', '<br>', cleaned_text, flags=re.MULTILINE)

        # Удаляем повторяющиеся <br>
        cleaned_text = re.sub(r'(<br>\s*)+', '<br>', cleaned_text, flags=re.MULTILINE)

        # Удаляем пробелы в начале и конце строки
        cleaned_text = cleaned_text.strip()

        return cleaned_text
