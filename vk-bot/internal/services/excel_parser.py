"""Excel parser for RFQ files."""

import pandas as pd
from io import BytesIO
from datetime import datetime
from typing import List, Optional, Dict
import re
from dateparser import parse as date_parse


class ExcelParser:
    """Parse Excel files with RFQ items."""

    COLUMN_ALIASES: Dict[str, List[str]] = {
        "name": [
            "наименование мтр", "наименование", "наименование товара",
            "наименование продукции", "name", "item", "item name",
            "номенклатура", "материал/оборудование",
        ],
        "qty": [
            "количество", "кол-во", "кол.во", "колво", "кол-во мтр",
            "количество (заявка)", "quantity", "qty", "count",
        ],
        "unit": [
            "ед.изм", "ед изм", "единица измерения", "ед. измерения",
            "единица изм", "единица", "ед.", "unit",
            "единица измерения (заявка)",
        ],
        "deadline": [
            "срок поставки", "дата поставки", "deadline", "delivery date",
            "поставка", "срок", "необходимый срок поставки",
            "необходимый срок поставки\n(месяц, год)", "срок поставки\n(месяц, год)",
            "месяц поставки", "дата", "срок отгрузки",
        ],
        "tech_code": [
            "техобозначение", "тех.обозначение", "тех обозначение",
            "технологическое обозначение", "техническое обозначение",
            "обозначение", "code", "tech code",
        ],
        "material": [
            "материал", "марка", "материал (марка, стандарт)",
            "материал (марка, стандарт)", "марка материала",
            "материал/марка",
        ],
        "gost": [
            "гост/ту", "гост", "ту", "гост ту",
            "гост/ту", "стандарт", "гост,ту",
            "нормативный документ",
        ],
        "location": [
            "место назначения", "место поставки", "location",
            "место назначения/ базис поставки",
            "базис поставки", "адрес доставки", "доставка", "город поставки",
        ],
        "payment_terms": [
            "условия оплаты", "оплата", "payment", "payment terms",
            "условия платежа", "форма оплаты",
        ],
        "city": [
            "город", "city", "населенный пункт", "населённый пункт",
        ],
        "budget": [
            "бюджет", "budget", "лимит", "сумма", "цена",
        ],
        "num": [
            "№", "номер", "№ п/п", "number", "num", "п/п",
            "№\nп/п",
        ],
    }

    def _clean_column_name(self, name: str) -> str:
        name = name.strip().lower().replace("\n", " ").replace("\r", "")
        name = re.sub(r"\s+", " ", name)
        return name

    def _find_column(self, col_map: Dict[str, str], field: str) -> Optional[str]:
        cleaned = {self._clean_column_name(k): k for k in col_map}
        for alias in self.COLUMN_ALIASES.get(field, []):
            alias_clean = self._clean_column_name(alias)
            for clean_col, orig_col in cleaned.items():
                if alias_clean == clean_col or alias_clean in clean_col or clean_col.startswith(alias_clean):
                    return orig_col
            for clean_col, orig_col in cleaned.items():
                if alias_clean in clean_col or clean_col in alias_clean:
                    return orig_col
        return None

    def parse(
        self, content: bytes
    ) -> tuple[List[dict], Optional[str], Optional[float]]:
        df = pd.read_excel(BytesIO(content), engine="openpyxl")
        col_map = {col: col for col in df.columns}

        name_col = self._find_column(col_map, "name")
        qty_col = self._find_column(col_map, "qty")
        deadline_col = self._find_column(col_map, "deadline")

        if not name_col:
            raise ValueError(
                "Не найден столбец с наименованием МТР "
                "(ожидается: 'Наименование МТР', 'Наименование', 'Name')"
            )
        if not qty_col:
            raise ValueError(
                "Не найден столбец с количеством "
                "(ожидается: 'Количество', 'Кол-во', 'Qty')"
            )
        if not deadline_col:
            raise ValueError(
                "Не найден столбец со сроком поставки "
                "(ожидается: 'Срок поставки', 'Deadline', 'Дата')"
            )

        items = []
        errors = []

        for idx, row in df.iterrows():
            try:
                item = self._parse_row(row, idx + 2, col_map)
                items.append(item)
            except Exception as e:
                errors.append(f"Строка {idx + 2}: {e}")

        if errors:
            raise ValueError(f"Ошибки парсинга:\n" + "\n".join(errors[-5:]))

        city_col = self._find_column(col_map, "city")
        city = None
        if city_col:
            city = df[city_col].dropna().iloc[0] if not df[city_col].dropna().empty else None
        city = str(city) if pd.notna(city) and city else "Москва"

        budget_col = self._find_column(col_map, "budget")
        total_budget = None
        if budget_col:
            val = df[budget_col].dropna().iloc[0] if not df[budget_col].dropna().empty else None
            try:
                total_budget = float(val)
            except (ValueError, TypeError):
                total_budget = val

        return items, city, total_budget

    def _resolve_col(self, col_map: Dict[str, str], field: str, row: pd.Series, default=None):
        col = self._find_column(col_map, field)
        if col:
            return row.get(col, default)
        return default

    def _parse_qty(self, raw) -> int:
        if isinstance(raw, str):
            s = raw.strip().replace(" ", "").replace(".", "").replace(",", "")
            return int(s) if s else 0
        return int(raw) if pd.notna(raw) else 0

    def _parse_row(self, row: pd.Series, row_num: int, col_map: Dict[str, str]) -> dict:
        name = str(self._resolve_col(col_map, "name", row, "")).strip()
        if not name:
            raise ValueError("Наименование МТР обязательно")

        qty_raw = self._resolve_col(col_map, "qty", row, 0)
        qty = self._parse_qty(qty_raw)

        unit = str(self._resolve_col(col_map, "unit", row, "шт")).strip() or "шт"

        deadline_raw = self._resolve_col(col_map, "deadline", row, "")
        if isinstance(deadline_raw, datetime):
            deadline = deadline_raw
        elif isinstance(deadline_raw, str):
            deadline = self._parse_date(deadline_raw)
        else:
            deadline = datetime.now()

        tech_code_raw = self._resolve_col(col_map, "tech_code", row)
        tech_code = str(tech_code_raw).strip() if pd.notna(tech_code_raw) else None

        material_raw = self._resolve_col(col_map, "material", row)
        material = str(material_raw).strip() if pd.notna(material_raw) else None

        gost_raw = self._resolve_col(col_map, "gost", row)
        gost = str(gost_raw).strip() if pd.notna(gost_raw) else None

        location_raw = self._resolve_col(col_map, "location", row)
        location = str(location_raw).strip() if pd.notna(location_raw) else ""

        payment_raw = self._resolve_col(col_map, "payment_terms", row)
        payment_terms = str(payment_raw).strip() if pd.notna(payment_raw) else None

        return {
            "num": row_num,
            "name": name,
            "tech_code": tech_code,
            "material": material,
            "gost": gost,
            "unit": unit,
            "qty": qty,
            "deadline": deadline,
            "location": location,
            "payment_terms": payment_terms,
        }

    def _parse_date(self, text: str) -> datetime:
        text = text.strip().replace("\n", " ").replace("\r", "")
        if not text:
            return datetime.now()
        dt = date_parse(text, languages=["ru", "en"])
        if dt:
            return dt
        match = re.match(r"(\d{1,2})[.-](\d{1,2})[.-](\d{4})", text)
        if match:
            day, month, year = map(int, match.groups())
            return datetime(year, month, day)
        match = re.match(r"(\d{4})[.-](\d{1,2})[.-](\d{1,2})", text)
        if match:
            year, month, day = map(int, match.groups())
            return datetime(year, month, day)
        month_names_ru = {
            "январь": 1, "января": 1, "февраль": 2, "февраля": 2,
            "март": 3, "марта": 3, "апрель": 4, "апреля": 4,
            "май": 5, "мая": 5, "июнь": 6, "июня": 6,
            "июль": 7, "июля": 7, "август": 8, "августа": 8,
            "сентябрь": 9, "сентября": 9, "октябрь": 10, "октября": 10,
            "ноябрь": 11, "ноября": 11, "декабрь": 12, "декабря": 12,
        }
        match = re.search(r"(\d{4})\s*[г]\s*[\.]?", text)
        year = int(match.group(1)) if match else datetime.now().year
        for month_name, month_num in month_names_ru.items():
            if month_name in text.lower():
                day_match = re.search(r"(\d{1,2})\s", text)
                day = int(day_match.group(1)) if day_match else 1
                return datetime(year, month_num, day)
        if re.search(r"\d{4}", text):
            match = re.search(r"(\d{4})", text)
            return datetime(int(match.group(1)), 12, 31)
        raise ValueError(f"Не удалось распарсить дату: {text}")