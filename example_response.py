#!/usr/bin/env python3
"""
Example of how the bot response would look for match analysis
"""

def format_match_analysis_example():
    """Example of formatted match analysis response"""

    example_response = """
🎯 <b>Análisis automático para 2026-03-26</b>

🏟️ <b>Real Madrid vs Barcelona</b>
✅ Recomendación: Over 2.5 (Más de 2.5 goles - 67.3% de probabilidad)
📊 Probabilidades: 1: 45.2% | X: 24.1% | 2: 30.7%
💡 Razonamiento: Modelo Poisson basado en forma reciente y estadísticas históricas

🏟️ <b>Manchester City vs Liverpool</b>
✅ Recomendación: Local gana (1 - 58.9% de probabilidad)
📊 Probabilidades: 1: 58.9% | X: 22.3% | 2: 18.8%
💡 Razonamiento: City en buena forma reciente (4 victorias en últimos 5)

🏟️ <b>Juventus vs Inter Milan</b>
✅ Recomendación: Ambos marcan (BTTS - 62.1% de probabilidad)
📊 Probabilidades: 1: 38.4% | X: 26.7% | 2: 34.9%
💡 Razonamiento: Ambos equipos tienen alta capacidad goleadora

🎰 <b>Combinada automática (3 legs):</b>
- Real Madrid vs Barcelona: Over 2.5
- Manchester City vs Liverpool: 1
- Juventus vs Inter Milan: BTTS
Probabilidad combinada: 23.8% | Cuota estimada: 4.20
"""

    print("Ejemplo de respuesta del bot:")
    print("=" * 50)
    print(example_response)

def format_single_match_example():
    """Example of single match analysis"""

    single_response = """
🏟️ <b>Real Madrid vs Barcelona</b>

📊 <b>Probabilidades calculadas:</b>
• Victoria Local: 45.2%
• Empate: 24.1%
• Victoria Visitante: 30.7%

🎯 <b>Recomendaciones de apuesta:</b>
1. <b>Over 2.5 goles</b> (67.3% prob) - Muy alta confianza
   💡 Ambos equipos tienen promedio alto de goles

2. <b>1X (Doble oportunidad)</b> (69.3% prob) - Alta confianza
   💡 Evita sorpresas, cubre empate

3. <b>Ambos marcan</b> (62.1% prob) - Alta confianza
   💡 Históricamente marcan en el 78% de sus partidos

📈 <b>Estadísticas utilizadas:</b>
• Goles esperados: Real Madrid 1.8 | Barcelona 1.5
• Forma reciente: Real Madrid 4/5 victorias | Barcelona 3/5 victorias
• xG reciente: Real Madrid +2.1 | Barcelona +1.8
• Elo ratings: Real Madrid 1850 | Barcelona 1820

⚠️ <b>Nota:</b> Estas son estimaciones basadas en modelos matemáticos.
El fútbol tiene incertidumbre. Apuesta responsablemente.
"""

    print("\nEjemplo de análisis detallado de un partido:")
    print("=" * 50)
    print(single_response)

if __name__ == "__main__":
    format_match_analysis_example()
    format_single_match_example()