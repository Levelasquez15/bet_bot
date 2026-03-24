from __future__ import annotations

import os

from dotenv import load_dotenv
import pandas as pd
import streamlit as st

load_dotenv()

from src.backtesting import Backtester
from src.data_sources import ApiFootballDataSource, DataValidationError, normalize_matches
from src.engine import PredictionEngine
from src.recommender import BettingRecommender


st.set_page_config(page_title="Football Predictor", layout="wide")
st.title("Football Predictor: Poisson + Elo")
st.caption("Probabilidades 1X2 y mercado +2.5 goles con backtesting rolling")


@st.cache_data(show_spinner=False)
def load_from_api(api_key: str, league_id: int, season: int) -> pd.DataFrame:
    provider = ApiFootballDataSource(api_key=api_key)
    return provider.get_historical_matches(league_id=league_id, season=season)


@st.cache_data(show_spinner=False)
def test_api_connection(api_key: str) -> pd.DataFrame:
    provider = ApiFootballDataSource(api_key=api_key)
    return provider.get_leagues()


@st.cache_data(show_spinner=False)
def load_upcoming_fixtures(api_key: str, league_id: int, season: int, next_n: int) -> pd.DataFrame:
    provider = ApiFootballDataSource(api_key=api_key)
    return provider.get_upcoming_fixtures(league_id=league_id, season=season, next_n=next_n)


@st.cache_data(show_spinner=False)
def load_fixture_odds(api_key: str, fixture_id: int) -> pd.DataFrame:
    provider = ApiFootballDataSource(api_key=api_key)
    return provider.get_odds_for_fixture(fixture_id=fixture_id)


@st.cache_data(show_spinner=False)
def load_from_csv_file(uploaded_file) -> pd.DataFrame:
    df = pd.read_csv(uploaded_file)
    return normalize_matches(df)


engine = PredictionEngine()
advisor = BettingRecommender()

if "matches_df" not in st.session_state:
    st.session_state["matches_df"] = pd.DataFrame()

with st.sidebar:
    st.header("Fuente de datos")
    source = st.radio("Selecciona origen", ["CSV", "API-Football"])

matches_df = pd.DataFrame()
api_key = ""

if source == "CSV":
    uploaded = st.file_uploader("Sube CSV de partidos", type=["csv"])
    st.markdown("Columnas minimas: `date, home_team, away_team, home_goals, away_goals`")
    if uploaded is not None:
        try:
            st.session_state["matches_df"] = load_from_csv_file(uploaded)
        except DataValidationError as exc:
            st.error(str(exc))
        except Exception as exc:  # noqa: BLE001
            st.error(f"Error leyendo CSV: {exc}")
else:
    with st.sidebar:
        api_key = st.text_input("API key", type="password", value=os.getenv("API_FOOTBALL_KEY", ""))
        league_id = st.number_input("League ID", min_value=1, value=39)
        season = st.number_input("Season", min_value=2000, value=2025)
        test_api_button = st.button("Probar conexion API")
        load_button = st.button("Cargar desde API")

    if test_api_button:
        if not api_key:
            st.error("Debes introducir API key")
        else:
            try:
                leagues_df = test_api_connection(api_key)
                st.success(f"Conexion OK. Ligas detectadas: {len(leagues_df)}")
                if not leagues_df.empty:
                    st.dataframe(leagues_df.head(10), use_container_width=True)
            except Exception as exc:  # noqa: BLE001
                st.error(f"Error de conexion API: {exc}")

    if load_button:
        if not api_key:
            st.error("Debes introducir API key")
        else:
            try:
                with st.spinner("Consultando API-Football..."):
                    st.session_state["matches_df"] = load_from_api(api_key, int(league_id), int(season))
            except Exception as exc:  # noqa: BLE001
                st.error(f"Error consultando API: {exc}")

matches_df = st.session_state["matches_df"]

if matches_df.empty:
    st.info("Carga datos para empezar")
    st.stop()

played_df = matches_df.dropna(subset=["home_goals", "away_goals"]).copy()

col_a, col_b, col_c = st.columns(3)
col_a.metric("Partidos totales", len(matches_df))
col_b.metric("Partidos jugados", len(played_df))
col_c.metric("Equipos", len(set(matches_df["home_team"]).union(set(matches_df["away_team"]))))

st.subheader("Vista de datos")
st.dataframe(matches_df.tail(30), use_container_width=True)

strengths = engine.build_team_strengths(played_df)
elo_model = engine.fit_elo(played_df)

st.subheader("Prediccion puntual")
teams = sorted(set(matches_df["home_team"]).union(set(matches_df["away_team"])))

c1, c2 = st.columns(2)
with c1:
    home_team = st.selectbox("Local", teams, index=0)
with c2:
    away_team = st.selectbox("Visitante", teams, index=1 if len(teams) > 1 else 0)

if home_team == away_team:
    st.warning("Selecciona equipos distintos")
else:
    probs = engine.predict_match(home_team, away_team, strengths, elo_model)
    fair_odds = {
        "1": 1 / max(probs["home_win"], 1e-9),
        "X": 1 / max(probs["draw"], 1e-9),
        "2": 1 / max(probs["away_win"], 1e-9),
        "+2.5": 1 / max(probs["over_2_5"], 1e-9),
    }

    p1, px, p2, pov = st.columns(4)
    p1.metric("P(1)", f"{probs['home_win']:.2%}", f"Cuota justa {fair_odds['1']:.2f}")
    px.metric("P(X)", f"{probs['draw']:.2%}", f"Cuota justa {fair_odds['X']:.2f}")
    p2.metric("P(2)", f"{probs['away_win']:.2%}", f"Cuota justa {fair_odds['2']:.2f}")
    pov.metric("P(+2.5)", f"{probs['over_2_5']:.2%}", f"Cuota justa {fair_odds['+2.5']:.2f}")

    st.write(
        {
            "lambda_home": round(probs["lambda_home"], 3),
            "lambda_away": round(probs["lambda_away"], 3),
            "elo_home": round(elo_model.get_rating(home_team), 1),
            "elo_away": round(elo_model.get_rating(away_team), 1),
        }
    )

if source == "API-Football" and api_key:
    st.subheader("Cuotas actuales por fixture (opcional)")
    fixture_id = st.number_input("Fixture ID", min_value=1, value=1)
    if st.button("Consultar cuotas"):
        try:
            odds_df = ApiFootballDataSource(api_key=api_key).get_odds_for_fixture(int(fixture_id))
            if odds_df.empty:
                st.warning("No se encontraron cuotas para ese fixture")
            else:
                st.dataframe(odds_df, use_container_width=True)
        except Exception as exc:  # noqa: BLE001
            st.error(f"Error obteniendo cuotas: {exc}")

    st.subheader("Bot de picks: comparar lineas y combinadas")
    next_n = st.slider("Proximos partidos a analizar", min_value=2, max_value=20, value=8)
    min_prob = st.slider("Probabilidad minima", min_value=0.40, max_value=0.90, value=0.55, step=0.01)
    min_ev = st.slider("EV minimo", min_value=-0.05, max_value=0.30, value=0.03, step=0.01)
    max_legs = st.slider("Piernas maximas combinada", min_value=2, max_value=6, value=3)

    if st.button("Analizar y generar picks"):
        with st.spinner("Analizando lineas y calculando picks..."):
            fixtures_df = load_upcoming_fixtures(api_key, int(league_id), int(season), int(next_n))

            if fixtures_df.empty:
                st.warning("No hay fixtures proximos para analizar")
            else:
                compared_rows = []
                for _, fixture in fixtures_df.iterrows():
                    fixture_id_i = int(fixture["fixture_id"])
                    home = str(fixture["home_team"])
                    away = str(fixture["away_team"])

                    probs_i = engine.predict_match(home, away, strengths, elo_model)
                    odds_i = load_fixture_odds(api_key, fixture_id_i)
                    compared_i = advisor.compare_lines(
                        fixture_id=fixture_id_i,
                        home_team=home,
                        away_team=away,
                        model_probs=probs_i,
                        odds_df=odds_i,
                    )
                    if not compared_i.empty:
                        compared_rows.append(compared_i)

                if not compared_rows:
                    st.warning("No se pudo comparar lineas en los fixtures consultados")
                else:
                    compared_df = pd.concat(compared_rows, ignore_index=True)
                    picks_df = advisor.best_pick_per_fixture(compared_df, min_probability=min_prob, min_expected_value=min_ev)

                    st.markdown("### Picks ordenados por facilidad + valor")
                    easy_df = compared_df.sort_values(["probability", "expected_value"], ascending=[False, False]).head(25)
                    st.dataframe(easy_df, use_container_width=True)

                    st.markdown("### Mejor pick por partido")
                    if picks_df.empty:
                        st.info("No hay picks que cumplan los filtros actuales")
                    else:
                        st.dataframe(picks_df, use_container_width=True)

                    acc = advisor.build_accumulator(picks_df, max_legs=max_legs)
                    st.markdown("### Propuesta combinada")
                    if acc is None:
                        st.info("No fue posible construir combinada con los filtros actuales")
                    else:
                        c_acc1, c_acc2, c_acc3 = st.columns(3)
                        c_acc1.metric("Prob. combinada", f"{acc['combined_probability']:.2%}")
                        c_acc2.metric("Cuota combinada", f"{acc['combined_odds']:.2f}")
                        c_acc3.metric("EV combinada", f"{acc['combined_expected_value']:.2%}")

st.subheader("Backtesting")
if len(played_df) < 30:
    st.warning("Se recomiendan al menos 30 partidos jugados para validar")
else:
    default_history = min(120, max(20, len(played_df) // 2))
    min_history = st.slider("Ventana minima de historial", min_value=20, max_value=len(played_df) - 1, value=default_history)

    if st.button("Ejecutar backtesting rolling"):
        with st.spinner("Corriendo backtesting..."):
            backtester = Backtester(engine)
            result = backtester.run_rolling(played_df, min_history=min_history)

        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Muestras", int(result.metrics["samples"]))
        m2.metric("Accuracy 1X2", f"{result.metrics['accuracy_1x2']:.2%}")
        m3.metric("LogLoss 1X2", f"{result.metrics['logloss_1x2']:.4f}")
        m4.metric("Brier +2.5", f"{result.metrics['brier_over25']:.4f}")

        st.dataframe(result.predictions.tail(100), use_container_width=True)
