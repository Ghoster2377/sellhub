"""Базовый интерфейс адаптера площадки.

Реальные адаптеры (FunPayAdapter, PlayerokAdapter) реализуют один контракт,
чтобы PlatformManager и Store не зависели от конкретной площадки:

    connect(key) -> {"login": str}      # авторизация + проверка ключа
    load_history(store)                 # начальная загрузка заказов/чатов в store
    run_events(store)                   # бесконечный поток живых событий
    send_message(chat, text)            # отправить сообщение в чат площадки
    order_action(order, to_status)      # действие по заказу (выдан/подтверждён/возврат)
    restart() / close()

Все площадки приводятся к единой модели заказа панели:
    {real, ext_id, platform, game, lot, buyer, price, status, mins, chat_ext}
где status: new (оплачен) | sent (выдан) | done (завершён) | dispute (спор/возврат).
"""


class BaseAdapter:
    """Заглушка: ничего не делает и никаких событий не генерирует.

    Используется, когда адаптер площадки не создан. Реальные данные
    приходят только от FunPayAdapter / PlayerokAdapter.
    """

    name = "none"

    async def start(self):
        return
