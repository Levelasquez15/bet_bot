FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8000

WORKDIR /app

# Instalar dependencias de Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar código fuente
COPY src ./src
COPY telegram_bot.py ./telegram_bot.py

# Crear directorio de persistencia para SQLite
RUN mkdir -p /app/data

EXPOSE 8000

CMD ["python", "telegram_bot.py"]
