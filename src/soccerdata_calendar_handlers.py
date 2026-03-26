from __future__ import annotations

import calendar
import math
import re
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Set, Tuple
from zoneinfo import ZoneInfo

import pandas as pd
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    CallbackQueryHandler,
    CommandHandler,
    ConversationHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from .soccerdata_fixtures import (
    BOGOTA_TZ,
    build_kickoff_dt_local,
    format_time_hhmm,
    get_matches_for_date_token,
    guess_home_away_cols,
    leagues_world_major_only,
)


CAL_PICK_DATE = "CAL_PICK_DATE"
CAL_PICK_MONTH_TEXT = "CAL_PICK_MONTH_TEXT"
CAL_PICK_DAY = "CAL_PICK_DAY"
CAL_MATCH_ACTION = "CAL_MATCH_ACTION"
CAL_PICK_MATCHES = "CAL_PICK_MATCHES"


def _bot_now() -> datetime:
    return datetime.now(BOGOTA_TZ)


def _parse_yyyy_mm(text: str) -> Optional[Tuple[int, int]]:
    m = re.match(r"^(\d{4})-(\d{2})$", text.strip())
    if not m:
        return None
    y = int(m.group(1))
    mo = int(m.group(2))
    if mo < 1 or mo > 12:
        return None
    return y, mo


def _month_add(y: int, m: int, delta_months: int) -> Tuple[int, int]:
    total = (y * 12 + (m - 1)) + delta_months
    new_y = total // 12
    new_m = (total % 12) + 1
    return new_y, new_m


def _build_initial_date_keyboard() -> InlineKeyboardMarkup:
    now = _bot_now()
    hoy = now.date()
    manana = (now + timedelta(days=1)).date()

    this_month = f"{hoy.year:04d}-{hoy.month:02d}"
    y2, m2 = _month_add(hoy.year, hoy.month, 1)
    next_month = f"{y2:04d}-{m2:02d}"

    buttons = [
        [
            InlineKeyboardButton("Hoy", callback_data="cal_date:hoy"),
            InlineKeyboardButton("Mañana", callback_data="cal_date:manana"),
        ],
        [
            InlineKeyboardButton(f"Mes {this_month}", callback_data=f"cal_month:{this_month}"),
            InlineKeyboardButton(f"Mes {next_month}", callback_data=f"cal_month:{next_month}"),
        ],
        [InlineKeyboardButton("Elegir mes (YYYY-MM)", callback_data="cal_month:ask_text")],
    ]
    return InlineKeyboardMarkup(buttons)


def _build_day_keyboard(year: int, month: int) -> InlineKeyboardMarkup:
    days_in_month = calendar.monthrange(year, month)[1]

    rows: List[List[InlineKeyboardButton]] = []
    row: List[InlineKeyboardButton] = []
    for d in range(1, days_in_month + 1):
        iso = f"{year:04d}-{month:02d}-{d:02d}"
        row.append(InlineKeyboardButton(str(d), callback_data=f"cal_day:{iso}"))
        if len(row) == 7:
            rows.append(row)
            row = []
    if row:
        rows.append(row)

    prev_y, prev_m = _month_add(year, month, -1)
    next_y, next_m = _month_add(year, month, 1)
    rows.append(
        [
            InlineKeyboardButton("« Mes anterior", callback_data=f"cal_month:{prev_y:04d}-{prev_m:02d}"),
            InlineKeyboardButton("Mes siguiente »", callback_data=f"cal_month:{next_y:04d}-{next_m:02d}"),
        ]
    )
    rows.append([InlineKeyboardButton("Volver", callback_data="cal_back_home")])
    return InlineKeyboardMarkup(rows)


def _matches_list_text(matches: List[Dict[str, Any]], max_lines: int = 18) -> str:
    if not matches:
        return "No hay partidos en esa fecha para las ligas configuradas."

    lines: List[str] = []
    for m in matches[:max_lines]:
        t = m.get("kickoff_str", "TBD")
        league = m.get("league", "")
        league_s = f" ({league})" if league else ""
        lines.append(f"{t} - {m['home']} vs {m['away']}{league_s}")
    if len(matches) > max_lines:
        lines.append(f"... y {len(matches) - max_lines} más")
    return "\n".join(lines)


def _build_action_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("Analizar TODOS", callback_data="cal_action:auto"),
                InlineKeyboardButton("Elegir MANUAL", callback_data="cal_action:manual"),
            ]
        ]
    )


def _pick_time_col(df: pd.DataFrame) -> Optional[str]:
    for cand in ("time", "kickoff", "kick_off"):
        if cand in df.columns:
            return cand
    return None


def _matches_to_objects(df: pd.DataFrame) -> List[Dict[str, Any]]:
    if df.empty:
        return []

    home_col, away_col = guess_home_away_cols(df)
    time_col = _pick_time_col(df)
    league_col = "league" if "league" in df.columns else None
    match_id_col = None
    for cand in ("match_id", "id", "fixture_id"):
        if cand in df.columns:
            match_id_col = cand
            break

    matches: List[Dict[str, Any]] = []
    df2 = df.reset_index(drop=True)
    for internal_id, row in df2.iterrows():
        kickoff_dt = build_kickoff_dt_local(
            row=row,
            date_parsed_col="date_parsed",
            time_col=time_col,
            fallback_to_noon=True,
        )
        matches.append(
            {
                "internal_id": int(internal_id),
                "home": str(row.get(home_col, "")).strip(),
                "away": str(row.get(away_col, "")).strip(),
                "league": str(row.get(league_col, "")).strip() if league_col else "",
                "match_id": int(row.get(match_id_col)) if match_id_col and pd.notna(row.get(match_id_col)) else None,
                "kickoff_dt_local": kickoff_dt,
                "kickoff_str": format_time_hhmm(kickoff_dt),
            }
        )
    return matches


def _build_manual_selection_kb(
    *,
    matches: List[Dict[str, Any]],
    selected_ids: Set[int],
    page: int,
    page_size: int = 8,
) -> InlineKeyboardMarkup:
    if not matches:
        return InlineKeyboardMarkup([[InlineKeyboardButton("Sin partidos", callback_data="msel:none")]])

    total_pages = max(1, math.ceil(len(matches) / page_size))
    page = max(0, min(page, total_pages - 1))

    start = page * page_size
    end = min(len(matches), start + page_size)
    slice_matches = matches[start:end]

    rows: List[List[InlineKeyboardButton]] = []
    for m in slice_matches:
        mid = int(m["internal_id"])
        checked = "✅" if mid in selected_ids else "⬜"
        label = f"{checked} {m['home']} vs {m['away']}"
        # Callback_data max ~64 bytes: mantenemos solo el id.
        rows.append([InlineKeyboardButton(label[:48], callback_data=f"msel:toggle:{mid}")])

    if total_pages > 1:
        nav: List[InlineKeyboardButton] = []
        if page > 0:
            nav.append(InlineKeyboardButton("« Anterior", callback_data=f"msel:page:{page-1}"))
        nav.append(InlineKeyboardButton(f"Página {page+1}/{total_pages}", callback_data="msel:nop"))
        if page < total_pages - 1:
            nav.append(InlineKeyboardButton("Siguiente »", callback_data=f"msel:page:{page+1}"))
        rows.append(nav)

    rows.append(
        [
            InlineKeyboardButton("Analizar seleccionados", callback_data="msel:analyze"),
            InlineKeyboardButton("Volver", callback_data="msel:back"),
        ]
    )
    return InlineKeyboardMarkup(rows)


async def cmd_calendario(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    /calendario -> selector: Hoy / Mañana primero, y luego meses y días.
    """
    kb = _build_initial_date_keyboard()
    if update.callback_query:
        query = update.callback_query
        await query.answer()
        await query.edit_message_text("Selecciona una fecha:", reply_markup=kb)
    else:
        await update.message.reply_text("Selecciona una fecha:", reply_markup=kb)
    return CAL_PICK_DATE


async def on_cal_pick_month(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    data = query.data or ""

    if data == "cal_month:ask_text":
        await query.edit_message_text(
            "Escribe el mes en formato `YYYY-MM` (ej: `2026-03`).",
            parse_mode="Markdown",
        )
        return CAL_PICK_MONTH_TEXT

    # cal_month:YYYY-MM
    _, ym = data.split(":", 1)
    parsed = _parse_yyyy_mm(ym)
    if not parsed:
        await query.edit_message_text("Mes inválido. Usa `YYYY-MM` (ej: `2026-03`).", parse_mode="Markdown")
        return CAL_PICK_MONTH_TEXT

    y, m = parsed
    kb = _build_day_keyboard(y, m)
    await query.edit_message_text(f"Días del mes {ym}. Selecciona uno:", reply_markup=kb)
    return CAL_PICK_DAY


async def on_cal_pick_day(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    data = query.data or ""

    # Normaliza el token a lo que entiende get_matches_for_date_token
    if data == "cal_date:hoy":
        iso = _bot_now().date().strftime("%Y-%m-%d")
        date_token = iso
    elif data == "cal_date:manana":
        iso = (_bot_now() + timedelta(days=1)).date().strftime("%Y-%m-%d")
        date_token = iso
    elif data.startswith("cal_day:"):
        date_token = data.split(":", 1)[1]  # YYYY-MM-DD
    else:
        await query.edit_message_text("Fecha inválida.")
        return CAL_PICK_DATE

    # Carga fixtures con soccerdata
    await query.edit_message_text("Cargando partidos con soccerdata...")
    try:
        df = get_matches_for_date_token(
            date_token=date_token,
            leagues=leagues_world_major_only(),
            seasons="2526",
            force_cache=False,
            now=_bot_now(),
        )
    except Exception as e:
        await query.edit_message_text(f"No pude cargar fixtures.\nError: `{e}`", parse_mode="Markdown")
        return CAL_PICK_DATE

    matches = _matches_to_objects(df)
    context.user_data["cal_date_token"] = date_token
    context.user_data["current_matches_list"] = matches

    text = _matches_list_text(matches)
    await query.edit_message_text(
        text=f"Partidos para <b>{date_token}</b>:\n\n{text}",
        parse_mode="HTML",
        reply_markup=_build_action_keyboard(),
    )
    return CAL_MATCH_ACTION


async def on_cal_back_home(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("Selecciona una fecha:", reply_markup=_build_initial_date_keyboard())
    return CAL_PICK_DATE


async def on_cal_month_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = (update.message.text or "").strip()
    parsed = _parse_yyyy_mm(text)
    if not parsed:
        await update.message.reply_text("Formato inválido. Usa `YYYY-MM` (ej: `2026-03`).", parse_mode="Markdown")
        return CAL_PICK_MONTH_TEXT

    y, m = parsed
    context.user_data["cal_month_temp"] = (y, m)
    kb = _build_day_keyboard(y, m)
    await update.message.reply_text(f"Días del mes {y:04d}-{m:02d}. Selecciona uno:", reply_markup=kb)
    return CAL_PICK_DAY


async def on_cal_match_action(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    action = (query.data or "").split(":", 1)[1] if ":" in (query.data or "") else ""

    date_token = context.user_data.get("cal_date_token", "fecha")
    matches = context.user_data.get("current_matches_list", [])

    if action == "auto":
        # Stub: en el siguiente paso conectamos con el análisis Poisson/soccerdata
        await query.edit_message_text(
            f"✅ Modo auto seleccionado para <b>{date_token}</b>.\n\n"
            f"Por ahora, esta entrega dejó listo el calendario/fixtures y la selección.\n"
            f"El análisis con Poisson vendrá en la siguiente fase.",
            parse_mode="HTML",
        )
        return ConversationHandler.END

    if action == "manual":
        context.user_data["selected_match_ids"] = set()
        context.user_data["matches_page"] = 0
        kb = _build_manual_selection_kb(
            matches=matches,
            selected_ids=context.user_data["selected_match_ids"],
            page=context.user_data["matches_page"],
        )
        await query.edit_message_text(
            f"Modo manual. Selecciona partidos para analizar.\nFecha: <b>{date_token}</b>",
            parse_mode="HTML",
            reply_markup=kb,
        )
        return CAL_PICK_MATCHES

    await query.edit_message_text("Acción inválida.")
    return CAL_MATCH_ACTION


async def on_msel_toggle(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    data = query.data or ""
    _, _, mid_str = data.split(":", 2)  # msel:toggle:{id}
    mid = int(mid_str)

    selected: Set[int] = context.user_data.setdefault("selected_match_ids", set())
    if mid in selected:
        selected.remove(mid)
    else:
        selected.add(mid)

    matches = context.user_data.get("current_matches_list", [])
    page = int(context.user_data.get("matches_page", 0))
    kb = _build_manual_selection_kb(
        matches=matches,
        selected_ids=selected,
        page=page,
    )
    await query.edit_message_text("Selección actualizada.", reply_markup=kb)
    return CAL_PICK_MATCHES


async def on_msel_page(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    data = query.data or ""
    _, _, page_str = data.split(":", 2)  # msel:page:{n}
    page = int(page_str)
    context.user_data["matches_page"] = page

    matches = context.user_data.get("current_matches_list", [])
    selected: Set[int] = context.user_data.get("selected_match_ids", set())
    kb = _build_manual_selection_kb(matches=matches, selected_ids=selected, page=page)
    await query.edit_message_text("Navegando selección.", reply_markup=kb)
    return CAL_PICK_MATCHES


async def on_msel_back(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    kb = _build_action_keyboard()
    date_token = context.user_data.get("cal_date_token", "fecha")
    await query.edit_message_text(
        f"Volviendo a acciones. Fecha: <b>{date_token}</b>",
        parse_mode="HTML",
        reply_markup=kb,
    )
    return CAL_MATCH_ACTION


async def on_msel_analyze(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    date_token = context.user_data.get("cal_date_token", "fecha")
    matches: List[Dict[str, Any]] = context.user_data.get("current_matches_list", [])
    selected_ids: Set[int] = context.user_data.get("selected_match_ids", set())

    if not selected_ids:
        await query.edit_message_text("No seleccionaste ningún partido. Marca al menos uno con ✅.")
        return CAL_PICK_MATCHES

    selected = [m for m in matches if int(m["internal_id"]) in selected_ids]
    await query.edit_message_text(
        f"✅ Selección lista ({len(selected)} partido(s)) para <b>{date_token}</b>.\n\n"
        f"Por ahora, esta entrega solo dejó el calendario y la selección.\n"
        f"El análisis (Poisson) vendrá en la siguiente fase.",
        parse_mode="HTML",
    )
    return ConversationHandler.END


def build_calendario_conversation(seasons: str = "2526") -> ConversationHandler:
    """
    Crea un ConversationHandler para /calendario.
    """
    return ConversationHandler(
        entry_points=[CommandHandler("calendario", cmd_calendario)],
        states={
            CAL_PICK_DATE: [
                CallbackQueryHandler(on_cal_pick_day, pattern=r"^(cal_date:hoy|cal_date:manana|cal_day:|cal_day:).*"),
                CallbackQueryHandler(on_cal_pick_month, pattern=r"^cal_month:"),
                CallbackQueryHandler(on_cal_back_home, pattern=r"^cal_back_home$"),
            ],
            CAL_PICK_MONTH_TEXT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, on_cal_month_text),
                CallbackQueryHandler(on_cal_back_home, pattern=r"^cal_back_home$"),
            ],
            CAL_PICK_DAY: [
                CallbackQueryHandler(on_cal_pick_day, pattern=r"^cal_day:"),
                CallbackQueryHandler(on_cal_pick_month, pattern=r"^cal_month:"),
                CallbackQueryHandler(on_cal_back_home, pattern=r"^cal_back_home$"),
            ],
            CAL_MATCH_ACTION: [
                CallbackQueryHandler(on_cal_match_action, pattern=r"^cal_action:"),
                CallbackQueryHandler(on_cal_back_home, pattern=r"^cal_back_home$"),
            ],
            CAL_PICK_MATCHES: [
                CallbackQueryHandler(on_msel_toggle, pattern=r"^msel:toggle:\d+$"),
                CallbackQueryHandler(on_msel_page, pattern=r"^msel:page:-?\d+$"),
                CallbackQueryHandler(on_msel_analyze, pattern=r"^msel:analyze$"),
                CallbackQueryHandler(on_msel_back, pattern=r"^msel:back$"),
                CallbackQueryHandler(lambda u, c: u.callback_query.answer(), pattern=r"^msel:nop$"),
            ],
        },
        fallbacks=[CommandHandler("start", cmd_calendario)],
        per_chat=True,
        per_user=True,
    )

