"""Bot message handlers — single route dispatcher."""

import re
import logging
import httpx
import tempfile
import os
from typing import Optional
from datetime import datetime

from vkbottle.bot import Message

from ..domain.models import User, UserProfile
from ..repository.postgres import PostgresRepository
from ..repository.redis import RedisRepositoryImpl
from ..services.excel_parser import ExcelParser
from vkbottle import Keyboard, KeyboardButtonColor, OpenLink

from ..keyboards.keyboards import (
    main_menu,
    confirm_create,
    cancel,
    profile_menu,
    rfq_list,
    rfq_detail,
    item_nav,
    report_action,
    MINI_APP_URL,
)

logger = logging.getLogger(__name__)


class _Storage(dict):
    def get(self, key, default=None):
        return super().get(key, default)

    def set(self, key, value):
        self[key] = value

    def clear_key(self, key):
        self.pop(key, None)

    def setdefault(self, key, default=None):
        return super().setdefault(key, default)


_store = _Storage()


def _ctx_clear(*keys: str):
    for key in keys:
        _store.clear_key(key)


def _ctx_set(key: str, value):
    _store.set(key, value)


def _ctx_get(key: str, default=None):
    return _store.get(key, default)


def _progress_bar(current, total, width=10):
    if total == 0:
        return "\u2014" * width
    filled = int(current / total * width)
    return "\u25a0" * filled + "\u2014" * (width - filled)


class BotHandlers:
    def __init__(
        self, pg: PostgresRepository, redis_repo: RedisRepositoryImpl, report_url: str
    ):
        self.pg = pg
        self.redis = redis_repo
        self.report_url = report_url
        self.parser = ExcelParser()

    async def route(self, message: Message):
        text = message.text.lower().strip()

        if not text and message.attachments:
            await self.file_handler(message)
            return

        known_commands = {
            "начать", "старт", "start", "привет", "помощь",
            "мои заявки", "заявки", "список заявок",
            "новая заявка", "заявка",
            "статус", "статус последней",
            "отчёт", "отчет", "скачать отчёт",
            "да, создать",
            "загрузить другой", "загрузить новый",
            "отмена", "назад", "главное меню",
            "к списку", "к статусу", "позиции",
            "< назад", "вперёд >", "вперед >",
            "уведомления",
            "настройки", "профиль", "реквизиты",
            "заполнить профиль", "посмотреть профиль",
        }

        if text in known_commands:
            await self._route_known(text, message)
            return

        m = re.match(r"заявка #(\d+)", text)
        if m:
            await self._show_rfq_detail(message, int(m.group(1)))
            return

        state = _ctx_get("state")
        if state in ("waiting_file", "confirm_rfq"):
            await message.answer(
                "Сначала завершите текущее действие или нажмите «Отмена».",
                keyboard=main_menu(),
            )
            return

        if state and state.startswith("profile_"):
            await self._handle_profile_input(message)
            return

        await message.answer(
            "Команда не распознана. Выберите действие из меню:",
            keyboard=main_menu(),
        )

    async def _route_known(self, text: str, message: Message):
        if text in ("начать", "старт", "start", "привет", "помощь"):
            await self.start_handler(message)
        elif text in ("мои заявки", "заявки", "список заявок"):
            await self.my_rfqs_handler(message)
        elif text in ("новая заявка", "заявка"):
            await self.new_rfq_handler(message)
        elif text in ("статус", "статус последней"):
            await self.status_handler(message)
        elif text in ("отчёт", "отчет", "скачать отчёт"):
            await self.report_handler(message)
        elif text in ("да, создать",):
            await self.confirm_handler(message)
        elif text in ("отмена", "назад", "главное меню"):
            await self.cancel_handler(message)
        elif text == "к списку":
            await self.my_rfqs_handler(message)
        elif text == "к статусу":
            rfq_id = _ctx_get("current_rfq_id")
            if rfq_id:
                await self.status_handler(message, rfq_id, from_detail=True)
            else:
                await message.answer("Выберите заявку.", keyboard=main_menu())
        elif text == "позиции":
            await self._show_items(message)
        elif text in ("загрузить новый", "загрузить другой"):
            _ctx_clear("state", "pending_items", "pending_city", "pending_budget")
            await self.new_rfq_handler(message)
        elif text in ("< назад", "вперёд >", "вперед >"):
            await self._navigate_items(text, message)
        elif text == "уведомления":
            await self._toggle_notifications(message)
        elif text in ("настройки", "профиль", "реквизиты"):
            await self.settings_handler(message)
        elif text == "заполнить профиль":
            await self.start_profile_wizard(message)
        elif text == "посмотреть профиль":
            await self.show_profile_handler(message)

    async def start_handler(self, message: Message):
        first_name = "Пользователь"
        try:
            users = await message.ctx_api.users.get(message.from_id)
            if users:
                first_name = users[0].first_name
        except Exception:
            pass
        await self._get_or_create_user(message.from_id, first_name)
        await message.answer(
            f"Здравствуйте, {first_name}!\n\n"
            "Я помогу вам собрать коммерческие предложения от поставщиков.\n\n"
            "Главные действия:\n"
            "  [Новая заявка] — загрузите Excel со спецификацией\n"
            "  [Мои заявки] — список всех ваших заявок\n"
            "  [Статус] — прогресс последней заявки\n"
            "  [Отчёт] — готовый Excel-файл с результатами\n\n"
            "Выберите действие в меню ниже:",
            keyboard=main_menu(),
        )

    async def my_rfqs_handler(self, message: Message):
        _ctx_clear("state", "viewing_rfq", "viewing_index")

        user = await self.pg.get_user(message.from_id)
        if not user:
            await message.answer("Напишите «начать», чтобы начать.", keyboard=main_menu())
            return

        rfqs = await self.pg.get_user_rfqs(message.from_id)
        if not rfqs:
            await message.answer(
                "Заявок пока нет.\nСоздайте новую — нажмите «Новая заявка».",
                keyboard=main_menu(),
            )
            return

        lines = ["Мои заявки:\n"]
        for rfq in rfqs:
            bar = _progress_bar(rfq["winner_count"], rfq["items_count"])
            done = rfq["winner_count"] == rfq["items_count"]
            created = ""
            if isinstance(rfq.get("created_at"), datetime):
                created = rfq["created_at"].strftime("%d.%m.%Y")
            elif rfq.get("created_at"):
                created = str(rfq["created_at"])[:10]
            status = "завершена" if done else "в работе"
            lines.append(
                f"Заявка #{rfq['id']} — {rfq['items_count']} поз.\n"
                f"  {bar} {rfq['winner_count']}/{rfq['items_count']} — {status}\n"
                f"  {created}, {rfq.get('city', '—')}\n"
            )

        await message.answer("\n".join(lines), keyboard=rfq_list(rfqs))

    async def status_handler(self, message: Message, rfq_id: int = None, from_detail: bool = False):
        user = await self.pg.get_user(message.from_id)
        if not user:
            await message.answer("Напишите «начать», чтобы начать.", keyboard=main_menu())
            return

        if rfq_id is None:
            rfq = await self.pg.get_latest_rfq_for_user(user.vk_id)
            if not rfq:
                await message.answer("Нет активных заявок.", keyboard=main_menu())
                return
            rfq_id = rfq.rfq_id

        status = await self.pg.get_rfq_status(rfq_id)
        total = status["total"]
        quoted = status["quoted"]
        winners = status["winners"]
        bar = _progress_bar(winners, total)
        ready = winners == total and total > 0

        # Краткий статус только по последней заявке
        lines = [
            f"📋 Заявка #{rfq_id}",
            f"",
            f"{bar} {winners}/{total} позиций с победителями",
            f"📊 Котировок: {quoted}/{total}",
            f"",
            f"{'✅ Готово' if ready else '🔄 В работе'}",
            f"",
            f"Подробности в приложении 👇",
        ]

        # Клавиатура с кнопкой открыть приложение
        kb = Keyboard(one_time=False, inline=False)
        kb.add(OpenLink(MINI_APP_URL, "📱 Открыть в приложении"), color=KeyboardButtonColor.POSITIVE)
        kb.row()
        kb.add(Text("Главное меню"), color=KeyboardButtonColor.PRIMARY)

        await message.answer("\n".join(lines), keyboard=kb)

    async def report_handler(self, message: Message, rfq_id: int = None):
        user = await self.pg.get_user(message.from_id)
        if not user:
            await message.answer("Напишите «начать», чтобы начать.", keyboard=main_menu())
            return

        if rfq_id is None:
            rfq = await self.pg.get_latest_rfq_for_user(user.vk_id)
            if not rfq:
                await message.answer("Нет заявок.", keyboard=main_menu())
                return
            rfq_id = rfq.rfq_id

        status = await self.pg.get_rfq_status(rfq_id)
        ready = status["winners"] == status["total"] and status["total"] > 0
        quoted = status["quoted"]

        if not ready:
            await message.answer(
                f"Генерирую отчёт (получено {quoted}/{status['total']} котировок).\n"
                "Это может занять до минуты.",
                keyboard=report_action(rfq_id, ready) if not ready else None,
            )
        else:
            await message.answer(
                "Генерирую отчёт. Это может занять до минуты.",
            )

        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    f"{self.report_url}/report/{rfq_id}/generate", timeout=60.0
                )
                if resp.status_code == 200:
                    with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as f:
                        f.write(resp.content)
                        temp_path = f.name

                    upload_resp = await message.ctx_api.request(
                        "docs.getMessagesUploadServer", {"peer_id": message.peer_id, "type": "doc"}
                    )
                    upload_url = upload_resp.get("response", {}).get("upload_url", "")

                    with open(temp_path, "rb") as file_obj:
                        files = {"file": file_obj}
                        upload = await httpx.post(upload_url, files=files)
                        upload_data = upload.json()

                    doc_data = (await message.ctx_api.request(
                        "docs.save",
                        {
                            "file": upload_data["file"],
                            "title": f"report_{rfq_id}.xlsx",
                        },
                    )).get("response", {})

                    status = await self.pg.get_rfq_status(rfq_id)
                    await message.answer(
                        f"Отчёт по заявке #{rfq_id}\n"
                        f"Позиций: {status['total']} | Победителей: {status['winners']}",
                        attachment=f"doc{doc_data['doc']['owner_id']}_{doc_data['doc']['id']}",
                    )

                    os.unlink(temp_path)
                else:
                    await message.answer(
                        f"Ошибка генерации отчёта (код {resp.status_code})"
                    )
        except Exception as e:
            logger.exception(f"Report generation failed: {e}")
            await message.answer("Ошибка при генерации отчёта. Попробуйте позже.")

    async def new_rfq_handler(self, message: Message):
        _ctx_set("state", "waiting_file")
        await message.answer(
            "Загрузите Excel-файл (.xlsx) со спецификацией.\n\n"
            "Файл должен содержать столбцы:\n"
            "  [Наименование МТР] — что нужно купить\n"
            "  [Количество] — сколько единиц\n"
            "  [Срок поставки] — дата (25.03.2026 или 25 Mar 2026)\n\n"
            "Максимум 100 позиций за раз.",
            keyboard=cancel(),
        )

    async def file_handler(self, message: Message):
        state = _ctx_get("state")
        if state != "waiting_file":
            return

        doc = None
        for attachment in message.attachments:
            if attachment.type.value == "doc":
                doc = attachment.doc
                break

        if not doc:
            await message.answer("Прикрепите Excel-файл (.xlsx).", keyboard=cancel())
            return

        if not doc.title.endswith(".xlsx"):
            await message.answer("Поддерживается только формат .xlsx.", keyboard=cancel())
            return

        async with httpx.AsyncClient() as client:
            resp = await client.get(
                doc.url,
                headers={"User-Agent": "Mozilla/5.0"},
                follow_redirects=True,
            )

        content = resp.content

        if len(content) < 100 or content[:2] != b"PK":
            try:
                api_resp = await message.ctx_api.request(
                    "docs.getDownloadUrl", {"doc_id": doc.id}
                )
                dl_url = api_resp.get("link", "")
                if dl_url:
                    async with httpx.AsyncClient() as client2:
                        resp2 = await client2.get(
                            dl_url,
                            headers={"User-Agent": "Mozilla/5.0"},
                            follow_redirects=True,
                        )
                        if resp2.status_code == 200:
                            content = resp2.content
            except Exception:
                pass

        if len(content) < 100 or content[:2] != b"PK":
            await message.answer(
                "Файл повреждён или это не Excel. Проверьте формат .xlsx.",
                keyboard=cancel(),
            )
            return

        await message.answer("Начинаю обработку файла...", keyboard=cancel())

        try:
            items, city, total_budget = self.parser.parse(content)
        except Exception as e:
            await message.answer(f"Ошибка при обработке файла: {e}", keyboard=cancel())
            return

        if len(items) > 100:
            await message.answer("Слишком много позиций — максимум 100.", keyboard=cancel())
            return

        if len(items) == 0:
            await message.answer(
                "В файле не найдено данных. Проверьте формат.",
                keyboard=cancel(),
            )
            return

        preview_lines = []
        for i, it in enumerate(items[:5]):
            d = it["deadline"]
            if isinstance(d, datetime):
                deadline_str = d.strftime("%d.%m.%Y")
            else:
                deadline_str = str(d)
            preview_lines.append(
                f"{i+1}. {it['name'][:40]} — {it['qty']} {it.get('unit', 'шт')} — {deadline_str}"
            )

        summary = f"Найдено {len(items)} позиций:\n\n" + "\n".join(preview_lines)
        if len(items) > 5:
            summary += f"\n  ...и ещё {len(items) - 5} позиций"

        summary += f"\n\nГород: {city or 'не указан'}"
        if total_budget:
            try:
                summary += f"\nБюджет: {float(total_budget):,.2f}"
            except (ValueError, TypeError):
                summary += f"\nБюджет: {total_budget}"

        _ctx_set("pending_items", items)
        _ctx_set("pending_city", city or "Москва")
        _ctx_set("pending_budget", total_budget)

        await message.answer(
            summary + "\n\nВсе верно? Создать заявку?",
            keyboard=confirm_create(),
        )
        _ctx_set("state", "confirm_rfq")

    async def confirm_handler(self, message: Message):
        state = _ctx_get("state")
        if state != "confirm_rfq":
            return

        text = message.text.lower().strip()
        if text in ("да, создать",):
            items = _ctx_get("pending_items")
            city = _ctx_get("pending_city")
            budget = _ctx_get("pending_budget")
            user_vk_id = message.from_id

            await message.answer("Создаю заявку...", keyboard=main_menu())

            rfq_id = await self.pg.create_rfq(
                items, city, budget, created_by_vk=user_vk_id
            )
            await self.redis.publish_new_rfq(rfq_id, items)

            _ctx_clear("state", "pending_items", "pending_city", "pending_budget")

            await message.answer(
                f"Заявка #{rfq_id} создана!\n\n"
                f"Позиций: {len(items)}\n"
                f"Город: {city}\n\n"
                "Поиск поставщиков запущен. Ориентировочное время "
                "40-60 минут.\n"
                "Я пришлю уведомления по мере поступления котировок.",
                keyboard=main_menu(),
            )
        elif text in ("загрузить другой", "загрузить новый"):
            _ctx_clear("state", "pending_items", "pending_city", "pending_budget")
            await self.new_rfq_handler(message)
        else:
            _ctx_clear("state", "pending_items", "pending_city", "pending_budget")
            await message.answer(
                "Создание заявки отменено.", keyboard=main_menu()
            )

    async def cancel_handler(self, message: Message):
        _ctx_clear(
            "state", "pending_items", "pending_city", "pending_budget",
            "current_rfq_id", "viewing_rfq", "viewing_index",
        )
        await message.answer(
            "Отменено. Возвращаюсь в главное меню:",
            keyboard=main_menu(),
        )

    async def _show_rfq_detail(self, message: Message, rfq_id: int):
        user = await self.pg.get_user(message.from_id)
        if not user:
            await message.answer("Напишите «начать», чтобы начать.", keyboard=main_menu())
            return

        rfq = await self.pg.get_rfq_by_id(rfq_id)
        if not rfq:
            await message.answer(f"Заявка #{rfq_id} не найдена.", keyboard=main_menu())
            return

        if rfq.get("created_by_vk") != message.from_id:
            await message.answer("У вас нет доступа к этой заявке.", keyboard=main_menu())
            return

        _ctx_set("current_rfq_id", rfq_id)

        status = await self.pg.get_rfq_status(rfq_id)
        total = status["total"]
        winners = status["winners"]
        ready = winners == total and total > 0

        lines = [
            f"Заявка #{rfq_id}\n",
            f"Позиций: {total}  |  Победителей: {winners}\n",
            f"Город: {rfq.get('city', '—')}\n",
        ]

        if ready:
            lines.append("Статус: завершена")
        else:
            lines.append("Статус: в работе")

        await message.answer("\n".join(lines), keyboard=rfq_detail(rfq_id))

    async def _show_items(self, message: Message):
        rfq_id = _ctx_get("current_rfq_id")
        if not rfq_id:
            await message.answer("Сначала выберите заявку.", keyboard=main_menu())
            return
        items = await self.pg.get_rfq_items_status(rfq_id)
        if not items:
            await message.answer("Позиции не найдены.", keyboard=rfq_detail(rfq_id))
            return
        lines = [f"Заявка #{rfq_id}\n"]
        for i, item in enumerate(items, 1):
            icon = "+" if item["winner_count"] > 0 else "  "
            lines.append(f"{i}. {item['name'][:55]} [{icon}]\n")
        await message.answer("\n".join(lines), keyboard=rfq_detail(rfq_id))

    async def _toggle_notifications(self, message: Message):
        rfq_id = _ctx_get("current_rfq_id")
        if not rfq_id:
            await message.answer("Сначала выберите заявку.", keyboard=main_menu())
            return
        key = f"notify:{message.from_id}:{rfq_id}"
        current = await self.redis.get(key)
        if current:
            await self.redis.delete(key)
            await message.answer(
                f"Уведомления по заявке #{rfq_id} отключены.",
                keyboard=rfq_detail(rfq_id),
            )
        else:
            await self.redis.set(key, "1")
            await message.answer(
                f"Уведомления по заявке #{rfq_id} включены.",
                keyboard=rfq_detail(rfq_id),
            )

    async def _navigate_items(self, text: str, message: Message):
        view_rfq = _ctx_get("viewing_rfq")
        view_idx = _ctx_get("viewing_index", 0)
        if not view_rfq:
            await message.answer("Нет активного просмотра.", keyboard=main_menu())
            return
        items = await self.pg.get_rfq_items_status(view_rfq)
        if not items:
            await message.answer("Нет позиций.", keyboard=rfq_detail(view_rfq))
            return
        total = len(items)
        if text == "< назад" and view_idx > 0:
            view_idx -= 1
        elif text in ("вперёд >", "вперед >") and view_idx < total - 1:
            view_idx += 1
        else:
            await message.answer("Это крайняя позиция.", keyboard=rfq_detail(view_rfq))
            return
        _ctx_set("viewing_index", view_idx)
        item = items[view_idx]
        try:
            quotes = await self.pg.get_rfq_quotes_for_item(item["id"])
        except Exception:
            quotes = []
        lines = [
            f"Позиция: {item['name']}\n"
            f"  Кол-во: {item['qty']} {item.get('unit', 'шт')}\n"
            f"  Срок: {item['deadline']}\n"
        ]
        if item.get("supplier_count"):
            lines.append(f"  Поставщиков: {item['supplier_count']}\n")
        if item.get("min_price"):
            lines.append(f"  Мин. цена: {item['min_price']:,.2f}\n")
        if quotes:
            lines.append("Котировки:")
            for q in quotes[:5]:
                winner = " +" if q["is_winner"] else ""
                lines.append(
                    f"  {q['supplier_name']}: {q['price']:,.2f} ({q['delivery_days']} дн.){winner}"
                )
        await message.answer(
            "\n".join(lines).strip(),
            keyboard=item_nav(view_rfq, view_idx, total),
        )

    async def settings_handler(self, message: Message):
        user = await self.pg.get_user(message.from_id)
        if not user:
            await message.answer("Напишите «начать», чтобы начать.", keyboard=main_menu())
            return

        await message.answer(
            "Настройки профиля компании.\n\n"
            "Эти данные будут добавлены в отчёт и использованы при заказе.",
            keyboard=profile_menu(),
        )

    async def show_profile_handler(self, message: Message):
        profile = await self.pg.get_profile(message.from_id)
        if not profile or not any([profile.company_name, profile.inn, profile.phone]):
            await message.answer(
                "Профиль не заполнен.\n\nНажмите «Заполнить профиль», чтобы добавить реквизиты.",
                keyboard=profile_menu(),
            )
            return

        fields = [
            ("Организация", profile.company_name),
            ("ИНН", profile.inn),
            ("КПП", profile.kpp),
            ("Адрес", profile.address),
            ("Телефон", profile.phone),
            ("Email", profile.email),
            ("Контактное лицо", profile.contact_person),
        ]
        lines = ["Ваш профиль:\n"]
        for label, value in fields:
            lines.append(f"  {label}: {value or '—'}")
        lines.append(
            "\nЧтобы изменить одно поле, отправьте его название\n"
            "(например «Телефон» или «Email»).\n"
            "Или нажмите «Заполнить профиль» для полного перезаполнения."
        )
        _ctx_set("state", "profile_edit_select")
        await message.answer("\n".join(lines), keyboard=profile_menu())

    _PROFILE_FIELDS = [
        ("company_name", "Название организации"),
        ("inn", "ИНН"),
        ("kpp", "КПП"),
        ("address", "Юридический адрес"),
        ("phone", "Телефон"),
        ("email", "Email"),
        ("contact_person", "Контактное лицо"),
    ]

    _FIELD_VALIDATORS = {
        "inn": lambda v: bool(re.match(r"^(?:\d{10}|\d{12})$", v)),
        "kpp": lambda v: bool(re.match(r"^\d{9}$", v)),
        "email": lambda v: bool(re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", v)),
        "phone": lambda v: bool(re.match(r"^[\d\s\-\+\(\)]{10,20}$", v)),
    }

    _FIELD_ERRORS = {
        "inn": "ИНН должен содержать 10 или 12 цифр",
        "kpp": "КПП должен содержать 9 цифр",
        "email": "Неверный формат Email",
        "phone": "Телефон должен содержать от 10 до 15 цифр",
    }

    _FIELD_LABELS = dict(_PROFILE_FIELDS)

    async def start_profile_wizard(self, message: Message):
        _ctx_set("profile_index", 0)
        _ctx_set("profile_data", {})
        _ctx_set("state", "profile_company_name")
        await self._ask_question(message, 0)

    async def _ask_question(self, message: Message, idx: int):
        _, field_label = self._PROFILE_FIELDS[idx]
        await message.answer(
            f"Заполнение профиля. Шаг {idx + 1} из {len(self._PROFILE_FIELDS)}.\n"
            f"Введите «{field_label}»:\n\n"
            "Отправьте «-» чтобы пропустить, или «Отмена» чтобы выйти.",
            keyboard=cancel(),
        )

    async def _handle_profile_input(self, message: Message):
        text = message.text.strip()

        state = _ctx_get("state")

        # edit mode: let the user pick which field to edit
        if state == "profile_edit_select":
            lower = text.lower()
            match = None
            for field_key, field_label in self._PROFILE_FIELDS:
                if field_label.lower() == lower or field_key == lower:
                    match = field_key
                    break
            if match:
                _ctx_set("profile_edit_field", match)
                _ctx_set("state", "profile_edit_value")
                await message.answer(
                    f"Введите новое значение для «{self._FIELD_LABELS[match]}»:\n\n"
                    "Отправьте «-» чтобы оставить без изменений, или «Отмена».",
                    keyboard=cancel(),
                )
            else:
                await message.answer(
                    "Поле не найдено. Напишите точное название поля из списка выше.",
                    keyboard=profile_menu(),
                )
            return

        # edit mode: save the value for
        if state == "profile_edit_value":
            if text.lower() in ("отмена", "назад"):
                _ctx_clear("state", "profile_edit_field")
                await message.answer("Изменение отменено.", keyboard=profile_menu())
                return

            field_key = _ctx_get("profile_edit_field")
            if text != "-":
                err = self._validate_field(field_key, text)
                if err:
                    await message.answer(err + "\n\nПопробуйте снова или поставьте «-».", keyboard=cancel())
                    return
                profile = await self.pg.get_profile(message.from_id)
                if profile:
                    setattr(profile, field_key, text)
                else:
                    profile = UserProfile(vk_id=message.from_id, **{field_key: text})
                await self.pg.upsert_profile(profile)

            _ctx_clear("state", "profile_edit_field")
            await message.answer("Профиль обновлён!", keyboard=profile_menu())
            return

        # regular wizard flow
        if text.lower() in ("отмена", "назад"):
            _ctx_clear("state", "profile_index", "profile_data")
            await message.answer(
                "Заполнение профиля отменено.", keyboard=profile_menu(),
            )
            return

        idx = _ctx_get("profile_index", 0)
        data = _ctx_get("profile_data", {})

        field_key, field_label = self._PROFILE_FIELDS[idx]
        if text != "-":
            err = self._validate_field(field_key, text)
            if err:
                await message.answer(err + "\n\nПопробуйте снова или поставьте «-» чтобы пропустить.", keyboard=cancel())
                return
            data[field_key] = text

        next_idx = idx + 1
        if next_idx >= len(self._PROFILE_FIELDS):
            data["vk_id"] = message.from_id
            profile = UserProfile(**data)
            await self.pg.upsert_profile(profile)
            _ctx_clear("state", "profile_index", "profile_data", "profile_edit_field")
            await message.answer(
                "Профиль сохранён!", keyboard=profile_menu(),
            )
            return

        _ctx_set("profile_index", next_idx)
        _ctx_set("profile_data", data)
        _ctx_set("state", f"profile_{self._PROFILE_FIELDS[next_idx][0]}")
        await self._ask_question(message, next_idx)

    def _validate_field(self, field_key: str, value: str) -> Optional[str]:
        if field_key not in self._FIELD_VALIDATORS:
            return None
        if not self._FIELD_VALIDATORS[field_key](value):
            return self._FIELD_ERRORS[field_key]
        return None

    async def _get_or_create_user(self, vk_id: int, vk_name: str) -> User:
        user = await self.pg.get_user(vk_id)
        if not user:
            user = await self.pg.create_user(vk_id, vk_name)
        return user