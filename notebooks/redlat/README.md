# Material para ReDLat

Notebooks dirigidos hacia afuera del equipo BrainLat — para colaboradores de
ReDLat, no análisis interno de cohorte (eso vive en `notebooks/cohort/`).

## Qué hay acá (para quien llega desde un link)

- **[`gemma_redlat_tutorial.ipynb`](gemma_redlat_tutorial.ipynb)** — el
  tutorial: qué es GEMMA, cómo está organizado el CSV que te entregan, cómo
  funcionan los radios de búsqueda, y un tutorial práctico con pandas
  (cargar, filtrar, comparar). **100% autocontenido**: no importa nada de
  `exposome.*` ni lee ningún archivo del repo — solo `pandas`/`numpy`/
  `matplotlib` sobre un DataFrame de ejemplo. Por eso es lo único de este
  proyecto que se publica en un repo público de GitHub; el resto del
  pipeline de GEMMA (código de geocodificación/extracción, datos de la
  cohorte) es privado.
  GitHub lo renderiza directo en el navegador, no hace falta clonar nada ni
  tener Jupyter:
  https://github.com/Bastian963/demo-exposome-santiago/blob/redlat-zipcode-tutorial/notebooks/redlat/gemma_redlat_tutorial.ipynb
- **Informe de cobertura** (`redlat_zipcode_exposome_report.pdf`, generado
  por `scripts/build_redlat_report.py`) — resumen con mapas de cuántos
  participantes tienen exposoma listo hoy. Es el que trae el "estado actual
  de la cohorte" — queda solo en el `.zip` de entrega, no en GitHub.
- **El CSV con los datos** (`point_exposome_wide.csv`) tampoco se sube a
  GitHub — viaja en el `.zip` de entrega
  (`output/redlat_exposome_delivery_2026-09.zip`, armado por
  `scripts/package_redlat_delivery.py`), que también incluye este mismo
  tutorial (`.ipynb` + `.html`), el informe y la metodología. Ver
  `docs/redlat_zipcode_pipeline.md` para el pipeline completo (privado).

## Tutorial de datos de exposoma

`gemma_redlat_tutorial.ipynb` es un **activo permanente, reutilizable y
autocontenido**, no un análisis de una entrega puntual: describe qué es
GEMMA, cómo está organizado el CSV entregable (`point_exposome_wide.csv`),
qué significa cada radio de búsqueda, y un tutorial práctico con pandas.
Pensado para acompañar cada vez que se entrega una descarga de exposoma a
alguien de ReDLat.

**Todos los ejemplos de código corren sobre un DataFrame sintético**
(participantes `EJ001`/`EJ002`/`EJ003`, inventados) con el mismo esquema de
columnas que el CSV real — así el notebook sirve igual sin importar qué
entrega esté vigente, y ningún `record_id` real circula más allá de quien ya
recibió su CSV. No lee `cohort.json`, `catalog.json` ni ningún otro archivo
interno de GEMMA — eso queda en el informe PDF, que es privado.

### Correr

```bash
uv sync --extra dev
PYTHONPYCACHEPREFIX=/tmp .venv/bin/python -m unittest tests.test_redlat_tutorial_notebook
```

Abrí el notebook seleccionando el kernel de `.venv` (Python 3.12) y ejecutá
todas las celdas.

### Exportar a HTML (para compartir sin Jupyter)

```bash
.venv/bin/jupyter nbconvert --to html --execute \
  notebooks/redlat/gemma_redlat_tutorial.ipynb \
  --output-dir output/jupyter-notebook/gemma_redlat_tutorial
cp -r notebooks/redlat/assets output/jupyter-notebook/gemma_redlat_tutorial/
```

El HTML queda en `output/jupyter-notebook/gemma_redlat_tutorial/` (gitignored,
como el resto de `output/`) — es lo que se puede mandar por correo o subir a
donde ReDLat lo necesite, sin que el destinatario tenga que clonar el repo.

### Actualizar el .zip cuando llegue una entrega nueva

Correr `docs/redlat_zipcode_pipeline.md` de punta a punta primero
(geocodificar + extraer + informe), después `scripts/package_redlat_delivery.py`.
El notebook en sí no depende de ninguna entrega — solo se re-sube a GitHub si
cambia su propio contenido.
