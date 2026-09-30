"""
Clasificador y filtro inteligente de ligas y competiciones.
Evita partidos juveniles, amateurs o sin liquidez en casas de apuestas.
"""

from typing import Tuple

# Patrones para descartar competiciones irrelevantes o sin liquidez
EXCLUDED_PATTERNS = [
    "sub17", "sub-17", "u17", "u-17",
    "sub18", "sub-18", "u18", "u-18",
    "sub19", "sub-19", "u19", "u-19",
    "sub20", "sub-20", "u20", "u-20",
    "sub-21", "sub21", "u21",
    "reserva", "reserve", "amateur",
    "7ª división", "8ª división", "amateur league",
    "amistoso de clubes", "club friendly"
]

# Ligas Tier 1 (Mayor liquidez, datos fiables, modelos de mayor precisión)
TIER_1_KEYWORDS = [
    "champions league", "europa league", "conference league",
    "premier league", "la liga", "laliga", "serie a", "bundesliga", "ligue 1",
    "copa libertadores", "copa sudamericana",
    "liga betplay", "liga profesional", "liga mx", "brasileirão", "brasileirao",
    "mls", "eredivisie", "liga portugal", "pro league"
]

# Ligas Tier 2 (Ligas secundarias de buen nivel profesional)
TIER_2_KEYWORDS = [
    "championship", "segunda división", "hypermotion",
    "serie b", "2. bundesliga", "ligue 2",
    "primera nacional", "copa del rey", "fa cup", "efl cup",
    "copa italia", "dfb pokal", "copa de la liga"
]


def classify_competition(comp_name: str) -> Tuple[int, str]:
    """
    Retorna (tier, razon):
      tier 1: Liga Top (Máxima prioridad)
      tier 2: Liga Profesional Secundaria
      tier 3: Otra liga profesional aceptable
      tier 0: Descartada (Juvenil / Amateur / Sin interés)
    """
    if not comp_name:
        return 0, "Sin nombre de competición"

    name_lower = comp_name.lower()

    # 1. Comprobar si coincide con patrones excluidos
    for pattern in EXCLUDED_PATTERNS:
        if pattern in name_lower:
            return 0, f"Excluida por patrón '{pattern}'"

    # 2. Comprobar Tier 1
    for kw in TIER_1_KEYWORDS:
        if kw in name_lower:
            return 1, "Liga Top (Tier 1)"

    # 3. Comprobar Tier 2
    for kw in TIER_2_KEYWORDS:
        if kw in name_lower:
            return 2, "Liga Secundaria (Tier 2)"

    # 4. Cualquier otra liga profesional reconocida
    return 3, "Liga Profesional (Tier 3)"


def is_valid_match(game: dict, min_tier: int = 3) -> bool:
    """Valida si un partido de 365scores pertenece a una liga permitida."""
    comp_name = game.get("competitionDisplayName") or game.get("competition", {}).get("name", "")
    tier, _ = classify_competition(comp_name)
    return 1 <= tier <= min_tier
