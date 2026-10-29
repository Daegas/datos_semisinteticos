"""
Agrega las columnas nombre, apellido_paterno y apellido_materno al parquet limpio.

    edr_{year}_limpio.parquet  ->  edr_{year}_limpio_con_nombres.parquet
"""

import time

import numpy as np
import pandas as pd
from pathlib import Path

from mx_nombres import generar_nombres

year = 2024
SEED = 2026

# --- COLUMNAS del parquet  ---------------------------------------------------
COL_EDAD = "edad_agru"   # texto "De 15 a 19", o bien edad numérica en años
COL_ENTIDAD = "ent_nac_nom"      # clave 1..32
COL_SEXO = "sexo"            # Hombre/Mujer, 1/2, H/M... (ver mapeos.py)
# -----------------------------------------------------------------------------

t0 = time.time()
PROJECT_PATH = Path(__file__).parent.parent
print(f"Proyecto: {PROJECT_PATH.name}, año: {year}, semilla: {SEED}")
entrada = PROJECT_PATH / "output" / f"edr_{year}_limpio.parquet"
salida = PROJECT_PATH / "output" / f"edr_{year}_limpio_con_nombres.parquet"

df = pd.read_parquet(entrada)
print(f"Leído {entrada.name}: {len(df):,} filas")

# sexo y entidad se normalizan dentro de generar_nombres (mapeos.py)
nombres = generar_nombres(df[COL_EDAD], df[COL_ENTIDAD], df[COL_SEXO], seed=SEED)

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
muestra = salida.parent / f"edr_{year}_limpio_con_nombres_muestra.csv"
df.sample(n=100, random_state=SEED).to_csv(muestra, index=False, encoding="utf-8-sig")
print(f"Guardada muestra: {muestra.name}")