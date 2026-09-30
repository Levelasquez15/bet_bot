"""
Repositorios de acceso a datos para BetBot.
Maneja operaciones transaccionales para suscriptores, picks, combinadas y bankroll.
"""

import json
import logging
import os
import uuid
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any, Optional, Set
from src.db.database import db

logger = logging.getLogger(__name__)
BOGOTA_TZ = timezone(timedelta(hours=-5))


def now_str() -> str:
    """Devuelve la fecha y hora actual en zona horaria Bogotá."""
    return datetime.now(tz=BOGOTA_TZ).strftime("%Y-%m-%d %H:%M:%S")


class SubscriberRepository:
    """Acceso a datos de suscriptores de Telegram."""

    @staticmethod
    def add_subscriber(chat_id: int, username: Optional[str] = None, first_name: Optional[str] = None) -> bool:
        """
        Registra un suscriptor. Devuelve True si es nuevo, False si ya existía.
        Si ya existía, reactiva el estado pausado a activo.
        """
        now = now_str()
        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT chat_id, is_paused FROM subscribers WHERE chat_id = ?", (chat_id,))
            row = cursor.fetchone()

            if row is None:
                cursor.execute("""
                INSERT INTO subscribers (chat_id, username, first_name, is_paused, created_at, updated_at)
                VALUES (?, ?, ?, 0, ?, ?)
                """, (chat_id, username, first_name, now, now))
                logger.info(f"Nuevo suscriptor guardado en BD: {chat_id}")
                return True
            else:
                # Si estaba pausado, reactivar
                cursor.execute("""
                UPDATE subscribers
                SET is_paused = 0, username = COALESCE(?, username), first_name = COALESCE(?, first_name), updated_at = ?
                WHERE chat_id = ?
                """, (username, first_name, now, chat_id))
                return False

    @staticmethod
    def set_paused(chat_id: int, paused: bool) -> None:
        """Pausa o reanuda las notificaciones de un usuario."""
        now = now_str()
        is_paused_val = 1 if paused else 0
        with db.get_connection() as conn:
            conn.execute("""
            UPDATE subscribers SET is_paused = ?, updated_at = ? WHERE chat_id = ?
            """, (is_paused_val, now, chat_id))
            logger.info(f"Suscriptor {chat_id} estado pausado actualizado a: {paused}")

    @staticmethod
    def get_active_subscribers() -> Set[int]:
        """Devuelve un set de chat_ids activos que deben recibir notificaciones."""
        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT chat_id FROM subscribers WHERE is_paused = 0")
            rows = cursor.fetchall()
            return {r["chat_id"] for r in rows}

    @staticmethod
    def get_subscriber(chat_id: int) -> Optional[dict]:
        """Obtiene los datos y preferencias configuradas de un suscriptor."""
        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM subscribers WHERE chat_id = ?", (chat_id,))
            row = cursor.fetchone()
            return dict(row) if row else None

    @staticmethod
    def update_prefs(
        chat_id: int,
        notify_live: Optional[int] = None,
        notify_upcoming: Optional[int] = None,
        min_odd: Optional[float] = None
    ) -> Optional[dict]:
        """Actualiza las preferencias de alertas de un suscriptor."""
        now = now_str()
        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM subscribers WHERE chat_id = ?", (chat_id,))
            row = cursor.fetchone()
            if not row:
                return None

            new_live = notify_live if notify_live is not None else row["notify_live"]
            new_upcoming = notify_upcoming if notify_upcoming is not None else row["notify_upcoming"]
            new_min_odd = min_odd if min_odd is not None else row["min_odd"]

            cursor.execute("""
            UPDATE subscribers
            SET notify_live = ?, notify_upcoming = ?, min_odd = ?, updated_at = ?
            WHERE chat_id = ?
            """, (new_live, new_upcoming, new_min_odd, now, chat_id))

            cursor.execute("SELECT * FROM subscribers WHERE chat_id = ?", (chat_id,))
            return dict(cursor.fetchone())

    @staticmethod
    def get_active_subscribers_for_type(pick_type: str = "live") -> Set[int]:
        """Devuelve chat_ids activos que desean recibir este tipo de señal ('live' o 'upcoming')."""
        with db.get_connection() as conn:
            cursor = conn.cursor()
            if pick_type == "live":
                cursor.execute("SELECT chat_id FROM subscribers WHERE is_paused = 0 AND notify_live = 1")
            elif pick_type == "upcoming":
                cursor.execute("SELECT chat_id FROM subscribers WHERE is_paused = 0 AND notify_upcoming = 1")
            else:
                cursor.execute("SELECT chat_id FROM subscribers WHERE is_paused = 0")
            rows = cursor.fetchall()
            return {r["chat_id"] for r in rows}

    @staticmethod
    def get_all_subscribers() -> Set[int]:
        """Devuelve un set con todos los chat_ids registrados en la base de datos."""
        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT chat_id FROM subscribers")
            rows = cursor.fetchall()
            return {r["chat_id"] for r in rows}


class PickRepository:
    """Acceso a datos de picks y análisis de rendimiento."""

    @staticmethod
    def _parse_odd(odd_val: Any) -> Optional[float]:
        """Extrae el valor flotante de la cuota."""
        if odd_val is None:
            return None
        if isinstance(odd_val, (int, float)):
            return float(odd_val)
        try:
            # Caso string '1.55 - 1.70': tomamos el mínimo para ser conservadores
            s = str(odd_val).replace(",", ".").strip()
            if "-" in s:
                parts = s.split("-")
                return float(parts[0].strip())
            return float(s)
        except (ValueError, TypeError):
            return None

    @staticmethod
    def record_pick(pick: dict, game_id: Any, score_at_pick: str, pick_type: str = "live") -> str:
        """
        Inserta un nuevo pronóstico en la base de datos relacional.
        Retorna el ID único del pick.
        """
        pick_id = pick.get("id") or str(uuid.uuid4())[:8]
        odd_num = PickRepository._parse_odd(pick.get("odd"))
        v_info = pick.get("value_info") or {}

        # Determinar stake sugerido si no viene explícito
        stake = pick.get("stake")
        if not stake:
            stake = v_info.get("recommended_stake") or (4 if pick.get("confidence", 0) >= 80 else 3 if pick.get("confidence", 0) >= 73 else 2)

        now = now_str()

        with db.get_connection() as conn:
            conn.execute("""
            INSERT OR REPLACE INTO picks (
                id, game_id, match_name, market, odd, minute, score_at_pick,
                confidence, ev_pct, fair_odd, stake, reason, pick_type,
                status, profit_units, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'PENDIENTE', 0.0, ?)
            """, (
                pick_id,
                str(game_id),
                pick["match"],
                pick["market"],
                odd_num,
                str(pick.get("minute", "?")),
                score_at_pick,
                float(pick["confidence"]),
                v_info.get("ev_pct"),
                v_info.get("fair_odd"),
                int(stake),
                pick.get("reason", ""),
                pick_type,
                now
            ))

        logger.info(f"Pick guardado en BD [{pick_id}]: {pick['match']} → {pick['market']} (Stake {stake})")
        return pick_id

    @staticmethod
    def update_pick_result(pick_id: str, status: str, final_score: str) -> None:
        """
        Actualiza el resultado y calcula el beneficio neto en unidades (+/- U).
        """
        now = now_str()
        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT odd, stake FROM picks WHERE id = ?", (pick_id,))
            row = cursor.fetchone()

            profit_units = 0.0
            if row:
                odd = row["odd"] or 1.50
                stake = row["stake"] or 2

                if status == "GANADO":
                    profit_units = round(stake * (odd - 1.0), 2)
                elif status == "PERDIDO":
                    profit_units = round(-1.0 * stake, 2)
                else:
                    profit_units = 0.0

            cursor.execute("""
            UPDATE picks
            SET status = ?, final_score = ?, profit_units = ?, verified_at = ?
            WHERE id = ?
            """, (status, final_score, profit_units, now, pick_id))

            # Registrar en log de balance si es GANADO o PERDIDO
            if status in ("GANADO", "PERDIDO"):
                cursor.execute("""
                SELECT COALESCE(SUM(profit_units), 0.0) as current_balance FROM picks WHERE status IN ('GANADO', 'PERDIDO')
                """)
                cur_bal = cursor.fetchone()["current_balance"]
                cursor.execute("""
                INSERT INTO bankroll_log (pick_id, delta_units, balance_units, note, created_at)
                VALUES (?, ?, ?, ?, ?)
                """, (pick_id, profit_units, cur_bal, f"{status} {final_score}", now))

        logger.info(f"Pick [{pick_id}] verificado en BD → {status} ({final_score}) | Ganancia: {profit_units:+.2f} U")

    @staticmethod
    def get_pending_picks() -> List[dict]:
        """Obtiene los pronósticos que esperan ser verificados."""
        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM picks WHERE status = 'PENDIENTE' ORDER BY created_at ASC")
            rows = cursor.fetchall()
            return [dict(r) for r in rows]

    @staticmethod
    def get_recent_picks(limit: int = 10) -> List[dict]:
        """Obtiene los últimos N picks ordenados por fecha descendente."""
        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM picks ORDER BY created_at DESC LIMIT ?", (limit,))
            rows = cursor.fetchall()
            return [dict(r) for r in rows]

    @staticmethod
    def get_stats() -> dict:
        """
        Calcula estadísticas avanzadas de efectividad y rentabilidad.
        """
        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN status = 'GANADO' THEN 1 ELSE 0 END) as ganados,
                SUM(CASE WHEN status = 'PERDIDO' THEN 1 ELSE 0 END) as perdidos,
                SUM(CASE WHEN status = 'PENDIENTE' THEN 1 ELSE 0 END) as pendientes,
                SUM(CASE WHEN status = 'NO_VERIFICABLE' THEN 1 ELSE 0 END) as no_verif,
                SUM(CASE WHEN status IN ('GANADO', 'PERDIDO') THEN stake ELSE 0 END) as total_staked,
                SUM(CASE WHEN status IN ('GANADO', 'PERDIDO') THEN profit_units ELSE 0.0 END) as net_profit
            FROM picks;
            """)
            row = cursor.fetchone()

            total = row["total"] or 0
            ganados = row["ganados"] or 0
            perdidos = row["perdidos"] or 0
            pendientes = row["pendientes"] or 0
            no_verif = row["no_verif"] or 0
            total_staked = row["total_staked"] or 0
            net_profit = round(row["net_profit"] or 0.0, 2)

            verificados = ganados + perdidos
            efectividad = round((ganados / verificados * 100), 1) if verificados > 0 else 0.0
            yield_pct = round((net_profit / total_staked * 100), 2) if total_staked > 0 else 0.0

            # Calcular racha actual
            cursor.execute("""
            SELECT status FROM picks
            WHERE status IN ('GANADO', 'PERDIDO')
            ORDER BY verified_at DESC, created_at DESC
            LIMIT 10
            """)
            recent_results = [r["status"] for r in cursor.fetchall()]

            streak_count = 0
            streak_type = ""
            if recent_results:
                streak_type = recent_results[0]
                for res in recent_results:
                    if res == streak_type:
                        streak_count += 1
                    else:
                        break

            streak_str = f"{'+' if streak_type == 'GANADO' else '-'}{streak_count}" if streak_count > 0 else "0"

            return {
                "total": total,
                "ganados": ganados,
                "perdidos": perdidos,
                "pendientes": pendientes,
                "no_verif": no_verif,
                "efectividad": efectividad,
                "net_profit": net_profit,
                "total_staked": total_staked,
                "yield_pct": yield_pct,
                "streak": streak_str,
            }


class ParlayRepository:
    """Acceso a datos de apuestas combinadas (parlays)."""

    @staticmethod
    def record_parlay(parlay: dict) -> str:
        """Guarda un ticket de combinada."""
        parlay_id = str(uuid.uuid4())[:8]
        now = now_str()
        legs_json = json.dumps(parlay.get("legs", []), ensure_ascii=False)

        with db.get_connection() as conn:
            conn.execute("""
            INSERT INTO parlays (
                id, total_odd, combined_prob, stake, legs_count, legs_json, status, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, 'PENDIENTE', ?)
            """, (
                parlay_id,
                float(parlay.get("total_odd", 0.0)),
                float(parlay.get("combined_prob", 0.0)),
                int(parlay.get("stake", 2)),
                len(parlay.get("legs", [])),
                legs_json,
                now
            ))
        logger.info(f"Parlay guardado en BD [{parlay_id}] | Cuota: {parlay.get('total_odd')}")
        return parlay_id


def migrate_json_to_db() -> None:
    """
    Migración automática idempotente:
    Si existen subscribers.json, paused_subscribers.json o picks_history.json,
    migra sus registros a la base de datos SQLite y no los duplica.
    """
    # 1. Migrar suscriptores
    if os.path.exists("subscribers.json"):
        try:
            with open("subscribers.json", "r", encoding="utf-8") as f:
                subs = json.load(f)
            paused = set()
            if os.path.exists("paused_subscribers.json"):
                with open("paused_subscribers.json", "r", encoding="utf-8") as f_p:
                    paused = set(json.load(f_p))

            for cid in subs:
                try:
                    chat_id = int(cid)
                    is_new = SubscriberRepository.add_subscriber(chat_id)
                    if chat_id in paused:
                        SubscriberRepository.set_paused(chat_id, True)
                except Exception as ex:
                    logger.debug(f"Error migrando suscriptor {cid}: {ex}")
            logger.info("Migración de suscriptores JSON a SQLite completada.")
        except Exception as e:
            logger.error(f"Error procesando migración de subscribers.json: {e}")

    # 2. Migrar historial de picks
    if os.path.exists("picks_history.json"):
        try:
            with open("picks_history.json", "r", encoding="utf-8") as f:
                picks = json.load(f)

            with db.get_connection() as conn:
                cursor = conn.cursor()
                for p in picks:
                    pid = p.get("id")
                    if not pid:
                        continue
                    cursor.execute("SELECT id FROM picks WHERE id = ?", (pid,))
                    if cursor.fetchone() is None:
                        cursor.execute("""
                        INSERT INTO picks (
                            id, game_id, match_name, market, odd, minute, score_at_pick,
                            confidence, ev_pct, fair_odd, stake, reason, pick_type,
                            status, final_score, profit_units, created_at, verified_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """, (
                            pid,
                            str(p.get("game_id", "")),
                            p.get("match", ""),
                            p.get("market", ""),
                            PickRepository._parse_odd(p.get("odd")),
                            str(p.get("minute", "?")),
                            p.get("score_at_pick", "0-0"),
                            float(p.get("confidence", 70.0)),
                            p.get("ev_pct"),
                            p.get("fair_odd"),
                            int(p.get("stake", 2)),
                            p.get("reason", ""),
                            p.get("type", "live"),
                            p.get("status", "PENDIENTE"),
                            p.get("final_score"),
                            float(p.get("profit_units", 0.0)),
                            p.get("timestamp", now_str()),
                            p.get("verified_at")
                        ))
            logger.info(f"Migración de {len(picks)} picks desde JSON a SQLite completada.")
        except Exception as e:
            logger.error(f"Error migrando picks_history.json: {e}")
