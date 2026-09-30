FROM python:3.12-slim

# Install system dependencies for scipy
RUN apt-get update && apt-get install -y \
    build-essential \
    gfortran \
    libopenblas-dev \
    liblapack-dev \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8000

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src ./src
COPY telegram_bot.py ./telegram_bot.py
RUN mkdir -p /app/data

EXPOSE 8000

CMD ["python", "telegram_bot.py"]
