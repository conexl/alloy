"""Domain models for report service."""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class Quote:
    """Quote from supplier."""

    id: int
    item_id: int
    supplier_id: int
    supplier_email: str
    price: float
    delivery_days: int
    pickup_address: Optional[str]
    source: str
    received_at: datetime


@dataclass
class Winner:
    """Winner selection for an item."""

    id: int
    item_id: int
    quote_id: int
    final_price: float
    margin_pct: float
    chosen_at: datetime


@dataclass
class Item:
    """Item from RFQ."""

    id: int
    rfq_id: int
    name: str
    tech_code: Optional[str]
    material: Optional[str]
    gost: Optional[str]
    tt_ol_ref: Optional[str]
    unit: str
    qty: float
    deadline: datetime
    location: str
    rkd_ref: Optional[str]
    payment_terms: Optional[str]


@dataclass
class Supplier:
    """Supplier info."""

    id: int
    name: str


@dataclass
class RFQStatus:
    """Status of RFQ processing."""

    rfq_id: int
    total: int
    quoted: int
    winners: int
    ready: bool
