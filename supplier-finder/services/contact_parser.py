"""
contact_parser.py — парсинг email-адресов с сайтов поставщиков.

Алгоритм (по убыванию приоритета):
  1. Главная страница сайта
  2. Ссылки с контактными словами из навигации
  3. Стандартные пути (/contacts, /kontakty, ...)
  4. Stealth режим (Chromium headless) — если ничего не нашли

Фильтрация мусора:
  - Публичные почтовые сервисы (gmail, mail.ru, ...)
  - Технические адреса (noreply, no-reply, admin, ...)
  - Адреса из JS/CSS/изображений (*.min.js, *.png, ...)
  - Версии библиотек (1.0@something, 2.5@example.com)
  - Слишком короткие / длинные адреса

Скоринг email:
  Контактные страницы > главная > остальные.
  Адрес совпадающий с доменом сайта получает бонус.
"""
import asyncio
import logging
import re
from dataclasses import dataclass, field
from urllib.parse import urljoin, urlparse

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Email regex — RFC 5321 упрощённый, без экзотики
# ---------------------------------------------------------------------------
_EMAIL_RE = re.compile(
    r"\b([a-zA-Z0-9](?:[a-zA-Z0-9._%+\-]{0,62}[a-zA-Z0-9])?)"
    r"@"
    r"([a-zA-Z0-9](?:[a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?"
    r"(?:\.[a-zA-Z0-9](?:[a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?)*"
    r"\.[a-zA-Z]{2,})\b"
)

# Публичные сервисы — не корпоративные email
_PUBLIC_DOMAINS = frozenset({
    "gmail.com", "googlemail.com",
    "mail.ru", "inbox.ru", "list.ru", "bk.ru",
    "yandex.ru", "yandex.com", "ya.ru",
    "yahoo.com", "yahoo.co.uk",
    "hotmail.com", "outlook.com", "live.com", "msn.com",
    "rambler.ru", "ro.ru",
    "icloud.com", "me.com", "mac.com",
    "protonmail.com", "pm.me",
})

# Технические / no-reply адреса — не для RFQ
_NOREPLY_PREFIXES = frozenset({
    "noreply", "no-reply", "no_reply", "donotreply",
    "mailer-daemon", "postmaster", "bounce", "bounces",
    "unsubscribe", "newsletter", "notifications",
    "robot", "bot", "daemon", "system",
    "webmaster", "hostmaster", "abuse",
    "test", "example", "demo",
    # Не закупочные отделы
    "hr", "job", "career", "vacancy", "recruit",
    "buh", "buhgalteriya", "accountant",
    "director", "ceo", "general",
    "pr", "press", "media", "smi",
    "legal", "juridical", "pravo",
    "security", "it", "admin",
})

# Технические субдомены — Sentry DSN, трекеры и т.д.
_TECHNICAL_SUBDOMAINS = frozenset({
    "sentry", "bugsnag", "rollbar", "datadog",
    "smtp", "mail", "mx", "relay",
    "tracking", "analytics", "stats",
    "cdn", "static", "assets", "media",
    "api", "dev", "staging", "test",
})

# Паттерн плюс-адресации: zakaz+abc123@domain.com → мусор
_PLUS_ADDRESSING_RE = re.compile(r"^(.+)\+[a-zA-Z0-9]{4,}$")

# Паттерн хэшей в local-части: 32+ hex символов = технический адрес
_HEX_HASH_RE = re.compile(r"^[0-9a-f]{16,}$")

# Расширения файлов — email-подобные строки в пути файла
_FILE_EXTENSIONS = frozenset({
    "js", "ts", "css", "scss", "less", "map",
    "png", "jpg", "jpeg", "gif", "svg", "webp", "ico",
    "woff", "woff2", "ttf", "eot",
    "json", "xml", "yml", "yaml",
    "min", "bundle", "chunk",
})

# Страницы контактов — стандартные пути
_CONTACT_PATHS = [
    "/kontakty", "/kontakt", "/contacts", "/contact",
    "/contact-us", "/contactus", "/about", "/about-us",
    "/o-nas", "/o-kompanii", "/o-kompanyi",
    "/company", "/about-company",
    "/feedback", "/obratnaya-svyaz",
    "/support", "/help",
    "/requisites", "/rekvizity",
    "/dealers", "/distributors",
    "/where-to-buy", "/gde-kupit",
]

# Ключевые слова для поиска ссылок в навигации
_NAV_KEYWORDS_HREF = frozenset({
    "contact", "kontakt", "about", "o-nas", "rekvizit",
    "contacts", "svyaz", "feedback", "kompan", "support",
    "obratno", "gde-kupit", "distributor", "dealer",
})
_NAV_KEYWORDS_TEXT = frozenset({
    "контакт", "о нас", "обратная связь", "реквизит",
    "поддержка", "о компании", "связаться", "написать",
    "дилер", "дистрибьютор", "где купить",
})

# Скоринг источников (выше = важнее)
_PAGE_SCORES = {
    "contact": 100,
    "about": 80,
    "main": 50,
    "nav": 60,
    "common": 40,
}

# Таймаут на весь сайт (секунды)
_SITE_TIMEOUT = 45


@dataclass
class EmailHit:
    email: str
    source_url: str
    page_type: str
    score: int = 0       # выше = лучше


@dataclass
class ParseResult:
    url: str
    domain: str
    emails: list[EmailHit] = field(default_factory=list)
    checked_urls: list[str] = field(default_factory=list)
    error: str | None = None

    def best_emails(self, limit: int = 5) -> list[EmailHit]:
        """Возвращает топ email отсортированные по score."""
        seen: set[str] = set()
        out: list[EmailHit] = []
        for hit in sorted(self.emails, key=lambda h: -h.score):
            if hit.email not in seen:
                seen.add(hit.email)
                out.append(hit)
            if len(out) >= limit:
                break
        return out


# ---------------------------------------------------------------------------
# Вспомогательные функции
# ---------------------------------------------------------------------------

def _is_valid_email(email: str, site_domain: str) -> tuple[bool, int]:
    """
    Проверяет корпоративный email.
    Возвращает (is_valid, score).
    """
    local, domain = email.lower().split("@", 1)

    # --- Отсеиваем публичные сервисы ---
    if domain in _PUBLIC_DOMAINS:
        return False, 0

    # --- Отсеиваем технические субдомены (Sentry DSN: xxx@sentry.cable.ru) ---
    subdomain = domain.split(".")[0] if domain.count(".") >= 2 else ""
    if subdomain in _TECHNICAL_SUBDOMAINS:
        return False, 0

    # --- Отсеиваем плюс-адресацию: zakaz+c08893@domain.com ---
    plus_match = _PLUS_ADDRESSING_RE.match(local)
    if plus_match:
        # Нормализуем к base: zakaz+c08893 → zakaz
        local = plus_match.group(1)

    # --- Отсеиваем hex-хэши в local: 1152702f480ebc92fd95e680cb8694bf@ ---
    if _HEX_HASH_RE.match(local):
        return False, 0

    # --- Отсеиваем технические адреса ---
    if local in _NOREPLY_PREFIXES:
        return False, 0
    if any(local.startswith(p + "-") or local.startswith(p + "_") for p in _NOREPLY_PREFIXES):
        return False, 0

    # --- Отсеиваем файловые расширения ---
    # e.g. "2.0@example", "chunk.js@bundle.min"
    local_ext = local.rsplit(".", 1)[-1] if "." in local else ""
    domain_ext = domain.rsplit(".", 1)[-1]
    if local_ext in _FILE_EXTENSIONS or domain_ext in _FILE_EXTENSIONS:
        return False, 0

    # --- Отсеиваем версии (1.2.3@lib, v2@framework) ---
    if re.match(r"^v?\d", local) and re.search(r"\d", local):
        # "3.14@example" — отсеиваем; "3d@supplier.ru" — оставляем
        if re.match(r"^v?[\d.]+$", local):
            return False, 0

    # --- Длина ---
    if len(local) < 2 or len(local) > 64:
        return False, 0
    if len(domain) > 253:
        return False, 0

    # --- Скоринг ---
    score = 10

    # Совпадение домена email с доменом сайта — хороший знак
    site_root = site_domain.split(".")
    email_root = domain.split(".")
    if site_root[-2:] == email_root[-2:]:
        score += 50

    # Контактные префиксы — высокий приоритет
    contact_locals = {"info", "sales", "zakupki", "tender", "snab",
                      "supply", "purchase", "order", "trade", "opt",
                      "manager", "office", "mail", "email"}
    if local in contact_locals:
        score += 30

    return True, score


def _extract_emails_from_html(html: str, source_url: str, page_type: str, site_domain: str) -> list[EmailHit]:
    """Извлекает и фильтрует email из HTML строки."""
    hits: list[EmailHit] = []
    seen: set[str] = set()

    for match in _EMAIL_RE.finditer(html):
        email = match.group(0).lower()

        valid, score = _is_valid_email(email, site_domain)
        if not valid:
            continue

        # Нормализуем плюс-адресацию для дедупликации
        local_part, domain_part = email.split("@", 1)
        plus_match = _PLUS_ADDRESSING_RE.match(local_part)
        if plus_match:
            email = f"{plus_match.group(1)}@{domain_part}"

        if email in seen:
            continue
        seen.add(email)

        # Бонус за тип страницы
        page_key = "main"
        url_path = urlparse(source_url).path.lower()
        for key in ("contact", "kontakt", "about", "o-nas", "rekvizit", "feedback", "svyaz"):
            if key in url_path:
                page_key = "contact"
                break

        score += _PAGE_SCORES.get(page_key, 0)

        hits.append(EmailHit(
            email=email,
            source_url=source_url,
            page_type=page_type,
            score=score,
        ))

    return hits


def _get_base_url(url: str) -> str:
    p = urlparse(url)
    return f"{p.scheme}://{p.netloc}"


def _get_contact_candidate_urls(base_url: str) -> list[str]:
    return [urljoin(base_url, path) for path in _CONTACT_PATHS]


# ---------------------------------------------------------------------------
# Синхронный парсер (запускается в отдельном потоке через asyncio.to_thread)
# ---------------------------------------------------------------------------

def _sync_parse(start_url: str, site_domain: str) -> ParseResult:
    """
    Синхронный парсинг одного сайта с помощью scrapling.Fetcher.
    Структура: главная → навигация → стандартные пути → stealth fallback.
    """
    from scrapling import Fetcher, StealthyFetcher

    result = ParseResult(url=start_url, domain=site_domain)
    checked: set[str] = set()
    all_emails: list[EmailHit] = []

    _HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "ru-RU,ru;q=0.8,en-US;q=0.5,en;q=0.3",
    }

    fetcher = Fetcher(auto_match=False)
    base_url = _get_base_url(start_url)

    def fetch_page(url: str, page_type: str) -> str | None:
        """Загружает страницу, возвращает HTML или None."""
        if url in checked:
            return None
        checked.add(url)
        try:
            resp = fetcher.get(url, timeout=10, headers=_HEADERS)
            status = getattr(resp, "status_code", 200)
            if status != 200:
                logger.debug(f"[Parser] {url} → HTTP {status}")
                return None
            html = str(resp)
            hits = _extract_emails_from_html(html, url, page_type, site_domain)
            all_emails.extend(hits)
            logger.debug(f"[Parser] {page_type} {url} → {len(hits)} email")
            return html
        except Exception as e:
            logger.debug(f"[Parser] Ошибка {url}: {e}")
            return None

    # --- 1. Главная страница ---
    main_html = fetch_page(start_url, "главная")

    # --- 2. Контактные ссылки из навигации (парсим из главной) ---
    nav_links: set[str] = set()
    if main_html:
        try:
            resp = fetcher.get(start_url, timeout=10, headers=_HEADERS)
            for a in resp.css("a[href]"):
                href = (a.attrib.get("href") or "").strip()
                text = (a.text or "").lower().strip()
                href_lower = href.lower()

                href_match = any(kw in href_lower for kw in _NAV_KEYWORDS_HREF)
                text_match = any(kw in text for kw in _NAV_KEYWORDS_TEXT)

                if href_match or text_match:
                    full = urljoin(base_url, href)
                    # Только страницы этого же сайта
                    if urlparse(full).netloc == urlparse(base_url).netloc:
                        nav_links.add(full)
                        if len(nav_links) >= 6:
                            break
        except Exception as e:
            logger.debug(f"[Parser] Ошибка парсинга навигации: {e}")

    for link in nav_links:
        fetch_page(link, "навигация")

    # --- 3. Стандартные пути ---
    for url in _get_contact_candidate_urls(base_url):
        if url not in checked:
            fetch_page(url, "стандартный путь")

    # --- 4. Stealth fallback — если ничего не нашли ---
    if not all_emails:
        logger.info(f"[Parser] Stealth режим для {start_url}")
        try:
            stealth = StealthyFetcher()
            resp = stealth.fetch(start_url, headless=True, timeout=20)
            html = str(resp)
            hits = _extract_emails_from_html(html, start_url, "stealth", site_domain)
            all_emails.extend(hits)

            # Также ищем контактные страницы через stealth
            if not hits:
                for path in ["/contacts", "/kontakty", "/contact", "/about"]:
                    contact_url = urljoin(base_url, path)
                    if contact_url not in checked:
                        try:
                            resp2 = stealth.fetch(contact_url, headless=True, timeout=15)
                            hits2 = _extract_emails_from_html(
                                str(resp2), contact_url, "stealth-contact", site_domain
                            )
                            all_emails.extend(hits2)
                            if hits2:
                                break
                        except Exception:
                            pass
        except Exception as e:
            logger.debug(f"[Parser] Stealth ошибка: {e}")

    result.emails = all_emails
    result.checked_urls = list(checked)

    logger.info(
        f"[Parser] {site_domain}: найдено {len(all_emails)} email, "
        f"проверено {len(checked)} страниц"
    )
    return result


# ---------------------------------------------------------------------------
# Публичный async API
# ---------------------------------------------------------------------------

async def parse_contacts(start_url: str, timeout: float = _SITE_TIMEOUT) -> ParseResult:
    """
    Асинхронный парсинг контактов с сайта.

    Args:
        start_url: URL сайта поставщика.
        timeout:   Максимальное время на весь сайт (секунды).

    Returns:
        ParseResult с дедуплицированными email и скорингом.
    """
    parsed = urlparse(start_url)
    site_domain = parsed.netloc.removeprefix("www.")

    try:
        result = await asyncio.wait_for(
            asyncio.to_thread(_sync_parse, start_url, site_domain),
            timeout=timeout,
        )
    except asyncio.TimeoutError:
        logger.warning(f"[Parser] Таймаут {timeout}s для {start_url}")
        result = ParseResult(
            url=start_url,
            domain=site_domain,
            error=f"timeout after {timeout}s",
        )
    except Exception as e:
        logger.error(f"[Parser] Критическая ошибка для {start_url}: {e}", exc_info=True)
        result = ParseResult(url=start_url, domain=site_domain, error=str(e))

    return result