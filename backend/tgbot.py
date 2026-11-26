"""Телеграм-бот SellHub — только стандартная библиотека Python.

Умеет:
  * слать уведомления: новый заказ, сообщение покупателя, смена статуса, спор;
  * команды /start /profile /orders /chats /help + кнопки-меню;
  * доступ только у «владельца»: первый нажавший /start (или TG_OWNER_ID).

Живёт внутри процесса панели (backend.main). Настройка через окружение:
  TG_BOT_TOKEN — токен от @BotFather;
  TG_OWNER_ID  — (необязательно) числовой telegram-id владельца.
"""
import asyncio
import html
import json
import logging
import os
import re
import time
import urllib.error
import urllib.request

log = logging.getLogger("sellhub.tgbot")

# адрес панели: открывается прямо внутри Telegram (WebView)
PANEL_URL = os.getenv("PANEL_URL", "https://sellhub-paa6.onrender.com").strip()

MENU = {"keyboard": [["📊 Дашборд", "📦 Заказы"],
                    ["👤 Профиль", "💬 Чаты"],
                    [{"text": "🌐 Открыть панель", "web_app": {"url": PANEL_URL}},
                     "❓ Помощь"]],
        "resize_keyboard": True}

ST_RU = {"new": "новый", "sent": "отправлено", "done": "завершён", "dispute": "возврат/спор"}
ST_EM = {"new": "🆕", "sent": "📦", "done": "✅", "dispute": "⚠️"}
PF_NAME = {"funpay": "FunPay", "playerok": "Playerok"}
PF_EM = {"funpay": "🔵", "playerok": "🟣"}


def _n(v) -> str:
    """Число с разделителями-пробелами: 35907 -> 35 907."""
    return f"{int(v or 0):,}".replace(",", " ")


def _msk_now() -> str:
    from datetime import datetime, timedelta, timezone
    return datetime.now(timezone(timedelta(hours=3))).strftime("%H:%M")


def _esc(s) -> str:
    return html.escape(str(s if s is not None else ""))


class Tg:
    def __init__(self, token: str):
        self.base = f"https://api.telegram.org/bot{token}/"
        self.bot = None   # обратная ссылка на Bot — для учёта ошибок/доставок

    def _call(self, method: str, payload: dict):
        req = urllib.request.Request(
            self.base + method,
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=45) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            # Telegram кладёт настоящую причину в тело ответа — читаем его,
            # иначе видим лишь «HTTP Error 400: Bad Request»
            try:
                body = json.load(e)
                if isinstance(body, dict):
                    body.setdefault("ok", False)
                    body["http_status"] = e.code
                    return body
            except Exception:
                pass
            return {"ok": False, "http_status": e.code,
                    "description": f"HTTPError {e.code}: {e.reason}"}

    async def call(self, method: str, **payload):
        try:
            res = await asyncio.to_thread(self._call, method, payload)
            if not res.get("ok"):
                log.warning("tg %s: %s", method, res.get("description"))
                try:
                    self.bot.last_err = f"{method}: {res.get('description')}"
                    self.bot.sent_fail += 1
                except Exception:
                    pass
            elif method == "sendMessage":
                try:
                    self.bot.sent_ok += 1
                except Exception:
                    pass
            return res
        except Exception as e:
            log.warning("tg %s: %s", method, e)
            try:
                self.bot.last_err = f"{method}: {type(e).__name__}: {e}"
                self.bot.sent_fail += 1
            except Exception:
                pass
            return None

    async def send(self, chat_id, text: str, menu=True):
        # важно: при menu=False НЕ отправляем reply_markup вовсе —
        # Telegram отбивает reply_markup:null ошибкой
        # «Bad Request: object expected as reply markup»
        payload = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
        if menu and MENU:
            payload["reply_markup"] = MENU
        return await self.call("sendMessage", **payload)

    async def delete(self, chat_id, message_id):
        """Стереть сообщение (секреты в истории чата не держим — как playerok-universal)."""
        if message_id is None:
            return None
        return await self.call("deleteMessage", chat_id=chat_id, message_id=message_id)


class Bot:
    def __init__(self, store, token: str):
        self.store = store
        self.tg = Tg(token)
        self.tg.bot = self
        env_owner = os.getenv("TG_OWNER_ID", "").strip()
        self.owner = int(env_owner) if env_owner.isdigit() else None
        self.offset = 0
        self.prev_orders = None     # ext_id -> status
        self.prev_chats = None      # ext_id -> (кол-во сообщений, unread)
        self.username = None        # @username бота после getMe
        self.ready = False          # getMe прошёл, поллер запущен
        self.last_err = None        # последняя ошибка Telegram (для диагностики)
        self.sent_ok = 0            # сколько сообщений реально ушло
        self.sent_fail = 0
        self.await_login = None     # chat_id, от которого ждём Cookie-строку Playerok
        self.await_ai = None        # chat_id, от которого ждём ссылки для AI-конвейера
        self.last_poll_ok = 0       # время последнего успешного getUpdates

    # ---------- запуск ----------
    async def run(self):
        me = await self.tg.call("getMe")
        if not me or not me.get("ok"):
            self.last_err = str((me or {}).get("description", "getMe: нет ответа"))
            log.warning("TG: токен не принят Telegram — бот не запущен (%s)",
                        self.last_err)
            return
        self.username = (me.get("result") or {}).get("username")
        self.ready = True
        # кнопка «Меню» слева внизу чата открывает панель внутри Telegram
        mb = await self.tg.call(
            "setChatMenuButton",
            menu_button={"type": "web_app", "text": "🌐 Панель",
                         "web_app": {"url": PANEL_URL}})
        if mb and mb.get("ok"):
            log.info("TG menu button -> %s", PANEL_URL)
        log.info("TG bot started: @%s", self.username)
        # супервизор: если поллер или вотчер упадут — поднимаем заново, бот не «умирает на часы»
        while True:
            try:
                await asyncio.gather(self._poll(), self._watch(), self._wd())
                break
            except asyncio.CancelledError:
                raise
            except Exception as e:
                log.exception("tg loop crashed, restart in 5s: %s", e)
                self.last_err = f"loop: {type(e).__name__}: {e}"[:120]
                await asyncio.sleep(5)

    async def _wd(self):
        """Сторож: если getUpdates молчит дольше 4 минут — перезапускаем поллер."""
        while True:
            await asyncio.sleep(60)
            try:
                if self.last_poll_ok and time.time() - self.last_poll_ok > 240:
                    log.warning("tg poller stuck (>240s without getUpdates) — bump offset timer")
                    self.last_poll_ok = time.time()   # метка сбрасывается, поллер пересоздаётся супервизором
                    raise RuntimeError("poller stuck")
            except RuntimeError:
                raise
            except Exception:
                pass

    # ---------- входящие сообщения ----------
    async def _poll(self):
        while True:
            try:
                res = await self.tg.call("getUpdates", offset=self.offset,
                                         timeout=25, allowed_updates=["message"])
                if not res or not res.get("ok"):
                    await asyncio.sleep(5)
                    continue
                self.last_poll_ok = time.time()
                for u in res.get("result", []):
                    try:
                        self.offset = max(self.offset, u["update_id"] + 1)
                        m = u.get("message") or {}
                        if m.get("text"):
                            asyncio.create_task(self._on_message(m))
                    except Exception as e:
                        log.warning("tg update: %s", e)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                log.warning("tg poll: %s", e)
                await asyncio.sleep(5)

    async def _on_message(self, m):
        cid = (m.get("chat") or {}).get("id")
        text = (m.get("text") or "").strip()
        if cid is None:
            return
        if self.owner is None:
            self.owner = cid
            log.info("TG owner assigned: %s", cid)
        elif cid != self.owner:
            await self.tg.call("sendMessage", chat_id=cid,
                               text="❌ Это приватный бот продавца.")
            return
        key = text.split()[0].lower() if text else ""
        # Cookie-строка или JWT любым сообщением = вход в Playerok (секрет стираем сразу).
        # age<600 c — защита от повторной обработки старых апдейтов после рестарта.
        if (text and not text.startswith("/") and time.time() - (m.get("date") or 0) < 600
                and ("token=eyJ" in text or re.search(r"eyJ[A-Za-z0-9_\-]{10,}\.eyJ", text))):
            self.await_login = None
            await self.tg.delete(cid, m.get("message_id"))
            ua = os.getenv("PLAYEROK_UA", "") or ""
            res = await self.store.manager.connect("playerok", text, ua)
            if res.get("ok"):
                await self.tg.send(cid, f"🟢 Playerok подключён: <b>{res.get('login')}</b>. "
                                        "Сообщение с секретом удалено из чата.")
            else:
                await self.tg.send(cid, f"⛠ Playerok: {res.get('error') or 'ошибка'} — "
                                        "нужна строка из Cookie-Editor (кнопка Copy) "
                                        "или свежий токен eyJ…")
            return
        if self.await_ai == cid and text and not text.startswith("/"):
            self.await_ai = None
            await self._ai_process(cid, text)
            return
        if self.await_login == cid and text and not text.startswith("/"):
            # вход в Playerok Cookie-строкой: секрет стираем из чата немедленно
            self.await_login = None
            await self.tg.delete(cid, m.get("message_id"))
            ua = os.getenv("PLAYEROK_UA", "") or ""
            res = await self.store.manager.connect("playerok", text, ua)
            if res.get("ok"):
                await self.tg.send(cid, f"🟢 Playerok подключён: <b>{res.get('login')}</b>. "
                                        "Сообщение с секретом удалено из чата.")
            else:
                await self.tg.send(cid, f"⛠ Playerok: {res.get('error') or 'ошибка'} — "
                                        "нужна строка из Cookie-Editor (кнопка Copy) "
                                        "или свежий токен eyJ…")
            return
        if key in ("/start", "меню"):
            await self.tg.send(cid,
                               "⚡ <b>SellHub — панель продавца</b>\n"
                               "Я пишу вам о новых заказах, полученных деньгах и спорах.\n"
                               "Кнопки ниже или команды: /stats /orders /profile /chats /help")
        elif key in ("/stats", "/dashboard", "📊", "дашборд"):
            await self.tg.send(cid, self._dashboard_text())
        elif key in ("/orders", "📦", "заказы"):
            await self.tg.send(cid, self._orders_text())
        elif key in ("/profile", "👤", "профиль"):
            await self.tg.send(cid, self._profile_text())
        elif key in ("/chats", "💬", "чаты"):
            await self.tg.send(cid, self._chats_text())
        elif key in ("/help", "❓", "помощь"):
            await self.tg.send(cid,
                               "<b>Команды</b>\n"
                               "/stats — дашборд: деньги, на руки после комиссии, счётчики\n"
                               "🌐 Панель продавца открывается кнопкой «Меню» слева внизу\n"
                               "   чата или кнопкой «🌐 Открыть панель» — прямо в Telegram\n"
                               "/orders — сводка: сколько всего, в работе, возвратов\n"
                               "/profile — аккаунты и итоги по площадкам\n"
                               "/chats — сколько диалогов и непрочитанных\n"
                               "/help — эта справка\n"
                               "/login — войти в Playerok Cookie-строкой из Cookie-Editor "
                               "(сообщение с секретом удаляется из чата)\n"
                               "/ai — выставление товаров по ссылкам: AI читает страницы, "
                               "сам пишет заголовок/описание/цену (черновики)\n"
                               "/token eyJ… — обновить токен Playerok, если площадка сбросила сессию\n"
                               "Плюс я сам пишу о новых заказах и полученных деньгах.")
        elif key == "/ai":
            parts = text.split(maxsplit=1)
            rest = parts[1].strip() if len(parts) > 1 else ""
            if rest and "http" in rest:
                await self._ai_process(cid, rest)
            else:
                self.await_ai = cid
                await self.tg.send(cid,
                                   "🤖 <b>AI-выставление</b>: пришли ссылки на товары "
                                   "(одну или несколько, с новой строки), подписи свободным текстом.\n"
                                   "Сам прочитаю страницы, определю площадку и категорию, "
                                   "напишу заголовок и описание, поставлю цену с наценкой — "
                                   "создам черновики в «Товарах». Без твоего «да» ничего не выставится.")
        elif key == "/login":
            self.await_login = cid
            await self.tg.send(cid,
                               "🔐 <b>Вход в Playerok</b> — как в playerok-universal, Cookie-строкой:\n"
                               "1. На ПК откройте playerok.com (вы залогинены) и расширение <b>Cookie-Editor</b>;\n"
                               "2. Нажмите кнопку <b>Copy</b> — скопируется строка куки целиком;\n"
                               "3. Пришлите её сюда одним сообщением (или просто токен eyJ…).\n"
                               "Сообщение с секретом я <b>удалю из чата сразу</b> и войду в аккаунт.")
        elif key == "/token":
            parts = text.split(maxsplit=1)
            if len(parts) < 2 or not parts[1].strip():
                await self.tg.send(cid, "Формат: /token eyJ… — токен, либо целиком Cookie-строка "
                                        "из Cookie-Editor (кнопка Copy) на playerok.com")
            else:
                ua = os.getenv("PLAYEROK_UA", "") or ""
                res = await self.store.manager.connect("playerok", parts[1].strip(), ua)
                if res.get("ok"):
                    await self.tg.send(cid, f"🟢 Playerok подключён: <b>{res.get('login')}</b>. "
                                            "Панель и пуши снова живые.")
                else:
                    await self.tg.send(cid, f"⛠ Playerok: {res.get('error') or 'ошибка'} — "
                                            "проверь, что токен свежий (скопирован только что).")
        else:
            await self.tg.send(cid, "Не понял команду. Нажмите ❓ Помощь.")

    # ---------- тексты ----------
    def _snap(self):
        return self.store.snapshot()

    def _dashboard_text(self) -> str:
        s = self._snap()
        st = s.get("stats", {})
        fees = s.get("fees", {}) or {}
        wfees = s.get("wfees", {}) or {}
        rev = st.get("revTotal", 0) or 0
        net = st.get("netTotal", 0) or 0
        fee_sum = rev - net
        done = st.get("doneTotal", 0) or 0
        total = st.get("orders", 0) or 0
        active = st.get("active", 0) or 0
        disp = st.get("disputes", 0) or 0
        lines = [f"<b>📊 Дашборд</b>  ·  {_msk_now()} МСК", ""]
        lines.append(f"💰 Выручка (завершённые): <b>{_n(rev)} ₽</b>")
        lines.append(f"🏦 Комиссия площадки: −{_n(fee_sum)} ₽")
        lines.append(f"✅ <b>На руки: {_n(net)} ₽</b>")
        lines.append(f"💳 После вывода средств: <b>{_n(st.get('netWTotal', 0) or 0)} ₽</b>")
        lines.append("")
        lines.append(f"📦 Всего сделок: <b>{total}</b>")
        lines.append(f"   • завершено: {done}")
        lines.append(f"   • в работе: {active}")
        lines.append(f"   • возврат/отмена: {disp}")
        lines.append(f"💬 Чатов: {st.get('chats',0)} · непрочитано: {st.get('unread',0)}")
        # разбивка по площадкам с процентами
        rev_pf = st.get("revPf", {}) or {}
        net_pf = st.get("netPf", {}) or {}
        if rev_pf:
            lines.append("")
            lines.append("<b>По площадкам</b> (выручка → на руки):")
            for pf in ("funpay", "playerok"):
                v = rev_pf.get(pf, 0) or 0
                nv = net_pf.get(pf, 0) or 0
                fee = fees.get(pf, 0) or 0
                w = wfees.get(pf, 0) or 0
                nw = round(nv * (1 - w / 100.0))
                em = PF_EM.get(pf, "•")
                lines.append(f"   {em} {PF_NAME.get(pf,pf)}: {_n(v)} ₽ → <b>{_n(nv)} ₽</b> "
                             f"(−{fee}%) → на карту {_n(nw)} ₽ (−{w}%)")
        return "\n".join(lines)

    def _orders_text(self) -> str:
        """Сводка по заказам — только счётчики, без конкретных лотов."""
        s = self._snap()
        st = s.get("stats", {})
        orders = [o for o in s.get("orders", []) if o.get("real")]
        if not orders:
            return "📭 Реальных заказов пока нет."
        by = {}
        by_pf = {}
        for o in orders:
            by[o.get("status")] = by.get(o.get("status"), 0) + 1
            by_pf[o.get("platform")] = by_pf.get(o.get("platform"), 0) + 1
        lines = [f"<b>📦 Заказы — сводка</b>  ·  {_msk_now()} МСК", ""]
        lines.append(f"Всего: <b>{len(orders)}</b>")
        lines.append(f"🆕 новых (оплачено, ждёт выдачи): {by.get('new',0)}")
        lines.append(f"📦 выдано, ждёт подтверждения: {by.get('sent',0)}")
        lines.append(f"✅ завершено: {by.get('done',0)}")
        lines.append(f"⚠️ возврат/отмена: {by.get('dispute',0)}")
        if len(by_pf) > 1 or True:
            lines.append("")
            lines.append("<b>По площадкам</b>:")
            for pf in ("funpay", "playerok"):
                if by_pf.get(pf):
                    lines.append(f"   {PF_EM.get(pf,'•')} {PF_NAME.get(pf,pf)}: {by_pf[pf]}")
        return "\n".join(lines)

    def _profile_text(self) -> str:
        s = self._snap()
        acc = s.get("accounts", {})
        st = s.get("stats", {})
        fees = s.get("fees", {}) or {}
        wfees = s.get("wfees", {}) or {}
        lines = ["<b>👤 Профиль продавца</b>"]
        for pf, a in acc.items():
            mark = "🟢" if a.get("connected") else "⚪"
            login = a.get("login") or "не подключён"
            fee = fees.get(pf, 0) or 0
            w = wfees.get(pf, 0) or 0
            lines.append(f"{mark} {PF_NAME.get(pf,pf)}: {login}  ·  "
                         f"продажа −{fee}% · вывод −{w}%")
        rev = st.get("revTotal", 0) or 0
        net = st.get("netTotal", 0) or 0
        done = st.get("doneTotal", 0) or 0
        avg = round(rev / done) if done else 0
        lines.append("")
        lines.append(f"💰 Выручка (завершённые): {_n(rev)} ₽")
        lines.append(f"✅ На руки после комиссии: <b>{_n(net)} ₽</b>")
        lines.append(f"💳 После вывода: <b>{_n(st.get('netWTotal', 0) or 0)} ₽</b>")
        lines.append(f"🧾 Завершённых сделок: {done} · средний чек: {_n(avg)} ₽")
        return "\n".join(lines)

    def _chats_text(self) -> str:
        s = self._snap()
        chats = [c for c in s.get("chats", []) if c.get("real") or c.get("ext_id")]
        if not chats:
            return "📭 Чатов пока нет."
        lines = []
        for c in chats[:12]:
            u = c.get("unread", 0)
            badge = f" · <b>новых: {u}</b>" if u else ""
            lines.append(f"💬 {_esc(c.get('buyer','?'))} — сообщений: {len(c.get('msgs', []))}{badge}")
        return f"<b>💬 Чаты ({len(chats)})</b>\n" + "\n".join(lines)

    # ---------- наблюдатель событий ----------
    async def _ai_process(self, cid, text):
        from . import ailots
        drafts, rep = await asyncio.to_thread(ailots.build_drafts, text)
        if not drafts:
            await self.tg.send(cid, "🤖 Не нашёл ссылок (нужны http… — по одной на строку, "
                                    "подписи свободным текстом).")
            return
        await self.store.apply({"action": "prodimport", "items": drafts})
        await self.tg.send(cid, f"🤖 <b>Черновиков создано: {len(drafts)}</b>\n" +
                           "\n".join(rep) +
                           "\n\nОни в панели «Товары» со статусом «черновик» — проверь, "
                           "поправь при желании и выставь вручную.")

    async def _watch(self):
        while True:
            await asyncio.sleep(5)
            try:
                await self._tick()
            except Exception as e:
                log.warning("tg watch: %s", e)

    async def _tick(self):
        s = self._snap()
        fees = s.get("fees", {}) or {}
        orders = {str(o.get("ext_id")): o for o in s.get("orders", []) if o.get("real") and o.get("ext_id")}
        chats = {str(c.get("ext_id")): c for c in s.get("chats", []) if c.get("ext_id")}
        if self.prev_orders is None:
            self.prev_orders = {k: o.get("status") for k, o in orders.items()}
            self.prev_chats = {k: (len(c.get("msgs", [])), c.get("unread", 0)) for k, c in chats.items()}
            return
        if self.owner is None:
            return
        msgs = []
        # новые заказы и смены статусов
        for ext, o in orders.items():
            old = self.prev_orders.get(ext)
            pf = o.get("platform")
            price = o.get("price", 0) or 0
            fee = fees.get(pf, 0) or 0
            wfee = (s.get("wfees", {}) or {}).get(pf, 0) or 0
            net = round(price * (1 - fee / 100.0))
            netw = round(net * (1 - wfee / 100.0))
            if old is None:
                msgs.append(f"🛒 <b>Новый заказ</b> ({PF_NAME.get(pf,pf)})\n"
                            f"{_esc(o.get('lot'))}\n💰 {_n(price)} ₽ · покупатель {_esc(o.get('buyer'))}")
            elif old != o.get("status"):
                new_st = o.get("status")
                em = ST_EM.get(new_st, "•")
                if new_st == "done":
                    msgs.append(f"✅ <b>Получены деньги</b> ({PF_NAME.get(pf,pf)})\n"
                                f"💰 {_n(price)} ₽ → на руки <b>{_n(net)} ₽</b> (−{fee}%) "
                                f"→ на карту {_n(netw)} ₽ (вывод −{wfee}%)")
                elif new_st == "dispute":
                    msgs.append(f"⚠️ <b>Возврат/спор</b> ({PF_NAME.get(pf,pf)})\n"
                                f"{_esc(o.get('lot'))[:60]} · {_n(price)} ₽")
                else:
                    msgs.append(f"{em} Заказ «{_esc(o.get('lot'))[:40]}» → {ST_RU.get(new_st, new_st)}")
        self.prev_orders = {k: o.get("status") for k, o in orders.items()}
        # новые сообщения покупателей
        for ext, c in chats.items():
            n, _u = len(c.get("msgs", [])), c.get("unread", 0)
            old_n, old_u = self.prev_chats.get(ext, (n, 0))
            if n > old_n:
                new_msgs = c.get("msgs", [])[old_n:]
                for m in new_msgs[-3:]:
                    if m.get("from") == "buyer":
                        msgs.append(f"💬 {_esc(c.get('buyer'))}: {_esc(m.get('text'))[:120]}")
            elif _u > old_u:
                msgs.append(f"💬 {_esc(c.get('buyer'))}: непрочитанных: {_u}")
            self.prev_chats[ext] = (n, _u)
        for text in msgs[:6]:
            await self.tg.send(self.owner, text)


_BOT = None


def get_bot():
    return _BOT


def telemetry() -> dict:
    """Состояние бота для /api/health — видно извне, жив ли поллер."""
    b = _BOT
    if not b:
        return {"ready": False}
    return {"ready": b.ready,
            "poll_age_s": int(time.time() - b.last_poll_ok) if b.last_poll_ok else None,
            "sent_ok": b.sent_ok, "sent_fail": b.sent_fail,
            "last_err": (b.last_err or "")[:120] or None}


async def send_test(store) -> str:
    """Настоящее тестовое уведомление владельцу бота."""
    bot = _BOT
    if bot is None:
        return "Бот не запущен: нет TG_BOT_TOKEN на сервере"
    if bot.owner is None:
        return ("Бот запущен, но владелец не определён — напишите боту "
                "/start в Telegram, затем повторите")
    st = store.snapshot()
    stats = st.get("stats", {})
    text = ("🔔 <b>SellHub: тестовое уведомление</b>\n"
            f"Сделок: {stats.get('orders', 0)} · завершено: {stats.get('doneTotal', 0)}\n"
            f"Выручка: {_n(stats.get('revTotal', 0))} ₽ → на руки {_n(stats.get('netTotal', 0))} ₽\n"
            f"В работе: {stats.get('active', 0)} · возврат/спор: {stats.get('disputes', 0)}\n"
            f"Непрочитанных сообщений: {stats.get('unread', 0)}")
    res = await bot.tg.send(bot.owner, text, menu=False)
    if res and res.get("ok"):
        return "ok"
    return "Telegram не принял сообщение: " + str((res or {}).get("description", "нет ответа"))


async def start(store):
    global _BOT
    token = os.getenv("TG_BOT_TOKEN", "").strip()
    if not token:
        return
    try:
        _BOT = Bot(store, token)
        await _BOT.run()
    except asyncio.CancelledError:
        raise
    except Exception as e:
        log.warning("tg bot stopped: %s", e)
