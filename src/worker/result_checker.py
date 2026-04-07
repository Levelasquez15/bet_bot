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

            status = verify_pick(pick, final_home, final_away)
            update_pick_result(pick["id"], status, final_score_str)

            emoji = _result_emoji(status)
            msg = (
                f"{emoji} <b>RESULTADO DEL PICK</b> {emoji}\n\n"
                f"⚽ <b>{pick['match']}</b>\n"
                f"🎯 Predicción: {pick['market']}\n"
                f"📊 Marcador final: <b>{final_score_str}</b>\n"
                f"⏱️ Pick enviado en min: {pick['minute']}\n"
                f"📈 Confianza: {pick['confidence']}%\n\n"
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
