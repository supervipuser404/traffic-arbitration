from bs4 import BeautifulSoup


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
