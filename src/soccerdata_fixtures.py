from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from functools import lru_cache
from typing import Any, Optional, Tuple
from zoneinfo import ZoneInfo

import pandas as pd
import soccerdata as sd


BOGOTA_TZ = ZoneInfo("America/Bogota")


def _normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    """
    Normaliza nombres de columnas para hacer la lógica más robusta
    ante cambios leves en el datasource.
    """
    df2 = df.copy()
    df2.columns = [
        str(c)
        .strip()
        .lower()
        .replace(" ", "_")
        .replace("/", "_")
        .replace("-", "_")
        for c in df2.columns
    ]
    return df2


def _pick_first_existing_column(df: pd.DataFrame, candidates: list[str]) -> Optional[str]:
    for c in candidates:
        if c in df.columns:
            return c
    return None


def _parse_target_token(token: str, now: datetime) -> Tuple[date, date, str]:
    """
    token:
      - hoy / manana
      - YYYY-MM-DD
      - YYYY-MM
    """
    t = token.strip().lower().replace("mañana", "manana")
    if t in ("hoy", "today"):
        d = now.date()
        return d, d, "hoy"
    if t in ("manana", "tomorrow"):
        d = (now + timedelta(days=1)).date()
        return d, d, "manana"

    if re.match(r"^\d{4}-\d{2}-\d{2}$", t):
        d = datetime.strptime(t, "%Y-%m-%d").date()
        return d, d, t

    if re.match(r"^\d{4}-\d{2}$", t):
        first = datetime.strptime(t, "%Y-%m").date().replace(day=1)
        if first.month == 12:
            next_month_first = date(first.year + 1, 1, 1)
        else:
            next_month_first = date(first.year, first.month + 1, 1)
        last = next_month_first - timedelta(days=1)
        return first, last, t

    raise ValueError("Formato de fecha no reconocido. Usa: hoy, manana, YYYY-MM-DD o YYYY-MM")


def _safe_parse_datetime(series: pd.Series, timezone: ZoneInfo) -> pd.Series:
    """
    Convierte una columna a datetime y ajusta a timezone (Bogotá) si viene tz-aware.
    Si viene naive, se localiza a Bogotá para evitar desfase de día.
    """
    dt = pd.to_datetime(series, errors="coerce")
    if getattr(dt.dt, "tz", None) is not None:
        return dt.dt.tz_convert(timezone)
    # dt es naive -> localizamos
    try:
        return dt.dt.tz_localize(timezone)
    except TypeError:
        return dt


def _default_noon_dt(d: date) -> datetime:
    return datetime(d.year, d.month, d.day, 12, 0, 0, tzinfo=BOGOTA_TZ)


@lru_cache(maxsize=1)
def leagues_world_major_only() -> list[str]:
    """
    Opción 2: países "mayores" (Europa + fuera) con base en prefijos de id.
    """
    MAJOR_COUNTRY_PREFIXES = {
        # Europa
        "ENG",
        "ESP",
        "ITA",
        "GER",
        "FRA",
        "POR",
        "NED",
        "BEL",
        "SCO",
        "TUR",
        "AUT",
        "CHE",
        "SWE",
        "NOR",
        "DEN",
        "FIN",
        "POL",
        "CZE",
        "HUN",
        "ROU",
        "BUL",
        "GRC",
        "UKR",
        "ISR",
        # Fuera de Europa (selección amplia)
        "BRA",
        "ARG",
        "URU",
        "PAR",
        "COL",
        "ECU",
        "PER",
        "CHI",
        "USA",
        "CAN",
        "MEX",
        "JPN",
        "KOR",
        "CHN",
        "AUS",
        "IND",
        "THA",
        "EGY",
        "MAR",
        "ALG",
        "TUN",
        "NGA",
        "ZAF",
    }

    all_ids = sd.FBref.available_leagues()

    def prefix_from_id(lid: str) -> str:
        lid = str(lid).strip()
        if "-" in lid:
            return lid.split("-", 1)[0].upper()
        m = re.match(r"^([A-Z]{3})", lid.upper())
        return m.group(1) if m else lid[:3].upper()

    chosen = {lid for lid in all_ids if prefix_from_id(lid) in MAJOR_COUNTRY_PREFIXES}
    return sorted(chosen)


def fetch_schedule(
    *,
    leagues: Any,
    seasons: Any,
    force_cache: bool = False,
) -> pd.DataFrame:
    fbref = sd.FBref(leagues=leagues, seasons=seasons)
    schedule = fbref.read_schedule(force_cache=force_cache)
    schedule = _normalize_columns(schedule)
    return schedule


def get_matches_for_date_token(
    *,
    date_token: str,
    leagues: Any | None = None,
    seasons: Any = "2526",
    force_cache: bool = False,
    now: datetime | None = None,
) -> pd.DataFrame:
    """
    Devuelve fixtures filtrados por:
      - hoy / manana
      - YYYY-MM-DD
      - YYYY-MM
    """
    if now is None:
        now = datetime.now(BOGOTA_TZ)

    start_d, end_d, _label = _parse_target_token(date_token, now=now)
    if leagues is None:
        leagues = leagues_world_major_only()

    # Reintento si la temporada/lectura falla por ambigüedad.
    try:
        schedule = fetch_schedule(leagues=leagues, seasons=seasons, force_cache=force_cache)
    except Exception:
        schedule = fetch_schedule(leagues=leagues, seasons=None, force_cache=force_cache)

    # Columna fecha: normalmente 'date', pero hacemos fallback.
    date_col = _pick_first_existing_column(schedule, ["date", "match_date", "datetime"])
    if date_col is None:
        date_like = [c for c in schedule.columns if "date" in c]
        if not date_like:
            raise KeyError(f"No encuentro columna de fecha en schedule. Columnas: {list(schedule.columns)[:50]}")
        date_col = date_like[0]

    schedule["date_parsed"] = _safe_parse_datetime(schedule[date_col], BOGOTA_TZ)

    mask = schedule["date_parsed"].dt.date.between(start_d, end_d)
    filtered = schedule.loc[mask].copy()
    filtered.attrs["date_range_label"] = _label
    return filtered


def guess_home_away_cols(df: pd.DataFrame) -> Tuple[str, str]:
    home_col = _pick_first_existing_column(df, ["home_team", "home", "local"])
    away_col = _pick_first_existing_column(df, ["away_team", "away", "visiting"])

    if home_col and away_col:
        return home_col, away_col

    # fallback por substring
    home_col = next((c for c in df.columns if "home" in str(c).lower()), None)
    away_col = next((c for c in df.columns if "away" in str(c).lower()), None)
    if not home_col or not away_col:
        raise KeyError(f"No encuentro columnas home/away. Columnas: {list(df.columns)[:60]}")
    return str(home_col), str(away_col)


def build_kickoff_dt_local(
    *,
    row: pd.Series,
    date_parsed_col: str = "date_parsed",
    time_col: Optional[str] = None,
    fallback_to_noon: bool = True,
) -> Optional[datetime]:
    """
    Construye kickoff datetime en America/Bogota.
    - Si `date_parsed` ya incluye hora -> lo usa
    - Si time_col existe -> intenta ajustar hh:mm
    - Si no hay hora -> usa mediodía (12:00) como fallback neutral
    """
    if date_parsed_col not in row.index:
        return None

    dt = row.get(date_parsed_col)
    if pd.isna(dt):
        if fallback_to_noon:
            # si dt viene vacío no podemos saber el día exacto
            return None
        return None

    dt_local = pd.to_datetime(dt, errors="coerce")
    if pd.isna(dt_local):
        return None

    if getattr(dt_local, "tzinfo", None) is not None:
        dt_local = dt_local.tz_convert(BOGOTA_TZ)
    else:
        try:
            dt_local = dt_local.tz_localize(BOGOTA_TZ)
        except Exception:
            pass

    # Ajuste por columna de hora si existe
    if time_col and time_col in row.index and not pd.isna(row.get(time_col)):
        t = str(row.get(time_col)).strip()
        # Caso: "19:45" (HH:MM)
        if re.match(r"^\d{1,2}:\d{2}$", t):
            hh, mm = t.split(":", 1)
            dt_local = dt_local.replace(hour=int(hh), minute=int(mm), second=0, microsecond=0)
        else:
            # fallback: parseo libre
            parsed_time = pd.to_datetime(t, errors="coerce")
            if not pd.isna(parsed_time):
                dt_local = dt_local.replace(
                    hour=int(parsed_time.hour),
                    minute=int(parsed_time.minute),
                    second=0,
                    microsecond=0,
                )

    # Si dt_local no trae hora "útil" y solo representa día (raro),
    # usamos mediodía como fallback.
    if fallback_to_noon:
        if dt_local.hour == 0 and dt_local.minute == 0 and (time_col is None):
            dt_local = _default_noon_dt(dt_local.date())

    return dt_local.to_pydatetime() if hasattr(dt_local, "to_pydatetime") else dt_local


def format_time_hhmm(dt: Optional[datetime]) -> str:
    if not dt:
        return "TBD"
    return dt.strftime("%H:%M")

