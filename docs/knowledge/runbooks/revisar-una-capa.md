# Revisar una capa

1. Abre la ficha en [Catálogo de capas](../generated/catalogo-capas.md).
2. Revisa metodología, configuración, implementación y prompt enlazados.
3. Ejecuta únicamente pruebas rápidas y locales permitidas.
4. Actualiza los campos manuales de `docs/exposome_status.csv`.
5. Regenera el dashboard con `scripts/audit_exposome_status.py --write` solo si
   verificaste que no pisará cambios simultáneos.
6. Regenera las fichas con `scripts/build_obsidian_knowledge.py --write`.
7. Ejecuta ambos chequeos con `--check`.
8. Confirma que no se modificaron resultados o cachés accidentalmente.

Para cualquier capa con soporte fino, aplica también
[Publicar y verificar resolución espacial](publicar-resolucion-espacial.md).

No marques `final_check=true` sin satisfacer los criterios definidos en `AGENTS.md`.
