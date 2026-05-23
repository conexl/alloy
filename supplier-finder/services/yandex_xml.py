"""
Yandex XML Search API клиент.

Документация: https://yandex.ru/dev/xml/doc/ru/
Лимиты (бесплатно): 1000 запросов/день, 1 rps.

ВАЖНО: этот модуль НЕ модифицирует запрос.
Все добавки ("купить", "поставщик" и т.д.) — задача query_builder.
"""
import asyncio
import logging
import xml.etree.ElementTree as ET
from dataclasses import dataclass

import aiohttp

logger = logging.getLogger(__name__)

YANDEX_SEARCH_URL = "https://yandex.ru/search/xml/"
_REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=15)


@dataclass
class SearchResult:
    url: str
    title: str = ""
    snippet: str = ""


async def search_yandex(
    query: str,
    user: str,
    key: str,
    region: int = 1,
    max_results: int = 10,
    retries: int = 2,
) -> list[SearchResult]:
    """
    Поиск через Yandex XML API.

    Args:
        query:       Готовый поисковый запрос (не модифицируется).
        user:        Логин Яндекс-аккаунта.
        key:         API ключ из кабинета Яндекс XML.
        region:      Код региона (1=Москва, 2=СПб, 37=Астрахань...).
        max_results: Максимум результатов.
        retries:     Повторы при сетевой ошибке.

    Returns:
        Список SearchResult, отсортированных по релевантности.
    """
    params = {
        "user": user,
        "key": key,
        "query": query,
        "lr": region,
        "l10n": "ru",
        "sortby": "rlv",
        "filter": "none",
        "maxpassages": "1",
        "groupby": f"attr=d.mode=deep.groups-on-page={max_results}.docs-in-group=1",
    }

    for attempt in range(retries + 1):
        try:
            async with aiohttp.ClientSession(timeout=_REQUEST_TIMEOUT) as session:
                async with session.get(YANDEX_SEARCH_URL, params=params) as resp:
                    if resp.status == 402:
                        logger.error("[Yandex XML] Превышен дневной лимит запросов (402)")
                        return []
                    if resp.status == 403:
                        logger.error("[Yandex XML] Неверный ключ или IP не авторизован (403)")
                        return []
                    if resp.status != 200:
                        text = await resp.text()
                        logger.warning(f"[Yandex XML] HTTP {resp.status}: {text[:300]}")
                        return []

                    xml_data = await resp.text()
                    return _parse_response(xml_data, max_results)

        except asyncio.TimeoutError:
            logger.warning(f"[Yandex XML] Таймаут (попытка {attempt + 1}/{retries + 1})")
        except aiohttp.ClientError as e:
            logger.warning(f"[Yandex XML] Сеть: {e} (попытка {attempt + 1}/{retries + 1})")
        except Exception as e:
            logger.error(f"[Yandex XML] Неожиданная ошибка: {e}", exc_info=True)
            return []

        if attempt < retries:
            await asyncio.sleep(1.5 * (attempt + 1))

    logger.error("[Yandex XML] Все попытки исчерпаны")
    return []


def _parse_response(xml_data: str, max_results: int) -> list[SearchResult]:
    """Парсит XML ответ Яндекса → список SearchResult."""
    results: list[SearchResult] = []
    try:
        root = ET.fromstring(xml_data)

        # Яндекс возвращает ошибку в теле XML
        error = root.find(".//error")
        if error is not None:
            logger.warning(f"[Yandex XML] Ошибка API: code={error.get('code')} text={error.text}")
            return []

        for doc in root.findall(".//doc"):
            url_el = doc.find("url")
            if url_el is None or not url_el.text:
                continue

            title_el = doc.find("title")
            snippet_el = doc.find(".//passage")

            results.append(
                SearchResult(
                    url=url_el.text.strip(),
                    title=_strip_xml_tags(title_el.text or "") if title_el is not None else "",
                    snippet=_strip_xml_tags(snippet_el.text or "") if snippet_el is not None else "",
                )
            )

    except ET.ParseError as e:
        logger.error(f"[Yandex XML] Ошибка парсинга XML: {e}\nОтвет: {xml_data[:500]}")

    return results[:max_results]


def _strip_xml_tags(text: str) -> str:
    """Убирает highlight-теги Яндекса: <hlword>текст</hlword> → текст."""
    import re
    return re.sub(r"<[^>]+>", "", text).strip()