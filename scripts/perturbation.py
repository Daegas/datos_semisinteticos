"""
Generación de datos semisintéticos para record linkage.

Flujo por conjunto:
    1. add_person_id        -> id_persona (identifica al individuo real, ground truth)
    2. add_duplicates       -> repite registros del mismo individuo (mismo id_persona)
    3. drop_individuals     -> elimina registros de algunos individuos.
    4. perturb_dataframe    -> ruido con dos probabilidades:
                               p_record: prob. de que un registro sea perturbado
                               p_column: prob. de que, dado un registro seleccionado,
                                         cada columna sea perturbada
                               => prob. por celda = p_record * p_column
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

ID_COLS = ("id_persona", "id_registro")
NUMERICA_NOISE_RANGE_DEFAULT = (1, 5)


# --------------------------------------------------------------------------- #
# IDs y duplicados
# --------------------------------------------------------------------------- #
def add_person_id(df: pd.DataFrame, col: str = "id_persona") -> pd.DataFrame:
    """Agrega un identificador único por individuo"""
    df = df.copy()
    df.insert(0, col, np.arange(len(df)))
    return df


def add_duplicates(
    df: pd.DataFrame,
    p_dup: float,
    *,
    rng: np.random.Generator,
    max_copies: int = 1,
    id_col: str = "id_persona",
) -> pd.DataFrame:
    """
    Duplica una fracción p_dup de los registros (cada elegido recibe entre 1 y
    `max_copies` copias). Las copias conservan id_persona. Se mezclan las filas y
    se agrega `id_registro`, único por fila dentro del conjunto.

    Debe llamarse ANTES de perturbar: así cada copia recibe ruido independiente.
    """
    if not 0 <= p_dup <= 1:
        raise ValueError("p_dup debe estar entre 0 y 1")
    if max_copies < 1:
        raise ValueError("max_copies debe ser >= 1")

    chosen = np.flatnonzero(rng.random(len(df)) < p_dup)
    n_copies = rng.integers(1, max_copies + 1, size=len(chosen))
    dup_pos = np.repeat(chosen, n_copies)

    out = pd.concat([df, df.iloc[dup_pos]], ignore_index=True)
    out = out.sample(frac=1, random_state=int(rng.integers(2**31 - 1)))
    out = out.reset_index(drop=True)
    out.insert(out.columns.get_loc(id_col) + 1, "id_registro", np.arange(len(out)))
    return out

def drop_individuals(
    df: pd.DataFrame,
    p_drop: float,
    *,
    rng: np.random.Generator,
    id_col: str = "id_persona",
) -> pd.DataFrame:
    """Elimina individuos aleatoriamente, conservando todos sus registros juntos."""

    if not 0 <= p_drop <= 1:
        raise ValueError("p_drop debe estar entre 0 y 1")

    if id_col not in df.columns:
        raise KeyError(f"Columna no encontrada: {id_col}")

    ids = df[id_col].dropna().unique()

    # Seleccionar individuos que serán eliminados
    drop_mask = rng.random(len(ids)) < p_drop
    ids_to_drop = ids[drop_mask]

    return df.loc[~df[id_col].isin(ids_to_drop)].copy()

# --------------------------------------------------------------------------- #
# Funciones de ruido: f(serie, mask, rng, ...) -> valores nuevos
# `mask` indica exactamente qué filas perturbar.
# --------------------------------------------------------------------------- #
def noise_categorical(s, mask, rng, mapping: dict[str, list[str]]):
    """Reemplaza el valor por un sinónimo distinto del original (si existe)."""
    values = s.to_numpy(dtype=object)
    out = values.copy()
    idx = np.flatnonzero(mask)
    if len(idx) == 0:
        return out
    sub = values[idx]
    for cat in pd.unique(sub):
        alts = [a for a in dict.fromkeys(mapping.get(cat, [])) if a != cat]
        if not alts:
            continue
        pos = idx[sub == cat]
        out[pos] = rng.choice(np.asarray(alts, dtype=object), size=len(pos))
    return out


def noise_swap(s, mask, rng):
    """Reemplaza por otro valor observado en la misma columna (siempre distinto)."""
    codes, uniques = pd.factorize(s)
    k = len(uniques)
    mask = mask & (codes >= 0)
    out = s.to_numpy(dtype=object).copy()
    if k < 2 or not mask.any():
        return out
    pos = np.flatnonzero(mask)
    new_codes = (codes[pos] + 1 + rng.integers(0, k - 1, size=len(pos))) % k
    out[pos] = np.asarray(uniques, dtype=object)[new_codes]
    return out


def noise_numeric(s, mask, rng, noise_range=NUMERICA_NOISE_RANGE_DEFAULT, min_value=0):
    """Suma/resta una magnitud entera en noise_range; nunca baja de min_value."""
    lo, hi = noise_range
    if lo < 0 or hi < lo:
        raise ValueError("noise_range inválido")
    vals = pd.to_numeric(s, errors="coerce").to_numpy(dtype=float)
    mask = mask & ~np.isnan(vals)
    noise = rng.integers(lo, hi + 1, size=len(vals)) * rng.choice([-1, 1], size=len(vals))
    out = vals.copy()
    out[mask] = np.maximum(vals[mask] + noise[mask], min_value)
    return pd.Series(out, index=s.index).round().astype("Int64")


def noise_datetime(s, mask, rng):
    """Mueve la fecha ±1 día, ±1 mes o ±1 año."""
    dates = pd.to_datetime(s, errors="coerce")
    mask = mask & dates.notna().to_numpy()
    comps = rng.choice(["days", "months", "years"], size=len(dates))
    signs = rng.choice([-1, 1], size=len(dates))
    out = dates.copy()
    for comp in ("days", "months", "years"):
        for sign in (-1, 1):
            pos = np.flatnonzero(mask & (comps == comp) & (signs == sign))
            if len(pos):
                out.iloc[pos] = dates.iloc[pos] + pd.DateOffset(**{comp: sign})
    return out


def noise_text(s, mask, rng):
    """Error tipográfico: omisión, truncamiento, transposición o espacio eliminado."""
    vals = s.to_numpy(dtype=object).copy()
    for i in np.flatnonzero(mask):
        t = vals[i]
        if not isinstance(t, str) or len(t) < 2:
            continue
        ops = ["omission", "truncation", "transposition"]
        if " " in t:
            ops.append("spacing")
        op = rng.choice(ops)

        if op == "spacing":
            p = rng.choice([j for j, c in enumerate(t) if c == " "])
            t = t[:p] + t[p + 1:]
        elif op == "omission":
            p = rng.integers(0, len(t))
            t = t[:p] + t[p + 1:]
        elif op == "truncation":
            t = t[: -rng.integers(1, len(t))]
        else:  # transposition
            p = rng.integers(0, len(t) - 1)
            t = t[:p] + t[p + 1] + t[p] + t[p + 2:]
        vals[i] = t
    return vals


# --------------------------------------------------------------------------- #
# Utilidades
# --------------------------------------------------------------------------- #
def age_group_label(age: int) -> str:
    """Etiqueta quinquenal con el mismo formato que `edad_agru` (aplica a edad >= 5)."""
    if age >= 120:
        return "De 120 y más"
    lo = (age // 5) * 5
    return f"De {lo} a {lo + 4}"


def _load_mapping(name: str, mapping_dir: Path, cache: dict) -> dict:
    if name not in cache:
        with open(Path(mapping_dir) / f"{name}.json", "r", encoding="utf-8") as f:
            cache[name] = json.load(f)
    return cache[name]


def _changed(before: pd.Series, after: pd.Series) -> np.ndarray:
    eq = before.eq(after).fillna(False).astype(bool)
    both_na = before.isna() & after.isna()
    return ~(eq | both_na).to_numpy()


# --------------------------------------------------------------------------- #
# Función principal
# --------------------------------------------------------------------------- #
def perturb_dataframe(
    df: pd.DataFrame,
    column_spec: dict,
    p_record: float,
    p_column: float,
    *,
    mapping_dir: str | Path,
    p_column_overrides: dict[str, float] | None = None,
    seed=None,
    age_col: str = "edad",
    age_group_col: str = "edad_agru",
    verbose: bool = True,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Perturba `df` según `column_spec`.

    column_spec : {columna: tipo} o {columna: (tipo, argumento)}
        tipos:
          "categorical", "<mapping>" -> sinónimo del diccionario JSON <mapping>
          "numeric",     {noise_range:(1,5), min_value:0}  (arg opcional)
          "datetime"
          "text"
          "swap"                     -> otro valor observado en la columna
    p_record : prob. de que un registro sea elegido para recibir ruido.
    p_column : prob. de que cada columna se perturbe en un registro elegido.
    p_column_overrides : {columna: p} para columnas con su propia probabilidad.

    Si `age_col` se perturba y existe `age_group_col`, ésta se recalcula en las
    filas cuya edad cambió (para que sea coherente).

    Devuelve (df_perturbado, reporte). Las columnas ID_COLS nunca se tocan.
    """
    for name, p in (("p_record", p_record), ("p_column", p_column)):
        if not 0 <= p <= 1:
            raise ValueError(f"{name} debe estar entre 0 y 1")
    overrides = p_column_overrides or {}

    for col, p in overrides.items(): # check overrides
        if not 0 <= p <= 1:
            raise ValueError(
                f"La probabilidad para {col} debe estar entre 0 y 1"
            )

    rng = np.random.default_rng(seed)
    out = df.reset_index(drop=True).copy()
    original = out.copy()
    n = len(out)

    record_mask = rng.random(n) < p_record      # selección por registro
    cache: dict = {}
    changed_masks: dict[str, np.ndarray] = {}
    report = []

    for col, spec in column_spec.items():
        if col in ID_COLS:
            raise ValueError(f"{col} es un ID y no puede perturbarse")
        if col not in out.columns:
            raise KeyError(f"Columna no encontrada: {col}")
        kind, arg = spec if isinstance(spec, tuple) else (spec, None)

        p_c = overrides.get(col, p_column)
        mask = record_mask & (rng.random(n) < p_c)   # selección por columna
        before = out[col]

        if kind == "categorical":
            new = noise_categorical(before, mask, rng, _load_mapping(arg, mapping_dir, cache))
        elif kind == "numeric":
            new = noise_numeric(before, mask, rng, **(arg or {}))
        elif kind == "datetime":
            new = noise_datetime(before, mask, rng)
            before = pd.to_datetime(before, errors="coerce")
        elif kind == "text":
            new = noise_text(before, mask, rng)
        elif kind == "swap":
            new = noise_swap(before, mask, rng)
        else:
            raise ValueError(f"Tipo de perturbación desconocido: {kind}")

        out[col] = new
        ch = _changed(before, out[col])
        changed_masks[col] = ch
        report.append(
            dict(
                columna=col, tipo=kind, p_celda=round(float(record_mask.mean() * p_c), 3),
                modificados=int(ch.sum()), pct_modificado=round(100 * ch.mean(), 2),
                unicos_antes=before.nunique(), unicos_despues=out[col].nunique(),
            )
        )

    # edad_agru coherente con la edad perturbada
    if age_col in changed_masks and age_group_col in out.columns:
        rows = changed_masks[age_col]
        out.loc[rows, age_group_col] = [age_group_label(int(a)) for a in out.loc[rows, age_col]]
        ch = _changed(original[age_group_col], out[age_group_col])
        report.append(
            dict(
                columna=age_group_col, tipo="derived", p_celda=np.nan,
                modificados=int(ch.sum()), pct_modificado=round(100 * ch.mean(), 2),
                unicos_antes=original[age_group_col].nunique(),
                unicos_despues=out[age_group_col].nunique(),
            )
        )

    report = pd.DataFrame(report)
    if verbose:
        print(f"Registros seleccionados: {record_mask.sum():,} de {n:,} ({100*record_mask.mean():.1f}%)")
        print(report.to_string(index=False))
    return out, report


# --------------------------------------------------------------------------- #
# Especificación de columnas por conjunto (según los "Resúmenes" del notebook)
# --------------------------------------------------------------------------- #
_NAMES = {c: "text" for c in ("nombre", "apellido_paterno", "apellido_materno")}

SPEC_A = {
    "sexo": ("categorical", "sexo"),
    "ent_resid_nom": ("categorical", "entidades_federativas"),
    "tipo_defun_nom": ("categorical", "tipo_defuncion"),
    "vio_fami_nom": ("categorical", "comunes"),
    "cirugia_nom": ("categorical", "comunes"),
    "natviole_nom": ("categorical", "comunes"),
    "fecha_nacim": "datetime",
    "par_agre_nom": "text",
    "cve_lengua_nom": "swap",  
}

SPEC_B = {
    "sexo": ("categorical", "sexo"),
    "ent_nac_nom": ("categorical", "entidades_federativas"),
    "afromex_nom": ("categorical", "comunes"),
    "conindig_nom": ("categorical", "comunes"),
    "ocupacion_nom": ("categorical", "ocupaciones"),
    "ent_resid_nom": ("categorical", "entidades_federativas"),
    "encefalica_nom": ("categorical", "comunes"),
    "rel_emba_nom": ("categorical", "comunes"),
    "edad": ("numeric", {"noise_range": (1, 5), "min_value": 0}),
    "fecha_regis": "datetime",
    "maternas_nom": "text",
    "nacionalid_nom": "text",
    "razon_m_nom": "text",
    "mun_resid_nom": "text",
    "loc_resid_nom": "text",
    "causa_def_nom": "text",
    **_NAMES,
}

SPEC_C = {
    "sexo": ("categorical", "sexo"),
    "cond_act_nom": ("categorical", "comunes"),
    "ent_ocurr_nom": ("categorical", "entidades_federativas"),
    "edad": ("numeric", {"noise_range": (1, 5), "min_value": 0}),
    "fecha_ocurr": "datetime",
    "lengua_nom": "text",
    "mun_resid_nom": "text",
    "area_ur_nom": "text",
    "mun_ocurr_nom": "text",
    "loc_ocurr_nom": "text",
    "lista_mex_nom": "text",
    **_NAMES,
}