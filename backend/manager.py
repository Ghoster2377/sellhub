"""PlatformManager — подключение реальных площадок и маршрутизация действий.

Ключи берёт из (по приоритету):
  1. data/credentials.json (сохраняются при подключении через панель),
  2. переменные окружения FUNPAY_GOLDEN_KEY / PLAYEROK_TOKEN (.env).

Жизненный цикл подключения:
  connect(key) -> быстрая авторизация (start + me) -> аккаунт помечается
  подключённым -> фоном: загрузка истории (заказы/чаты) и супервизор потока
  событий с автопереподключением каждые 30 с при обрыве.
"""
import asyncio
import json
import logging
import os
import re

log = logging.getLogger("sellhub.manager")

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
CRED_FILE = os.path.join(DATA_DIR, "credentials.json")

TITLES = {"funpay": "FunPay", "playerok": "Playerok"}


# ---------- ключи ----------
def load_credentials() -> dict:
    creds = {}
    if os.getenv("FUNPAY_GOLDEN_KEY"):
        creds["funpay"] = {"key": os.getenv("FUNPAY_GOLDEN_KEY"),
                           "ua": os.getenv("FUNPAY_USER_AGENT") or ""}
    if os.getenv("PLAYEROK_TOKEN"):
        creds["playerok"] = {"key": os.getenv("PLAYEROK_TOKEN"),
                             "ua": os.getenv("PLAYEROK_UA", "")}
    try:
        with open(CRED_FILE, encoding="utf-8") as f:
            for k, v in json.load(f).items():
                if not v:
                    continue
                creds[k] = v if isinstance(v, dict) else {"key": v, "ua": ""}
    except Exception:
        pass
    return creds


def save_credential(platform: str, data: dict | None):
    os.makedirs(DATA_DIR, exist_ok=True)
    creds = {}
    try:
        with open(CRED_FILE, encoding="utf-8") as f:
            creds = json.load(f)
    except Exception:
        pass
    if data is None:
        creds.pop(platform, None)
    else:
        creds[platform] = data
    with open(CRED_FILE, "w", encoding="utf-8") as f:
        json.dump(creds, f)
    try:
        os.chmod(CRED_FILE, 0o600)
    except Exception:
        pass


def friendly_error(e: Exception) -> str:
    name = type(e).__name__
    if "Unauthorized" in name:
        return "ключ отклонён площадкой (неверный или истёк) — проверьте и попробуйте снова"
    if "Cloudflare" in name:
        return "площадка закрылась защитой Cloudflare — попробуйте позже (или смените IP/прокси сервера)"
    if "AccountNotInitiated" in name:
        return "сессия не установлена — проверьте ключ и доступ сервера в интернет"
    if any(x in name for x in ("RequestFailed", "Transport", "Connect", "Timeout", "Resolution")):
        return "не удалось связаться с площадкой (сеть/таймаут) — проверьте доступ сервера в интернет"
    return f"{name}: {str(e)[:180]}"


def mask_key(key: str) -> str:
    return (key[:4] + "•" * 8 + key[-4:]) if len(key) > 12 else "•" * 10


_PO_JWT_RE = re.compile(r"(eyJ[A-Za-z0-9_\-]{10,}\.eyJ[A-Za-z0-9_\-\.]+)")


def normalize_po_key(key: str) -> str:
    """Принимает и чистый JWT, и Cookie-строку из Cookie-Editor (как playerok-universal):
    'token=eyJ…; mdd=…; …' — вытаскивает оттуда JWT. Не похоже на JWT — вернёт как есть."""
    k = (key or "").strip()
    if not k:
        return k
    if k.startswith("eyJ") and ";" not in k and "=" not in k:
        return k
    m = _PO_JWT_RE.search(k)
    return m.group(1) if m else k


# ---------- менеджер ----------
class PlatformManager:
    def __init__(self, store):
        self.store = store
        self.adapters: dict = {}
        self.tasks: dict = {}
        self._manual_off: set = set()   # площадки, отключённые вручную — их не переподключаем сами
        self.po_persist = None          # статус сохранения токена в env Render

    def status(self) -> dict:
        out = {}
        for p in TITLES:
            acc = self.store.state.get("accounts", {}).get(p, {})
            out[p] = {"connected": p in self.adapters,
                      "error": (acc.get("error") or "")[:120] or None}
        out["playerok"]["persist"] = self.po_persist
        return out

    # ----- подключение -----
    async def connect(self, platform: str, key: str, user_agent: str = "") -> dict:
        key = (key or "").strip()
        if platform == "playerok":
            key = normalize_po_key(key)
        user_agent = (user_agent or "").strip()
        if not key:
            return {"ok": False, "error": "пустой ключ"}
        if platform == "funpay":
            from .adapters.funpay import FunPayAdapter as Adapter
        elif platform == "playerok":
            from .adapters.playerok import PlayerokAdapter as Adapter
        else:
            return {"ok": False, "error": "неизвестная площадка"}

        await self.disconnect(platform, quiet=True)
        adapter = Adapter()
        try:
            if platform == "funpay":
                info = await adapter.connect(key, user_agent or None)
            else:
                info = await adapter.connect(key)
        except ImportError:
            return {"ok": False, "error": "библиотека aiosellers не установлена — выполните pip install -r requirements.txt на сервере"}
        except Exception as e:
            await adapter.close()
            err = friendly_error(e)
            self.store.set_account(platform, connected=False, error=err)
            await self.store.broadcast()
            return {"ok": False, "error": err}

        self.adapters[platform] = adapter
        self._manual_off.discard(platform)
        if platform == "playerok":
            asyncio.create_task(self._persist_po_token(key))
        self.store.set_account(platform, connected=True,
                               login=info.get("login"), key=mask_key(key), error=None,
                               avatar=info.get("avatar") or "")
        save_credential(platform, {"key": key, "ua": user_agent})
        self.tasks[platform] = asyncio.create_task(self._supervise(platform, adapter))
        asyncio.create_task(self._load_history(platform, adapter))
        await self.store.broadcast({
            "text": f"{TITLES[platform]}: аккаунт {info.get('login')} подключён — загружаю заказы и чаты",
            "kind": "ok", "icon": "🟢"})
        return {"ok": True, "login": info.get("login")}

    async def _persist_po_token(self, token: str):
        """Сохранить рабочий токен Playerok в env Render, чтобы подключение
        переживало рестарты и деплои (autostart поднимет его сам).
        Всегда отправляет ПОЛНЫЙ набор env-ключей."""
        rkey = os.getenv("RENDER_API_KEY", "").strip()
        sid = os.getenv("RENDER_SERVICE_ID", "").strip()
        if not rkey or not sid or not token:
            self.po_persist = f"no-creds(key={bool(rkey)},sid={bool(sid)})"
            return
        url = f"https://api.render.com/v1/services/{sid}/env-vars"

        def _do():
            import urllib.request as ur
            hdr = {"Authorization": f"Bearer {rkey}"}
            with ur.urlopen(ur.Request(url, headers=hdr), timeout=30) as r:
                cur = json.load(r)
            envs = {}
            for d in cur:
                ev = d.get("envVar") or {}
                if ev.get("key"):
                    if ev.get("value") is None:
                        return "skip:masked-secret"   # не трогаем env
                    envs[ev["key"]] = ev["value"]
            if envs.get("PLAYEROK_TOKEN") == token:
                return "skip:same"
            envs["PLAYEROK_TOKEN"] = token
            body = json.dumps([{"key": k, "value": v} for k, v in envs.items()]).encode()
            req = ur.Request(url, data=body, method="PUT",
                             headers={**hdr, "Content-Type": "application/json"})
            with ur.urlopen(req, timeout=30) as r:
                r.read()
            return "ok"

        try:
            self.po_persist = await asyncio.to_thread(_do)
            log.info("po persist: %s", self.po_persist)
        except Exception as e:
            self.po_persist = f"err: {type(e).__name__}: {e}"[:120]
            log.warning("persist po token: %s", e)

    async def _load_history(self, platform: str, adapter):
        try:
            await adapter.load_history(self.store)
            log.info("%s: история загружена", platform)
        except Exception as e:
            log.warning("%s: load_history: %s", platform, e)
            self.store.push_alert("⚠️", f"{TITLES[platform]}: не удалось загрузить историю ({friendly_error(e)})", "warn")
            await self.store.broadcast()

    async def _supervise(self, platform: str, adapter):
        while True:
            try:
                await adapter.run_events(self.store)
                raise RuntimeError("поток событий завершился")
            except asyncio.CancelledError:
                raise
            except Exception as e:
                log.warning("%s: события прерваны: %s", platform, e)
                self.store.push_alert(
                    "🔌", f"{TITLES[platform]}: соединение прервано ({friendly_error(e)}), переподключение через 30 с", "warn")
                await self.store.broadcast()
                await asyncio.sleep(30)
                try:
                    await adapter.restart()
                    self.store.push_alert("🟢", f"{TITLES[platform]}: переподключено", "ok")
                    await self.store.broadcast()
                except Exception as e2:
                    log.warning("%s: restart: %s", platform, e2)

    # ----- отключение -----
    async def disconnect(self, platform: str, quiet: bool = False, wipe: bool = True):
        task = self.tasks.pop(platform, None)
        if task:
            task.cancel()
        adapter = self.adapters.pop(platform, None)
        if adapter:
            await adapter.close()
        if wipe:  # при перезапуске сервера сохранённые ключи НЕ стираем
            save_credential(platform, None)
        if not quiet:
            self._manual_off.add(platform)   # пользователь отключил сам — автоповтор не трогаем
            self.store.set_account(platform, connected=False, error=None)
            await self.store.broadcast()

    # ----- маршрутизация действий -----
    async def send_message(self, chat: dict, text: str):
        adapter = self.adapters.get(chat.get("platform"))
        if not adapter:
            raise RuntimeError("площадка не подключена")
        await adapter.send_message(chat, text)

    async def order_action(self, order: dict, to: str):
        adapter = self.adapters.get(order.get("platform"))
        if not adapter:
            raise RuntimeError("площадка не подключена")
        await adapter.order_action(order, to)

    # ----- автостарт по сохранённым ключам -----
    async def autostart(self):
        creds = load_credentials()
        if not creds:
            log.info("autostart: сохранённых ключей нет — панель останется пустой, "
                     "пока площадки не подключены")
        for platform, cred in creds.items():
            if platform in TITLES:
                if self.store.state.get("pfmode", "both") not in ("both", platform):
                    continue                      # площадка на паузе режимом
                if platform == "playerok":
                    # ждём, пока прежний инстанс сервера полностью остановился:
                    # два одновременных слушателя с одной сессией Playerok не любит
                    await asyncio.sleep(25)
                res = await self.connect(platform, cred.get("key", ""), cred.get("ua", ""))
                log.info("autostart %s: %s", platform, res)

    async def apply_mode(self, mode: str):
        """Режим площадок: both | funpay | playerok (пауза = сервер не держит сессию)."""
        for p in ("funpay", "playerok"):
            desired = mode in ("both", p)
            live = p in self.adapters
            if desired and not live:
                self._manual_off.discard(p)
                cred = (load_credentials() or {}).get(p)
                if cred:
                    res = await self.connect(p, cred.get("key", ""), cred.get("ua", ""))
                    log.info("apply_mode %s: %s", p, res)
            elif not desired and live:
                await self.disconnect(p, quiet=True, wipe=False)
                self._manual_off.add(p)
                self.store.set_account(p, connected=False, error=None)
                await self.store.broadcast()

    async def retry_disconnected(self, interval: int = 1800):
        """Раз в ~30 мин пробуем подключить площадки, которые отключены НЕ вручную.

        Нужно для Playerok: площадка привязывает сессию к IP и может временно
        отклонять сервер; когда отпустит — подключимся сами, без действий пользователя.
        """
        await asyncio.sleep(45)          # ранняя проба вскоре после старта
        fails = 1                        # первая проба обычно «вхолостую» — дальше цикл каждые 5 мин
        while True:
            # пока площадки отклоняют (временный блок IP) — пробуем каждые 5 минут,
            # после 6 неудач подряд — реже, раз в interval (30 мин)
            await asyncio.sleep(300 if 0 < fails < 6 else interval)
            try:
                creds = load_credentials()
                bad = 0
                for platform, cred in creds.items():
                    if platform in TITLES \
                            and platform not in self.adapters \
                            and platform not in self._manual_off \
                            and self.store.state.get("pfmode", "both") in ("both", platform):
                        res = await self.connect(platform, cred.get("key", ""), cred.get("ua", ""))
                        log.info("retry %s: %s", platform, res)
                        if not res.get("ok"):
                            bad += 1
                fails = bad
            except Exception as e:
                log.warning("retry loop: %s", e)
