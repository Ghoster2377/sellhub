@echo off
chcp 65001 >nul
title SellHub - запуск
cd /d "%~dp0"

echo.
echo   SellHub - панель продавца на этом компьютере
echo   ------------------------------------------------
echo.

where py >nul 2>&1
if %errorlevel%==0 (set PY=py -3) else (set PY=python)

%PY% --version >nul 2>&1
if errorlevel 1 (
  echo   [ОШИБКА] На компьютере не установлен Python.
  echo.
  echo   1^) Откройте сайт https://www.python.org/downloads/
  echo   2^) Нажмите жёлтую кнопку "Download Python 3..."
  echo   3^) Запустите скачанный установщик и ОБЯЗАТЕЛЬНО
  echo     поставьте галочку "Add python.exe to PATH" внизу окна,
  echo     затем нажмите "Install Now".
  echo   4^) Снова дважды кликните по этому файлу.
  echo.
  pause
  exit /b 1
)

echo   [1/3] Устанавливаю компоненты панели...
%PY% -m pip install --disable-pip-version-check -q -r requirements.txt
if errorlevel 1 (
  echo   [ОШИБКА] Не удалось установить компоненты.
  echo   Проверьте, что компьютер подключён к интернету, и повторите запуск.
  pause
  exit /b 1
)

echo   [2/3] Запускаю сервер панели...
start "SellHub-сервер" /min %PY% -m uvicorn backend.main:app --host 127.0.0.1 --port 8000

echo   [3/3] Открываю панель в браузере...
timeout /t 4 /nobreak >nul
start "" http://localhost:8000

echo.
echo   ГОТОВО. Панель открыта в браузере: http://localhost:8000
echo.
echo   Это окно можно закрыть. Сервер работает в отдельном
echo   свёрнутом окне "SellHub-сервер".
echo   Чтобы выключить панель - закройте окно "SellHub-сервер"
echo   или запустите файл stop.bat
echo.
pause
