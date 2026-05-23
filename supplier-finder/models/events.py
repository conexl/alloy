from dataclasses import dataclass, field
from typing import Optional
from datetime import datetime


@dataclass
class EmailInfo:
    email: str
    source: str
    page_type: str


@dataclass
class ContactResult:
    url: str
    domain: str
    emails: list[EmailInfo] = field(default_factory=list)
    checked_urls: list[str] = field(default_factory=list)


@dataclass
class Supplier:
    id: Optional[int]
    domain: str
    source_url: str
    emails: list[str] = field(default_factory=list)


@dataclass
class SearchResult:
    item_id: int
    item_name: str
    query: str
    engine: str                          # 'yandex' | 'duckduckgo'
    urls_found: int
    emails_found: int
    suppliers: list[Supplier] = field(default_factory=list)


# --- Redis события ---

@dataclass
class NewItemEvent:
    """
    Входящее событие из Redis.
    Канал: new_items_to_search
    Публикует: telegram-bot
    """
    id: int
    name: str
    tech_code: str = ""
    gost: str = ""
    location: str = ""                   # город — для уточнения запроса
    region: int = 1                      # код региона Яндекс (1=Москва и т.д.)


@dataclass
class SuppliersFoundEvent:
    """
    Исходящее событие в Redis.
    Канал: suppliers_found
    Потребитель: communication-service
    """
    item_id: int
    item_name: str
    emails_count: int
    suppliers: list[dict] = field(default_factory=list)  # [{supplier_id, emails[]}]
    
    def to_dict(self) -> dict:
        """Конвертирует событие в словарь для JSON"""
        return {
            "item_id": self.item_id,
            "item_name": self.item_name,
            "emails_count": self.emails_count,
            "suppliers": self.suppliers,
            "timestamp": datetime.now().isoformat()
        }
    
    def to_json(self) -> str:
        """Конвертирует событие в JSON строку"""
        import json
        return json.dumps(self.to_dict(), ensure_ascii=False)