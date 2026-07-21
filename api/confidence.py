from typing import Literal

# Calibración original (2026-07-14, bge-m3 @ 1024): gap 0.03 separaba aciertos de
# fallos y d1 máx de un acierto fue 0.511 -> dist 0.52.
#
# RE-CALIBRACIÓN 2026-07-21 tras migrar embeddings a gemini-embedding-001 @ 1024:
# el corpus se re-embebió con Gemini (los vectores bge-m3 del dump no son
# comparables con consultas Gemini). Medición sobre consultas reales con el nuevo
# espacio: matches in-domain caen en d1 ~0.18–0.39; consultas fuera de alcance
# ("receta de pizza" 0.45, "capital de francia" 0.47) caen ~0.34–0.47. Gemini
# comprime el rango coseno: la separación in/out es más chica que con bge-m3, así
# que el gate por distancia absoluta es más débil (las guardas de alcance del
# prompt de síntesis en api/prompts.py son la segunda línea de defensa). Se sube
# el máximo a 0.55 para NO gatear consultas reales fuzzy; el gap 0.03 se mantiene
# (detecta bien duplicados: dos "Licencia de Funcionamiento" dieron gap 0.0017).
# TODO producción: re-embeber con task_type RETRIEVAL_DOCUMENT/QUERY (mejora la
# separación) y correr tests/calibrar_gate.py completo con los datos ya en Gemini.
UMBRAL_GAP = 0.03
UMBRAL_DISTANCIA_MAX = 0.55


def evaluar_confianza(
    distancias: list[float],
    umbral_gap: float = UMBRAL_GAP,
    umbral_distancia_max: float = UMBRAL_DISTANCIA_MAX,
) -> Literal["claro", "ambiguo", "vacio", "lejano"]:
    """Gate determinista sobre las distancias coseno del retrieval (ascendentes).

    - "lejano": el mejor match está más allá de umbral_distancia_max — el trámite
      probablemente no está en la DB; preguntar no lo va a hacer aparecer.
    - "ambiguo": gap chico entre top-1 y top-2 con d1 razonable — ambigüedad
      genuina entre candidatos, corresponde aclarar.
    """
    if not distancias:
        return "vacio"
    if distancias[0] > umbral_distancia_max:
        return "lejano"
    if len(distancias) == 1:
        return "claro"
    if distancias[1] - distancias[0] >= umbral_gap:
        return "claro"
    return "ambiguo"
