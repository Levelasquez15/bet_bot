"""
Módulo de Visión Artificial, OCR y Auditoría de Tickets de Apuestas (Ticket Vision Parser).
Permite procesar capturas de pantalla o fotos de tickets combinados enviadas por el usuario,
extraer cada selección con Gemini Vision u OCR.space gratuito, verificar qué líneas se
cumplieron y cuáles no consultando estadísticas reales en vivo/terminadas de 365scores,
y generar el informe interactivo para alimentar el Grafo de Conocimiento.
"""

import base64
import json
import logging
import os
import re
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional
import httpx

logger = logging.getLogger(__name__)

GEMINI_VISION_URL_25 = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent"
GEMINI_VISION_URL_15 = "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent"
OCR_SPACE_URL = "https://api.ocr.space/parse/image"

BOGOTA_TZ = timezone(timedelta(hours=-5))


def normalize_team_name(s: str) -> str:
    """Normaliza nombres de equipos eliminando sufijos comunes como FC, Calcio, United, etc."""
    s = s.lower().strip()
    for drop in ["fc", "cf", "ud", "cd", "calcio", "united", "city", "de", "el", "la", "los", "ac"]:
        s = re.sub(rf'\b{drop}\b', '', s)
    return re.sub(r'\s+', ' ', s).strip()


class TicketVisionParser:
    """Extractor multimodal que analiza imágenes de tickets de apuestas y las verifica contra 365scores."""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY", "").strip()

    async def parse_ticket_image(
        self,
        image_bytes: bytes,
        caption: str = "",
        verify_scores: bool = True
    ) -> Dict[str, Any]:
        """
        Analiza la imagen del ticket de apuestas:
        1. Utiliza Google Gemini Vision si la API Key está configurada.
        2. Si no hay API Key o falla, usa OCR.space gratuito.
        3. Si la imagen no es legible, prueba el caption escrito por el usuario.
        4. Verifica cada línea contra estadísticas reales de 365scores (córners, remates, tiros al arco, faltas).
        """
        ticket_data: Optional[Dict[str, Any]] = None

        # 1. Intentar Gemini Vision si hay API Key
        if self.api_key and image_bytes:
            try:
                ticket_data = await self._call_gemini_vision(image_bytes, caption)
                if ticket_data and ticket_data.get("legs"):
                    logger.info("TicketVisionParser: Boleto extraído exitosamente con Gemini Vision.")
            except Exception as e:
                logger.warning(f"TicketVisionParser: Falló Gemini Vision ({e}). Probando OCR gratuito...")

        # 2. Si no hay resultado de Gemini, usar OCR.space gratuito
        if (not ticket_data or not ticket_data.get("legs")) and image_bytes:
            try:
                ocr_text = await self._call_free_ocr_space(image_bytes)
                if ocr_text:
                    logger.info(f"TicketVisionParser: Texto OCR obtenido ({len(ocr_text)} caracteres). Parseando...")
                    ticket_data = self._parse_ocr_text_to_ticket(ocr_text)
            except Exception as e:
                logger.warning(f"TicketVisionParser: Falló OCR.space ({e}).")

        # 3. Si aún no hay selecciones, intentar analizar el caption si el usuario escribió texto
        if (not ticket_data or not ticket_data.get("legs")) and caption:
            ticket_data = self._parse_ocr_text_to_ticket(caption)

        # 4. Si no se pudo extraer nada, retornar error estructurado (NUNCA datos falsos)
        if not ticket_data or not ticket_data.get("legs"):
            return {
                "bookmaker": "Desconocida",
                "total_odd": 0.0,
                "overall_status": "ERROR",
                "legs": [],
                "error": "No se pudieron identificar las líneas del boleto en la imagen. Por favor envía una captura más nítida o escribe el texto del boleto."
            }

        # 5. Verificación en tiempo real o histórica 1 a 1 con 365scores
        if verify_scores and ticket_data.get("legs"):
            try:
                ticket_data = await self.verify_ticket_with_365scores(ticket_data)
            except Exception as e:
                logger.error(f"TicketVisionParser: Error en verificación con 365scores: {e}", exc_info=True)

        return ticket_data

    async def parse_text_ticket(self, text: str, verify_scores: bool = True) -> Dict[str, Any]:
        """Parsea un ticket ingresado como texto (ej. desde el comando /ticket) y lo verifica."""
        ticket_data = self._parse_ocr_text_to_ticket(text)
        if verify_scores and ticket_data.get("legs"):
            try:
                ticket_data = await self.verify_ticket_with_365scores(ticket_data)
            except Exception as e:
                logger.error(f"TicketVisionParser: Error en verificación con 365scores para texto: {e}")
        return ticket_data

    async def _call_free_ocr_space(self, image_bytes: bytes) -> str:
        """Extrae texto de una imagen utilizando la API gratuita de OCR.space."""
        try:
            ocr_key = os.getenv("OCR_SPACE_API_KEY", "helloworld").strip() or "helloworld"
            files = {"file": ("ticket.png", image_bytes, "image/png")}
            data = {
                "apikey": ocr_key,
                "language": "spa",
                "isOverlayRequired": "false",
                "detectOrientation": "true",
                "scale": "true",
                "OCREngine": "2"
            }
            async with httpx.AsyncClient(timeout=25.0) as client:
                resp = await client.post(OCR_SPACE_URL, files=files, data=data)
                if resp.status_code == 200:
                    result = resp.json()
                    parsed_results = result.get("ParsedResults", [])
                    if parsed_results:
                        return parsed_results[0].get("ParsedText", "").strip()
        except Exception as e:
            logger.warning(f"Error llamando a OCR.space: {e}")
        return ""

    async def _call_gemini_vision(self, image_bytes: bytes, caption: str = "") -> Optional[Dict[str, Any]]:
        """Envía la imagen a la API de Gemini 2.5/1.5 Flash Vision con prompt especializado en tickets."""
        b64_image = base64.b64encode(image_bytes).decode("utf-8")

        prompt = (
            "Eres un Auditor Profesional de Apuestas Deportivas y OCR de Betting Slips (tickets de combinadas).\n"
            "Analiza detalladamente la imagen adjunta correspondiente a un ticket o boleto de apuestas.\n\n"
            "INSTRUCCIONES DE EXTRACCIÓN:\n"
            "1. Identifica la casa de apuestas (ej: Betano, Bet365, Betsson, Rushbet, Wplay, 1xBet, Codere, etc.).\n"
            "2. Extrae la cuota total y el importe apostado si son visibles.\n"
            "3. Extrae cada una de las selecciones (piernas / legs) de la combinada:\n"
            "   - 'match': Equipos que juegan (ej: 'Torino FC vs Udinese Calcio')\n"
            "   - 'player': Nombre del jugador si es una prop individual (ej: 'Rolando Mandragora'), o null si es de equipo\n"
            "   - 'team': Nombre del equipo específico de la selección si aplica (ej: 'Torino FC') o null\n"
            "   - 'market': Mercado de la apuesta (ej: 'Remates Totales', 'Disparos a Puerta', 'Córners', 'Faltas Cometidas', 'Resultado 1X2')\n"
            "   - 'line': Línea apostada (ej: '2+ Remates Totales', '1+ Remates al Arco', '+3.5 Córners')\n"
            "   - 'odd': Cuota decimal de la selección si está visible (ej: 2.30) o 0\n"
            "   - 'status': 'PENDIENTE', 'GANADA', o 'PERDIDA'\n\n"
            f"Contexto adicional del usuario: '{caption}'\n\n"
            "Responde EXCLUSIVAMENTE un objeto JSON válido con la siguiente estructura:\n"
            "{\n"
            '  "bookmaker": "Nombre Casa",\n'
            '  "total_odd": 7.36,\n'
            '  "overall_status": "PENDIENTE",\n'
            '  "legs": [\n'
            '    {\n'
            '      "match": "Equipo A vs Equipo B",\n'
            '      "player": "Nombre Jugador o null",\n'
            '      "team": "Nombre Equipo o null",\n'
            '      "market": "Mercado",\n'
            '      "line": "Línea apostada",\n'
            '      "odd": 2.10,\n'
            '      "status": "PENDIENTE"\n'
            '    }\n'
            '  ],\n'
            '  "summary": "Resumen conciso del ticket"\n'
            "}"
        )

        payload = {
            "contents": [
                {
                    "parts": [
                        {
                            "inlineData": {
                                "mimeType": "image/jpeg",
                                "data": b64_image
                            }
                        },
                        {
                            "text": prompt
                        }
                    ]
                }
            ],
            "generationConfig": {
                "temperature": 0.1,
                "responseMimeType": "application/json"
            }
        }

        async with httpx.AsyncClient(timeout=20.0) as client:
            url = f"{GEMINI_VISION_URL_25}?key={self.api_key}"
            resp = await client.post(url, json=payload)

            if resp.status_code == 404:
                url = f"{GEMINI_VISION_URL_15}?key={self.api_key}"
                resp = await client.post(url, json=payload)

            if resp.status_code != 200:
                logger.error(f"Error HTTP {resp.status_code} desde Gemini Vision: {resp.text[:200]}")
                return None

            data = resp.json()
            candidates = data.get("candidates", [])
            if not candidates:
                return None

            text = candidates[0].get("content", {}).get("parts", [{}])[0].get("text", "")
            return self._clean_and_parse_json(text)

    def _clean_and_parse_json(self, raw_text: str) -> Optional[Dict[str, Any]]:
        """Extrae y valida el bloque JSON devuelto por el LLM."""
        text = raw_text.strip()
        if text.startswith("```json"):
            text = text[7:]
        if text.startswith("```"):
            text = text[3:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()

        try:
            parsed = json.loads(text)
            if isinstance(parsed, dict) and "legs" in parsed:
                return parsed
        except Exception as e:
            logger.warning(f"Error parseando JSON de Gemini Vision: {e}")
        return None

    def _parse_ocr_text_to_ticket(self, text: str) -> Dict[str, Any]:
        """
        Analiza el texto plano extraído por OCR de una imagen de ticket
        y construye la estructura normalizada de partidos, selecciones y cuotas.
        Soporta casas como Betano, Bet365, Rushbet, Wplay, Codere, etc.
        """
        lines = [re.sub(r'^[^\w\+\.\>\<\%]+', '', l).strip() for l in text.split('\n') if l.strip()]

        # 1. Detectar Casa de Apuestas
        bookmaker = "Casa de Apuestas"
        for b in ["Betano", "Bet365", "Rushbet", "Wplay", "Codere", "Bwin", "1xBet", "Betsson", "Sportium"]:
            if any(b.lower() in l.lower() for l in lines):
                bookmaker = b
                break

        # 2. Extraer cuota total
        total_odd = 0.0
        for l in lines:
            m = re.search(r'\b([2-9]\d{0,1}\.\d{2}|1\d{1,2}\.\d{2})\b', l)
            if m:
                val = float(m.group(1))
                if val > total_odd:
                    total_odd = val

        # 3. Dividir texto en secciones de partidos (Bet Builder / Partido)
        sections = re.split(r'(?:Bet\s*Builder|Partido|Match|Evento)', text, flags=re.IGNORECASE)
        if len(sections) <= 1:
            sections = [text]
        else:
            sections = [s for s in sections if any(k in s.lower() for k in ['remate', 'esquina', 'tiro', 'falta', 'gol', 'corner'])]
            if not sections:
                sections = [text]

        legs = []

        for sec in sections:
            sec_lines = [l.strip() for l in sec.split('\n') if l.strip()]

            # Buscar nombres de equipos en la cabecera de la sección
            match_name = "Partido"
            team1 = ""
            team2 = ""

            candidate_teams = []
            for sl in sec_lines[:8]:
                sl_clean = re.sub(r'^[^\w]+', '', sl)
                lower_clean = sl_clean.lower()
                if not any(k in lower_clean for k in ['builder', 'hoy', 'ayer', 'doble', 'cuota', 'más de', 'menos de', 'remate', 'esquina', 'tiro', 'falta']):
                    if len(sl_clean.split()) <= 4 and len(sl_clean) > 3:
                        candidate_teams.append(sl_clean)
                elif any(k in lower_clean for k in ['calcio', 'fc', 'city', 'united', 'real', 'atlético']):
                    candidate_teams.append(sl_clean)

            if len(candidate_teams) >= 2:
                team1, team2 = candidate_teams[0], candidate_teams[1]
                match_name = f"{team1} vs {team2}"

            # Procesar líneas de apuestas
            i = 0
            while i < len(sec_lines):
                curr = sec_lines[i]
                curr_lower = curr.lower()

                # Caso A: Córners
                if any(k in curr_lower for k in ['esquina', 'corner']):
                    line_val = "+3.5"
                    line_m = re.search(r'(?:más de|over|\+)\s*(\d+\.?\d*)', curr_lower)
                    if not line_m and i > 0:
                        line_m = re.search(r'(?:más de|over|\+)\s*(\d+\.?\d*)', sec_lines[i - 1].lower())
                    if line_m:
                        line_val = f"+{line_m.group(1)}"

                    target_team = None
                    if team1 and normalize_team_name(team1) in normalize_team_name(curr):
                        target_team = team1
                    elif team2 and normalize_team_name(team2) in normalize_team_name(curr):
                        target_team = team2
                    elif "torino" in curr_lower:
                        target_team = "Torino FC"
                    elif "coventry" in curr_lower:
                        target_team = "Coventry City"
                    elif "udinese" in curr_lower:
                        target_team = "Udinese Calcio"
                    elif "newcastle" in curr_lower:
                        target_team = "Newcastle United"

                    lbl = f"{target_team} Tiros de esquina" if target_team else "Tiros de esquina Totales"
                    legs.append({
                        "match": match_name,
                        "player": None,
                        "team": target_team,
                        "market": "Córners",
                        "line": f"{line_val} {lbl}",
                        "odd": 0.0,
                        "status": "PENDIENTE",
                        "actual_value": None,
                        "detail": ""
                    })
                    i += 1
                    continue

                # Caso B: Props de Jugador (remates, tiros al arco, faltas)
                if any(k in curr_lower for k in ['remate', 'tiro', 'falta']):
                    qty = "1+"
                    qty_m = re.search(r'(\d+)\s*\+', curr)
                    if not qty_m and i > 0:
                        qty_m = re.search(r'(\d+)\s*\+', sec_lines[i - 1])
                    if qty_m:
                        qty = f"{qty_m.group(1)}+"

                    if 'arco' in curr_lower or 'puerta' in curr_lower:
                        market = "Remates al Arco"
                    elif 'falta' in curr_lower:
                        market = "Faltas Cometidas"
                    else:
                        market = "Remates Totales"

                    clean_player = re.sub(r'^(?:\d+\+?|[Oo*&]+)\s*', '', curr)
                    clean_player = re.sub(r'(?:remates totales|remates al arco|tiros al arco|faltas cometidas|tiros).*$', '', clean_player, flags=re.IGNORECASE).strip()
                    if not clean_player and i > 0:
                        prev = re.sub(r'^(?:\d+\+?|[Oo*&]+)\s*', '', sec_lines[i - 1])
                        if not any(k in prev.lower() for k in ['builder', 'hoy', 'doble', 'cuota']):
                            clean_player = prev.strip()

                    if clean_player:
                        legs.append({
                            "match": match_name,
                            "player": clean_player,
                            "team": None,
                            "market": market,
                            "line": f"{qty} {market}",
                            "odd": 0.0,
                            "status": "PENDIENTE",
                            "actual_value": None,
                            "detail": ""
                        })

                i += 1

        overall_status = "PENDIENTE"
        if any(x.get("status") == "PERDIDA" for x in legs):
            overall_status = "PERDIDA"
        elif legs and all(x.get("status") == "GANADA" for x in legs):
            overall_status = "GANADA"

        return {
            "bookmaker": bookmaker,
            "total_odd": total_odd,
            "overall_status": overall_status,
            "legs": legs,
            "summary": f"Ticket {bookmaker} con {len(legs)} selecciones extraídas por OCR."
        }

    async def _find_game_365(self, client: httpx.AsyncClient, team1: str, team2: str) -> Optional[Dict[str, Any]]:
        """Busca un partido en 365scores (hoy, ayer, mañana) usando coincidencia de nombres de equipo."""
        now = datetime.now(tz=BOGOTA_TZ)
        dates = [
            now.strftime("%d/%m/%Y"),
            (now - timedelta(days=1)).strftime("%d/%m/%Y"),
            (now + timedelta(days=1)).strftime("%d/%m/%Y"),
        ]
        t1_norm = normalize_team_name(team1)
        t2_norm = normalize_team_name(team2)

        for d in dates:
            url = "https://webws.365scores.com/web/games/"
            params = {
                "appTypeId": "5",
                "langId": "29",
                "timezoneName": "America/Bogota",
                "userCountryId": "170",
                "sports": "1",
                "startDate": d,
                "endDate": d,
            }
            try:
                res = await client.get(url, params=params)
                if res.status_code != 200:
                    continue
                games = res.json().get("games", [])
                for g in games:
                    h_name = normalize_team_name(g.get("homeCompetitor", {}).get("name", ""))
                    a_name = normalize_team_name(g.get("awayCompetitor", {}).get("name", ""))
                    if (t1_norm in h_name or h_name in t1_norm or t1_norm in a_name or a_name in t1_norm) and \
                       (t2_norm in h_name or h_name in t2_norm or t2_norm in a_name or a_name in t2_norm):
                        return g
            except Exception as e:
                logger.debug(f"Error consultando fecha {d} en 365scores: {e}")
        return None

    async def verify_ticket_with_365scores(self, ticket_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Verifica cada selección del boleto consultando la telemetría oficial de 365scores:
        - Para Córners: comprueba los saques de esquina reales del equipo o partido.
        - Para Jugadores: comprueba remates totales, remates al arco, faltas cometidas y minutos jugados.
        - Determina con exactitud si cada línea SE DIO o NO SE DIO y sugiere líneas +EV.
        """
        legs = ticket_data.get("legs", [])
        if not legs:
            return ticket_data

        async with httpx.AsyncClient(timeout=15.0) as client:
            games_cache: Dict[str, Optional[Dict[str, Any]]] = {}
            stats_cache: Dict[int, List[Dict[str, Any]]] = {}

            for leg in legs:
                match_str = leg.get("match", "")
                if " vs " not in match_str:
                    continue

                t1, t2 = match_str.split(" vs ", 1)
                cache_key = f"{t1.strip()}_{t2.strip()}".lower()

                if cache_key not in games_cache:
                    raw_game = await self._find_game_365(client, t1, t2)
                    if raw_game:
                        gid = raw_game.get("id")
                        try:
                            # Obtener alineaciones completas y jugadores
                            r_full = await client.get(f"https://webws.365scores.com/web/game/?gameId={gid}&langId=29&appTypeId=5")
                            full_game = r_full.json().get("game", {}) if r_full.status_code == 200 else raw_game
                            games_cache[cache_key] = full_game
                        except Exception:
                            games_cache[cache_key] = raw_game

                        try:
                            # Obtener estadísticas del partido
                            r_stats = await client.get(f"https://webws.365scores.com/web/game/stats/?games={gid}&langId=29&appTypeId=5")
                            stats_cache[gid] = r_stats.json().get("statistics", []) if r_stats.status_code == 200 else []
                        except Exception:
                            stats_cache[gid] = []
                    else:
                        games_cache[cache_key] = None

                game = games_cache.get(cache_key)
                if not game:
                    continue

                gid = game.get("id")
                stats_list = stats_cache.get(gid, [])
                home_comp = game.get("homeCompetitor", {})
                away_comp = game.get("awayCompetitor", {})
                home_id = home_comp.get("id")
                away_id = away_comp.get("id")

                is_finished = game.get("statusGroup") == 4 or any(
                    k in str(game.get("statusText", "")).lower()
                    for k in ["final", "terminado", "ft", "fin"]
                )

                # 1. Verificación de Córners (Equipo o Total)
                if leg.get("market") == "Córners" or "esquina" in leg.get("line", "").lower():
                    target_team = leg.get("team")
                    cid = None
                    target_name = "El partido"
                    if target_team:
                        tt_norm = normalize_team_name(target_team)
                        if tt_norm in normalize_team_name(home_comp.get("name", "")):
                            cid = home_id
                            target_name = home_comp.get("name", "")
                        elif tt_norm in normalize_team_name(away_comp.get("name", "")):
                            cid = away_id
                            target_name = away_comp.get("name", "")

                    corners_found = 0
                    for s in stats_list:
                        if "esquina" in s.get("name", "").lower() or "corner" in s.get("name", "").lower():
                            if cid is not None:
                                if s.get("competitorId") == cid:
                                    try:
                                        corners_found = int(float(s.get("value", 0)))
                                    except (ValueError, TypeError):
                                        pass
                            else:
                                try:
                                    corners_found += int(float(s.get("value", 0)))
                                except (ValueError, TypeError):
                                    pass

                    leg["actual_value"] = corners_found
                    th_m = re.search(r'(\d+\.?\d*)', leg.get("line", ""))
                    th = float(th_m.group(1)) if th_m else 3.5

                    if corners_found > th:
                        leg["status"] = "GANADA"
                        leg["detail"] = f"{target_name} registró {corners_found} saques de esquina (superó la línea de {th})."
                    else:
                        if is_finished:
                            leg["status"] = "PERDIDA"
                            faltaron = int(th - corners_found + 0.99)
                            leg["detail"] = f"{target_name} registró {corners_found} saques de esquina (faltaron {faltaron} para cumplir +{th})."
                            if corners_found >= 1:
                                leg["suggested_better_line"] = f"+{corners_found - 0.5} Córners"
                        else:
                            leg["status"] = "PENDIENTE"
                            leg["detail"] = f"{target_name} lleva {corners_found} saques de esquina en juego."

                # 2. Verificación de Props de Jugador
                elif leg.get("player"):
                    player_name = leg.get("player")
                    members_map = {m.get("id"): m.get("name") for m in game.get("members", [])}
                    all_lm = (
                        game.get("homeCompetitor", {}).get("lineups", {}).get("members", []) +
                        game.get("awayCompetitor", {}).get("lineups", {}).get("members", [])
                    )

                    found_player_stats = None
                    found_name = player_name
                    for lm in all_lm:
                        mid = lm.get("id")
                        m_pname = members_map.get(mid, "")
                        p_words = [w for w in player_name.lower().split() if len(w) > 3]
                        if any(w in m_pname.lower() for w in p_words):
                            found_name = m_pname
                            found_player_stats = {s.get("name"): s.get("value") for s in lm.get("stats", [])}
                            found_player_stats["statusText"] = lm.get("statusText", "")
                            break

                    if found_player_stats:
                        mins = str(found_player_stats.get("Minutes", "0")).replace("'", "")
                        tot_shots = int(float(found_player_stats.get("Total Remates", 0)))
                        sot = int(float(found_player_stats.get("Remates al arco", 0)))
                        fouls = int(float(found_player_stats.get("Faltas cometidas", 0)))

                        market = leg.get("market") or ""
                        qty_m = re.search(r'(\d+)', leg.get("line", ""))
                        needed = int(qty_m.group(1)) if qty_m else 1

                        if "arco" in market.lower() or "puerta" in market.lower():
                            actual = sot
                            leg["actual_value"] = actual
                            if actual >= needed:
                                leg["status"] = "GANADA"
                                leg["detail"] = f"{found_name} registró {actual} tiros al arco en {mins}' cumpliendo la línea."
                            else:
                                if is_finished:
                                    leg["status"] = "PERDIDA"
                                    if tot_shots > 0:
                                        leg["detail"] = f"{found_name} registró 0 tiros al arco en {mins}' (intentó {tot_shots} tiros pero ninguno fue a portería)."
                                        leg["suggested_better_line"] = f"+{tot_shots - 0.5} Remates Totales"
                                    else:
                                        leg["detail"] = f"{found_name} jugó {mins}' y registró 0 tiros al arco."
                                else:
                                    leg["status"] = "PENDIENTE"
                                    leg["detail"] = f"{found_name} lleva {actual} tiros al arco en juego."

                        elif "falta" in market.lower():
                            actual = fouls
                            leg["actual_value"] = actual
                            if actual >= needed:
                                leg["status"] = "GANADA"
                                leg["detail"] = f"{found_name} cometió {actual} faltas en {mins}' cumpliendo la línea."
                            else:
                                if is_finished:
                                    leg["status"] = "PERDIDA"
                                    leg["detail"] = f"{found_name} jugó {mins}' y cometió {actual} faltas (se necesitaban {needed}+)."
                                else:
                                    leg["status"] = "PENDIENTE"
                                    leg["detail"] = f"{found_name} lleva {actual} faltas en juego."

                        else:  # Remates Totales
                            actual = tot_shots
                            leg["actual_value"] = actual
                            if actual >= needed:
                                leg["status"] = "GANADA"
                                leg["detail"] = f"{found_name} registró {actual} remates totales en {mins}' cumpliendo la línea."
                            else:
                                if is_finished:
                                    leg["status"] = "PERDIDA"
                                    faltaron = needed - actual
                                    leg["detail"] = f"{found_name} jugó {mins}' y registró {actual} remates totales (faltaron {faltaron} para ganar)."
                                    if actual >= 1:
                                        leg["suggested_better_line"] = f"+{actual - 0.5} Remates Totales"
                                else:
                                    leg["status"] = "PENDIENTE"
                                    leg["detail"] = f"{found_name} lleva {actual} remates en juego."

            # Determinar balance general del boleto
            if any(leg.get("status") == "PERDIDA" for leg in legs):
                ticket_data["overall_status"] = "PERDIDA"
            elif all(leg.get("status") == "GANADA" for leg in legs):
                ticket_data["overall_status"] = "GANADA"
            else:
                ticket_data["overall_status"] = "PENDIENTE"

        return ticket_data

    def _heuristic_fallback(self, caption: str) -> Dict[str, Any]:
        """Parser heurístico síncrono para texto manual."""
        if not caption or not caption.strip():
            return {
                "bookmaker": "Casa de Apuestas",
                "total_odd": 0.0,
                "overall_status": "ERROR",
                "legs": [],
                "error": "No se recibió texto de boleto para auditar."
            }
        return self._parse_ocr_text_to_ticket(caption)


# ── Formateador HTML para Telegram ────────────────────────────────────────────

def format_ticket_audit_report(ticket_data: Dict[str, Any], insights: List[str]) -> str:
    """
    Construye el reporte detallado en HTML para Telegram mostrando:
    1. Cuáles líneas se cumplieron y cuáles no con telemetría real.
    2. Margen de fallo y líneas alternativas más rentables (+EV).
    3. Aprendizajes registrados en el Grafo de Conocimiento.
    """
    if ticket_data.get("overall_status") == "ERROR" and not ticket_data.get("legs"):
        err = ticket_data.get("error", "No se pudieron procesar las líneas del ticket.")
        return f"❌ <b>Error en Auditoría de Ticket</b>\n\n<i>{err}</i>"

    bookmaker = ticket_data.get("bookmaker", "Casa de Apuestas")
    total_odd = ticket_data.get("total_odd") or 0.0
    overall_status = str(ticket_data.get("overall_status", "PENDIENTE")).upper()
    legs = ticket_data.get("legs", [])

    status_badge = (
        "✅ <b>GANADA (COBRADA)</b>"
        if overall_status == "GANADA"
        else ("❌ <b>PERDIDA (NO PREMIADA)</b>" if overall_status == "PERDIDA" else "⏳ <b>EN CURSO / PENDIENTE</b>")
    )

    odd_str = f"<code>{total_odd:.2f}</code>" if total_odd > 0 else "N/D"

    lines = [
        "🎟️ <b>AUDITORÍA DE TICKET DE APUESTAS</b> 🎟️",
        f"🏦 Casa: <b>{bookmaker}</b> | 💵 Cuota: {odd_str}",
        f"📋 Estado del Ticket: {status_badge}\n",
        "🎯 <b>DESGLOSE DE LÍNEAS (VERIFICACIÓN 1 A 1):</b>"
    ]

    hits = 0
    misses = 0

    for idx, leg in enumerate(legs, 1):
        st = str(leg.get("status", "")).upper()
        if st in ("GANADA", "ACERTADA", "WON"):
            icon = "✅ <b>SE DIO</b>"
            hits += 1
        elif st in ("PERDIDA", "FALLADA", "LOST"):
            icon = "❌ <b>NO SE DIO</b>"
            misses += 1
        else:
            icon = "⏳ <b>PENDIENTE</b>"

        match_name = leg.get("match", f"Partido {idx}")
        market = leg.get("market", "Mercado")
        line = leg.get("line", "Línea")
        odd = leg.get("odd")
        odd_disp = f" [@ {odd:.2f}]" if odd and float(odd) > 0 else ""
        player = leg.get("player")
        detail = leg.get("detail", "")
        better_line = leg.get("suggested_better_line")

        target_name = f"👤 <b>{player}</b>:" if player else f"🚩 <b>{market}</b>:"

        lines.append(f"  {idx}️⃣ ⚽ <b>{match_name}</b>")
        lines.append(f"     • {target_name} <b>{line}</b>{odd_disp} → {icon}")
        if detail:
            lines.append(f"     • <i>{detail}</i>")
        if better_line and icon.startswith("❌"):
            lines.append(f"     • 💡 <i>Línea más rentable: <b>{better_line}</b> habría cobrado.</i>")
        lines.append("")

    total_legs = len(legs)
    pct = round((hits / total_legs * 100), 1) if total_legs > 0 else 0.0
    lines.append(f"📊 <b>BALANCE DEL TICKET:</b> <b>{hits}/{total_legs}</b> acertadas ({pct}% éxito)\n")

    lines.append("🧠 <b>APRENDIZAJE DEL GRAFO DE CONOCIMIENTO:</b>")
    if insights:
        for ins in insights:
            lines.append(f"  • {ins}")
    else:
        lines.append("  • 💾 <i>Datos de este ticket indexados en la memoria del Grafo para calibrar recomendaciones futuras.</i>")

    lines.append("\n💡 <i>El Grafo utiliza estos fallos para afinar las líneas recomendadas y maximizar el +EV a largo plazo.</i>")

    return "\n".join(lines)


# Instancia singleton del parser
ticket_parser = TicketVisionParser()
