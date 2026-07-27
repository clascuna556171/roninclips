@echo off
title RoninClips - Local Dashboard
echo ========================================================
echo               RONINCLIPS - LAUNCHER
echo ========================================================
echo.
echo Launching local server at http://127.0.0.1:8000 ...
echo.
start "" http://127.0.0.1:8000
php artisan serve --port=8000
pause
