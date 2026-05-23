"""
Построение поисковых запросов из полей позиции МТР.

Проблемы оригинала:
  - ГОСТ парсился только split()[0] — номер "166-89" из "ГОСТ 166-89" терялся
  - Дублирование: tech_code часто содержит name или его часть
  - Нет нормализации регистра и мусора в name
  - location мог быть "г. Астрахань" — Яндекс не всегда матчит
  - Один запрос — нет fallback стратегии

Что исправлено:
  - Умная нормализация строк: мусор, скобки, ссылки на ТТ-ОЛ
  - Дедупликация токенов между полями
  - ГОСТ/ТУ парсится полностью через regex
  - Несколько пресетов intent для разных движков
  - Нормализация города: "г. Астрахань" → "Астрахань"
  - QuerySet: основной запрос + fallback-и
"""
import re
from dataclasses import dataclass, field


# ---------------------------------------------------------------------------
# Коды регионов Яндекса
# Справочник: https://yandex.ru/dev/xml/doc/ru/reference/regions
# ---------------------------------------------------------------------------
YANDEX_REGIONS: dict[str, int] = {
    # Центр
    "москва": 1,
    "moscow": 1,
    "мск": 1,
    "санкт-петербург": 2,
    "петербург": 2,
    "спб": 2,
    "питер": 2,
    # Урал / Сибирь
    "екатеринбург": 54,
    "новосибирск": 65,
    "красноярск": 62,
    "тюмень": 55,
    "омск": 66,
    "челябинск": 56,
    "пермь": 50,
    "уфа": 172,
    "ханты-мансийск": 118,
    "сургут": 973,
    "нижневартовск": 11168,
    "тобольск": 968,
    # Поволжье
    "казань": 43,
    "нижний новгород": 47,
    "нн": 47,
    "самара": 51,
    "саратов": 194,
    "волгоград": 38,
    "астрахань": 37,
    "ульяновск": 195,
    # Юг
    "краснодар": 35,
    "ростов-на-дону": 39,
    "ростов": 39,
    "ставрополь": 36,
    "сочи": 239,
    # Дальний Восток
    "владивосток": 75,
    "хабаровск": 76,
    "якутск": 74,
    # Северо-Запад
    "воронеж": 193,
    "калининград": 22,
    "мурманск": 23,
    "архангельск": 20,
    "вологда": 21,
}

# Убираем префиксы города: "г. Астрахань" → "Астрахань"
_CITY_PREFIX_RE = re.compile(r"^(город\s+|гор\.?\s+|г\.\s*)", re.IGNORECASE)

# Извлекаем номер ГОСТ/ТУ
# "ГОСТ 166-89" → "166-89"
# "ГОСТ Р 52857-2007" → "52857-2007"
# "ТУ 3414-001-00220302-2007" → "3414-001-00220302-2007"
_GOST_NUMBER_RE = re.compile(
    r"(?:ГОСТ\s*Р?\s*|ТУ\s*|ISO\s*|EN\s*)?"
    r"(\d[\d\-\.]+(?:\-\d{2,4})?)",
    re.IGNORECASE,
)

# Мусорные паттерны в наименовании МТР
_NOISE_PATTERNS = [
    re.compile(r"см\.\s*ТТ[-\s]?ОЛ[^,;]*", re.IGNORECASE),
    re.compile(r"№\s*\d+[\w\-]*"),
    re.compile(r"по\s+чертежу[^,;]*", re.IGNORECASE),
    re.compile(r"согласно[^,;]{0,40}", re.IGNORECASE),
    re.compile(r"\bсм\.\s+\w+", re.IGNORECASE),
    re.compile(r"\([^)]{30,}\)"),   # длинные скобки — обычно уточнения
]

# Слова услуг/документации — мешают поиску поставщиков
_SERVICE_KEYWORDS = frozenset({
    "поверка", "калибровка", "паспорт", "документация",
    "фса", "отг", "сертификат", "метрология",
    "ремонт", "обслуживание", "проверка",
})


# ---------------------------------------------------------------------------
# Публичный API
# ---------------------------------------------------------------------------

@dataclass
class QuerySet:
    """
    Набор поисковых запросов для одной позиции МТР.

    primary   — основной запрос (максимально специфичный)
    fallbacks — упрощённые варианты, если primary даёт 0 результатов
    region    — код региона Яндекса
    """
    primary: str
    fallbacks: list[str] = field(default_factory=list)
    region: int = 1


def build_query_set(
    name: str,
    tech_code: str = "",
    gost: str = "",
    location: str = "",
) -> QuerySet:
    """
    Строит набор поисковых запросов из полей позиции МТР.

    Args:
        name:       Наименование МТР
        tech_code:  Технологическое обозначение / марка / артикул
        gost:       ГОСТ/ТУ
        location:   Город получения (любой формат)

    Returns:
        QuerySet с основным запросом, fallback-ами и кодом региона.

    Примеры:
        >>> qs = build_query_set("Набор ВИК", "ВИК-НК-2", "ГОСТ 166-89", "г. Астрахань")
        >>> qs.primary
        'Набор ВИК ВИК-НК-2 166-89 Астрахань купить оптом поставщик'
        >>> qs.fallbacks[0]
        'Набор ВИК ВИК-НК-2 Астрахань купить поставщик'
    """
    city = _normalize_city(location)
    region = get_region_code(city)

    clean_name = _clean_name(name)
    clean_tech = _clean_tech_code(tech_code)
    gost_num = _extract_gost_number(gost)

    # Если tech_code дублирует name или является его подстрокой — убираем
    if clean_tech and _is_redundant(clean_tech, clean_name):
        clean_tech = ""

    # Основной запрос: name + tech + ГОСТ + город + intent
    primary = _build(clean_name, clean_tech, gost_num, city, "купить оптом поставщик")

    # Fallback 1: без ГОСТ (когда ГОСТ редкий — выдача пустая)
    fb1 = _build(clean_name, clean_tech, "", city, "купить поставщик")

    # Fallback 2: только name + город (самый широкий)
    fb2 = _build(clean_name, "", "", city, "дистрибьютор производитель")

    fallbacks = _dedup([fb1, fb2], exclude=primary)

    return QuerySet(primary=primary, fallbacks=fallbacks, region=region)


def build_query(
    name: str,
    tech_code: str = "",
    gost: str = "",
    location: str = "",
) -> str:
    """
    Короткий вариант — возвращает только основной запрос.
    Совместим со старым API finder.py.
    """
    return build_query_set(name, tech_code, gost, location).primary


def get_region_code(city: str) -> int:
    """Возвращает код региона Яндекса по названию города."""
    if not city:
        return 1
    return YANDEX_REGIONS.get(city.lower().strip(), 1)


# ---------------------------------------------------------------------------
# Внутренние функции
# ---------------------------------------------------------------------------

def _normalize_city(raw: str) -> str:
    """
    "г. Астрахань"   → "Астрахань"
    "гор.Москва"     → "Москва"
    "Ростов-на-Дону" → "Ростов-на-Дону"
    """
    if not raw:
        return ""
    city = _CITY_PREFIX_RE.sub("", raw.strip())
    return city.strip().title()


def _clean_name(raw: str) -> str:
    """
    Убирает мусор из наименования МТР.

    "Набор ВИК (Поверка, Калибровка ФСА), см. ТТ-ОЛ №12"
    → "Набор ВИК"
    """
    text = raw.strip()
    for pattern in _NOISE_PATTERNS:
        text = pattern.sub(" ", text)
    text = re.sub(r"[,;:()\[\]{}\"'«»]", " ", text)
    # Убираем слова услуг/документации
    tokens = [t for t in text.split() if t.lower() not in _SERVICE_KEYWORDS]
    text = " ".join(tokens)
    text = re.sub(r"\s{2,}", " ", text).strip()
    return text


def _clean_tech_code(raw: str) -> str:
    """
    Убирает обрамляющие скобки и пробелы.

    "(ВИК-НК-2)" → "ВИК-НК-2"
    """
    if not raw:
        return ""
    return re.sub(r"^[(\[]+|[)\]]+$", "", raw.strip()).strip()


def _extract_gost_number(raw: str) -> str:
    """
    "ГОСТ 166-89"          → "166-89"
    "ГОСТ Р 52857-2007"    → "52857-2007"
    "ТУ 3414-001-00220302" → "3414-001-00220302"
    "166-89"               → "166-89"  (уже номер)
    """
    if not raw:
        return ""
    match = _GOST_NUMBER_RE.search(raw.strip())
    return match.group(1) if match else ""


def _is_redundant(short: str, long: str) -> bool:
    """
    True если short — подстрока или подмножество токенов long.

    "ШЦ-1-125" in "Штангенциркуль ШЦ-1-125 ГОСТ" → True
    "ВВГнг"    in "Кабель ВВГнг 3х2.5"            → True
    """
    s, l = short.lower(), long.lower()
    if s in l:
        return True
    return set(s.split()) <= set(l.split())


def _build(name: str, tech: str, gost: str, city: str, intent: str) -> str:
    """Собирает запрос из непустых частей."""
    parts: list[str] = []
    seen: set[str] = set()

    for part in (name, tech, gost, city):
        p = part.strip()
        if p and p.lower() not in seen:
            seen.add(p.lower())
            parts.append(p)

    parts.append(intent)
    return " ".join(parts)


def _dedup(queries: list[str], exclude: str) -> list[str]:
    """Убирает дубли и исключает основной запрос из fallback-ов."""
    seen: set[str] = {exclude}
    result: list[str] = []
    for q in queries:
        if q not in seen:
            seen.add(q)
            result.append(q)
    return result