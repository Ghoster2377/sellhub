@echo off
chcp 65001 >nul
taskkill /fi "WINDOWTITLE eq SellHub-сервер*" /f >nul 2>&1
echo   Панель остановлена. Окно "SellHub-сервер" закрыто.
timeout /t 3 >nul
