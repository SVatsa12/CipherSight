@echo off
setlocal
color 0A

echo ========================================================
echo        CipherSight Hybrid Verification Checkout
echo ========================================================
echo.

:: Check for Python installation
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo  [!] ERROR: Python is not installed or not added to your system PATH.
    echo  Please install Python 3.9 or newer and try again.
    pause
    exit /b
)

:: Check/Create Virtual Environment
if not exist ".venv\Scripts\activate.bat" (
    echo  [*] Creating Python Virtual Environment...
    python -m venv .venv
)

:: Activate Virtual Environment
echo  [*] Activating Virtual Environment...
call .venv\Scripts\activate.bat

:: Install Requirements Silently
echo  [*] Installing required libraries... (This may take a moment)
python -m pip install --upgrade pip >nul 2>&1
pip install -q flask paho-mqtt qrcode[pil] numpy 

:: Provide Instructions for Hardware
echo.
echo ========================================================
echo  Hardware Check:
echo  1. Ensure your ESP32 is powered on.
echo  2. Ensure it is connected to WiFi and Broker.
echo  (The OLED should show the CipherSight scanning eye)
echo ========================================================
echo.

:: Launch the Web Frontend in default browser
echo  [*] Launching Merchant POS System in your browser...
:: Ping localhost hack to create a tiny delay so the server can bind the port first
start /B cmd /c "ping localhost -n 3 >nul 2>&1 && start http://localhost:5000/merchant"

:: Start the Server
echo  [*] Starting Backend Server (Press CTRL+C to stop)...
echo.
python pos/app.py

pause
