def transliterate(text: str) -> str:
    """
    Транслитерация русского текста в латинские символы.
    Используется для генерации slug'ов.
    """
    # Словарь соответствий русских символов латинским
    translit_map = {
        'а': 'a', 'б': 'b', 'в': 'v', 'г': 'g', 'д': 'd', 'е': 'e', 'ё': 'e',
        'ж': 'zh', 'з': 'z', 'и': 'i', 'й': 'y', 'к': 'k', 'л': 'l', 'м': 'm',
        'н': 'n', 'о': 'o', 'п': 'p', 'р': 'r', 'с': 's', 'т': 't', 'у': 'u',
        'ф': 'f', 'х': 'kh', 'ц': 'ts', 'ч': 'ch', 'ш': 'sh', 'щ': 'sch',
        'ъ': '', 'ы': 'y', 'ь': '', 'э': 'e', 'ю': 'yu', 'я': 'ya',
        'А': 'A', 'Б': 'B', 'В': 'V', 'Г': 'G', 'Д': 'D', 'Е': 'E', 'Ё': 'E',
        'Ж': 'Zh', 'З': 'Z', 'И': 'I', 'Й': 'Y', 'К': 'K', 'Л': 'L', 'М': 'M',
        'Н': 'N', 'О': 'O', 'П': 'P', 'Р': 'R', 'С': 'S', 'Т': 'T', 'У': 'U',
        'Ф': 'F', 'Х': 'Kh', 'Ц': 'Ts', 'Ч': 'Ch', 'Ш': 'Sh', 'Щ': 'Sch',
        'Ъ': '', 'Ы': 'Y', 'Ь': '', 'Э': 'E', 'Ю': 'Yu', 'Я': 'Ya'
    }
    
    result = []
    for char in text:
        if char in translit_map:
            result.append(translit_map[char])
        else:
            result.append(char)
    
    return ''.join(result)


def unify_str_values(existing_value: str, new_value: str, sep=";") -> str:
    """
    Объединяет два строковых поля, где значения разделены sep.
    Удаляет дубли, сортирует, возвращает итог.
    Подходит для категорий, тегов, гео и т.д.
    """
    set1 = set(filter(None, existing_value.split(sep)))
    set2 = set(filter(None, new_value.split(sep)))
    merged = sorted(set1.union(set2))
    return sep.join(merged)
