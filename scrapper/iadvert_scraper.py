import time
from typing import List, Dict, Any
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed

from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium import webdriver
from webdriver_manager.chrome import ChromeDriverManager

from scrapper.base_scraper import BaseScraperHandler
from scrapper.runner import CATEGORIES

logger = logging.getLogger(__name__)


class IAdvertScraper(BaseScraperHandler):
    """
    Пример конкретного скрапера для source_handler='iadvert'.
    Параллелим категории в scrape_all_categories.
    """

    def _setup_driver(self) -> webdriver.Chrome:
        chrome_options = Options()
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")

        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=chrome_options)
        return driver

    def scrape_category_previews(self, category_slug: str) -> List[Dict[str, Any]]:
        domain = self.source_info.get("domain", "")
        if not domain.endswith("/"):
            domain += "/"

        url = f"https://{domain}{category_slug}"
        logger.info(f"[iadvert:{self.source_info['name']}] Парсинг категории {category_slug} => {url}")

        driver = self._setup_driver()
        driver.get(url)
        # Прокрутка
        for i in range(10):
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(1)
            logger.debug(f"[iadvert:{category_slug}] Прокрутка {i + 1}/10")
        time.sleep(2)

        elements = driver.find_elements(By.CLASS_NAME, "item-container")
        logger.debug(f"[iadvert:{category_slug}] Найдено элементов: {len(elements)}")

        unique_map = {}
        slugs = {v: k for k, v in CATEGORIES}
        for el in elements:
            try:
                link = el.get_attribute("href") + "full/"
                img_link = el.find_element(By.XPATH, ".//img").get_attribute("src")
                cat_txt = el.find_element(By.XPATH, ".//div[@class='item-category']").text.strip()
                title = el.find_element(By.XPATH, ".//span[@class='item-link']").text

                key = (link, img_link, title)
                if key not in unique_map:
                    unique_map[key] = set()
                unique_map[key].add(slugs.get(cat_txt, "other"))
            except Exception as ex:
                logger.debug(f"Ошибка в элементе: {ex}", exc_info=True)

        driver.quit()

        # Превращаем в список
        results = []
        for (lk, im, ttl), cat_set in unique_map.items():
            merged_cats = ";".join(sorted(cat_set))
            results.append({
                "link": lk,
                "image_link": im,
                "category_text": merged_cats,
                "title": ttl,
            })
        logger.info(f"[iadvert:{category_slug}] Уникальных превью: {len(results)}")
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
        logger.info(f"[iadvert:{self.source_info['name']}] Всего итоговых превью: {len(final_results)}")
        return final_results
