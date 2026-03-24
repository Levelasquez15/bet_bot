FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src ./src
COPY scripts ./scripts
COPY telegram_bot.py ./telegram_bot.py
COPY app_streamlit.py ./app_streamlit.py

CMD ["python", "telegram_bot.py"]
