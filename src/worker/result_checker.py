"""
Result Checker — verifica automáticamente si los picks pendientes 
se cumplieron cuando finalizan los partidos.
"""
import logging
from telegram.ext import ContextTypes
from src.scraper.scraper_365 import Scraper365
from src.bot.pick_tracker import (
    get_pending_picks, update_pick_result, verify_pick
)
from src.bot.subscribers import get_active_subscribers

logger = logging.getLogger(__name__)


def _result_emoji(status: str) -> str:
    return {"GANADO": "✅", "PERDIDO": "❌", "NO_VERIFICABLE": "⚪"}.get(status, "❓")


async def result_check_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Corre cada 10 minutos.
    Busca picks PENDIENTES y verifica si su partido ya terminó.
    Si terminó, calcula si la predicción fue correcta y notifica.
    """
    pending = get_pending_picks()
    if not pending:
        logger.info("Result checker: sin picks pendientes.")
        return

    logger.info(f"Result checker: verificando {len(pending)} pick(s) pendiente(s)...")
    scraper = Scraper365()

    try:
        # Obtener todos los partidos del día (incluidos los finalizados)
        all_games = await scraper._fetch_games()
        finished_map = {
            str(g.get("id", "")): g
            for g in all_games
            if g.get("statusGroup") == 4  # 4 = finalizado
        }

        subscribers = get_active_subscribers()

        for pick in pending:
            game_id = pick.get("game_id", "")
            if game_id not in finished_map:
                continue  # El partido aún no ha terminado

            game = finished_map[game_id]
            final_home = int(game.get("homeCompetitor", {}).get("score", 0) or 0)
            final_away = int(game.get("awayCompetitor", {}).get("score", 0) or 0)
            final_score_str = f"{final_home}-{final_away}"

            # Si el mercado requiere estadísticas avanzadas (córners, tarjetas), consultarlas
            market_lower = pick.get("market", "").lower()
            stats = None
            stats_extra_str = ""
            if any(term in market_lower for term in ("córner", "corner", "tarjeta", "card")):
                try:
                    home_id = int(game.get("homeCompetitor", {}).get("id", 0))
                    stats = await scraper.fetch_game_live_stats(int(game_id), home_id)
                    if stats and stats.get("has_stats"):
                        c_tot = stats.get("corners", {}).get("home", 0) + stats.get("corners", {}).get("away", 0)
                        y_tot = stats.get("yellow_cards", {}).get("home", 0) + stats.get("yellow_cards", {}).get("away", 0)
                        r_tot = stats.get("red_cards", {}).get("home", 0) + stats.get("red_cards", {}).get("away", 0)
                        stats_extra_str = f"\n⛳ <b>Córners totales:</b> {c_tot}\n🟨 <b>Tarjetas totales:</b> {y_tot + r_tot}"
                except Exception as e:
                    logger.debug(f"No se pudieron obtener estadísticas avanzadas para verificar partido {game_id}: {e}")

            status = verify_pick(pick, final_home, final_away, stats=stats)
            update_pick_result(pick["id"], status, final_score_str)

            emoji = _result_emoji(status)
            profit_str = ""
            odd_val = float(pick.get("odd") or 1.50) if isinstance(pick.get("odd"), (int, float)) else 1.50
            stake_val = int(pick.get("stake") or 2)
            if status == "GANADO":
                net = round(stake_val * (odd_val - 1.0), 2)
                profit_str = f"\n💰 <b>Beneficio Neto:</b> <code>+{net} U</code> (Stake {stake_val})"
            elif status == "PERDIDO":
                profit_str = f"\n📉 <b>Balance:</b> <code>-{stake_val} U</code> (Stake {stake_val})"

            msg = (
                f"{emoji} <b>RESULTADO DEL PICK</b> {emoji}\n\n"
                f"⚽ <b>{pick['match']}</b>\n"
                f"🎯 Predicción: {pick['market']}\n"
                f"📊 Marcador final: <b>{final_score_str}</b>"
                f"{stats_extra_str}\n"
                f"⏱️ Pick enviado en: {pick['minute']}\n"
                f"📈 Confianza: {pick['confidence']}%"
                f"{profit_str}\n\n"
                f"Resultado: <b>{status}</b> {emoji}"
            )

            logger.info(f"Pick [{pick['id']}] {pick['match']}: {status} ({final_score_str})")

            for chat_id in subscribers:
                try:
                    await context.bot.send_message(
                        chat_id=chat_id,
                        text=msg,
                        parse_mode="HTML"
                    )
                except Exception as e:
                    logger.error(f"Error notificando resultado a {chat_id}: {e}")

    except Exception as e:
        logger.error(f"Error en result_check_job: {e}", exc_info=True)
    finally:
        await scraper.close()


def setup_result_checker(app) -> None:
    """Registra el job de verificación de resultados (cada 10 minutos)."""
    app.job_queue.run_repeating(result_check_job, interval=600, first=60)
    logger.info("⚙️  Result checker registrado: ciclo de 10 min.")
