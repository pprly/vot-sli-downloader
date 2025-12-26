@echo off
chcp 65001 >nul
title YouTube Video Dubbing Tool v2.0
color 0A

cls
echo ========================================
echo   YouTube Video Dubbing Tool v2.0
echo ========================================
echo.

echo [1/2] Checking project files...

if not exist "package.json" (
    color 0C
    echo.
    echo [ERROR] package.json not found!
    echo.
    echo Current folder: %CD%
    echo.
    echo Make sure you have these files in the same folder:
    echo - package.json
    echo - run2.py
    echo - dub2.bat
    echo - cookies.txt
    echo.
    goto END
)

if not exist "run2.py" (
    color 0C
    echo.
    echo [ERROR] run2.py not found!
    echo.
    echo Make sure run2.py is in the same folder
    echo.
    goto END
)

echo [OK] Project files found
echo.

echo [2/2] Checking npm dependencies...

if not exist "node_modules" (
    echo [INFO] Installing vot-cli-live...
    echo        This will take 1-2 minutes on first run
    echo.
    call npm install
    if errorlevel 1 (
        color 0C
        echo.
        echo [ERROR] Failed to install npm packages!
        echo.
        echo Possible reasons:
        echo 1. Node.js not installed (download from https://nodejs.org/)
        echo 2. No internet connection
        echo 3. Permission issues
        echo.
        echo Try manually: npm install
        echo.
        goto END
    )
    echo.
) else (
    echo [OK] npm packages installed
    echo.
)

echo [BONUS] Checking Python libraries...
python -c "import deep_translator" 2>nul
if errorlevel 1 (
    echo [INFO] Installing deep-translator for title translation...
    pip install deep-translator >nul 2>&1
)
echo [OK] Python libraries ready
echo.

echo [INFO] ffmpeg will be used for video processing
echo        Make sure ffmpeg is installed and in PATH
echo.

color 0A
echo ========================================
echo   Starting video processing...
echo ========================================
echo.

if not exist "urls.txt" (
    echo [INFO] urls.txt not found
    echo        It will be created automatically
    echo.
)

python run2.py

if errorlevel 1 (
    color 0C
    echo.
    echo ========================================
    echo   Program finished with errors
    echo ========================================
    echo.
    echo Possible reasons:
    echo - Python not installed
    echo - yt-dlp not installed (pip install yt-dlp)
    echo - ffmpeg not installed
    echo - Error processing video
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
