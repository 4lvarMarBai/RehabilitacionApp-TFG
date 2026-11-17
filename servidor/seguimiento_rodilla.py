"""Compara medidas registradas y presenta objetivos sin interpretar su relevancia clínica."""

from comun.medidas_rodilla import MEDIDAS, puntuacion_koos_jr


def resumir_medidas_rodilla(rows):
    series = {medida: [] for medida in MEDIDAS}
    objetivo = None
    for fecha, flexion, extension, tug, condiciones, koos, medida, meta in rows:
        if medida is not None and (
            objetivo is None or (medida, meta) != (objetivo["medida"], objetivo["meta"])
        ):
            objetivo = {
                "medida": medida, "meta": meta, "fecha": fecha.isoformat(),
                "medicion": None,
            }

        mediciones = (flexion, extension, tug, puntuacion_koos_jr(koos))
        for nombre, valor in zip(MEDIDAS, mediciones):
            if valor is None:
                continue
            punto = {"fecha": fecha.isoformat(), "valor": valor}
            if nombre == "tug_seconds":
                punto["condiciones"] = condiciones
            series[nombre].append(punto)
            if objetivo is not None and nombre == objetivo["medida"]:
                objetivo["medicion"] = punto

    return {
        "series": series,
        "objetivo": objetivo,
        "objetivo_descripcion": describir_objetivo(objetivo) if objetivo else None,
    }


def comparar_medidas(nombre, puntos):
    if nombre == "tug_seconds" and puntos:
        condiciones_actuales = (puntos[-1]["condiciones"] or "").casefold()
        puntos = [
            punto for punto in puntos
            if (punto["condiciones"] or "").casefold() == condiciones_actuales
        ]
    inicial, actual = puntos[0], puntos[-1]
    cambio = actual["valor"] - inicial["valor"] if len(puntos) > 1 else None
    return inicial, actual, cambio


def describir_objetivo(objetivo):
    nombre, unidad = MEDIDAS[objetivo["medida"]]
    valor_meta = objetivo["meta"]
    minimo = objetivo["medida"] == "knee_flexion_deg"
    comparador = "≥" if minimo else "≤"
    texto = f"{nombre} {comparador} {valor_meta:g} {unidad} (fijado el {objetivo['fecha']})."
    medicion = objetivo["medicion"]
    if medicion is None:
        return f"{texto} Pendiente de medición desde que se fijó la meta."
    valor = medicion["valor"]
    alcanzado = valor >= valor_meta if minimo else valor <= valor_meta
    estado = "Umbral alcanzado" if alcanzado else "Umbral pendiente"
    return f"{texto} {estado}: {valor:g} {unidad} el {medicion['fecha']}."


def formatear_seguimiento_rodilla(seguimiento):
    medidas = seguimiento["series"]
    objetivo = seguimiento["objetivo"]
    if not any(medidas.values()) and objetivo is None:
        return ""

    lineas = ["Medidas registradas de rodilla"]
    for medida, puntos in medidas.items():
        if not puntos:
            continue
        nombre, unidad = MEDIDAS[medida]
        inicial, actual, cambio = comparar_medidas(medida, puntos)
        linea = f"- {nombre}: {actual['valor']:g} {unidad} el {actual['fecha']}"
        if medida == "tug_seconds":
            linea += f" ({actual['condiciones']})"
        if cambio is not None:
            cambio_texto = f"{cambio:+.3f}".rstrip("0").rstrip(".")
            linea += (
                f"; inicial comparable {inicial['valor']:g} {unidad} el {inicial['fecha']}; "
                f"cambio {cambio_texto} {unidad}"
            )
        else:
            linea += "; sin otra medición comparable"
        lineas.append(linea + ".")
    if objetivo is not None:
        lineas.extend(("", "Objetivo individual", seguimiento["objetivo_descripcion"]))
    return "\n".join(lineas)
