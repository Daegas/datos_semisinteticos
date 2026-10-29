import pandas as pd
from .mapeos import normalizar_entidad_escalar

# =====================================================================
# CÓDIGOS DE ENTIDADES
# Fuente: INEGI
# =====================================================================

ENT_CODE_A_NOMBRE = {
    1: "aguascalientes",
    2: "baja california",
    3: "baja california sur",
    4: "campeche",
    5: "coahuila",
    6: "colima",
    7: "chiapas",
    8: "chihuahua",
    9: "ciudad de méxico",
    10: "durango",
    11: "guanajuato",
    12: "guerrero",
    13: "hidalgo",
    14: "jalisco",
    15: "estado de méxico",
    16: "michoacán",
    17: "morelos",
    18: "nayarit",
    19: "nuevo león",
    20: "oaxaca",
    21: "puebla",
    22: "querétaro",
    23: "quintana roo",
    24: "san luis potosí",
    25: "sinaloa",
    26: "sonora",
    27: "tabasco",
    28: "tamaulipas",
    29: "tlaxcala",
    30: "veracruz",
    31: "yucatán",
    32: "zacatecas",
}


# =====================================================================
# MODELO 1: OCHO REGIONES
# Fuente: https://es.wikipedia.org/wiki/Regiones_de_M%C3%A9xico
# =====================================================================

ENTIDAD_A_REGION_8 = {
    "baja california": "Noroeste",
    "baja california sur": "Noroeste",
    "chihuahua": "Noroeste",
    "durango": "Noroeste",
    "sinaloa": "Noroeste",
    "sonora": "Noroeste",

    "coahuila": "Noreste",
    "nuevo león": "Noreste",
    "tamaulipas": "Noreste",

    "colima": "Occidente",
    "jalisco": "Occidente",
    "michoacán": "Occidente",
    "nayarit": "Occidente",

    "hidalgo": "Oriente",
    "puebla": "Oriente",
    "tlaxcala": "Oriente",
    "veracruz": "Oriente",

    "aguascalientes": "Centronorte",
    "guanajuato": "Centronorte",
    "querétaro": "Centronorte",
    "san luis potosí": "Centronorte",
    "zacatecas": "Centronorte",

    "ciudad de méxico": "Centrosur",
    "estado de méxico": "Centrosur",
    "morelos": "Centrosur",

    "chiapas": "Suroeste",
    "guerrero": "Suroeste",
    "oaxaca": "Suroeste",

    "campeche": "Sureste",
    "quintana roo": "Sureste",
    "tabasco": "Sureste",
    "yucatán": "Sureste",
}


# =====================================================================
# MODELO 2: CINCO MESORREGIONES
# Fuente: https://es.wikipedia.org/wiki/Mesorregiones_de_M%C3%A9xico
# =====================================================================

ENTIDAD_A_MESORREGION_5 = {
    "baja california": "Noroeste",
    "baja california sur": "Noroeste",
    "sinaloa": "Noroeste",
    "sonora": "Noroeste",

    "chihuahua": "Noreste",
    "durango": "Noreste",
    "coahuila": "Noreste",
    "nuevo león": "Noreste",
    "tamaulipas": "Noreste",

    "hidalgo": "Centro",
    "puebla": "Centro",
    "tlaxcala": "Centro",
    "querétaro": "Centro",
    "ciudad de méxico": "Centro",
    "estado de méxico": "Centro",
    "morelos": "Centro",

    "aguascalientes": "Centro Occidente",
    "guanajuato": "Centro Occidente",
    "san luis potosí": "Centro Occidente",
    "zacatecas": "Centro Occidente",
    "colima": "Centro Occidente",
    "jalisco": "Centro Occidente",
    "michoacán": "Centro Occidente",
    "nayarit": "Centro Occidente",

    "campeche": "Sureste",
    "quintana roo": "Sureste",
    "tabasco": "Sureste",
    "veracruz": "Sureste",
    "yucatán": "Sureste",
    "chiapas": "Sureste",
    "guerrero": "Sureste",
    "oaxaca": "Sureste",
}


MODELOS = {
    8: ENTIDAD_A_REGION_8,
    5: ENTIDAD_A_MESORREGION_5,
}


# =====================================================================
# ALIAS
# =====================================================================

ALIAS_ENTIDADES = {
    "coahuila de zaragoza": "coahuila",
    "veracruz de ignacio de la llave": "veracruz",
    "michoacán de ocampo": "michoacán",

    "cdmx": "ciudad de méxico",
    "cdmx.": "ciudad de méxico",
    "df": "ciudad de méxico",
    "d.f.": "ciudad de méxico",
    "distrito federal": "ciudad de méxico",

    "méxico": "estado de méxico",
    "edomex": "estado de méxico",
    "edo. de méxico": "estado de méxico",
    "estado de mexico": "estado de méxico",

    "nuevo leon": "nuevo león",
    "queretaro": "querétaro",
    "san luis potosi": "san luis potosí",
    "yucatan": "yucatán",
    "michoacan": "michoacán",
}


# =====================================================================
# FUNCIONES
# =====================================================================

def _obtener_mapa(modelo: int) -> dict:
    if modelo not in MODELOS:
        raise ValueError(
            f"Modelo '{modelo}' no válido. "
            "Usa 5 (mesorregiones) u 8 (regiones)."
        )

    return MODELOS[modelo]


from .mapeos import normalizar_entidad_escalar


def entidad_a_region(nombre, modelo: int = 8):
    """Devuelve la región de una entidad o 99 si no está especificada."""
    mapa = _obtener_mapa(modelo)

    if pd.isna(nombre):
        return 99

    try:
        codigo = normalizar_entidad_escalar(nombre)
    except (ValueError, TypeError):
        return None

    if codigo is None or codigo == 99:
        return 99 if codigo is None or codigo == 99 else None

    nombre_canonico = ENT_CODE_A_NOMBRE.get(codigo)

    if nombre_canonico is None:
        return None

    return mapa.get(nombre_canonico)


def agregar_region(
    df: pd.DataFrame,
    columna_entidad: str,
    columna_region: str = "region",
    modelo: int = 8,
    inplace: bool = False,
) -> pd.DataFrame:

    mapa = _obtener_mapa(modelo)

    if not inplace:
        df = df.copy()

    columna = df[columna_entidad]

    # Identificar códigos numéricos
    codigos = pd.to_numeric(columna, errors="coerce")
    es_codigo = columna.notna() & codigos.notna()

    # ---------------------------------------------------------------
    # Códigos
    # ---------------------------------------------------------------

    regiones_codigo = (
        codigos
        .map(ENT_CODE_A_NOMBRE)
        .map(mapa)
        .astype(object)
    )

    # 99 → 99
    regiones_codigo.loc[codigos.eq(99)] = 99

    # NaN → 99
    regiones_codigo.loc[columna.isna()] = 99

    # ---------------------------------------------------------------
    # Nombres
    # ---------------------------------------------------------------

    nombres = (
        columna
        .where(~es_codigo)
        .astype("string")
        .str.strip()
        .str.lower()
        .replace(ALIAS_ENTIDADES)
    )

    regiones_nombre = nombres.map(mapa)

    # ---------------------------------------------------------------
    # Combinar
    # ---------------------------------------------------------------

    regiones = regiones_codigo.combine_first(regiones_nombre)

    df[columna_region] = regiones

    return df


# # USO
# df = agregar_region(df, modelo=8, inplace=True)
# entidad_a_region("CDMX")