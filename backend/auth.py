"""Защита публичной панели: вход по одноразовому коду из Telegram владельца.

PANEL_PASS используется ТОЛЬКО как секрет для подписи cookie-сессии (не как
пароль для входа). Сам вход — код, который бот присылает в личный чат владельца
(TG_OWNER_ID), поэтому панель открыть может только владелец Telegram-аккаунта.

Когда PANEL_PASS не задан (локальный запуск) — защита выключена.
"""
import hashlib
import hmac
import os
import random
import time

PASS = os.getenv("PANEL_PASS", "").strip()
COOKIE = "sellhub_sid"
TTL = 60 * 60 * 24 * 30          # 30 дней
CODE_TTL = 300                   # код живёт 5 минут

_code = {"val": None, "exp": 0.0}


def enabled() -> bool:
    return bool(PASS)


def _sign(exp: int) -> str:
    return hmac.new(PASS.encode(), str(exp).encode(), hashlib.sha256).hexdigest()


def make_token() -> str:
    exp = int(time.time()) + TTL
    return f"{exp}.{_sign(exp)}"


def check_token(tok: str) -> bool:
    try:
        exp_s, sig = tok.split(".", 1)
        exp = int(exp_s)
    except Exception:
        return False
    if exp < int(time.time()):
        return False
    return hmac.compare_digest(sig, _sign(exp))


def make_login_code() -> str:
    """Сгенерировать одноразовый 6-значный код входа (живёт CODE_TTL)."""
    c = f"{random.randint(0, 999999):06d}"
    _code["val"] = c
    _code["exp"] = time.time() + CODE_TTL
    return c


def check_code(c) -> bool:
    """Проверить одноразовый код; после успеха код сгорает."""
    if not _code["val"] or time.time() > _code["exp"]:
        return False
    ok = hmac.compare_digest(str(c or "").strip(), _code["val"])
    if ok:
        _code["val"] = None
        _code["exp"] = 0.0
    return ok
