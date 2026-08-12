# Vault de conocimiento de BrainLat

La raíz del repositorio se puede abrir directamente como un vault de Obsidian.
Este directorio agrega navegación y memoria de proyecto sin reemplazar las
fuentes de verdad del pipeline.

## Tipos de contenido

- `maps/`, `runbooks/`, `meetings/` y `notes/`: contenido compartido y editable.
- `generated/`: fichas generadas; no se editan manualmente.
- `templates/`: plantillas para contenido nuevo.
- `local-notes/`: borradores personales y transcripciones crudas, ignorados por Git.

La configuración, dependencias, estado de revisión y metodología continúan en
sus ubicaciones canónicas. Comienza en [Inicio](00-inicio.md).

## Actualización de catálogos

```bash
PYTHONPYCACHEPREFIX=/tmp .venv/bin/python scripts/build_obsidian_knowledge.py --write
PYTHONPYCACHEPREFIX=/tmp .venv/bin/python scripts/build_obsidian_knowledge.py --check
```

Obsidian no requiere MCP ni plugins comunitarios para este flujo. Los archivos
compartidos usan enlaces Markdown relativos y siguen siendo navegables en GitHub.

## Otro checkout

1. Sincroniza el entorno con `uv sync --all-extras`.
2. Abre la raíz del repositorio como vault.
3. Crea, si no existen, `local-notes/inbox`, `local-notes/daily` y
   `local-notes/meetings-inbox`.
4. Ejecuta el generador con `--check`.
