import pathlib

import yaml
import logging
import os
from pathlib import Path

# Имена файлов конфигурации
CONFIG_FILE = Path(__file__).parent.parent / "config.yml"
CONFIG_TPL_FILE = Path(__file__).parent.parent / "config.tpl.yml"

# Глобальный словарь с настройками
config = {}

# Инициализация логгера
logger = logging.getLogger()
logging.basicConfig(format='%(asctime)s %(process)d: %(levelname)s: %(message)s',
                    datefmt='[%Y-%m-%d %H:%M:%S]')


def ensure_config_exists():
    """
    Проверяем наличие config.yml, если нет — копируем из шаблона config.tpl.yml.
    """
    if not os.path.exists(CONFIG_FILE):
        import shutil
        print("[INFO] config.yml not found. Creating from template...")
        shutil.copyfile(CONFIG_TPL_FILE, CONFIG_FILE)


def load_config():
    """
    Заполняет глобальную переменную settings.
    """
    global config

    ensure_config_exists()

    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        file_settings = yaml.safe_load(f) or {}
        config.update(file_settings)

    logger.setLevel(config['log']['level'])


# При импорте модуля — сразу загружаем
load_config()
