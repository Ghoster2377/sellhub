"""Адаптер FunPay — РЕАЛЬНОЕ подключение (фаза 1).

Библиотека: aiosellers (асинхронный клиент FunPay: golden key + внутренние
эндпоинты сайта, polling /runner/ с интервалом ~6 с — так же, как это делают
проверенные боты FunPayAPI/FunPay Cardinal).

Возможности сейчас:
  * авторизация по golden key, профиль (username/id);
  * загрузка недавних продаж и чатов с историей сообщений;
  * живой поток: новые заказы, смена статусов, новые сообщения, отзывы;
  * отправка сообщений в чат FunPay прямо из панели;
  * возврат по заказу (refund) из панели.
Пометка «выдан»/«завершён» для FunPay локальная: реальный статус на сайте
меняет покупатель/площадка, и он синхронизируется обратно событиями.

Автовыдача товара намеренно не реализована (по запросу владельца — позже).
"""
import logging

from ..store import fmt

log = logging.getLogger("sellhub.funpay")

# OrderStatuses (aiosellers) -> статус канбана панели
STATUS_MAP = {
    "PAID": "new",               # оплачен, ждёт выдачи
    "CLOSED": "done",            # завершён
    "REFUNDED": "dispute",
    "PARTIALLY_REFUNDED": "dispute",
    "UNPAID": None,              # неоплаченные не показываем
}

ORDER_EVENTS = {
    "INITIAL_ORDER", "NEW_ORDER", "ORDER_STATUS_CHANGED",
    "ORDER_CLOSED", "ORDER_REFUNDED", "ORDER_PARTIALLY_REFUNDED",
}


class FunPayAdapter:
    platform = "funpay"
    title = "FunPay"

    def __init__(self):
        self.client = None
        self.key = None
        self.user_agent = None
        self.my_id = None
        self.login = None

    # ---------- подключение ----------
    async def connect(self, key: str, user_agent: str | None = None):
        from aiosellers.funpay import FunPay, FunPayClientConfig

        self.key = key
        # ВАЖНО: FunPay привязывает сессию к User-Agent браузера, из которого
        # взят golden key (cookie). При несовпадении UA сессия сбрасывается.
        self.user_agent = (user_agent or "").strip() or None
        self.client = FunPay(FunPayClientConfig(
            golden_key=key, locale="ru", poll_interval=6.0,
            user_agent=self.user_agent))
        await self.client.start()               # при неверном ключе бросит UnauthorizedError
        me = await self.client.account.me()
        self.my_id = me.id
        self.login = me.username
        self.avatar = getattr(me, "avatar_url", None) or ""
        return {"login": self.login, "avatar": self.avatar}

    async def close(self):
        try:
            if self.client is not None:
                await self.client.close()
        except Exception:
            pass
        self.client = None

    async def restart(self):
        await self.close()
        return await self.connect(self.key, self.user_agent)

    # ---------- маппинг ----------
    def _msg_from(self, m) -> str:
        if getattr(m, "is_auto_reply", False):
            return "auto"
        if getattr(m, "by_bot", False) or getattr(m, "author_id", None) == self.my_id:
            return "me"
        return "buyer"

    def map_order(self, o):
        status = STATUS_MAP.get(getattr(o.status, "name", str(o.status)))
        if not status:
            return None
        return {
            "real": True,
            "ext_id": str(o.id),
            "platform": "funpay",
            "game": getattr(o, "subcategory_name", None) or "FunPay",
            "lot": (getattr(o, "description", None) or "Заказ")[:120],
            "buyer": getattr(o, "buyer_username", None) or "?",
            "price": round(getattr(o, "price", 0) or 0),
            "status": status,
            "mins": 0,
            "auto": False,
            "chat_ext": str(o.chat_id) if getattr(o, "chat_id", None) else None,
        }

    # ---------- начальная загрузка ----------
    async def load_history(self, store):
        store.clear_platform_demo("funpay")
        try:
            _, orders = await self.client.orders.list(limit=25)
            for o in orders:
                mo = self.map_order(o)
                if mo:
                    store.upsert_order(mo)
        except Exception as e:
            log.warning("FunPay orders.list: %s", e)
        try:
            chats = await self.client.chats.list()
            for ch in chats[:12]:
                try:
                    msgs = await ch.get_messages(limit=15)
                    c = store.chat_by_ext("funpay", ch.id, buyer=ch.name)
                    for m in sorted(msgs, key=lambda x: x.id or 0):
                        if not m.text:
                            continue
                        c["msgs"].append({"from": self._msg_from(m), "text": m.text, "mins": 0})
                    c["msgs"] = c["msgs"][-60:]
                    if getattr(ch, "unread", False):
                        c["unread"] = max(c.get("unread", 0), 1)
                except Exception as e:
                    log.warning("FunPay chat %s: %s", getattr(ch, "id", "?"), e)
        except Exception as e:
            log.warning("FunPay chats.list: %s", e)
        await store.broadcast()

    # ---------- живой поток событий ----------
    async def run_events(self, store):
        async for ev in self.client.listen(purchases=False):
            t = getattr(getattr(ev, "type", None), "name", str(getattr(ev, "type", "")))
            try:
                if t in ORDER_EVENTS:
                    mo = self.map_order(ev.order)
                    if not mo:
                        continue
                    res, order = store.upsert_order(mo)
                    if res == "new" and t == "NEW_ORDER":
                        store.push_alert("🛒", f"Новый заказ (FunPay): {mo['lot']} — {fmt(mo['price'])}", "ok")
                        await store.broadcast({"text": f"Новый заказ (FunPay) — {mo['lot']} · {fmt(mo['price'])}",
                                               "kind": "ok", "icon": "🛒"})
                    else:
                        await store.broadcast()
                elif t == "NEW_MESSAGE":
                    m = ev.message
                    if not m.text:
                        continue
                    frm = self._msg_from(m)
                    store.upsert_message("funpay", ev.chat.id, frm, m.text,
                                         buyer=ev.chat.name, unread=(frm == "buyer"))
                    await store.broadcast(
                        {"text": f"FunPay · {ev.chat.name}: {m.text[:60]}", "kind": "", "icon": "💬"}
                        if frm == "buyer" else None)
                elif t == "NEW_REVIEW":
                    review = getattr(ev, "review", None)
                    stars = getattr(review, "stars", None)
                    store.push_alert("⭐", f"Новый отзыв на FunPay" + (f" ({stars}★)" if stars else ""), "ok")
                    await store.broadcast()
            except Exception as e:
                log.warning("FunPay event %s: %s", t, e)

    # ---------- действия ----------
    async def send_message(self, chat, text):
        await self.client.chats.send_message(int(chat["ext_id"]), text=text)

    async def order_action(self, order, to):
        if to == "dispute":
            await self.client.orders.refund(order["ext_id"])
        # 'sent'/'done' — локальные отметки (см. докстринг модуля)
