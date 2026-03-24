Write-Host "Installing dependencies..."
pip install -q -r requirements.txt

Write-Host ""
Write-Host "Starting Telegram bot..."
python telegram_bot.py
