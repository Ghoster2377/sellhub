"""Точка входа для облачного хостинга (Hugging Face Spaces и подобные).

Платформа задаёт порт через переменную PORT (по умолчанию 7860)
и сама устанавливает зависимости из requirements.txt.
"""
import os

import uvicorn

from backend.main import app  # noqa: F401


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", "7860")))
