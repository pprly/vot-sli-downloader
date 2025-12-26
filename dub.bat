@echo off
chcp 65001 >nul
title YouTube Video Dubbing with Live Voices
color 0A

:start
cls
echo ==========================================
echo    YouTube Video Dubbing Tool
echo    С живыми голосами Яндекса
echo ==========================================
echo.
echo Для выхода введите: exit
echo.

set "url="
set /p url="Вставьте ссылку на YouTube видео: "

if "%url%"=="" (
    echo ❌ Ошибка: Ссылка не введена!
    timeout /t 2 >nul
    goto start
)

if /i "%url%"=="exit" (
    echo.
    echo 👋 Работа завершена!
    timeout /t 2 >nul
    exit
)

echo.
echo ⏳ Запуск обработкии...
echo.

python run.py "%url%"

echo.
echo ✅ Обработка завершена!
echo.
echo ==========================================
timeout /t 3 >nul

goto start 