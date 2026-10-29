"""
Genera N personas sintéticas (nombre + 2 apellidos) con sexo, entidad y
edad agrupada aleatorios, usando mx_nombres, y las guarda en CSV.

Uso:
    python generar_personas.py                 # 1000 personas, salida por defecto
    python generar_personas.py --n 5000
    python generar_personas.py --seed 42 --out output/personas.csv
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from mx_nombres import (
    seleccionar_nombre,
    seleccionar_primer_apellido,
    seleccionar_segundo_apellido,
    _warmup,  # precarga el CSV/groupbys una sola vez
)
from mx_nombres.map_regiones import ENT_CODE_A_NOMBRE


# ---------------------------------------------------------------------------
# Catálogos (deben coincidir con los del notebook)
# ---------------------------------------------------------------------------
EDADES_AGRUPADAS = [
    "De 15 a 19", "De 20 a 24", "De 25 a 29", "De 30 a 34",
    "De 35 a 39", "De 40 a 44", "De 45 a 49", "De 50 a 54",
    "De 55 a 59", "De 60 a 64", "De 65 a 69", "De 70 a 74",
    "De 75 a 79", "De 80 a 84", "De 85 a 89", "De 90 a 94",
    "De 95 a 99", "De 100 a 104", "De 105 a 109", "De 110 a 114",
    "De 115 a 119", "De 120 y más",
]

# Entidades 1..32 (excluimos 99 = desconocido para datos sintéticos)
ENTIDADES = list(range(1, 33))

SEXOS = ["FEMENINO", "MASCULINO"]


# ---------------------------------------------------------------------------
# Generación
# ---------------------------------------------------------------------------
def generar_personas(n: int, seed: int | None = None) -> pd.DataFrame:
    rng = np.random.default_rng(seed)

    # Precarga única de los agrupados
    _warmup()

    registros = []
    for i in range(n):
        sexo = rng.choice(SEXOS)
        entidad = int(rng.choice(ENTIDADES))
        edad_agrupada = rng.choice(EDADES_AGRUPADAS)

        sub_seed = int(rng.integers(0, 2**31 - 1))

        nombre = seleccionar_nombre(
            edad_agrupada=edad_agrupada,
            entidad=entidad,
            sexo=sexo,
            seed=sub_seed,
            solo_misma_edad=False,
            max_pasos=5
        )
        apellido1 = seleccionar_primer_apellido(
            edad_agrupada=edad_agrupada,
            entidad=entidad,
            sexo=sexo,
            seed=sub_seed + 1,
            solo_misma_edad=False,
            max_pasos=5
        )
        apellido2 = seleccionar_segundo_apellido(
            edad_agrupada=edad_agrupada,
            entidad=entidad,
            sexo=sexo,
            seed=sub_seed + 2,
            solo_misma_edad=False,
            max_pasos=5
        )

        registros.append(
            {
                "NOMBRE": nombre,
                "PRIMER APELLIDO": apellido1,
                "SEGUNDO APELLIDO": apellido2,
                "SEXO": sexo,
                "CVE_ENTIDAD": entidad,
                "ENTIDAD": ENT_CODE_A_NOMBRE[entidad],
                "EDAD_AGRUPADA": edad_agrupada,
            }
        )


        if (i + 1) % 100 == 0:
            print(f"  {i + 1}/{n} generados...")

    return pd.DataFrame(registros)



# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main() -> None:
    parser = argparse.ArgumentParser(description="Genera personas sintéticas.")
    parser.add_argument("--n", type=int, default=1000, help="Número de personas")
    parser.add_argument("--seed", type=int, default=None, help="Semilla global")
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("output/personas_sinteticas.csv"),
        help="Ruta de salida CSV",
    )
    args = parser.parse_args()

    print(f"Generando {args.n} personas (seed={args.seed})...")
    df = generar_personas(args.n, seed=args.seed)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(args.out, index=False, encoding="utf-8-sig")
    print(f"Guardado en: {args.out}  ({len(df)} filas)")

    # Vista rápida
    print(df.head(10).to_string(index=False))


if __name__ == "__main__":
    main()