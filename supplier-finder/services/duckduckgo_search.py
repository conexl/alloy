"""
DuckDuckGo HTML поиск — fallback когда Yandex XML недоступен.

Использует публичный HTML endpoint, не требует API ключа.
Скорость ниже Yandex, но работает без регистрации.

Поддерживает ротацию прокси (round-robin) для обхода блокировок.
"""
import asyncio
import logging
import time
from dataclasses import dataclass
from urllib.parse import parse_qs, unquote, urlparse

import aiohttp
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

DDG_URL = "https://html.duckduckgo.com/html/"
_REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=20)
_REQUEST_DELAY = 3.0
_last_request_time = 0.0
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.5",
    "Accept-Encoding": "gzip, deflate, br",
}

# Proxy rotation (round-robin)
_PROXY_LIST: list[str] = []
_PROXY_INDEX = 0
_PROXY_LOCK = asyncio.Lock()

# Домены которые никогда не являются поставщиками
_EXCLUDE_DOMAINS = frozenset({
    "avito.ru", "wildberries.ru", "ozon.ru", "market.yandex.ru",
    "aliexpress.com", "amazon.com", "ebay.com",
    "wikipedia.org", "wikipe dia.ru",
    "youtube.com", "vk.com", "instagram.com", "facebook.com",
    "2gis.ru", "maps.google.com",
    "government.ru", "gosuslugi.ru",
})


@dataclass
class SearchResult:
    url: str
    title: str = ""
    snippet: str = ""


def configure_proxies(proxies: list[str]) -> None:
    global _PROXY_LIST
    _PROXY_LIST = list(proxies)
    logger.info(f"[DDG] Прокси ротация: {len(_PROXY_LIST)} прокси")


async def _next_proxy() -> str | None:
    global _PROXY_INDEX
    if not _PROXY_LIST:
        return None
    async with _PROXY_LOCK:
        proxy = _PROXY_LIST[_PROXY_INDEX % len(_PROXY_LIST)]
        _PROXY_INDEX += 1
        return proxy


async def search_duckduckgo(
    query: str,
    max_results: int = 10,
    retries: int = 3,
) -> list[SearchResult]:
    global _last_request_time

    for attempt in range(retries + 1):
        proxy = await _next_proxy()
        proxy_label = proxy.split("@")[-1] if proxy else "direct"
        logger.info(f"[DDG] Попытка {attempt + 1}/{retries + 1} через {proxy_label}: {query!r}")

        now = time.monotonic()
        since_last = now - _last_request_time
        if since_last < _REQUEST_DELAY:
            await asyncio.sleep(_REQUEST_DELAY - since_last)
        _last_request_time = time.monotonic()

        try:
            kwargs = {"data": {"q": query, "kl": "ru-ru"}}
            if proxy:
                kwargs["proxy"] = proxy

            async with aiohttp.ClientSession(
                timeout=_REQUEST_TIMEOUT, headers=_HEADERS
            ) as session:
                async with session.post(DDG_URL, **kwargs) as resp:
                    if resp.status == 202:
                        delay = 5.0 * (attempt + 1)
                        logger.warning(
                            f"[DDG] HTTP 202 (блокировка) через {proxy_label}, "
                            f"повтор через {delay:.0f}с "
                            f"(попытка {attempt + 1}/{retries + 1})"
                        )
                        await asyncio.sleep(delay)
                        continue

                    if resp.status != 200:
                        logger.warning(f"[DDG] HTTP {resp.status} через {proxy_label}")
                        await asyncio.sleep(3.0)
                        continue

                    html = await resp.text()
                    results = _parse_html(html, max_results)
                    logger.info(
                        f"[DDG] {len(results)} результатов через {proxy_label}"
                    )
                    return results

        except asyncio.TimeoutError:
            logger.warning(
                f"[DDG] Таймаут через {proxy_label} "
                f"(попытка {attempt + 1}/{retries + 1})"
            )
        except aiohttp.ClientError as e:
            logger.warning(
                f"[DDG] Ошибка сети через {proxy_label}: {e} "
                f"(попытка {attempt + 1}/{retries + 1})"
            )
        except Exception as e:
            logger.error(f"[DDG] Неожиданная ошибка: {e}", exc_info=True)
            return []

        if attempt < retries:
            await asyncio.sleep(2.0 * (attempt + 1))

    return []


def _parse_html(html: str, max_results: int) -> list[SearchResult]:
    """Парсит HTML страницы DuckDuckGo → список SearchResult."""
    soup = BeautifulSoup(html, "lxml")
    results: list[SearchResult] = []

    for tag in soup.find_all("a", class_="result__a"):
        url = _extract_url(tag.get("href", ""))
        if not url or _is_excluded(url):
            continue

        # Текст ссылки = заголовок
        title = tag.get_text(strip=True)

        # Сниппет — следующий элемент .result__snippet
        snippet = ""
        parent = tag.find_parent(class_="result__body") or tag.find_parent(class_="result")
        if parent:
            snip_tag = parent.find(class_="result__snippet")
            if snip_tag:
                snippet = snip_tag.get_text(strip=True)

        results.append(SearchResult(url=url, title=title, snippet=snippet))

        if len(results) >= max_results:
            break

    return results


def _extract_url(href: str) -> str | None:
    """Извлекает реальный URL из редиректа DuckDuckGo."""
    if not href:
        return None

    # Формат: /l/?uddg=https%3A%2F%2F...
    if "/l/?uddg=" in href or "uddg=" in href:
        try:
            qs = parse_qs(urlparse(href).query)
            if "uddg" in qs:
                return unquote(qs["uddg"][0])
        except Exception:
            return None

    if href.startswith("http"):
        return href

    return None


def _is_excluded(url: str) -> bool:
    """Проверяет, входит ли домен в список исключений."""
    try:
        domain = urlparse(url).netloc.lower().removeprefix("www.")
        return any(domain == exc or domain.endswith("." + exc) for exc in _EXCLUDE_DOMAINS)
    except Exception:
        return False