"""
Agrega las columnas nombre, apellido_paterno y apellido_materno al parquet limpio.

    edr_{year}_limpio.parquet  ->  edr_{year}_limpio_con_nombres.parquet
"""

import time

import numpy as np
import pandas as pd

from mx_nombres import EDADES_AGRUPADAS, OUTPUTPATH, generar_nombres

year = 2024
SEED = 42

# --- COLUMNAS del parquet  ---------------------------------------------------
COL_EDAD = "edad_agru"   # texto "De 15 a 19", o bien edad numérica en años
COL_ENTIDAD = "ent_nac_nom"      # clave 1..32
COL_SEXO = "sexo"            # Hombre/Mujer, 1/2, H/M... (ver mapeos.py)
# -----------------------------------------------------------------------------


def edad_a_grupo(edad: pd.Series) -> pd.Series:
    """Edad numérica -> etiqueta 'De 15 a 19', ... (menores de 15 caen en el primer grupo)."""
    idx = ((pd.to_numeric(edad, errors="coerce") - 15) // 5).clip(lower=0, upper=len(EDADES_AGRUPADAS) - 1)
    return idx.map(lambda i: EDADES_AGRUPADAS[int(i)] if pd.notna(i) else None)


t0 = time.time()
entrada = OUTPUTPATH / f"edr_{year}_limpio.parquet"
salida = OUTPUTPATH / f"edr_{year}_limpio_con_nombres.parquet"

df = pd.read_parquet(entrada)
print(f"Leído {entrada.name}: {len(df):,} filas")

# Edad agrupada
edad = df[COL_EDAD]
if pd.api.types.is_numeric_dtype(edad):
    edad = edad_a_grupo(edad)

# sexo y entidad se normalizan dentro de generar_nombres (mapeos.py)
nombres = generar_nombres(edad, df[COL_ENTIDAD], df[COL_SEXO], seed=SEED)

# Evita duplicar columnas si se vuelve a correr
df = df.drop(columns=[c for c in nombres.columns if c in df.columns])
df = pd.concat([df, nombres], axis=1)

faltantes = nombres.isna().sum()
if faltantes.any():
    print("Registros sin nombre asignado (sin bolsa o llaves nulas):")
    print(faltantes[faltantes > 0].to_string())

df.to_parquet(salida, index=False)
print(f"Guardado {salida.name} en {time.time() - t0:.1f}s")
print(df[["nombre", "apellido_paterno", "apellido_materno"]].head(10).to_string())

# Muestra de 100 filas en CSV (utf-8-sig para que Excel respete los acentos)
muestra = OUTPUTPATH / f"edr_{year}_limpio_con_nombres_muestra.csv"
df.sample(n=100, random_state=SEED).to_csv(muestra, index=False, encoding="utf-8-sig")
print(f"Guardada muestra: {muestra.name}")