from bs4 import BeautifulSoup
import re


def insert_teasers(html_content: str, teasers_every_n_paragraphs: int = 3) -> str:
    """
    Вставляет рекламные блоки в HTML-контент после каждого N-го абзаца.

    :param html_content: Исходный HTML-контент статьи.
    :param teasers_every_n_paragraphs: Частота вставки тизеров (каждые N абзацев).
    :return: Модифицированный HTML-контент с тизерами.
    """
    if not html_content:
        return ""

    soup = BeautifulSoup(html_content, 'html.parser')
    paragraphs = soup.find_all('p')

    if not paragraphs:
        return html_content

    teaser_html = "<div class='teaser'>Рекламный блок</div>"
    teaser_soup = BeautifulSoup(teaser_html, 'html.parser')

    for i, p in enumerate(paragraphs):
        if (i + 1) % teasers_every_n_paragraphs == 0:
            p.insert_after(teaser_soup.div.clone())

    return str(soup)


def inject_in_article_teasers(content: str) -> str:
    """
    Обрабатывает текст статьи, разделенный тегами <br>, и вставляет тизеры.

    Логика:
    1. Разбиваем текст по <br> (любым вариациям).
    2. Склеиваем пустые или слишком короткие фрагменты обратно, чтобы не считать их за полноценные абзацы.
    3. Оборачиваем каждый значимый кусок текста в <div> с отступом (эмуляция абзаца).
    4. Вставляем тизер после каждого 2-го "абзаца" (если до конца осталось > 1).
    """
    if not content:
        return ""

    # 1. Нормализация разрывов строк.
    # Заменяем все вариации <br>, <br/>, <br /> на единый маркер, например, '\n'
    # (или можно использовать специальный токен, если \n встречается в тексте).
    normalized_content = re.sub(r'<br\s*/?>', '\n', content, flags=re.IGNORECASE)

    # Разбиваем по переносам строк
    raw_paragraphs = normalized_content.split('\n')

    # 2. Фильтрация и группировка "настоящих" абзацев.
    # Мы хотим игнорировать пустые строки.
    paragraphs = [p.strip() for p in raw_paragraphs if p.strip()]

    total_paragraphs = len(paragraphs)
    processed_blocks = []
    teaser_counter = 0

    for i, p_text in enumerate(paragraphs):
        # Оборачиваем текст в блок с отступом (как просил пользователь)
        # Используем класс article-paragraph для стилизации в CSS
        paragraph_html = f'<div class="article-paragraph">{p_text}</div>'
        processed_blocks.append(paragraph_html)

        # Логика вставки тизера: "через каждые 2 абзаца"
        # Индекс i=1 (2-й абзац), i=3 (4-й абзац)...
        if (i + 1) % 2 == 0:
            remaining = total_paragraphs - (i + 1)

            # Если осталось больше 1 абзаца, вставляем тизер
            if remaining > 1:
                # Формируем имя виджета: i + 0 (колонка) + hex-счетчик (2 символа)
                widget_name = f"i0{teaser_counter:02x}"

                placeholder = (
                    f'<div id="widget-{widget_name}" '
                    f'class="in-article-widget-placeholder" '
                    f'data-widget-name="{widget_name}">...</div>'
                )
                processed_blocks.append(placeholder)
                teaser_counter += 1

    # Собираем все обратно в одну строку
    return "".join(processed_blocks)
