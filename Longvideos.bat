@echo off
chcp 65001 >nul
title YouTube Long Videos Dubbing Tool
color 0E

cls
echo ========================================
echo   Long Videos Dubbing Tool
echo   Timeout: 20 minutes per video
echo ========================================
echo.

echo [1/2] Checking project files...

if not exist "package.json" (
    color 0C
    echo.
    echo [ERROR] package.json not found!
    echo.
    goto END
)

if not exist "run_longvideos.py" (
    color 0C
    echo.
    echo [ERROR] run_longvideos.py not found!
    echo.
    goto END
)

if not exist "failed.txt" (
    color 0E
    echo.
    echo [WARNING] failed.txt not found!
    echo.
    echo This script processes failed videos from failed.txt
    echo Run dub2.bat first to generate failed.txt
    echo.
    goto END
)

echo [OK] Project files found
echo.

echo [2/2] Checking npm dependencies...

if not exist "node_modules" (
    echo [INFO] Installing vot-cli-live...
    echo.
    call npm install
    if errorlevel 1 (
        color 0C
        echo.
        echo [ERROR] Failed to install npm packages!
        echo.
        goto END
    )
    echo.
) else (
    echo [OK] npm packages installed
    echo.
)

color 0E
echo ========================================
echo   Processing long videos...
echo   Timeout: 20 minutes per video
echo ========================================
echo.
echo.

python run_longvideos.py

if errorlevel 1 (
    color 0C
    echo.
    echo ========================================
    echo   Program finished with errors
    echo ========================================
    echo.
) else (
    color 0A
    echo.
    echo ========================================
    echo   Processing completed successfully!
    echo ========================================
    echo.
)

:END
echo.
pause