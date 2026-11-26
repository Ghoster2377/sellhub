"""FastAPI-приложение SellHub.

Запуск:  uvicorn backend.main:app --host 0.0.0.0 --port 8000
REST:    GET /api/state · POST /api/action · POST /api/connect · POST /api/disconnect · GET /api/health
WS:      /ws — рассылка состояния всем открытым панелям
Статика: frontend/ монтируется в /

При старте автоматически подключает площадки по ключам из data/credentials.json
и .env (FUNPAY_GOLDEN_KEY / PLAYEROK_TOKEN). Без ключей панель пустая —
демо-данных нет: всё, что видно на экране, приходит только с реальных площадок.
"""
import asyncio
import logging
import os

from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

load_dotenv()

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(name)s %(levelname)s %(message)s")
log = logging.getLogger("sellhub")

from .adapters import adapter_status  # noqa: E402
from .manager import PlatformManager  # noqa: E402
from .store import store              # noqa: E402


async def _age_ticker(store_):
    """Раз в минуту увеличивает возраст реальных событий и рассылает состояние.

    Площадки не отдают время создания сделки, поэтому «N минут назад» считаем
    сами, пока сервер работает. Никаких данных при этом не выдумывается.
    """
    while True:
        await asyncio.sleep(60)
        try:
            store_.age()
            await store_.broadcast()
        except asyncio.CancelledError:
            raise
        except Exception as e:
            log.debug("age ticker: %s", e)


@asynccontextmanager
async def lifespan(app: FastAPI):
    manager = PlatformManager(store)
    store.manager = manager
    app.state.manager = manager
    # демо-движка больше нет: панель показывает только реальные данные площадок.
    # Вместо него — счётчик относительного времени («N минут назад») для реальных событий.
    age_task = asyncio.create_task(_age_ticker(store))
    auto_task = asyncio.create_task(manager.autostart())    # реальные подключения по ключам
    retry_task = asyncio.create_task(manager.retry_disconnected())  # фоновый автоповтор отключённых
    tg_task = None
    if os.getenv("TG_BOT_TOKEN"):                           # телеграм-бот уведомлений
        from . import tgbot
        tg_task = asyncio.create_task(tgbot.start(store))
    app.state.tg_task = tg_task
    ping_task = None
    self_url = os.getenv("SELF_PING_URL", "").strip()      # авто-«будильник» фри-хостинга
    if self_url:
        import urllib.request

        async def _selfping():
            while True:
                await asyncio.sleep(300)
                try:
                    await asyncio.to_thread(
                        urllib.request.urlopen,
                        self_url.rstrip("/") + "/api/health", 20)
                except Exception as e:
                    log.debug("selfping: %s", e)

        ping_task = asyncio.create_task(_selfping())
    log.info("SellHub запущен (только реальные данные площадок + автоподключение)")
    yield
    age_task.cancel()
    auto_task.cancel()
    if tg_task:
        tg_task.cancel()
    if ping_task:
        ping_task.cancel()
    for p in list(manager.tasks):
        await manager.disconnect(p, quiet=True, wipe=False)


app = FastAPI(title="SellHub", version="0.2.0", lifespan=lifespan)

# CORS открыт: панель могут открывать с любых host'ов предпросмотра
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
app.add_middleware(CORSMiddleware, allow_origins=["*"],
                   allow_methods=["*"], allow_headers=["*"])


@app.middleware("http")
async def no_store_assets(request: Request, call_next):
    """HTML/JS/CSS всегда свежие — исключаем показ устаревшей версии из кэша."""
    resp = await call_next(request)
    ct = resp.headers.get("content-type", "")
    if ct.startswith(("text/html", "application/javascript", "text/css")):
        resp.headers["Cache-Control"] = "no-store, max-age=0"
    return resp


from . import auth  # noqa: E402


_PUBLIC = ("/api/login/code", "/api/login/verify", "/api/health", "/api/diag",
           "/api/selfconnect")


@app.middleware("http")
async def gate(request: Request, call_next):
    """Публичная защита: если задан PANEL_PASS, /api/* (кроме входа/health)
    отдаются только при валидной cookie-сессии."""
    if auth.enabled() and request.url.path.startswith("/api") \
            and request.url.path not in _PUBLIC:
        tok = request.cookies.get(auth.COOKIE, "")
        if not auth.check_token(tok):
            return JSONResponse({"login_required": True}, status_code=401)
    return await call_next(request)


@app.post("/api/login/code")
async def api_login_code():
    """Выслать одноразовый код входа в личный Telegram владельца."""
    if not auth.enabled():
        return {"ok": True, "auth": False}
    from . import tgbot
    bot = tgbot.get_bot()
    if bot is None or getattr(bot, "owner", None) is None:
        return JSONResponse({"ok": False,
                             "error": "Бот ещё не готов. Подождите минуту и повторите."},
                            status_code=503)
    code = auth.make_login_code()
    res = await bot.tg.send(
        bot.owner,
        f"🔐 Код входа в панель SellHub: <b>{code}</b>\n"
        "Действует 5 минут. Никому не сообщайте его.",
        menu=False)
    if res and res.get("ok"):
        return {"ok": True}
    why = ""
    if isinstance(res, dict) and res.get("description"):
        why = res["description"]
    elif res is None:
        why = getattr(bot.tg, "last_err", None) or "нет ответа от Telegram"
    else:
        why = "неизвестная ошибка"
    hint = (" Откройте @shopchezze_bot и нажмите /start один раз."
            if "bot can't initiate" in why or "chat not found" in why else "")
    log.warning("login code not delivered: %s", why)
    return JSONResponse({"ok": False, "reason": why,
                         "error": f"Код не доставлен. Telegram: {why}.{hint}"},
                        status_code=502)


@app.get("/api/diag")
async def api_diag(request: Request):
    """Диагностика связки панель↔Telegram. Доступ — только с ключом
    из PANEL_PASS (заголовок x-diag-key), секретов не раскрывает."""
    secret = os.getenv("PANEL_PASS", "").strip()
    if not secret or request.headers.get("x-diag-key", "") != secret:
        return JSONResponse({"ok": False, "error": "forbidden"}, status_code=403)
    from . import tgbot
    bot = tgbot.get_bot()
    task = getattr(app.state, "tg_task", None)
    out = {
        "ok": True,
        "token_in_env": bool(os.getenv("TG_BOT_TOKEN", "").strip()),
        "token_len": len(os.getenv("TG_BOT_TOKEN", "").strip()),
        "owner_env": os.getenv("TG_OWNER_ID", ""),
        "bot_created": bot is not None,
        "bot_owner": getattr(bot, "owner", None),
        "bot_username": getattr(bot, "username", None),
        "bot_ready": getattr(bot, "ready", False),
        "sent_ok": getattr(bot, "sent_ok", 0),
        "sent_fail": getattr(bot, "sent_fail", 0),
        "last_err": getattr(bot, "last_err", None),
        "task": (task.done() and f"done(exc={task.exception()!r})"
                 or ("cancelled" if task.cancelled() else "running"))
        if task else "не создавался",
    }
    if bot is not None:
        me = await bot.tg.call("getMe")
        out["getMe"] = (me or {}).get("ok"), (me or {}).get("description")
        probe = await bot.tg.send(bot.owner, "🩺 Диагностика: канал доставки кода работает.",
                                  menu=False)
        out["probe_send"] = {"ok": bool(probe and probe.get("ok")),
                             "description": (probe or {}).get("description"),
                             "exception": getattr(bot, "last_err", None)}
    return out


@app.post("/api/login/verify")
async def api_login_verify(request: Request):
    """Проверить одноразовый код и выдать cookie-сессию."""
    if not auth.enabled():
        return {"ok": True, "auth": False}
    try:
        body = await request.json()
    except Exception:
        body = {}
    if auth.check_code(body.get("code", "")):
        resp = JSONResponse({"ok": True, "auth": True})
        resp.set_cookie(auth.COOKIE, auth.make_token(), max_age=auth.TTL,
                        httponly=True, samesite="lax", path="/")
        return resp
    return JSONResponse({"ok": False, "error": "Неверный или просроченный код"},
                        status_code=401)


@app.get("/api/state")
async def api_state():
    return store.snapshot()


@app.post("/api/tgtest")
async def api_tgtest():
    """Настоящее тестовое уведомление через TG-бота."""
    from . import tgbot
    try:
        res = await tgbot.send_test(store)
    except Exception as e:
        return {"ok": False, "msg": f"Ошибка: {e}"}
    return {"ok": res == "ok", "msg": res}


@app.post("/api/action")
async def api_action(request: Request):
    try:
        payload = await request.json()
    except Exception:
        payload = {}
    await store.apply(payload)
    return {"ok": True}


@app.post("/api/selfconnect")
async def api_selfconnect(request: Request):
    """Разовое подключение из Console браузера: {pass, platform, key, ua}.
    Защищено PANEL_PASS в теле; CORS открыт, чтобы snippet с playerok.com дошёл."""
    try:
        d = await request.json()
    except Exception:
        d = {}
    secret = os.getenv("PANEL_PASS", "")
    if not secret or (d.get("pass") or "") != secret:
        return JSONResponse({"ok": False, "error": "нет доступа"}, status_code=401)
    platform = d.get("platform") or "playerok"
    if platform not in ("funpay", "playerok"):
        return JSONResponse({"ok": False, "error": "площадка: funpay или playerok"}, status_code=400)
    return await app.state.manager.connect(platform, d.get("key") or "", d.get("ua") or "")


@app.post("/api/connect")
async def api_connect(request: Request):
    """Подключить площадку по ключу: {platform: funpay|playerok, key: ...}"""
    try:
        payload = await request.json()
    except Exception:
        payload = {}
    platform = payload.get("platform")
    key = payload.get("key")
    ua = payload.get("ua") or ""
    if platform not in ("funpay", "playerok"):
        return JSONResponse({"ok": False, "error": "площадка должна быть funpay или playerok"}, status_code=400)
    result = await app.state.manager.connect(platform, key, ua)
    return result


@app.post("/api/disconnect")
async def api_disconnect(request: Request):
    try:
        payload = await request.json()
    except Exception:
        payload = {}
    platform = payload.get("platform")
    if platform in ("funpay", "playerok"):
        await app.state.manager.disconnect(platform)
    return {"ok": True}


@app.get("/api/health")
async def api_health():
    tg = None
    try:
        from . import tgbot as _tgmod
        tg = _tgmod.telemetry()
    except Exception:
        tg = None
    return {
        "ok": True,
        "adapter": adapter_status(),
        "platforms": app.state.manager.status(),
        "clients": len(store.listeners),
        "tg": tg,
    }


@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    if auth.enabled() and not auth.check_token(ws.cookies.get(auth.COOKIE, "")):
        await ws.close(code=4401)
        return
    await ws.accept()
    store.listeners.add(ws)
    try:
        await ws.send_json({"type": "state", "state": store.snapshot()})
        while True:
            await ws.receive_text()  # keep-alive; клиент ничего не шлёт
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        store.listeners.discard(ws)


FRONTEND_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "frontend")
app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
