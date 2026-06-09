# TradSense - Installation Script
# Jalankan: .\install.ps1

Write-Host "=== TradSense Installer ===" -ForegroundColor Cyan

# Detect Python
$python = "C:\msys64\ucrt64\bin\python3.12.exe"
if (-not (Test-Path $python)) {
    Write-Host "Python 3.12 tidak ditemukan di MSYS2!" -ForegroundColor Red
    exit 1
}

# Set SSL cert
$env:SSL_CERT_FILE = & $python -c "import certifi; print(certifi.where())" 2>$null

# Install MSYS2 system packages (numpy, pandas, cffi)
Write-Host "`nInstalling system packages via pacman..." -ForegroundColor Yellow
C:\msys64\usr\bin\bash.exe -lc "pacman -S --noconfirm --needed mingw-w64-ucrt-x86_64-python-numpy mingw-w64-ucrt-x86_64-python-pandas mingw-w64-ucrt-x86_64-python-cffi mingw-w64-ucrt-x86_64-python-pip mingw-w64-ucrt-x86_64-python-certifi"

# Install pip packages
Write-Host "`nInstalling pip packages..." -ForegroundColor Yellow
& $python -m pip install --break-system-packages --trusted-host pypi.org --trusted-host files.pythonhosted.org yfinance requests feedparser SQLAlchemy APScheduler "python-telegram-bot>=21.0" openai google-genai textblob python-dotenv rich

Write-Host "`n=== Installation Complete ===" -ForegroundColor Green
Write-Host "Jalankan: $python main.py --mode test" -ForegroundColor Cyan
