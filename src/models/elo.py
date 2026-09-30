"""
Sistema de Rating Elo de Equipos de Fútbol con ventaja de localía.
Conecta la fuerza relativa de los equipos con las tasas esperadas de gol (Poisson Lambdas).
"""

from __future__ import annotations
import json
import os
import logging
from dataclasses import dataclass, field
from typing import Dict, Tuple

logger = logging.getLogger(__name__)

# Base de datos inicial de ratings Elo de referencia para clubes destacados
INITIAL_CLUB_ELO = {
    # Inglaterra
    "manchester city": 2040, "liverpool": 1990, "arsenal": 1960, "aston villa": 1780,
    "tottenham": 1790, "chelsea": 1810, "newcastle": 1780, "manchester united": 1750,
    "brighton": 1740, "west ham": 1710, "everton": 1660, "wolverhampton": 1650,
    # España
    "real madrid": 2030, "barcelona": 1950, "atlético de madrid": 1870, "atletico madrid": 1870,
    "athletic club": 1820, "real sociedad": 1800, "girona": 1790, "villarreal": 1770,
    "real betis": 1760, "sevilla": 1730, "valencia": 1700,
    # Alemania
    "bayern munich": 1980, "bayer leverkusen": 1950, "borussia dortmund": 1860,
    "rb leipzig": 1840, "stuttgart": 1800, "eintracht frankfurt": 1760,
    # Italia
    "inter": 1940, "atalanta": 1850, "milan": 1840, "juventus": 1840,
    "roma": 1790, "napoli": 1830, "lazio": 1780, "fiorentina": 1750,
    # Francia
    "paris saint-germain": 1910, "psg": 1910, "monaco": 1810, "lille": 1790,
    "marseille": 1780, "lyon": 1750,
    # Sudamérica
    "palmeiras": 1790, "flamengo": 1780, "river plate": 1750, "boca juniors": 1710,
    "atlético mineiro": 1720, "são paulo": 1710, "racing club": 1690,
    "millonarios": 1540, "junior": 1520, "santa fe": 1530, "atlético nacional": 1540,
    "américa de cali": 1520, "deportes tolima": 1520, "independiente medellín": 1530
}


@dataclass
class EloModel:
    """Modelo Elo con persistencia local y mapeo a tasas Poisson."""

    k_factor: float = 20.0
    base_rating: float = 1500.0
    home_advantage: float = 65.0
    ratings: Dict[str, float] = field(default_factory=lambda: dict(INITIAL_CLUB_ELO))
    storage_file: str = "elo_ratings.json"

    def __post_init__(self):
        self.load_ratings()

    def _normalize_name(self, team: str) -> str:
        return team.lower().strip()

    def get_rating(self, team: str) -> float:
        norm = self._normalize_name(team)
        if norm in self.ratings:
            return self.ratings[norm]
        # Búsqueda parcial si no coincide exacto
        for k, v in self.ratings.items():
            if k in norm or norm in k:
                return v
        return self.base_rating

    def expected_home_score(self, home_team: str, away_team: str) -> float:
        """Retorna probabilidad de victoria del local ajustada por ventaja de campo."""
        home_rating = self.get_rating(home_team) + self.home_advantage
        away_rating = self.get_rating(away_team)
        return 1.0 / (1.0 + 10.0 ** ((away_rating - home_rating) / 400.0))

    def estimate_lambdas(
        self,
        home_team: str,
        away_team: str,
        base_league_goals: float = 2.6
    ) -> Tuple[float, float]:
        """
        Transforma la diferencia de ratings Elo en goles esperados (lambda)
        para el modelo de Poisson de cada equipo.
        """
        exp_home = self.expected_home_score(home_team, away_team)
        # exp_home suele oscilar entre 0.25 (muy inferior) y 0.85 (muy superior)

        # Repartición de goles esperados según probabilidad de triunfo
        share_home = 0.25 + (exp_home * 0.70)  # ej: si exp_home=0.5 -> share=0.60 local
        share_away = 1.0 - (share_home * 0.75)  # away share balanceado

        lambda_home = round(base_league_goals * share_home * 0.58, 2)
        lambda_away = round(base_league_goals * (1.0 - share_home * 0.58), 2)

        # Garantizar mínimos lógicos en fútbol profesional
        lambda_home = max(0.40, min(lambda_home, 3.80))
        lambda_away = max(0.30, min(lambda_away, 3.20))

        return lambda_home, lambda_away

    def update(self, home_team: str, away_team: str, home_goals: int, away_goals: int) -> None:
        """Actualiza el rating Elo tras finalizar un partido."""
        norm_h = self._normalize_name(home_team)
        norm_a = self._normalize_name(away_team)

        exp_home = self.expected_home_score(home_team, away_team)
        exp_away = 1.0 - exp_home

        if home_goals > away_goals:
            act_h, act_a = 1.0, 0.0
        elif home_goals < away_goals:
            act_h, act_a = 0.0, 1.0
        else:
            act_h, act_a = 0.5, 0.5

        r_h = self.get_rating(home_team)
        r_a = self.get_rating(away_team)

        self.ratings[norm_h] = round(r_h + self.k_factor * (act_h - exp_home), 1)
        self.ratings[norm_a] = round(r_a + self.k_factor * (act_a - exp_away), 1)
        self.save_ratings()

    def load_ratings(self) -> None:
        if os.path.exists(self.storage_file):
            try:
                with open(self.storage_file, "r", encoding="utf-8") as f:
                    saved = json.load(f)
                    self.ratings.update(saved)
            except Exception as e:
                logger.error(f"Error cargando elo_ratings.json: {e}")

    def save_ratings(self) -> None:
        try:
            with open(self.storage_file, "w", encoding="utf-8") as f:
                json.dump(self.ratings, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Error guardando elo_ratings.json: {e}")
