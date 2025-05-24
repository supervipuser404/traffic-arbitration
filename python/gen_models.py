from traffic_arbirtation.common.config import config
import subprocess
import os
from pathlib import Path

from traffic_arbirtation.common.config import config

DB = config['database']
HOME = Path(__file__).parent
PY_MODELS_DIR = HOME / "python" / "traffic_arbitration" / "models"
GO_MODELS_DIR = HOME / "go" / "pkg" / "models_autogen"


def make_pg_url():
    return f"postgresql://{DB['user']}:{DB['password']}@{DB['host']}:{DB['port']}/{DB['dbname']}"


def gen_python_models():
    os.makedirs(PY_MODELS_DIR, exist_ok=True)
    pg_url = make_pg_url()
    output_file = os.path.join(PY_MODELS_DIR, "autogen_models.py")
    cmd = [
        "poetry", "run", "sqlacodegen",
        "--noindexes",
        "--noconstraints",
        "--noviews",
        pg_url
    ]
    print(f"=== Генерируем Python-модели в {output_file} ===")
    with open(output_file, "w", encoding="utf-8") as f:
        subprocess.run(cmd, stdout=f, check=True)


def gen_go_models():
    os.makedirs(GO_MODELS_DIR, exist_ok=True)
    # Ожидается, что sqlboiler настроен через sqlboiler.toml в go/pkg/models_autogen
    # Можно запускать из go/pkg, или через absolute path
    print(f"=== Генерируем Go-модели через sqlboiler ===")
    subprocess.run([
        "sqlboiler", "psql", "--no-tests", "--output", GO_MODELS_DIR
    ], check=True, cwd=os.path.join("go", "pkg"))  # Важно запускать из папки с конфигом!


if __name__ == "__main__":
    print("\nШАГ 1: Alembic upgrade head")
    subprocess.run([
        "poetry", "run", "alembic", "upgrade", "head"
    ], check=True, cwd="python")

    print("\nШАГ 2: Генерируем Python-модели")
    gen_python_models()

    print("\nШАГ 3: Генерируем Go-модели")
    gen_go_models()
