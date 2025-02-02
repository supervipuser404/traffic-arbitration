import os
import shutil
import yaml

CONFIG_TEMPLATE_PATH = os.path.join(os.path.dirname(__file__), '..', '..', 'config.tpl.yml')
CONFIG_PATH = os.path.join(os.path.dirname(__file__), '..', '..', 'config.yml')

def ensure_config_exists():
    """
    Проверяем наличие config.yml, если нет — копируем из шаблона config.tpl.yml.
    """
    if not os.path.exists(CONFIG_PATH):
        print("[INFO] config.yml not found. Creating from template...")
        shutil.copyfile(CONFIG_TEMPLATE_PATH, CONFIG_PATH)

def load_config():
    """
    Загружаем конфиг из config.yml (предварительно убедившись, что он существует).
    """
    ensure_config_exists()
    with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)

if __name__ == "__main__":
    config = load_config()
    print("Config loaded:", config)
