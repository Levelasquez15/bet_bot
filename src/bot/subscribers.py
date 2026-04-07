import json
import logging
import os

logger = logging.getLogger(__name__)

# Archivo donde se guardan los chat_ids de los suscriptores
SUBSCRIBERS_FILE = "subscribers.json"

def load_subscribers() -> set:
    """Lee los suscriptores registrados del archivo JSON."""
    if not os.path.exists(SUBSCRIBERS_FILE):
        return set()
    try:
        with open(SUBSCRIBERS_FILE, "r") as f:
            data = json.load(f)
            return set(data)
    except Exception as e:
        logger.error(f"Error leyendo subscribers.json: {e}")
        return set()

def save_subscribers(subscribers: set) -> None:
    """Guarda el set de chat_ids en disco."""
    try:
        with open(SUBSCRIBERS_FILE, "w") as f:
            json.dump(list(subscribers), f)
    except Exception as e:
        logger.error(f"Error guardando subscribers.json: {e}")

def add_subscriber(chat_id: int) -> bool:
    """Agrega un chat_id. Retorna True si era nuevo, False si ya existía."""
    subscribers = load_subscribers()
    is_new = chat_id not in subscribers
    subscribers.add(chat_id)
    save_subscribers(subscribers)
    return is_new

def get_subscribers() -> set:
    """Devuelve todos los chat_ids registrados."""
    return load_subscribers()
