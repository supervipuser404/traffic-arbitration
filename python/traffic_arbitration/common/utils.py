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
