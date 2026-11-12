from mx_nombres import seleccionar_nombre, seleccionar_primer_apellido, seleccionar_segundo_apellido

nombre = seleccionar_nombre(
    edad_agrupada="De 15 a 19",
    entidad=1,
    sexo="FEMENINO",
)

apellido1 = seleccionar_primer_apellido(
    edad_agrupada="De 15 a 19",
    entidad=1,
    sexo="FEMENINO",
)

apellido2 = seleccionar_segundo_apellido(
    edad_agrupada="De 15 a 19",
    entidad=1,
    sexo="FEMENINO",
)

print(f"{nombre} {apellido1} {apellido2}")