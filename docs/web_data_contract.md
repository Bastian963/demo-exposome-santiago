# Contrato de datos de la aplicación

La aplicación no consume directamente nombres de archivos del pipeline. Cada
estudio se publica como un bundle versionado y autocontenido:

```text
webapp/public/data/
├── catalog.json
└── v1/<country>/<city>/<study>/
    ├── manifest.json
    ├── master.geojson          # estudios agregados
    ├── profiles/               # opcional, por unidad espacial
    ├── layers/                 # estudios nativos
    ├── sources.json
    └── methodology/
```

`catalog.json` contiene los estudios configurados y solo marca `available` los
bundles publicados. El `manifest.json` declara el modo (`aggregate` o `native`),
la unidad espacial, el periodo, las capas disponibles y cada asset con tamaño y
SHA-256.

Para publicar los estudios actualmente disponibles:

```bash
.conda/envs/exposome/bin/python scripts/publish_webapp.py \
  --study santiago_communes \
  --study caba_native
```

`buenos_aires_zipcodes` permanece no disponible hasta que exista un GeoJSON de
códigos postales válido. El modo nativo de CABA conserva los GeoTIFF/GeoPackage
originales y añade `native_preview.geojson` para carga inicial en MapLibre.

Los assets generados no deben versionarse junto con el código cuando el número
de ciudades crezca. El repositorio conserva configuración, manifests de ejemplo,
schemas, documentación y fixtures pequeños; el bundle completo se publica en
un almacenamiento de artefactos y la app usa `VITE_DATA_BASE_URL` para resolver
su prefijo.
