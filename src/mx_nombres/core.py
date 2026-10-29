"""
Selección de nombres y apellidos aleatorios desde `df_nombres.csv`.

Versión optimizada: las "bolsas" se precalculan como diccionarios
(llave -> (valores, probabilidades)) y la generación es vectorizada por
grupos únicos (edad, entidad, sexo), en lugar de filtrar un DataFrame por registro.

Uso individual (compatible con la versión anterior):
    from mx_nombres import seleccionar_nombre
    seleccionar_nombre("De 15 a 19", 1, "FEMENINO")

Uso masivo:
    from mx_nombres import generar_nombres
    df_nombres = generar_nombres(df["edad_agrupada"], df["entidad"], df["sexo"], seed=42)
    # -> DataFrame con: nombre, apellido_paterno, apellido_materno
"""

from __future__ import annotations

from pathlib import Path
from importlib.resources import as_file, files

import numpy as np
import pandas as pd

from .map_regiones import entidad_a_region
from .mapeos import (
    ENTIDADES_VALIDAS,
    normalizar_entidad,
    normalizar_entidad_escalar,
    normalizar_sexo,
    normalizar_sexo_escalar,
)


# ---------------------------------------------------------------------------
# Configuración
# ---------------------------------------------------------------------------
PARQUET_RECURSO = files("mx_nombres").joinpath(
    "data", "df_nombres_zstd.parquet"
)

# Se conservan valores con CONTEO > MIN_CONTEO (igual que antes)
MIN_CONTEO = 2

NIVELES = {"entidad": "CVE_ENTIDAD", "region8": "region8", "region5": "region5"}
COLUMNAS = ("NOMBRE", "PRIMER APELLIDO", "SEGUNDO APELLIDO")

EDADES_AGRUPADAS = [
    "De 15 a 19", "De 20 a 24", "De 25 a 29", "De 30 a 34",
    "De 35 a 39", "De 40 a 44", "De 45 a 49", "De 50 a 54",
    "De 55 a 59", "De 60 a 64", "De 65 a 69", "De 70 a 74",
    "De 75 a 79", "De 80 a 84", "De 85 a 89", "De 90 a 94",
    "De 95 a 99", "De 100 a 104", "De 105 a 109", "De 110 a 114",
    "De 115 a 119", "De 120 y más",
]
_EDAD_A_IDX = {e: i for i, e in enumerate(EDADES_AGRUPADAS)}

EDAD_MIN_DEFAULT = "De 15 a 19"
EDAD_MAX_DEFAULT = "De 80 a 84"

# Cache interno
_BOLSAS: dict[str, dict[str, dict]] | None = None
_CACHE_RESOLVER: dict[tuple, tuple | None] = {}


# ---------------------------------------------------------------------------
# Carga y construcción de bolsas
# ---------------------------------------------------------------------------
def _construir_bolsas(df: pd.DataFrame, columna: str) -> dict[str, dict]:
    """
    Para cada nivel geográfico devuelve:
        {(edad, geo, sexo): (valores: ndarray, probabilidades: ndarray)}
    """
    df = df[df[columna] != ""]
    resultado = {}
    for nivel, col_geo in NIVELES.items():
        g = (
            df.groupby(["EDAD_AGRUPADA", col_geo, "SEXO", columna])
            .size()
            .rename("CONTEO")
            .reset_index()
        )
        g = g[g["CONTEO"] > MIN_CONTEO]

        bolsas = {}
        for llave, sub in g.groupby(["EDAD_AGRUPADA", col_geo, "SEXO"], sort=False):
            pesos = sub["CONTEO"].to_numpy(dtype=float)
            bolsas[llave] = (sub[columna].to_numpy(), pesos / pesos.sum())
        resultado[nivel] = bolsas
    return resultado


def _cargar(
    csv_path: str | Path | None = None,
) -> dict[str, dict[str, dict]]:
    """Carga el CSV y construye las bolsas (una sola vez)."""
    global _BOLSAS

    if _BOLSAS is not None:
        return _BOLSAS

    usecols = [
        "EDAD_AGRUPADA",
        "CVE_ENTIDAD",
        "SEXO",
        "region5",
        "region8",
        *COLUMNAS,
    ]

    if csv_path is None:
        with as_file(PARQUET_RECURSO) as ruta_csv:
            df = pd.read_csv(
                ruta_csv,
                encoding="latin-1",
                low_memory=False,
                usecols=usecols,
            )
    else:
        ruta_csv = Path(csv_path)

        if not ruta_csv.is_file():
            raise FileNotFoundError(
                f"No se encontró el CSV: {ruta_csv}"
            )

        df = pd.read_csv(
            ruta_csv,
            encoding="latin-1",
            low_memory=False,
            usecols=usecols,
        )

    for c in COLUMNAS:
        df[c] = df[c].fillna("").astype(str).str.strip()

    _BOLSAS = {
        c: _construir_bolsas(df, c)
        for c in COLUMNAS
    }

    return _BOLSAS


def recargar(csv_path: str | Path | None = None) -> None:
    """Fuerza la recarga del CSV y reconstruye las bolsas."""
    global _BOLSAS

    _BOLSAS = None
    _CACHE_RESOLVER.clear()

    _cargar(csv_path)


# ---------------------------------------------------------------------------
# Búsqueda en cascada (edad más cercana -> entidad -> region8 -> region5)
# ---------------------------------------------------------------------------
def _edades_candidatas(
    edad_agrupada: str,
    edad_min: str = EDAD_MIN_DEFAULT,
    edad_max: str = EDAD_MAX_DEFAULT,
    max_pasos: int | None = None,
) -> list[str]:
    """Orden: idx, idx-1, idx+1, idx-2, idx+2, ... dentro de [edad_min, edad_max]."""
    if edad_agrupada not in _EDAD_A_IDX:
        return [edad_agrupada]

    idx = _EDAD_A_IDX[edad_agrupada]
    lo = _EDAD_A_IDX.get(edad_min, 0)
    hi = _EDAD_A_IDX.get(edad_max, len(EDADES_AGRUPADAS) - 1)

    inf = list(range(idx - 1, lo - 1, -1))
    sup = list(range(idx + 1, hi + 1))
    if max_pasos is not None:
        inf, sup = inf[:max_pasos], sup[:max_pasos]

    orden: list[int] = []
    for a, b in zip(inf, sup):
        orden += [a, b]
    orden += inf[len(sup):] if len(inf) > len(sup) else sup[len(inf):]

    return [EDADES_AGRUPADAS[idx]] + [EDADES_AGRUPADAS[i] for i in orden]


def _resolver_bolsa(
    columna: str,
    edad: str,
    entidad: int,
    sexo: str,
    solo_misma_edad: bool,
    edad_min: str,
    edad_max: str,
    max_pasos: int | None,
):
    """Devuelve (valores, probs) de la primera bolsa no vacía, o None. Con cache."""
    if entidad not in ENTIDADES_VALIDAS:   # 33, 88, 99 u otras: no hay bolsas
        return None
    llave_cache = (columna, edad, entidad, sexo, solo_misma_edad, edad_min, edad_max, max_pasos)
    if llave_cache in _CACHE_RESOLVER:
        return _CACHE_RESOLVER[llave_cache]

    bolsas = _cargar()[columna]
    edades = [edad] if solo_misma_edad else _edades_candidatas(edad, edad_min, edad_max, max_pasos)
    geos = (
        ("entidad", entidad),
        ("region8", entidad_a_region(entidad, modelo=8)),
        ("region5", entidad_a_region(entidad, modelo=5)),
    )

    encontrada = None
    for e in edades:
        for nivel, geo in geos:
            if geo is None:
                continue
            b = bolsas[nivel].get((e, geo, sexo))
            if b is not None:
                encontrada = b
                break
        if encontrada is not None:
            break

    _CACHE_RESOLVER[llave_cache] = encontrada
    return encontrada


# ---------------------------------------------------------------------------
# Generación masiva (vectorizada por grupos únicos)
# ---------------------------------------------------------------------------
def _generar_columna(
    columna: str,
    edades: pd.Series,
    entidades: pd.Series,
    sexos: pd.Series,
    rng: np.random.Generator,
    ponderar: bool,
    solo_misma_edad: bool,
    edad_min: str,
    edad_max: str,
    max_pasos: int | None,
) -> np.ndarray:
    out = np.full(len(edades), None, dtype=object)

    llaves = pd.DataFrame(
        {
            "e": edades.to_numpy(),
            "ent": pd.to_numeric(entidades, errors="coerce").astype("Int64").to_numpy(),
            "s": sexos.to_numpy(),
        }
    )
    # groupby omite filas con NaN en alguna llave -> quedan en None
    grupos = llaves.groupby(["e", "ent", "s"], sort=True).indices

    for (edad, entidad, sexo), pos in grupos.items():
        bolsa = _resolver_bolsa(
            columna, edad, int(entidad), sexo,
            solo_misma_edad, edad_min, edad_max, max_pasos,
        )
        if bolsa is None:
            continue
        valores, probs = bolsa
        out[pos] = rng.choice(valores, size=len(pos), p=probs if ponderar else None)
    return out


def generar_nombres(
    edad_agrupada: pd.Series,
    entidad: pd.Series,
    sexo: pd.Series,
    seed: int | None = None,
    ponderar: bool = True,
    solo_misma_edad: bool = False,
    edad_min: str = EDAD_MIN_DEFAULT,
    edad_max: str = EDAD_MAX_DEFAULT,
    max_pasos: int | None = None,
) -> pd.DataFrame:
    """
    Genera nombre, apellido_paterno (PRIMER APELLIDO) y apellido_materno
    (SEGUNDO APELLIDO) para cada registro. Devuelve un DataFrame con el mismo índice.

    ponderar=True  -> muestrea proporcional a la frecuencia (nombres comunes salen más).
    ponderar=False -> uniforme sobre valores distintos.
    """
    # sexo y entidad aceptan varias formas (ver mapeos.py); nulos / no especificados -> sin nombre
    sexo = normalizar_sexo(sexo)
    entidad = normalizar_entidad(entidad)
    edad = edad_agrupada
    if pd.api.types.is_numeric_dtype(edad):
        edad = edad_a_grupo(edad)


    _cargar()
    ss = np.random.SeedSequence(seed)
    rngs = [np.random.default_rng(s) for s in ss.spawn(len(COLUMNAS))]

    kw = dict(
        ponderar=ponderar, solo_misma_edad=solo_misma_edad,
        edad_min=edad_min, edad_max=edad_max, max_pasos=max_pasos,
    )
    cols = {
        salida: _generar_columna(col, edad, entidad, sexo, rng, **kw)
        for (col, salida), rng in zip(
            zip(COLUMNAS, ("nombre", "apellido_paterno", "apellido_materno")), rngs
        )
    }
    return pd.DataFrame(cols, index=edad.index)


# ---------------------------------------------------------------------------
# API individual (compatible con la versión anterior)
# ---------------------------------------------------------------------------
def _seleccionar(columna, edad_agrupada, entidad, sexo, seed=None, **kw) -> str | None:
    sexo = normalizar_sexo_escalar(sexo)
    entidad = normalizar_entidad_escalar(entidad)
    if sexo is None or entidad is None:
        return None
    bolsa = _resolver_bolsa(
        columna, edad_agrupada, entidad, sexo,
        kw.get("solo_misma_edad", False),
        kw.get("edad_min", EDAD_MIN_DEFAULT),
        kw.get("edad_max", EDAD_MAX_DEFAULT),
        kw.get("max_pasos"),
    )
    if bolsa is None:
        return None
    rng = np.random.default_rng(seed)
    valores, probs = bolsa
    return rng.choice(valores, p=probs if kw.get("ponderar", True) else None)


def seleccionar_nombre(edad_agrupada, entidad, sexo, seed=None, **kw):
    return _seleccionar("NOMBRE", edad_agrupada, entidad, sexo, seed, **kw)


def seleccionar_primer_apellido(edad_agrupada, entidad, sexo, seed=None, **kw):
    return _seleccionar("PRIMER APELLIDO", edad_agrupada, entidad, sexo, seed, **kw)


def seleccionar_segundo_apellido(edad_agrupada, entidad, sexo, seed=None, **kw):
    return _seleccionar("SEGUNDO APELLIDO", edad_agrupada, entidad, sexo, seed, **kw)


__all__ = [
    "generar_nombres",
    "seleccionar_nombre",
    "seleccionar_primer_apellido",
    "seleccionar_segundo_apellido",
    "recargar",
    "EDADES_AGRUPADAS",
]