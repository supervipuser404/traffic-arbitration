from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
import queue
import threading
import logging


class DriverPool:
    """ Пул Selenium-драйверов с ленивой инициализацией и контекстным менеджером """

    def __init__(self, max_drivers=5):
        self.max_drivers = max_drivers
        self.pool = queue.Queue()
        self.lock = threading.Lock()
        self._initialized = False

    @staticmethod
    def _create_driver():
        """ Создаёт новый Selenium-драйвер. """
        chrome_options = Options()
        chrome_options.add_argument('--headless')
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')

        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=chrome_options)
        return driver

    def _initialize_pool(self):
        """ Лениво инициализирует пул драйверов. """
        if not self._initialized:
            with self.lock:
                if not self._initialized:
                    logging.info(f"🔄 Инициализация пула Selenium-драйверов ({self.max_drivers} шт.)")
                    for _ in range(self.max_drivers):
                        self.pool.put(self._create_driver())
                    self._initialized = True

    def get_driver(self):
        """ Берёт драйвер из пула (ленивая инициализация). """
        self._initialize_pool()
        with self.lock:
            if self.pool.empty():
                logging.warning("⚠ Пул драйверов пуст, создаётся аварийный экземпляр.")
                return self._create_driver()  # Если пул пуст, создаём новый (аварийный случай)
            return self.pool.get()

    def release_driver(self, driver):
        """ Возвращает драйвер в пул (если есть место). """
        with self.lock:
            if self.pool.qsize() < self.max_drivers:
                self.pool.put(driver)  # Возвращаем в пул
            else:
                driver.quit()  # Закрываем лишний драйвер

    def close_all(self):
        """ Закрывает все драйверы в пуле. """
        while not self.pool.empty():
            driver = self.pool.get()
            driver.quit()
        self._initialized = False
        logging.info("🛑 Все Selenium-драйверы закрыты.")

    def __enter__(self):
        """ Контекстный менеджер для использования пула. """
        self._initialize_pool()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        """ Закрываем пул при выходе из контекста. """
        self.close_all()
