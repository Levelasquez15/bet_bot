"""
Gestión de suscriptores respaldada por base de datos relacional SQLite/Postgres.
Mantiene compatibilidad total con la API existente.
"""

import logging
from typing import Set
from src.db.repositories import SubscriberRepository, migrate_json_to_db

logger = logging.getLogger(__name__)

# Ejecutar migración automática si existen archivos JSON antiguos
try:
    migrate_json_to_db()
except Exception as e:
    logger.debug(f"Migración inicial JSON: {e}")


def add_subscriber(chat_id: int) -> bool:
    """Agrega un chat_id a la base de datos. Retorna True si era nuevo, False si ya existía."""
    return SubscriberRepository.add_subscriber(chat_id)


def get_subscribers() -> Set[int]:
    """Devuelve todos los chat_ids registrados."""
    return SubscriberRepository.get_all_subscribers()


def set_paused(chat_id: int, paused: bool) -> None:
    """Pausa o reanuda las alertas de un chat_id."""
    SubscriberRepository.set_paused(chat_id, paused)


def get_active_subscribers() -> Set[int]:
    """Devuelve chat_ids activos que no están pausados."""
    return SubscriberRepository.get_active_subscribers()
