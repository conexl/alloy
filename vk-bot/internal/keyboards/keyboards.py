"""VK keyboards — modern clean layout, message-based flow."""

from vkbottle import Keyboard, KeyboardButtonColor, Text, OpenLink

# URL Mini App (заменить на реальный URL после деплоя)
MINI_APP_URL = "https://vk.com/app238402953"


def main_menu():
    return (
        Keyboard(one_time=False, inline=False)
        .add(Text("Новая заявка"), color=KeyboardButtonColor.POSITIVE)
        .row()
        .add(Text("Мои заявки"), color=KeyboardButtonColor.PRIMARY)
        .add(Text("Статус"), color=KeyboardButtonColor.PRIMARY)
        .row()
        .add(OpenLink(MINI_APP_URL, "📱 Открыть приложение"), color=KeyboardButtonColor.PRIMARY)
        .row()
        .add(Text("Настройки"), color=KeyboardButtonColor.PRIMARY)
        .add(Text("Помощь"), color=KeyboardButtonColor.PRIMARY)
    )


def profile_menu():
    return (
        Keyboard(one_time=False, inline=False)
        .add(Text("Заполнить профиль"), color=KeyboardButtonColor.POSITIVE)
        .add(Text("Посмотреть профиль"), color=KeyboardButtonColor.PRIMARY)
        .row()
        .add(Text("Главное меню"), color=KeyboardButtonColor.PRIMARY)
    )


def confirm_create():
    return (
        Keyboard(one_time=True, inline=False)
        .add(Text("Да, создать"), color=KeyboardButtonColor.POSITIVE)
        .row()
        .add(Text("Загрузить другой"), color=KeyboardButtonColor.PRIMARY)
        .add(Text("Отмена"), color=KeyboardButtonColor.NEGATIVE)
    )


def cancel():
    return Keyboard(one_time=True, inline=False).add(
        Text("Отмена"), color=KeyboardButtonColor.NEGATIVE
    )


def rfq_list(rfqs: list):
    kb = Keyboard(one_time=False, inline=False)
    for rfq in rfqs[:10]:
        r_id = rfq["id"] if isinstance(rfq, dict) else rfq
        kb.add(Text(f"Заявка #{r_id}"), color=KeyboardButtonColor.PRIMARY)
        kb.row()
    kb.add(Text("Главное меню"), color=KeyboardButtonColor.PRIMARY)
    return kb


def rfq_detail(rfq_id: int):
    return (
        Keyboard(one_time=False, inline=False)
        .add(Text("Статус"), color=KeyboardButtonColor.POSITIVE)
        .add(Text("Позиции"), color=KeyboardButtonColor.PRIMARY)
        .row()
        .add(Text("Скачать отчёт"), color=KeyboardButtonColor.PRIMARY)
        .add(Text("Уведомления"), color=KeyboardButtonColor.PRIMARY)
        .row()
        .add(Text("К списку"), color=KeyboardButtonColor.PRIMARY)
    )


def item_nav(rfq_id: int, current: int, total: int):
    kb = Keyboard(one_time=False, inline=False)
    if current > 0:
        kb.add(Text("< Назад"), color=KeyboardButtonColor.PRIMARY)
    if current < total - 1:
        kb.add(Text("Вперёд >"), color=KeyboardButtonColor.PRIMARY)
    kb.row()
    kb.add(Text("К статусу"), color=KeyboardButtonColor.PRIMARY)
    kb.add(Text("Главное меню"), color=KeyboardButtonColor.PRIMARY)
    return kb


def report_action(rfq_id: int, ready: bool = False):
    kb = Keyboard(one_time=False, inline=False)
    if ready:
        kb.add(Text("Скачать отчёт"), color=KeyboardButtonColor.POSITIVE)
    else:
        kb.add(Text("Статус"), color=KeyboardButtonColor.PRIMARY)
    kb.row()
    kb.add(Text("Назад"), color=KeyboardButtonColor.PRIMARY)
    return kb