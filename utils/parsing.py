from bs4 import BeautifulSoup
import re


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
