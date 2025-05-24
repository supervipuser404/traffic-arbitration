import os
import yaml


def find_config_file(filename="config.yml"):
    # Если указана переменная окружения CONFIG_PATH — используем её
    config_path = os.environ.get("CONFIG_PATH")
    if config_path and os.path.isfile(config_path):
        return config_path

    # Если не указана — ищем config.yml вверх по дереву от cwd
    cur_dir = os.getcwd()
    while True:
        candidate = os.path.join(cur_dir, filename)
        if os.path.isfile(candidate):
            return candidate
        parent = os.path.dirname(cur_dir)
        if parent == cur_dir:
            break
        cur_dir = parent
    raise FileNotFoundError(
        f"Config file not found. Please specify CONFIG_PATH or place config.yml above {os.getcwd()}"
    )


def load_config():
    # Загружает YAML-конфиг в виде dict
    config_file = find_config_file()
    with open(config_file, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)
