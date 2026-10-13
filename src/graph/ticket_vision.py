"""
Módulo de Visión Artificial, OCR y Auditoría de Tickets de Apuestas (Ticket Vision Parser).
Permite procesar capturas de pantalla o fotos de tickets combinados enviadas por el usuario,
extraer cada selección con Gemini Vision u OCR.space gratuito, verificar qué líneas se
cumplieron y cuáles no consultando estadísticas reales en vivo/terminadas de 365scores,
y generar el informe interactivo para alimentar el Grafo de Conocimiento.
Soporta boletos de Betano, Bet365 (incluyendo mercados Opta y boletos numerados), Rushbet, Wplay, etc.
"""

import base64
import json
import logging
import os
import re
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional, Tuple
import httpx

logger = logging.getLogger(__name__)

GEMINI_VISION_URL_25 = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent"
GEMINI_VISION_URL_15 = "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent"
OCR_SPACE_URL = "https://api.ocr.space/parse/image"

BOGOTA_TZ = timezone(timedelta(hours=-5))

MONTHS_ES = {
    "ene": "01", "feb": "02", "mar": "03", "abr": "04", "may": "05", "jun": "06",
    "jul": "07", "ago": "08", "sep": "09", "sept": "09", "oct": "10", "nov": "11", "dic": "12"
}


def normalize_team_name(s: str) -> str:
    """Normaliza nombres de equipos eliminando sufijos o palabras secundarias."""
    s = s.lower().strip()
    s = s.replace("palses", "paises")
    for drop in ["fc", "cf", "ud", "cd", "calcio", "united", "city", "de", "el", "la", "los", "ac", "sub19", "sub21", "fgtdoi", "fgtbol"]:
        s = re.sub(rf'\b{drop}\b', '', s)
    return re.sub(r'\s+', ' ', s).strip()


def extract_date_from_ticket(text: str) -> str:
    """Extrae fechas en formato español (ej: '24 sept 2026') y retorna 'dd/mm/yyyy'."""
    m = re.search(r'(\d{1,2})\s*(?:de\s*)?(ene|feb|mar|abr|may|jun|jul|ago|sep|sept|oct|nov|dic)[a-z]*[\s,]*(\d{4})?', text, re.IGNORECASE)
    if m:
        day = int(m.group(1))
        mon_raw = m.group(2).lower()
        mon = MONTHS_ES.get(mon_raw[:4], MONTHS_ES.get(mon_raw[:3], "09"))
        yr = m.group(3) or datetime.now(tz=BOGOTA_TZ).strftime("%Y")
        return f"{day:02d}/{mon}/{yr}"
    return ""


def match_teams(h_name: str, a_name: str, t1: str, t2: str) -> bool:
    """Compara si dos equipos coinciden con el partido de 365scores usando palabras clave."""
    h = h_name.lower()
    a = a_name.lower()
    t1_clean = normalize_team_name(t1)
    t2_clean = normalize_team_name(t2)

    tokens_1 = [w for w in t1_clean.split() if len(w) > 3 and w not in ["fútbol", "uefa", "nations", "league", "copa"]]
    tokens_2 = [w for w in t2_clean.split() if len(w) > 3 and w not in ["fútbol", "uefa", "nations", "league", "copa"]]

    if not tokens_1 or not tokens_2:
        return (t1_clean in h or t1_clean in a) and (t2_clean in h or t2_clean in a)

    m1_h = any(tk in h for tk in tokens_1)
    m1_a = any(tk in a for tk in tokens_1)
    m2_h = any(tk in h for tk in tokens_2)
    m2_a = any(tk in a for tk in tokens_2)

    return (m1_h and m2_a) or (m1_a and m2_h)


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
        4. Verifica cada línea contra estadísticas reales de 365scores o conserva el estado resuelto del boleto.
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
                "error": "No se pudieron identificar las líneas del boleto en la imagen. Por favor envía una captura más nítida o escribe el texto del boleto con /ticket."
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
            "2. Extrae la cuota total y fecha del boleto si son visibles.\n"
            "3. Extrae cada una de las selecciones (piernas / legs) de la combinada:\n"
            "   - 'match': Equipos que juegan (ej: 'Países Bajos vs Alemania')\n"
            "   - 'player': Nombre del jugador si es una prop individual (ej: 'Kai Havertz'), o null si es de equipo\n"
            "   - 'team': Nombre del equipo específico de la selección si aplica o null\n"
            "   - 'market': Mercado (ej: 'Disparos Totales', 'Total de Goles', 'Doble Oportunidad', 'Córners')\n"
            "   - 'line': Línea apostada (ej: '+1.5 Disparos Totales', '+1.5 Goles', 'Alemania o Empate')\n"
            "   - 'odd': Cuota decimal si está visible o 0\n"
            "   - 'status': 'GANADA', 'PERDIDA', o 'PENDIENTE'\n"
            "   - 'detail': Breve detalle de lo resuelto si se muestra en el boleto\n\n"
            f"Contexto adicional del usuario: '{caption}'\n\n"
            "Responde EXCLUSIVAMENTE un objeto JSON válido con la siguiente estructura:\n"
            "{\n"
            '  "bookmaker": "Nombre Casa",\n'
            '  "total_odd": 3.70,\n'
            '  "date": "24/09/2026",\n'
            '  "overall_status": "GANADA" | "PERDIDA" | "PENDIENTE",\n'
            '  "legs": [\n'
            '    {\n'
            '      "match": "Equipo A vs Equipo B",\n'
            '      "player": "Nombre Jugador o null",\n'
            '      "team": "Nombre Equipo o null",\n'
            '      "market": "Mercado",\n'
            '      "line": "Línea apostada",\n'
            '      "odd": 1.57,\n'
            '      "status": "GANADA" | "PERDIDA" | "PENDIENTE",\n'
            '      "detail": ""\n'
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
        Analiza el texto plano extraído por OCR y construye la estructura normalizada.
        Soporta:
        1. Boletos numerados (Bet365 / Opta con selecciones 1, 2, 3...).
        2. Boletos agrupados por Bet Builder (Betano).
        3. Boletos individuales y de múltiples casas de apuestas.
        """
        lines = [re.sub(r'^[^\w\+\.\>\<\%\@\:\-\(\)]+', '', l).strip() for l in text.split('\n') if l.strip()]

        # 1. Detectar Casa de Apuestas
        bookmaker = "Casa de Apuestas"
        for b in ["Bet365", "Betano", "Rushbet", "Wplay", "Codere", "Bwin", "1xBet", "Betsson", "Sportium"]:
            if any(b.lower() in l.lower() for l in lines):
                bookmaker = b
                break
        if bookmaker == "Casa de Apuestas" and any("opta" in l.lower() for l in lines):
            bookmaker = "Bet365"

        # 2. Extraer cuota total
        total_odd = 0.0
        for l in lines:
            m = re.search(r'\b([2-9]\d{0,1}\.\d{2}|1\d{1,2}\.\d{2})\b', l)
            if m:
                val = float(m.group(1))
                if val > total_odd:
                    total_odd = val

        ticket_date = extract_date_from_ticket(text)

        # 3. Detectar estructura de bloques (Numerada como Bet365 o Secciones como Betano)
        is_numbered = bool(re.search(r'(?:^|\n)\s*[1-9]\s*\n', text))
        blocks: List[str] = []

        if is_numbered:
            parts = re.split(r'(?:^|\n)\s*([1-9]\d?)\s*(?:\n|$)', text)
            for i in range(1, len(parts), 2):
                blocks.append(parts[i + 1].strip())
        else:
            parts = re.split(r'(?:Bet\s*Builder|Partido|Match|Evento)', text, flags=re.IGNORECASE)
            for p in parts:
                if p.strip() and any(k in p.lower() for k in ['remate', 'esquina', 'tiro', 'falta', 'gol', 'corner', 'disparo']):
                    blocks.append(p.strip())
            if not blocks:
                blocks = [text.strip()]

        legs: List[Dict[str, Any]] = []

        for b in blocks:
            b_lines = [l.strip() for l in b.split('\n') if l.strip()]
            b_lower = b.lower()

            # Encontrar nombre del partido
            match_name = "Partido"
            team1 = ""
            team2 = ""
            for l in b_lines:
                if " - " in l and not any(k in l.lower() for k in ["más de", "menos de", "disparos", "goles", "opta"]):
                    parts = l.split(" - ")
                    team1, team2 = parts[0].strip(), parts[1].strip()
                    match_name = f"{team1} vs {team2}"
                    break
                elif " vs " in l.lower():
                    parts = re.split(r'\s+vs\s+', l, flags=re.IGNORECASE)
                    team1, team2 = parts[0].strip(), parts[1].strip()
                    match_name = f"{team1} vs {team2}"
                    break

            # Si los equipos están en líneas separadas (ej. Betano)
            if match_name == "Partido":
                cand = []
                for sl in b_lines[:6]:
                    sl_clean = re.sub(r'^[^\w]+', '', sl)
                    lower_c = sl_clean.lower()
                    if not any(k in lower_c for k in ['builder', 'hoy', 'ayer', 'doble', 'cuota', 'más de', 'menos de', 'remate', 'esquina', 'tiro', 'falta']):
                        if len(sl_clean.split()) <= 4 and len(sl_clean) > 3:
                            cand.append(sl_clean)
                    elif any(k in lower_c for k in ['calcio', 'fc', 'city', 'united', 'real', 'atlético']):
                        cand.append(sl_clean)
                if len(cand) >= 2:
                    team1, team2 = cand[0], cand[1]
                    match_name = f"{team1} vs {team2}"

            # Detectar estado resuelto del boleto si ya viene cerrado
            block_status = "PENDIENTE"
            if any(w in b_lower for w in ["ganada", "ganadas", "acertada", "won", "verde", "resultado: más de"]):
                block_status = "GANADA"
            if any(w in b_lower for w in ["perdida", "perdido", "fallada", "lost", "roja", "resultado: menos de"]):
                block_status = "PERDIDA"

            # Parsear selecciones dentro de este bloque
            detected_in_block = []
            i = 0
            while i < len(b_lines):
                curr = b_lines[i]
                curr_l = curr.lower()

                # A. Total de Goles
                if "total de goles" in curr_l or ("goles" in curr_l and any(k in curr_l for k in ["más de", "menos de", "+"])):
                    gm = re.search(r'(?:más de|over|\+)\s*(\d+\.?\d*)', curr_l)
                    line_str = f"+{gm.group(1)} Goles" if gm else "+1.5 Goles"
                    detected_in_block.append({
                        "match": match_name,
                        "player": None,
                        "market": "Total de Goles",
                        "line": line_str,
                        "odd": 0.0,
                        "status": block_status,
                        "date": ticket_date,
                        "detail": ""
                    })
                    i += 1
                    continue

                # B. Doble Oportunidad
                if "doble oportunidad" in curr_l:
                    dm = re.search(r'doble oportunidad:\s*([^\n\r]+)', curr, re.IGNORECASE)
                    line_str = dm.group(1).strip() if dm else "Doble Oportunidad"
                    detected_in_block.append({
                        "match": match_name,
                        "player": None,
                        "market": "Doble Oportunidad",
                        "line": line_str,
                        "odd": 0.0,
                        "status": block_status,
                        "date": ticket_date,
                        "detail": ""
                    })
                    i += 1
                    continue

                # C. Resultado Final (1X2)
                if "resultado final" in curr_l:
                    odd_m = re.search(r'@\s*(\d+\.?\d*)', curr)
                    odd_val = float(odd_m.group(1)) if odd_m else 0.0
                    rm = re.search(r'resultado final:\s*([^@\n\r]+)', curr, re.IGNORECASE)
                    line_str = rm.group(1).strip() if rm else "Resultado Final"
                    detected_in_block.append({
                        "match": match_name,
                        "player": None,
                        "market": "Resultado Final",
                        "line": line_str,
                        "odd": odd_val,
                        "status": block_status,
                        "date": ticket_date,
                        "detail": ""
                    })
                    i += 1
                    continue

                # D. Córners
                if any(k in curr_l for k in ['esquina', 'corner']):
                    cm = re.search(r'(?:más de|over|\+)\s*(\d+\.?\d*)', curr_l)
                    if not cm and i > 0:
                        cm = re.search(r'(?:más de|over|\+)\s*(\d+\.?\d*)', b_lines[i - 1].lower())
                    line_val = f"+{cm.group(1)}" if cm else "+3.5"

                    target_team = None
                    if team1 and team1.lower() in curr_l:
                        target_team = team1
                    elif team2 and team2.lower() in curr_l:
                        target_team = team2

                    lbl = f"{target_team} Tiros de esquina" if target_team else "Tiros de esquina Totales"
                    detected_in_block.append({
                        "match": match_name,
                        "player": None,
                        "team": target_team,
                        "market": "Córners",
                        "line": f"{line_val} {lbl}",
                        "odd": 0.0,
                        "status": block_status,
                        "date": ticket_date,
                        "detail": ""
                    })
                    i += 1
                    continue

                # E. Props de Jugador (Disparos, Remates, Tiros, Faltas)
                if any(k in curr_l for k in ['disparo', 'remate', 'tiro', 'falta']):
                    market = "Disparos Totales" if "disparo" in curr_l else "Remates Totales"
                    if "arco" in curr_l or "puerta" in curr_l:
                        market = "Remates al Arco"
                    elif "falta" in curr_l:
                        market = "Faltas Cometidas"

                    # Formato Bet365 / Opta: "Kai Havertz - Más de 1.5" o "Karim Adeyemi-Mis de 1.5"
                    pm = re.search(r'(?:opta\)\s*[\:\)]*\s*)?([A-ZÁÉÍÓÚ][a-záéíóú]+(?:\s+[A-ZÁÉÍÓÚ][a-záéíóú]+)+)\s*[\-\–]\s*(?:m[aá]s\s*de|mis\s*de|over|\+)?\s*(\d+\.?\d*)', curr, re.IGNORECASE)
                    if pm:
                        pname = pm.group(1).strip()
                        th = pm.group(2)
                        line_str = f"+{th} {market}"
                        detected_in_block.append({
                            "match": match_name,
                            "player": pname,
                            "team": None,
                            "market": market,
                            "line": line_str,
                            "odd": 0.0,
                            "status": block_status,
                            "date": ticket_date,
                            "detail": ""
                        })
                        i += 1
                        continue

                    # Formato Betano: "2+ Mandragora Remates totales"
                    qty = "1+"
                    qty_m = re.search(r'(\d+)\s*\+', curr)
                    if not qty_m and i > 0:
                        qty_m = re.search(r'(\d+)\s*\+', b_lines[i - 1])
                    if qty_m:
                        qty = f"{qty_m.group(1)}+"

                    clean_player = re.sub(r'^(?:\d+\+?|[Oo*&]+)\s*', '', curr)
                    clean_player = re.sub(r'(?:remates totales|remates al arco|tiros al arco|faltas cometidas|disparos|tiros).*$', '', clean_player, flags=re.IGNORECASE).strip()
                    if not clean_player and i > 0:
                        prev = re.sub(r'^(?:\d+\+?|[Oo*&]+)\s*', '', b_lines[i - 1])
                        if not any(k in prev.lower() for k in ['builder', 'hoy', 'doble', 'cuota']):
                            clean_player = prev.strip()

                    if clean_player:
                        detected_in_block.append({
                            "match": match_name,
                            "player": clean_player,
                            "team": None,
                            "market": market,
                            "line": f"{qty} {market}",
                            "odd": 0.0,
                            "status": block_status,
                            "date": ticket_date,
                            "detail": ""
                        })

                i += 1

            legs.extend(detected_in_block)

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
            "date": ticket_date,
            "summary": f"Ticket {bookmaker} con {len(legs)} selecciones extraídas."
        }

    async def _find_game_365(
        self,
        client: httpx.AsyncClient,
        team1: str,
        team2: str,
        match_date: str = ""
    ) -> Optional[Dict[str, Any]]:
        """Busca un partido en 365scores consultando la fecha del ticket, hoy, ayer y mañana."""
        now = datetime.now(tz=BOGOTA_TZ)
        dates: List[str] = []
        if match_date:
            dates.append(match_date)
        dates.extend([
            now.strftime("%d/%m/%Y"),
            (now - timedelta(days=1)).strftime("%d/%m/%Y"),
            (now + timedelta(days=1)).strftime("%d/%m/%Y"),
        ])

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
                    h_name = g.get("homeCompetitor", {}).get("name", "")
                    a_name = g.get("awayCompetitor", {}).get("name", "")
                    if match_teams(h_name, a_name, team1, team2):
                        return g
            except Exception as e:
                logger.debug(f"Error consultando fecha {d} en 365scores: {e}")
        return None

    async def verify_ticket_with_365scores(self, ticket_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Verifica cada selección consultando la telemetría oficial de 365scores:
        - Si el partido se encuentra en 365scores: extrae goles, córners, remates y alineaciones (titular / suplente).
        - Si el partido es histórico y no está en la API, preserva los estados cerrados del boleto (GANADA/PERDIDA).
        """
        legs = ticket_data.get("legs", [])
        if not legs:
            return ticket_data

        ticket_date = ticket_data.get("date", "")

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
                    raw_game = await self._find_game_365(client, t1, t2, ticket_date)
                    if raw_game:
                        gid = raw_game.get("id")
                        try:
                            r_full = await client.get(f"https://webws.365scores.com/web/game/?gameId={gid}&langId=29&appTypeId=5")
                            full_game = r_full.json().get("game", {}) if r_full.status_code == 200 else raw_game
                            games_cache[cache_key] = full_game
                        except Exception:
                            games_cache[cache_key] = raw_game

                        try:
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

                # 1. Total de Goles
                if leg.get("market") == "Total de Goles":
                    h_score = float(home_comp.get("score", 0) or 0)
                    a_score = float(away_comp.get("score", 0) or 0)
                    tot_goals = int(h_score + a_score)
                    leg["actual_value"] = tot_goals
                    th_m = re.search(r'(\d+\.?\d*)', leg.get("line", ""))
                    th = float(th_m.group(1)) if th_m else 1.5

                    if tot_goals > th:
                        leg["status"] = "GANADA"
                        leg["detail"] = f"Marcador: {int(h_score)}-{int(a_score)} ({tot_goals} goles totales, superó +{th})."
                    else:
                        if is_finished:
                            leg["status"] = "PERDIDA"
                            leg["detail"] = f"Marcador: {int(h_score)}-{int(a_score)} ({tot_goals} goles totales)."

                # 2. Doble Oportunidad
                elif leg.get("market") == "Doble Oportunidad":
                    h_score = int(float(home_comp.get("score", 0) or 0))
                    a_score = int(float(away_comp.get("score", 0) or 0))
                    leg["detail"] = f"Marcador final: {h_score}-{a_score}."

                # 3. Resultado Final
                elif leg.get("market") == "Resultado Final":
                    h_score = int(float(home_comp.get("score", 0) or 0))
                    a_score = int(float(away_comp.get("score", 0) or 0))
                    h_name = home_comp.get("name", "")
                    a_name = away_comp.get("name", "")
                    leg["detail"] = f"Resultado final: {h_name} {h_score} - {a_score} {a_name}."

                # 4. Córners
                elif leg.get("market") == "Córners" or "esquina" in leg.get("line", "").lower():
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

                # 5. Props de Jugador (Disparos, Tiros al arco, Faltas)
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
                        tot_shots = int(float(found_player_stats.get("Total Remates", 0) or 0))
                        sot = int(float(found_player_stats.get("Remates al arco", 0) or 0))
                        fouls = int(float(found_player_stats.get("Faltas cometidas", 0) or 0))
                        st_text = str(found_player_stats.get("statusText", "")).lower()
                        is_sub = "substitut" in st_text or (mins.isdigit() and int(mins) < 45)

                        market = leg.get("market") or ""
                        th_m = re.search(r'(\d+\.?\d*)', leg.get("line", ""))
                        threshold = float(th_m.group(1)) if th_m else 1.5

                        if "arco" in market.lower() or "puerta" in market.lower():
                            actual = sot
                            leg["actual_value"] = actual
                            if actual >= threshold:
                                leg["status"] = "GANADA"
                                leg["detail"] = f"{found_name} registró {actual} tiros al arco en {mins}' cumpliendo la línea."
                            else:
                                if is_finished:
                                    leg["status"] = "PERDIDA"
                                    if tot_shots > 0:
                                        leg["detail"] = f"{found_name} registró 0 tiros al arco en {mins}' (intentó {tot_shots} tiros fuera o bloqueados)."
                                        leg["suggested_better_line"] = f"+{tot_shots - 0.5} Remates Totales"
                                    else:
                                        leg["detail"] = f"{found_name} jugó {mins}' y registró 0 tiros al arco."
                        elif "falta" in market.lower():
                            actual = fouls
                            leg["actual_value"] = actual
                            if actual >= threshold:
                                leg["status"] = "GANADA"
                                leg["detail"] = f"{found_name} cometió {actual} faltas en {mins}' cumpliendo la línea."
                            else:
                                if is_finished:
                                    leg["status"] = "PERDIDA"
                                    leg["detail"] = f"{found_name} jugó {mins}' y cometió {actual} faltas."
                        else:  # Disparos / Remates Totales
                            actual = tot_shots
                            leg["actual_value"] = actual
                            if actual >= threshold:
                                leg["status"] = "GANADA"
                                leg["detail"] = f"{found_name} jugó {mins}' y registró {actual} disparos totales, superando la línea de {threshold}."
                            else:
                                if is_finished:
                                    leg["status"] = "PERDIDA"
                                    if is_sub:
                                        leg["detail"] = f"{found_name} fue suplente (jugó sólo {mins}') y registró {actual} disparos totales."
                                        leg["suggested_better_line"] = "Verificar alineaciones titulares antes de entrar a líneas de remate"
                                    else:
                                        leg["detail"] = f"{found_name} jugó {mins}' y registró {actual} disparos totales (faltó {int(threshold - actual + 0.99)})."
                                        if actual >= 1:
                                            leg["suggested_better_line"] = f"+{actual - 0.5} Disparos Totales"

            # Determinar balance general
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
    ticket_date = ticket_data.get("date")
    overall_status = str(ticket_data.get("overall_status", "PENDIENTE")).upper()
    legs = ticket_data.get("legs", [])

    status_badge = (
        "✅ <b>GANADA (COBRADA)</b>"
        if overall_status == "GANADA"
        else ("❌ <b>PERDIDA (NO PREMIADA)</b>" if overall_status == "PERDIDA" else "⏳ <b>EN CURSO / PENDIENTE</b>")
    )

    odd_str = f"<code>{total_odd:.2f}</code>" if total_odd > 0 else "N/D"
    date_header = f" | 📅 <i>{ticket_date}</i>" if ticket_date else ""

    lines = [
        "🎟️ <b>AUDITORÍA DE TICKET DE APUESTAS</b> 🎟️",
        f"🏦 Casa: <b>{bookmaker}</b> | 💵 Cuota: {odd_str}{date_header}",
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
            lines.append(f"     • 💡 <i>Línea más rentable: <b>{better_line}</b></i>")
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
