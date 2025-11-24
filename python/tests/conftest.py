import sys
import os

# Получаем путь к корневой папке проекта
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

# Добавляем его в sys.path, если его там нет
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)
