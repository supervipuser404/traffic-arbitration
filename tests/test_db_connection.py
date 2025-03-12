import pytest
from db.connection import get_connection


@pytest.mark.parametrize("test_query", ["SELECT 1;", "SELECT version();"])
def test_get_connection(test_query):
    """
    Проверяем, что get_connection() возвращает рабочее соединение,
    и мы можем выполнить простой запрос в БД.
    """
    conn = None
    try:
        conn = get_connection()
        assert conn is not None, "get_connection() вернул None"

        # Проверяем, что соединение работает
        with conn.cursor() as cur:
            cur.execute(test_query)
            result = cur.fetchone()
            assert result is not None, f"Запрос {test_query} не вернул результат"
    finally:
        if conn:
            conn.close()
