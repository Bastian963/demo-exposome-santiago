# DEIS raw inputs

Directorio para insumos crudos de DEIS usados por pipelines reproducibles.

## Convención

- Guardar los archivos grandes localmente bajo `data/raw/deis/<dataset>/`.
- No commitear los CSV completos.
- Sí commitear este `README.md`, `.gitkeep` y muestras pequeñas (`sample_*.csv`) si hacen falta para tests.

## Datasets esperados

### Defunciones

- Ruta esperada:
  `data/raw/deis/defunciones/DEFUNCIONES_FUENTE_DEIS_1990_2023_CIFRAS_OFICIALES.csv`
- Origen:
  https://deis.minsal.cl/#datosabiertos
- Formato observado:
  `CSV` separado por `;`, codificación `latin1`
- Uso actual:
  comparador ecológico `neuro_mortality`

### Egresos hospitalarios

- Ruta sugerida:
  `data/raw/deis/egresos/EGRE_DATOS_ABIERTOS_2006.csv`
- Origen:
  https://deis.minsal.cl/#datosabiertos
- Formato observado:
  `CSV` separado por `;` (verificar columnas/encoding al incorporarlo a un pipeline)
- Uso actual:
  evaluación exploratoria; todavía no integrado al pipeline
