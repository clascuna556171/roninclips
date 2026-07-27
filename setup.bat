@echo off
title RoninClips - One-Click Installer
echo ========================================================
echo               RONINCLIPS - INSTALLER
echo ========================================================
echo.

REM 1. Check PHP
where php >nul 2>nul
if %errorlevel% neq 0 (
    echo [ERROR] PHP is not installed or not in PATH!
    echo Please install PHP 8.2+ from https://windows.php.net
    pause
    exit /b 1
)

REM 2. Check Composer
where composer >nul 2>nul
if %errorlevel% neq 0 (
    echo [ERROR] Composer is not installed or not in PATH!
    echo Please install Composer from https://getcomposer.org
    pause
    exit /b 1
)

REM 3. Check Python
where python >nul 2>nul
if %errorlevel% neq 0 (
    echo [ERROR] Python is not installed or not in PATH!
    echo Please install Python 3.10+ from https://python.org
    pause
    exit /b 1
)

REM 4. Check FFmpeg
where ffmpeg >nul 2>nul
if %errorlevel% neq 0 (
    echo [WARNING] FFmpeg was not found in system PATH!
    echo FFmpeg is required to process videos. Download from https://ffmpeg.org
    echo.
)

echo [1/4] Setting up environment configuration...
if not exist .env (
    copy .env.example .env
    call php artisan key:generate
)

echo.
echo [2/4] Installing PHP dependencies via Composer...
call composer install --no-interaction --prefer-dist

echo.
echo [3/4] Installing Python processing dependencies...
pip install -r processor/requirements.txt

echo.
echo [4/4] Running database migrations...
call php artisan migrate --force

echo.
echo ========================================================
echo   [SUCCESS] RoninClips installation complete!
echo.
echo   1. Edit your .env file to add your GROQ_API_KEY
echo   2. Run 'start.bat' to launch the local web dashboard!
echo ========================================================
echo.
pause
