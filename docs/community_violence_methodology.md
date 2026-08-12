# Violencia comunitaria registrada — SNIC departamentos

## Rol en el exposoma

`community_violence` representa el contexto territorial de violencia
registrada. Es una exposición social agregada, no una medición de
victimización individual, peligrosidad personal ni causalidad. Se mantiene
separada de `community_safety`, que describe delitos contra la propiedad.

## Fuente y granularidad

La fuente requerida es **SNIC — Departamentos, anual, 2000–2025**, publicada
por la Dirección Nacional de Estadística Criminal. El pipeline usa 2017–2025
y agrega únicamente las unidades departamentales correspondientes a las 15
comunas de CABA y 40 partidos bonaerenses del estudio AMBA. No se permite
reemplazarla por las tablas de país o provincia, porque perderían la variación
territorial necesaria. La fuente contiene 150 unidades de CABA y provincia de
Buenos Aires; 95 partidos fuera del perímetro del estudio se excluyen de forma
explícita y la salida exige cobertura completa de las 55 unidades AMBA.

## Indicadores

Se construyen tasas por 100.000 personas-año para homicidio doloso, tentativa
de homicidio, lesiones dolosas, violencia sexual y robo agravado. Las
categorías se seleccionan con una política SNIC explícita y se valida su
presencia por unidad y año. Para violencia sexual se usan `10 + 11` entre
2017–2022; desde 2023, cuando el total agrupado `11` deja de publicarse, se
usan `10 + 11_1 + 11_2 + 11_3 + 11_4 + 11_5`. El padre y sus hijos nunca se
suman en el mismo año, evitando doble conteo.

La web usa ventanas móviles de tres años, desde 2017–2019 hasta 2023–2025.
Cuando el numerador acumulado es menor que cinco, la tasa pública es nula. Los
recuentos y personas-año quedan en diagnósticos internos, no en el CSV, el
GeoJSON ni la web.

## Limitaciones

- Son hechos o víctimas registrados por el sistema, no prevalencia real.
- Denuncia, capacidad institucional y reglas de carga pueden variar entre
  jurisdicciones y años.
- La asociación ecológica no identifica riesgo individual.
- La capa no se materializa ni se anuncia disponible mientras falte el archivo
  departamental oficial y sus validaciones de cobertura.
- `master_coverage.csv` reporta esta capa como `partial` (55/55 unidades
  presentes, ~72.7% de celdas completas) porque la supresión de privacidad
  (numerador < 5) deja `NaN` en ventanas/métricas puntuales para unidades de
  baja población — 7 comunas CABA y 8 partidos bonaerenses de menor tamaño, sin
  patrón geográfico único. Es el resultado esperado de la regla de privacidad,
  no una descarga incompleta; no requiere re-ejecución.

## Reproducibilidad

La descarga se incorpora con
`scripts/import_argentina_criminal_sources.py --download-missing`; el importador
preserva el original, hash y procedencia. La ejecución canónica es
`exposome run --study buenos_aires_amba --layers community_violence --resume`.
