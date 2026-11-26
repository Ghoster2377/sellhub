"""Адаптеры площадок.

Заглушка: BaseAdapter (no-op) — используется только для
неподключённых площадок.

Реальный режим (фаза 1): PlatformManager (backend/manager.py) создаёт
FunPayAdapter / PlayerokAdapter по ключам из .env, data/credentials.json
или из формы «Настройки» в панели.
"""
import os

from .base import BaseAdapter


def get_adapter() -> BaseAdapter:
    return BaseAdapter()


def adapter_status() -> dict:
    return {
        "mode": "real: только реальные данные подключённых площадок, демо-данных нет",
        "funpay": {"key_in_env": bool(os.getenv("FUNPAY_GOLDEN_KEY")), "implemented": True},
        "playerok": {"token_in_env": bool(os.getenv("PLAYEROK_TOKEN")), "implemented": True},
    }
