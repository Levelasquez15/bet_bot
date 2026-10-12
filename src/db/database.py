"""
Motor de Base de Datos y Persistencia Relacional para BetBot.
Soporta SQLite con modo WAL de alto rendimiento y PostgreSQL si se define DATABASE_URL.
Incluye creación automática de esquema, índices optimizados y migración desde JSON.
"""

import os
import sqlite3
import logging
import threading
from contextlib import contextmanager
from typing import Generator, Optional

logger = logging.getLogger(__name__)

# Ruta por defecto para base de datos SQLite local
DEFAULT_DB_DIR = os.path.join(os.getcwd(), "data")
DEFAULT_DB_PATH = os.path.join(DEFAULT_DB_DIR, "betbot.db")

_lock = threading.Lock()


class DatabaseManager:
    """Gestiona conexiones, esquema y transacciones de base de datos."""

    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or os.getenv("SQLITE_DB_PATH") or DEFAULT_DB_PATH
        self.database_url = os.getenv("DATABASE_URL")
        self._is_postgres = bool(self.database_url and self.database_url.startswith("postgres"))
        
        # Asegurar directorio de datos si es SQLite y no en memoria
        if not self._is_postgres and self.db_path != ":memory:":
            db_dir = os.path.dirname(self.db_path)
            if db_dir:
                os.makedirs(db_dir, exist_ok=True)
            
        self.init_db()

    @contextmanager
    def get_connection(self) -> Generator[sqlite3.Connection, None, None]:
        """Context manager seguro para transacciones con lock para hilos."""
        with _lock:
            conn = sqlite3.connect(
                self.db_path,
                timeout=30.0,
                detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES
            )
            conn.row_factory = sqlite3.Row
            try:
                # Optimización de concurrencia SQLite
                conn.execute("PRAGMA journal_mode = WAL;")
                conn.execute("PRAGMA synchronous = NORMAL;")
                conn.execute("PRAGMA busy_timeout = 5000;")
                yield conn
                conn.commit()
            except Exception as e:
                conn.rollback()
                logger.error(f"Error en transacción de base de datos: {e}")
                raise
            finally:
                conn.close()

    def init_db(self) -> None:
        """Crea las tablas e índices necesarios si no existen."""
        with self.get_connection() as conn:
            cursor = conn.cursor()

            # 1. Tabla de suscriptores
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS subscribers (
                chat_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                is_paused INTEGER NOT NULL DEFAULT 0,
                notify_live INTEGER NOT NULL DEFAULT 1,
                notify_upcoming INTEGER NOT NULL DEFAULT 1,
                min_odd REAL NOT NULL DEFAULT 1.30,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            """)

            # Columnas de preferencias (idempotente para bases de datos existentes)
            cursor.execute("PRAGMA table_info(subscribers);")
            existing_sub_cols = [c["name"] for c in cursor.fetchall()]
            if "notify_live" not in existing_sub_cols:
                cursor.execute("ALTER TABLE subscribers ADD COLUMN notify_live INTEGER NOT NULL DEFAULT 1;")
            if "notify_upcoming" not in existing_sub_cols:
                cursor.execute("ALTER TABLE subscribers ADD COLUMN notify_upcoming INTEGER NOT NULL DEFAULT 1;")
            if "min_odd" not in existing_sub_cols:
                cursor.execute("ALTER TABLE subscribers ADD COLUMN min_odd REAL NOT NULL DEFAULT 1.30;")

            # 2. Tabla de picks / pronósticos individuales
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS picks (
                id TEXT PRIMARY KEY,
                game_id TEXT NOT NULL,
                match_name TEXT NOT NULL,
                market TEXT NOT NULL,
                odd REAL,
                minute TEXT,
                score_at_pick TEXT,
                confidence REAL NOT NULL,
                ev_pct REAL,
                fair_odd REAL,
                stake INTEGER NOT NULL DEFAULT 2,
                reason TEXT,
                pick_type TEXT NOT NULL, -- 'live', 'upcoming', 'manual'
                status TEXT NOT NULL DEFAULT 'PENDIENTE', -- PENDIENTE, GANADO, PERDIDO, NO_VERIFICABLE, ANULADO
                final_score TEXT,
                profit_units REAL NOT NULL DEFAULT 0.0,
                created_at TEXT NOT NULL,
                verified_at TEXT
            );
            """)

            # 3. Tabla de combinadas / parlays
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS parlays (
                id TEXT PRIMARY KEY,
                total_odd REAL NOT NULL,
                combined_prob REAL NOT NULL,
                stake INTEGER NOT NULL DEFAULT 2,
                legs_count INTEGER NOT NULL DEFAULT 2,
                legs_json TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'PENDIENTE',
                profit_units REAL NOT NULL DEFAULT 0.0,
                created_at TEXT NOT NULL,
                verified_at TEXT
            );
            """)

            # 4. Tabla de auditoría / registro de bankroll
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS bankroll_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                pick_id TEXT,
                delta_units REAL NOT NULL,
                balance_units REAL NOT NULL,
                note TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY (pick_id) REFERENCES picks (id)
            );
            """)

            # 5. Tablas de Grafo de Conocimiento y Auditoría de Tickets
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS knowledge_nodes (
                id TEXT PRIMARY KEY,
                node_type TEXT NOT NULL, -- PLAYER, TEAM, MARKET, RUNG, ERROR_PATTERN
                name TEXT NOT NULL,
                properties_json TEXT NOT NULL DEFAULT '{}',
                updated_at TEXT NOT NULL
            );
            """)

            cursor.execute("""
            CREATE TABLE IF NOT EXISTS knowledge_edges (
                id TEXT PRIMARY KEY,
                source_id TEXT NOT NULL,
                target_id TEXT NOT NULL,
                relation TEXT NOT NULL, -- FAILS_ON, SUCCEEDS_ON, TRIGGERED_PATTERN, HAS_VALUE
                weight REAL NOT NULL DEFAULT 1.0,
                properties_json TEXT NOT NULL DEFAULT '{}',
                updated_at TEXT NOT NULL
            );
            """)

            cursor.execute("""
            CREATE TABLE IF NOT EXISTS ticket_audits (
                id TEXT PRIMARY KEY,
                chat_id INTEGER,
                bookmaker TEXT,
                total_odd REAL,
                legs_count INTEGER NOT NULL DEFAULT 0,
                hits_count INTEGER NOT NULL DEFAULT 0,
                misses_count INTEGER NOT NULL DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'PENDIENTE',
                legs_json TEXT NOT NULL DEFAULT '[]',
                insights_json TEXT NOT NULL DEFAULT '[]',
                raw_summary TEXT,
                created_at TEXT NOT NULL
            );
            """)

            # Índices de aceleración para consultas frecuentes
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_picks_status ON picks(status);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_picks_created_at ON picks(created_at);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_picks_game_id ON picks(game_id);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_subscribers_paused ON subscribers(is_paused);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_knodes_type ON knowledge_nodes(node_type);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_kedges_source ON knowledge_edges(source_id);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_kedges_target ON knowledge_edges(target_id);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_ticket_audits_chat ON ticket_audits(chat_id);")

            logger.info("Base de datos inicializada correctamente con modo WAL, índices y tablas de Grafo de Conocimiento.")


# Instancia singleton para toda la aplicación
db = DatabaseManager()
