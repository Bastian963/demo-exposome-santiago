# IBGE — referencia oficial de la RMBH

Este directorio congela las dos fuentes que definen el estudio
`belo_horizonte_rmbh`:

1. La lista oficial de municipios del **Recorte Metropolitano** de IBGE,
   filtrada a la categoría `Região Metropolitana de Belo Horizonte` dentro del
   recorte metropolitano.
2. La Malha Municipal Digital de Minas Gerais de IBGE, que aporta la
   geometría de esos municipios.

El estudio cubre los 34 municipios de la RMBH y excluye explícitamente el
**Colar Metropolitano**, que es un recorte legal distinto. No descargar estas
fuentes desde código de producción: se obtienen manualmente, se guardan bajo
un subdirectorio versionado y el migrador registra nombres, URLs y SHA-256 en
`source_manifest.json`.

La instrucción exacta y el contrato de validación están en
`scripts/migrations/build_belo_horizonte_rmbh_reference.py`.
