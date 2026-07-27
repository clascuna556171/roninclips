# RoninClips One-Line PowerShell Installer
Write-Host "========================================================" -ForegroundColor Cyan
Write-Host "               RONINCLIPS INSTALLER" -ForegroundColor Cyan
Write-Host "========================================================" -ForegroundColor Cyan
Write-Host ""

$installDir = Join-Path $HOME "roninclips"

if (-not (Test-Path $installDir)) {
    Write-Host "[1/4] Cloning RoninClips repository to $installDir..." -ForegroundColor Yellow
    git clone https://github.com/clascuna556171/roninclips.git $installDir
} else {
    Write-Host "[1/4] RoninClips directory exists at $installDir. Pulling updates..." -ForegroundColor Yellow
    Set-Location $installDir
    git pull
}

Set-Location $installDir

Write-Host "`n[2/4] Setting up environment configuration..." -ForegroundColor Yellow
if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
    php artisan key:generate
}

Write-Host "`n[3/4] Installing PHP & Python dependencies..." -ForegroundColor Yellow
composer install --no-interaction
pip install -r processor/requirements.txt

Write-Host "`n[4/4] Running database setup..." -ForegroundColor Yellow
php artisan migrate --force

Write-Host "`n========================================================" -ForegroundColor Green
Write-Host "   [SUCCESS] RoninClips Installed Successfully!" -ForegroundColor Green
Write-Host "   Launching Dashboard at http://127.0.0.1:8000..." -ForegroundColor Green
Write-Host "========================================================" -ForegroundColor Green

Start-Process "http://127.0.0.1:8000"
php artisan serve --port=8000
