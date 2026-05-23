"""Domain models."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class User:
    vk_id: int
    vk_name: str
    is_active: bool = True
    created_at: datetime = None


@dataclass
class RFQ:
    rfq_id: int
    item_id: int
    item_name: str
    tech_code: Optional[str] = None
    material: Optional[str] = None
    gost: Optional[str] = None
    unit: str = ""
    qty: int = 0
    deadline: datetime = None
    location: str = ""
    payment_terms: Optional[str] = None
    suppliers: list = None


@dataclass
class UserProfile:
    vk_id: int
    company_name: Optional[str] = None
    inn: Optional[str] = None
    kpp: Optional[str] = None
    address: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    contact_person: Optional[str] = None
