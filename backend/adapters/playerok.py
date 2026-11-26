"""Адаптер Playerok — РЕАЛЬНОЕ подключение (фаза 1, исправленный).

Библиотека: aiosellers (access-токен = cookie `token`; GraphQL + WebSocket).

Исправления по итогам живого теста:
  * история сделок берётся RAW-запросом get_deals: в ответе уже встроены
    item (название+цена) и user (покупатель) — entity-метод get_item() для
    проданных (удалённых) лотов возвращает None;
  * продажи отделяются от покупок: direction == OUT (и/или контрагент != я);
  * обход бага aiosellers 0.1.10: Playerok возвращает item.category объектом,
    а схема ждёт строку → ValidationError при разборе сообщений чата.
    Лечится нормализацией входящих данных перед разбором (_normalize_payload);
  * чат создаётся в панели даже если история сообщений не разобралась.

Возможности: живые события (ITEM_PAID, ITEM_SENT, DEAL_CONFIRMED, проблемы,
сообщения, отзывы), отправка сообщений в чат, deal.complete()/confirm().
Автовыдача не реализована (по запросу владельца).
"""
import logging
from datetime import datetime, timezone

from ..store import fmt

log = logging.getLogger("sellhub.playerok")

STATUS_MAP = {
    "PAID": "new",
    "PENDING": None,
    "SENT": "sent",
    "CONFIRMED": "done",
    "CONFIRMED_AUTOMATICALLY": "done",
    "ROLLED_BACK": "dispute",
}

DEAL_EVENTS = {
    "NEW_DEAL", "ITEM_PAID", "ITEM_SENT", "DEAL_CONFIRMED",
    "DEAL_CONFIRMED_AUTOMATICALLY", "DEAL_ROLLED_BACK",
    "DEAL_HAS_PROBLEM", "DEAL_STATUS_CHANGED",
}
PROBLEM_EVENTS = {"DEAL_HAS_PROBLEM", "DEAL_ROLLED_BACK"}

_SCHEMAS_PATCHED = False


def _normalize_payload(obj):
    """Playerok присылает item.category / item.obtainingType объектами, часто
    без id, а схемы aiosellers ждут строку-id. Превращаем такие объекты в None
    (id нам не нужен, важны name/price/text). Объекты с id не трогаем — их
    штатный before-валидатор Item сам превращает в строку."""
    if isinstance(obj, dict):
        for k in ("category", "obtainingType"):
            v = obj.get(k)
            if isinstance(v, dict) and not v.get("id"):
                obj[k] = None
        for k in ("rawPrice", "price"):
            v = obj.get(k)
            if isinstance(v, float):
                obj[k] = int(round(v))
        for v in obj.values():
            if isinstance(v, (dict, list)):
                _normalize_payload(v)
    elif isinstance(obj, list):
        for v in obj:
            if isinstance(v, (dict, list)):
                _normalize_payload(v)
    return obj


def _patch_schemas():
    """Обход бага aiosellers 0.1.10 (категория-объект в item): оборачиваем
    __init__ и model_validate всех pydantic-схем Playerok нормализацией
    входящих данных. Пересборка схем (model_rebuild) не помогала: pydantic
    встраивает в ChatMessage старую копию схемы Item."""
    global _SCHEMAS_PATCHED
    if _SCHEMAS_PATCHED:
        return
    try:
        import importlib
        import pkgutil
        import pydantic
        import aiosellers.playerok.schemas as pkg

        modules = [pkg]
        for mi in pkgutil.iter_modules(pkg.__path__):
            try:
                modules.append(importlib.import_module(f"{pkg.__name__}.{mi.name}"))
            except Exception:
                pass

        def make_init(orig):
            def __init__(self, **data):
                orig(self, **_normalize_payload(data))
            return __init__

        def make_mv(orig):
            def mv(cls, data, **kw):
                if isinstance(data, (dict, list)):
                    data = _normalize_payload(data)
                return orig(cls, data, **kw)
            return classmethod(mv)

        count = 0
        seen = set()
        for mod in modules:
            for obj in list(vars(mod).values()):
                if not (isinstance(obj, type) and issubclass(obj, pydantic.BaseModel)):
                    continue
                if obj in seen or getattr(obj, "_sellhub_norm", False):
                    continue
                seen.add(obj)
                obj.__init__ = make_init(obj.__init__)
                obj.model_validate = make_mv(obj.model_validate.__func__)
                obj._sellhub_norm = True
                count += 1
        _SCHEMAS_PATCHED = True
        log.info("Playerok payload normalizer installed on %d schemas", count)
    except Exception as e:
        log.warning("patch schemas: %s", e)


def _direction_str(v) -> str:
    return str(getattr(v, "value", getattr(v, "name", v)))


def _status_str(v) -> str:
    return str(getattr(v, "value", getattr(v, "name", v)))


def _mins_since(dt) -> int:
    try:
        if dt is None:
            return 0
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return max(0, int((datetime.now(timezone.utc) - dt).total_seconds() // 60))
    except Exception:
        return 0


class PlayerokAdapter:
    platform = "playerok"
    title = "Playerok"

    def __init__(self):
        self.client = None
        self.key = None
        self.ua = ""
        self.my_id = None
        self.login = None
        self._chat_started = {}     # ext_id чата -> дата начала (для дат сделок)

    # ---------- подключение ----------
    async def connect(self, token: str, user_agent: str | None = None):
        from aiosellers.playerok import Playerok, PlayerokClientConfig

        _patch_schemas()
        self.key = token
        self.ua = (user_agent or "").strip()
        # user_agent важен: Cloudflare на playerok.com сверяет его с тем
        # браузером, где был получен токен, и режет «чужие» запросы
        self.client = Playerok(PlayerokClientConfig(
            access_token=token, user_agent=self.ua or None))
        await self.client.start()               # при неверном токене бросит Unauthorized
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
        return await self.connect(self.key)

    # ---------- маппинг ----------
    def _schema_to_order(self, s):
        """ItemDeal (raw-схема) -> заказ панели. Только продажи (direction=OUT)."""
        if _direction_str(s.direction) != "OUT":
            return None
        status = STATUS_MAP.get(_status_str(s.status))
        if not status:
            return None
        item = s.item
        user = s.user
        chat_ext = str(s.chat.id) if getattr(s, "chat", None) and getattr(s.chat, "id", None) else None
        # у списка сделок нет даты сделки — берём дату начала привязанного чата
        dt = getattr(s, "created_at", None) or (self._chat_started or {}).get(chat_ext)
        return {
            "real": True,
            "ext_id": str(s.id),
            "platform": "playerok",
            "game": "Playerok",
            "lot": (getattr(item, "name", None) or f"Сделка {s.id}")[:120] if item else f"Сделка {s.id}",
            "buyer": (getattr(user, "username", None) or "?") if user else "?",
            "price": round(getattr(item, "price", 0) or 0) if item else 0,
            "status": status,
            "mins": _mins_since(dt),
            "auto": False,
            "chat_ext": chat_ext,
        }

    async def _deal_to_order(self, d, force_status=None):
        """Deal (entity из событий) -> заказ панели."""
        status = force_status or STATUS_MAP.get(_status_str(d.status))
        if not status:
            return None
        lot, price, buyer = None, 0, None
        try:
            item = await d.get_item()
            if item is not None:
                lot = (getattr(item, "name", None) or None)
                lot = lot[:120] if lot else None
                price = getattr(item, "price", 0) or 0
        except Exception as e:
            log.debug("deal %s get_item: %s", getattr(d, "id", "?"), e)
        try:
            u = await d.get_user()
            if u is not None:
                buyer = getattr(u, "username", None)
        except Exception as e:
            log.debug("deal %s get_user: %s", getattr(d, "id", "?"), e)
        if buyer == self.login:      # это моя покупка, не продажа
            return None
        return {
            "real": True,
            "ext_id": str(d.id),
            "platform": "playerok",
            "game": "Playerok",
            "lot": lot,               # None -> upsert не затрёт известное имя
            "buyer": buyer or "?",
            "price": price,
            "status": status,
            "mins": 0,
            "auto": False,
            "chat_ext": str(d.chat_id) if getattr(d, "chat_id", None) else None,
        }

    def _msg_from(self, m) -> str:
        direction = _direction_str(getattr(m, "direction", ""))
        if direction == "OUT":
            return "me"
        if direction == "IN":
            return "buyer"
        # у сообщений чата направления нет — смотрим на автора
        u = getattr(m, "user", None)
        uname = getattr(u, "username", None) if u else None
        uid = getattr(u, "id", None) if u else None
        if uname and uname == self.login:
            return "me"
        if uid and self.my_id and str(uid) == str(self.my_id):
            return "me"
        if uname or uid:
            return "buyer"
        return "auto"      # системные события ({{ITEM_PAID}} и т.п.)

    # ---------- начальная загрузка ----------
    async def load_history(self, store):
        store.clear_platform_demo("playerok")
        # 1) чаты: создаём чат, историю пробуем отдельно, копим даты начала чатов
        try:
            try:
                chats = await self.client.chats.list(limit=30)
            except TypeError:
                chats = await self.client.chats.list()
            for ch in chats[:30]:
                try:
                    if getattr(ch, "is_system", False):
                        continue
                    self._chat_started[str(ch.id)] = getattr(ch, "started_at", None)
                    user = getattr(ch, "user", None) or getattr(ch, "users", None)
                    if isinstance(user, list):
                        user = next((u for u in user if getattr(u, "username", None) != self.login), None)
                    buyer = (getattr(user, "username", None) if user else None) \
                        or getattr(ch, "name", None) or "Покупатель"
                    c = store.chat_by_ext("playerok", ch.id, buyer=buyer)
                    try:
                        msgs = await ch.get_messages(limit=15)
                        for m in sorted(msgs, key=lambda x: getattr(x, "created_at", None) or 0):
                            if not m.text:
                                continue
                            if m.text.startswith("{{"):     # служебные маркеры сделок
                                continue
                            frm = self._msg_from(m)
                            if frm == "auto":
                                continue
                            c["msgs"].append({"from": frm, "text": m.text,
                                              "mins": _mins_since(getattr(m, "created_at", None))})
                        c["msgs"] = c["msgs"][-60:]
                    except Exception as e:
                        log.warning("Playerok messages chat %s: %s", getattr(ch, "id", "?"), e)
                    unread = getattr(ch, "unread_messages_counter", 0) or 0
                    if unread:
                        c["unread"] = max(c.get("unread", 0), unread)
                except Exception as e:
                    log.warning("Playerok chat %s: %s", getattr(ch, "id", "?"), e)
        except Exception as e:
            log.warning("Playerok chats.list: %s", e)
        # 2) сделки: raw-запрос (item и user уже встроены в ответ)
        try:
            cursor, fetched = None, 0
            while fetched < 200:      # глубже история -> честнее статистика/график
                resp = await self.client._raw.deals.get_deals(
                    user_id=self.my_id, count=24, after_cursor=cursor)
                if resp is None or not resp.deals:
                    break
                for s in resp.deals:
                    mo = self._schema_to_order(s)
                    if mo:
                        store.upsert_order(mo)
                fetched += len(resp.deals)
                if not resp.page_info.has_next_page:
                    break
                cursor = resp.page_info.end_cursor
        except Exception as e:
            log.warning("Playerok deals (raw): %s", e)
        await store.broadcast()

    # ---------- живой поток событий ----------
    async def run_events(self, store):
        async for ev in self.client.listen():
            t = _status_str(getattr(ev, "type", ""))
            try:
                if t in DEAL_EVENTS:
                    deal = getattr(ev, "deal", None)
                    if deal is None:
                        continue
                    force = "dispute" if t in PROBLEM_EVENTS else None
                    mo = await self._deal_to_order(deal, force_status=force)
                    if not mo:
                        continue
                    res, order = store.upsert_order(mo)
                    if res == "new" and t in ("NEW_DEAL", "ITEM_PAID"):
                        store.push_alert("🛒",
                                         f"Новый заказ (Playerok): {mo['lot'] or 'сделка'} — {fmt(mo['price'])}", "ok")
                        await store.broadcast({"text": f"Новый заказ (Playerok) — {mo['lot'] or 'сделка'} · {fmt(mo['price'])}",
                                               "kind": "ok", "icon": "🛒"})
                    else:
                        await store.broadcast()
                elif t == "NEW_MESSAGE":
                    m = getattr(ev, "message", None)
                    chat = getattr(ev, "chat", None)
                    if m is None or not m.text or m.text.startswith("{{"):
                        continue
                    frm = self._msg_from(m)
                    if frm == "auto":
                        continue
                    ext_chat = getattr(chat, "id", None) or getattr(m, "chat_id", None)
                    if not ext_chat:
                        continue
                    user = getattr(chat, "user", None) if chat else None
                    buyer = (getattr(user, "username", None) if user else None) or None
                    store.upsert_message("playerok", ext_chat, frm, m.text,
                                         buyer=buyer, unread=(frm == "buyer"))
                    await store.broadcast(
                        {"text": f"Playerok · {buyer or 'чат'}: {m.text[:60]}", "kind": "", "icon": "💬"}
                        if frm == "buyer" else None)
                elif t == "NEW_REVIEW":
                    deal = getattr(ev, "deal", None)
                    review = getattr(deal, "review", None) if deal else None
                    rating = getattr(review, "rating", None)
                    store.push_alert("⭐", f"Новый отзыв на Playerok" + (f" ({rating}★)" if rating else ""), "ok")
                    await store.broadcast()
            except Exception as e:
                log.warning("Playerok event %s: %s", t, e)

    # ---------- действия ----------
    async def send_message(self, chat, text):
        await self.client.chats.send_message(str(chat["ext_id"]), text=text)

    async def order_action(self, order, to):
        deal_id = order["ext_id"]
        if to == "sent":
            await self.client.deals.complete(deal_id)   # «товар отправлен»
        elif to == "done":
            await self.client.deals.confirm(deal_id)    # подтвердить сделку
