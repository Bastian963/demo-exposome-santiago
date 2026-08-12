# Recuperar ALAN nativo por ciudad

Este procedimiento recupera el mapa ALAN de VIIRS sin convertir los valores en
promedios administrativos. La comuna, distrito o municipio sólo se usa para
disolver el AOI de la ciudad y, después, para resumir el producto; no define
los píxeles ni la fase de la grilla.

La fuente canónica es `NOAA/VIIRS/DNB/MONTHLY_V1/VCMSLCFG`, banda `avg_rad`,
promedio de 2024, en su grilla de **15 arc-segundos** (463,83 m nominales). No
publicar un TIFF histórico solicitado a 500 m: aunque tenga variación visual,
no conserva la grilla de origen.

## Qué debe ejecutar una persona

La primera orden de cada par consulta Google Earth Engine y puede tardar. Debe
ejecutarla una persona desde la raíz del repositorio, con autenticación GEE
activa; el asistente sólo prepara y revisa el procedimiento. `--resume` conserva
los productos ya materializados.

| Ciudad visible | Estudio nativo | Estudio agregado que se publica |
|---|---|---|
| Santiago | `santiago_native` | `santiago_communes` |
| AMBA | `buenos_aires_amba_native` | `buenos_aires_amba` |
| CABA | `caba_native` | `buenos_aires_comunas` |
| Bogotá | `bogota_native` | `bogota_localidades` |
| Medellín | `medellin_native` | `medellin_comunas` |
| Valle de Aburrá | `valle_aburra_native` | `valle_aburra_municipios` |
| CDMX | `cdmx_native` | `cdmx_alcaldias` |
| Lima | `lima_native` | `lima_distritos` |
| São Paulo | `sao_paulo_native` | `sao_paulo_distritos` |

Para una fila de la tabla, sustituye `<native>` y `<aggregate>`:

```bash
uv sync --all-extras
source .venv/bin/activate
earthengine authenticate                 # sólo si ee.Initialize falla
exposome run --study <native> --layers alan --resume
exposome run --study <aggregate> --layers alan --resume
exposome detail --study <aggregate> --indicators alan --resume
exposome verify --study <aggregate>
python scripts/export_study_profiles.py --study <aggregate>
exposome publish --study <aggregate>
```

La corrida nativa descarga el ráster sobre el AOI disuelto. La corrida
agregada produce las estadísticas zonales necesarias para el master. El paso
`detail` es local: sólo transforma el TIFF nativo existente en el COG que verá
la app y escribe su sidecar de procedencia.

## Verificación antes de promover

Después de publicar, se debe aprobar esta secuencia para el bundle de la
ciudad:

```bash
exposome spatial-audit --bundle webapp/public/data/v1/<iso2>/<city>/<aggregate> --strict
exposome resolution-coverage --bundle webapp/public/data/v1/<iso2>/<city>/<aggregate> --tier preview
```

Para que una ciudad pase de **VISTA PREVIA** a producción, el segundo comando
debe ejecutarse con `--tier production` y terminar correctamente. Si ALAN
falla, inspecciona `detail/alan.metadata.json`: debe contener
`source_grid.crs: EPSG:4326` y resolución `x/y` de aproximadamente
`0.0041666667` grados. No se acepta corregir ese dato editando el JSON; hay que
regenerar el TIFF desde la fuente.

Tras completar un lote de ciudades:

```bash
exposome spatial-audit --all --strict
exposome resolution-coverage --all --tier preview
python scripts/export_webapp_distributions.py
```

El último comando de cobertura sólo informa brechas. El modo
`--tier production` se reserva para el hito en que todas las capas disponibles
de todas las ciudades tengan su máximo soporte publicado.
