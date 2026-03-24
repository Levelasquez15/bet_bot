@echo off
REM Run Telegram bot with project dependencies
echo Installing dependencies...
pip install -q -r requirements.txt

echo.
echo Starting Telegram bot...
python telegram_bot.py
pause
