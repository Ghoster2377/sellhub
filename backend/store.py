"""Единое хранилище состояния SellHub.

Store владеет всем состоянием панели (заказы, чаты, уведомления…).

Источник данных ровно один: РЕАЛЬНЫЕ данные подключённых площадок
(адаптеры пишут сюда через upsert_order / upsert_message / chat_by_ext,
см. backend/adapters/). Демо-движок, выдуманные заказы/сообщения/цены
и стартовый демо-набор удалены: если площадка не подключена, её цифры
равны нулю, а не «нарисованы».

Фронтенд получает состояние через GET /api/state и WebSocket /ws,
действия продавца приходят через POST /api/action и маршрутизируются
в PlatformManager (отправка сообщений и действия по сделкам — на площадку).
"""
import asyncio
import copy

from .demo_data import INITIAL, PF_NAMES


def _pct(v) -> float:
    """Процент из настроек: число 0–30 с одним знаком после запятой."""
    try:
        return round(min(30.0, max(0.0, float(v))), 1)
    except (TypeError, ValueError):
        return 0.0


def fmt(n) -> str:
    return f"{int(n):,}".replace(",", " ") + " ₽"


class Store:
    def __init__(self):
        self.state = copy.deepcopy(INITIAL)
        self.listeners: set = set()
        self.manager = None          # PlatformManager, устанавливается в main.lifespan
        self._oid = 200

    # ---------- рассылка ----------
    def snapshot(self):
        """Снимок состояния для панели: ТОЛЬКО реальные данные.

        Демо-заказы/чаты/товары/уведомления сюда не попадают вовсе —
        даже если что-то подобное осталось в состоянии.
        """
        st = copy.deepcopy(self.state)
        st["orders"] = [o for o in st.get("orders", []) if o.get("real")]
        st["chats"] = [c for c in st.get("chats", []) if c.get("real")]
        # товары ведутся: каталог продавца (черновики и выставленные лоты)
        st["alerts"] = [a for a in st.get("alerts", []) if not a.get("demo")]
        st["rules"] = []                        # правила автоматизации не ведутся
        st["pfmode"] = st.get("pfmode", "both")   # режим площадок: both|funpay|playerok
        st["stats"] = self._calc_stats(st)
        return st

    def _calc_stats(self, st):
        """Настоящая статистика по реальным заказам.

        Площадки (Playerok) не отдают дату создания сделки в списке сделок,
        поэтому «выручка сегодня» не честная — её не показываем вовсе.
        Только то, что можно посчитать правдиво: итоговые счётчики и суммы.
        """
        orders = [o for o in st.get("orders", [])
                  if o.get("real") and o.get("platform") in ("funpay", "playerok")]
        active = disputes = rev_total = done_total = 0
        rev_pf = {}
        for o in orders:
            price = o.get("price", 0) or 0
            status = o.get("status")
            if status in ("new", "sent"):
                active += 1
            elif status == "dispute":
                disputes += 1
            elif status == "done":
                done_total += 1
                rev_total += price
                rev_pf[o.get("platform")] = rev_pf.get(o.get("platform"), 0) + price
        chats = [c for c in st.get("chats", []) if c.get("ext_id")]
        fees = st.get("fees", {}) or {}
        wfees = st.get("wfees", {}) or {}
        net_pf = {}
        net_w_pf = {}
        for p, v in rev_pf.items():
            fee = fees.get(p, 0) or 0
            net_pf[p] = round(v * (1 - fee / 100.0))
            # после комиссии вывода средств на карту/кошелёк
            net_w_pf[p] = round(net_pf[p] * (1 - (wfees.get(p, 0) or 0) / 100.0))
        return {
            "active": active, "disputes": disputes,
            "unread": sum(c.get("unread", 0) or 0 for c in chats),
            "chats": len(chats), "orders": len(orders),
            "revTotal": rev_total, "doneTotal": done_total,
            "revPf": rev_pf, "netPf": net_pf,
            "netTotal": sum(net_pf.values()),
            "netWPf": net_w_pf, "netWTotal": sum(net_w_pf.values()),
        }

    async def broadcast(self, toast=None):
        msg = {"type": "state", "state": self.snapshot()}
        if toast:
            msg["toast"] = toast
        dead = []
        for ws in list(self.listeners):
            try:
                await ws.send_json(msg)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.listeners.discard(ws)

    def push_alert(self, icon: str, text: str, kind: str = "warn"):
        self.state["alerts"].insert(0, {"icon": icon, "text": text, "mins": 0, "kind": kind})
        self.state["alerts"] = self.state["alerts"][:30]

    # ---------- реальные данные (пишут адаптеры) ----------
    def next_id(self) -> int:
        self._oid += 1
        return self._oid

    def set_account(self, platform: str, connected: bool, login=None, key=None, error=None,
                    avatar=None):
        acc = self.state["accounts"].setdefault(platform, {})
        acc["connected"] = connected
        if login:
            acc["login"] = login
        if key:
            acc["key"] = key
        if avatar is not None:
            acc["avatar"] = avatar
        acc["error"] = error or ""

    def clear_platform_demo(self, platform: str):
        """Служебная чистка: убрать из состояния всё, что не помечено real.

        Вызывается адаптерами при подключении площадки. Демо-данные больше
        не создаются, так что обычно это просто страховка.
        """
        st = self.state
        st["orders"] = [o for o in st["orders"]
                        if not (o["platform"] == platform and not o.get("real"))]
        st["chats"] = [c for c in st["chats"]
                       if not (c["platform"] == platform and not c.get("real"))]

    # ---------- каталог товаров (выставление и конфигурация) ----------
    def norm_product(self, p: dict) -> dict:
        """Привести карточку товара к единому виду; неизвестные поля игнор."""
        keep = ("platform", "game", "cat", "lot", "desc", "price", "cost",
                "stock", "status", "url")
        out = {k: p.get(k, "") for k in keep}
        out["platform"] = out["platform"] if out["platform"] in ("funpay", "playerok") else "playerok"
        out["status"] = out["status"] if out["status"] in ("draft", "listed") else "draft"
        out["dest"] = out.get("dest", "")
        if out["dest"] not in ("", "funpay", "playerok"):
            out["dest"] = ""
        for k in ("price", "cost", "stock"):
            try:
                out[k] = max(0, int(float(out[k] or 0)))
            except (TypeError, ValueError):
                out[k] = 0
        out["id"] = self.next_id()
        out["mins"] = 0
        return out

    def upsert_order(self, o: dict):
        """Добавить или обновить реальный заказ (ключ: platform + ext_id).
        Возвращает ("new"|"changed"|None, order)."""
        st = self.state
        existing = next((x for x in st["orders"]
                         if x.get("real") and x["platform"] == o["platform"]
                         and str(x.get("ext_id")) == str(o.get("ext_id"))), None)
        if existing:
            changed = existing["status"] != o["status"]
            keep_id = existing["id"]
            # пустые значения (lot/price/buyer неизвестны) не затирают известные
            for k, v in o.items():
                if k == "id":
                    continue
                if v in (None, "") and k in ("lot", "price", "buyer", "game", "chat_ext"):
                    continue
                existing[k] = v
            existing["id"] = keep_id
            existing["mins"] = 0
            return ("changed" if changed else None), existing
        o = dict(o)
        o["id"] = self.next_id()
        st["orders"].insert(0, o)
        st["orders"] = st["orders"][:200]
        return "new", o

    def chat_by_ext(self, platform: str, ext_id, buyer=None, game=None, lot=None) -> dict:
        c = next((x for x in self.state["chats"]
                  if x.get("real") and x["platform"] == platform
                  and str(x.get("ext_id")) == str(ext_id)), None)
        if not c:
            c = {"id": self.next_id(), "real": True, "ext_id": str(ext_id),
                 "platform": platform, "buyer": buyer or "Покупатель",
                 "game": game or "", "lot": lot or "", "unread": 0, "msgs": []}
            self.state["chats"].insert(0, c)
            self.state["chats"] = self.state["chats"][:60]
        elif buyer and c.get("buyer") in ("Покупатель", "", None):
            c["buyer"] = buyer
        return c

    def upsert_message(self, platform: str, ext_id, frm: str, text: str,
                       buyer=None, unread=False) -> dict:
        c = self.chat_by_ext(platform, ext_id, buyer=buyer)
        c["msgs"].append({"from": frm, "text": text or "", "mins": 0})
        c["msgs"] = c["msgs"][-120:]
        if unread:
            c["unread"] += 1
        return c

    # ---------- действия фронтенда ----------
    async def apply(self, a: dict):
        t = a.get("action")
        st = self.state
        if t == "move":
            o = next((x for x in st["orders"] if x["id"] == a.get("id")), None)
            if o:
                o["status"] = a.get("to", o["status"])
                o["mins"] = 0
                if o["status"] == "sent":
                    p = next((p for p in st["products"]
                              if p["lot"] == o["lot"] and p["platform"] == o["platform"]), None)
                    if p and p["stock"] > 0:
                        p["stock"] -= 1
                if o.get("real") and self.manager and o["status"] in ("sent", "done", "dispute"):
                    try:
                        await self.manager.order_action(o, o["status"])
                    except Exception as e:
                        self.push_alert("⚠️", f"Действие на {PF_NAMES.get(o['platform'], '')} не выполнено: {e}", "bad")
        elif t == "rule":
            r = next((x for x in st["rules"] if x["id"] == a.get("id")), None)
            if r:
                r["on"] = not r["on"]
        elif t == "autoprice":
            p = next((x for x in st["products"] if x["id"] == a.get("id")), None)
            if p:
                p["auto"] = not p["auto"]
        elif t == "match":
            p = next((x for x in st["products"] if x["id"] == a.get("id")), None)
            if p:
                p["price"] = max(p["comp"] - 10, round(p["price"] * 0.9))
        elif t == "matchall":
            for p in st["products"]:
                if p["active"] and p["comp"] < p["price"]:
                    p["price"] = p["comp"] - 10
        elif t == "connect":
            if a.get("p") in st["accounts"]:
                st["accounts"][a["p"]]["connected"] = True
        elif t == "disconnect":
            if a.get("p") in st["accounts"]:
                st["accounts"][a["p"]]["connected"] = False
        elif t == "message":
            c = next((x for x in st["chats"] if x["id"] == a.get("id")), None)
            if c and a.get("text"):
                text = str(a["text"])[:1000]
                c["msgs"].append({"from": "me", "text": text, "mins": 0})
                if c.get("real") and self.manager:
                    try:
                        await self.manager.send_message(c, text)   # реальная отправка на площадку
                    except Exception as e:
                        self.push_alert("⚠️",
                                        f"Сообщение не отправлено ({PF_NAMES.get(c['platform'], '')}): {e}", "bad")
                else:
                    self.push_alert(
                        "⚠️", "Сообщение не отправлено: чат не связан с реальной "
                              "площадкой (подключите аккаунт в настройках)", "bad")
        elif t == "createchat":
            ch = a.get("chat")
            if ch and not any(x["id"] == ch.get("id") for x in st["chats"]):
                st["chats"].insert(0, ch)
        elif t == "chatread":
            c = next((x for x in st["chats"] if x["id"] == a.get("id")), None)
            if c:
                c["unread"] = 0
        elif t == "alertclear":
            st["alerts"] = []
        elif t == "prodadd":
            st["products"].insert(0, self.norm_product(a.get("product") or {}))
        elif t == "prodimport":
            items = [self.norm_product(x) for x in (a.get("items") or [])
                     if isinstance(x, dict)]
            st["products"] = items + st["products"]
        elif t == "aidrafts":
            from . import ailots
            drafts, rep = await asyncio.to_thread(ailots.build_drafts, a.get("text") or "")
            items = [self.norm_product(x) for x in drafts]
            if items:
                st["products"] = items + st["products"]
                self.push_alert("🤖", f"AI-конвейер: черновиков {len(items)} — "
                                      f"проверь во вкладке «Товар» и выставь вручную", "ok")
            else:
                self.push_alert("🤖", "AI-конвейер: не нашёл ни одной ссылки в тексте", "bad")
        elif t == "produpd":
            pid = a.get("id")
            p = next((x for x in st["products"] if x["id"] == pid), None)
            if p:
                up = self.norm_product({**p, **(a.get("product") or {})})
                up["id"] = pid
                p.update(up)
        elif t == "proddel":
            st["products"] = [x for x in st["products"] if x["id"] != a.get("id")]
        elif t == "setmode":
            mode = a.get("mode")
            st["pfmode"] = mode if mode in ("both", "funpay", "playerok") else "both"
            mgr = getattr(self, "manager", None)
            if mgr is not None:
                await mgr.apply_mode(st["pfmode"])
        elif t == "saveset":
            fees = a.get("fees") or {}
            wfees = a.get("wfees") or {}
            for k in ("funpay", "playerok"):
                if k in fees:
                    st["fees"][k] = _pct(fees[k])
                if k in wfees:
                    st.setdefault("wfees", {})[k] = _pct(wfees[k])
        await self.broadcast()

    # ---------- время «N минут назад» для реальных событий ----------
    def age(self):
        """Прибавляет минуту к возрасту реальных заказов/сообщений/уведомлений.

        Площадки не отдают время создания сделки, поэтому это единственный
        честный счётчик относительного времени: он растёт, пока панель работает.
        """
        st = self.state
        for o in st["orders"]:
            o["mins"] += 1
        for c in st["chats"]:
            for m in c["msgs"]:
                m["mins"] += 1
        for a in st["alerts"]:
            a["mins"] += 1


store = Store()
