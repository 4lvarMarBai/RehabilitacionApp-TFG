"""Medidas de seguimiento tras una artroplastia de rodilla."""

MEDIDAS = {
    "knee_flexion_deg": ("Flexión", "°"),
    "knee_extension_deficit_deg": ("Déficit de extensión", "°"),
    "tug_seconds": ("Timed Up and Go", "s"),
    "koos_jr_score": ("KOOS, JR", "puntos"),
}
MEDIDAS_OBJETIVO = ("knee_flexion_deg", "knee_extension_deficit_deg")

# Conversión de la suma de los siete ítems según la tabla de Hospital for Special Surgery.
INSTRUCCIONES_KOOS_JR = "https://www.hss.edu/globalassets/files/research/hss-koos-jr-scoring-instructions.pdf"
PUNTUACIONES_KOOS_JR = (
    100.000, 91.975, 84.600, 79.914, 76.332, 73.342, 70.704, 68.284,
    65.994, 63.776, 61.583, 59.381, 57.140, 54.840, 52.465, 50.012,
    47.487, 44.905, 42.281, 39.625, 36.931, 34.174, 31.307, 28.251,
    24.875, 20.941, 15.939, 8.291, 0.000,
)


def puntuacion_koos_jr(suma: int | None) -> float | None:
    return None if suma is None else PUNTUACIONES_KOOS_JR[suma]
