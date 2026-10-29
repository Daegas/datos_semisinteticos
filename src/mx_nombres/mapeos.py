"""
Catálogos y normalización de variables (sexo, entidad federativa).

    from mapeos import normalizar_sexo, normalizar_entidad

    normalizar_sexo(pd.Series(["Hombre", "mujer", 1, "2", 9]))
        -> MASCULINO, FEMENINO, MASCULINO, FEMENINO, None

    normalizar_entidad(pd.Series(["Nuevo León", "CDMX", 19, "7"]))
        -> 19, 9, 19, 7   (Int64)

Todas las comparaciones ignoran mayúsculas, acentos, puntos y espacios extra.
"""

from __future__ import annotations

import unicodedata

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------
def _norm_txt(x) -> str:
    """'  Nuevo  León. ' -> 'NUEVO LEON'"""
    s = unicodedata.normalize("NFKD", str(x))
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.replace(".", " ").replace(",", " ")
    return " ".join(s.upper().split())


def _a_texto(v) -> str | None:
    """Valor escalar -> texto normalizado; None si es nulo. 1.0 -> '1'."""
    if v is None or (not isinstance(v, str) and pd.isna(v)):
        return None
    if isinstance(v, (float, np.floating)) and float(v).is_integer():
        v = int(v)
    return _norm_txt(v)


# ---------------------------------------------------------------------------
# SEXO
# ---------------------------------------------------------------------------
SEXO_ALIAS = {
    # MASCULINO
    "MASCULINO": "MASCULINO", "HOMBRE": "MASCULINO", "HOMBRES": "MASCULINO",
    "H": "MASCULINO", "MALE": "MASCULINO", "1": "MASCULINO",
    # FEMENINO
    "FEMENINO": "FEMENINO", "MUJER": "FEMENINO", "MUJERES": "FEMENINO",
    "F": "FEMENINO", "FEMALE": "FEMENINO", "2": "FEMENINO",
    # 'M' se interpreta como Mujer (convención H/M). Cámbialo si en tus datos es Masculino.
    "M": "FEMENINO",
}

# Valores que se consideran "sin dato" (no truena; el registro queda sin nombre)
SEXO_NO_ESPECIFICADO = {"", "9", "NO ESPECIFICADO", "NE", "NA", "NAN", "NONE", "NULL"}


def normalizar_sexo_escalar(v) -> str | None:
    s = _a_texto(v)
    if s is None or s in SEXO_NO_ESPECIFICADO:
        return None
    if s in SEXO_ALIAS:
        return SEXO_ALIAS[s]
    raise ValueError(f"Sexo no reconocido: {v!r}")


def normalizar_sexo(serie: pd.Series, estricto: bool = True) -> pd.Series:
    """Serie -> object con 'FEMENINO' / 'MASCULINO' / None. Mapea sólo valores únicos."""
    mapa, desconocidos = {}, []
    for v in serie.drop_duplicates():
        try:
            mapa[v] = normalizar_sexo_escalar(v)
        except ValueError:
            mapa[v] = None
            desconocidos.append(v)
    if desconocidos and estricto:
        raise ValueError(
            f"Valores de sexo no reconocidos: {desconocidos[:10]} -> agrégalos a SEXO_ALIAS en mapeos.py"
        )
    out = serie.map(mapa)
    return out.astype(object).where(out.notna(), None)


# ---------------------------------------------------------------------------
# ENTIDAD
# ---------------------------------------------------------------------------
ENTIDADES = {
    1: "Aguascalientes",
    2: "Baja California",
    3: "Baja California Sur",
    4: "Campeche",
    5: "Coahuila de Zaragoza",
    6: "Colima",
    7: "Chiapas",
    8: "Chihuahua",
    9: "Ciudad de México",
    10: "Durango",
    11: "Guanajuato",
    12: "Guerrero",
    13: "Hidalgo",
    14: "Jalisco",
    15: "México",
    16: "Michoacán de Ocampo",
    17: "Morelos",
    18: "Nayarit",
    19: "Nuevo León",
    20: "Oaxaca",
    21: "Puebla",
    22: "Querétaro",
    23: "Quintana Roo",
    24: "San Luis Potosí",
    25: "Sinaloa",
    26: "Sonora",
    27: "Tabasco",
    28: "Tamaulipas",
    29: "Tlaxcala",
    30: "Veracruz de Ignacio de la Llave",
    31: "Yucatán",
    32: "Zacatecas",
    33: "Estados Unidos de Norteamérica",
    88: "Entidad no aplica para A00 - R99 Y V90 - Y89",
    99: "Entidad no especificada",
}

# Sólo estas claves tienen bolsas de nombres; 33, 88 y 99 quedan sin nombre
ENTIDADES_VALIDAS = frozenset(range(1, 33))

# Nombres alternos frecuentes (ya sin acentos ni mayúsculas)
ENTIDAD_ALIAS = {
    "COAHUILA": 5,
    "MICHOACAN": 16,
    "VERACRUZ": 30,
    "CDMX": 9, "DF": 9, "DISTRITO FEDERAL": 9, "CIUDAD DE MEXICO": 9,
    "ESTADO DE MEXICO": 15, "EDO MEX": 15, "EDOMEX": 15, "MEXICO": 15,
    "BCS": 3, "BC": 2, "NL": 19, "SLP": 24, "QRO": 22, "QROO": 23,
    "EUA": 33, "USA": 33, "ESTADOS UNIDOS": 33,
    "NO ESPECIFICADO": 99,
}

_NOMBRE_A_CODIGO = {_norm_txt(n): c for c, n in ENTIDADES.items()}
_NOMBRE_A_CODIGO.update(ENTIDAD_ALIAS)


def normalizar_entidad_escalar(v) -> int | None:
    """Clave (1, '01', 1.0) o nombre ('nuevo leon') -> int. None si es nulo."""
    s = _a_texto(v)
    if s is None or s in ("", "NAN", "NONE", "NULL"):
        return None
    if s.isdigit():
        return int(s)
    if s in _NOMBRE_A_CODIGO:
        return _NOMBRE_A_CODIGO[s]
    raise ValueError(f"Entidad no reconocida: {v!r}")


def normalizar_entidad(serie: pd.Series, estricto: bool = True) -> pd.Series:
    """Serie de claves y/o nombres -> Int64 con la clave de entidad."""
    mapa, desconocidos = {}, []
    for v in serie.drop_duplicates():
        try:
            mapa[v] = normalizar_entidad_escalar(v)
        except ValueError:
            mapa[v] = None
            desconocidos.append(v)
    if desconocidos and estricto:
        raise ValueError(
            f"Entidades no reconocidas: {desconocidos[:10]} -> agrégalas a ENTIDAD_ALIAS en mapeos.py"
        )
    return serie.map(mapa).astype("Int64")