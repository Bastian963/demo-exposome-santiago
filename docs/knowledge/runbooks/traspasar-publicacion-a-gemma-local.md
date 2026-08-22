# Traspasar una publicación de Joaco a GEMMA local

## Propósito

GEMMA se ejecuta localmente en el Mac mientras está en desarrollo. Los datos
publicados en el computador de Joaco viven en una ruta ignorada por Git, por lo
que un `git push` no los transfiere. Este procedimiento mueve **un bundle web ya
publicado** por AnyDesk, sin copiar cachés, PBF de OSM, datos crudos ni tokens.

El archivo de handoff incluye hashes SHA-256 de cada archivo. El Mac verifica
todo antes de instalarlo y reconstruye su catálogo local.

## En Joaco: preparar un bundle

Primero debe haber terminado `materialize`, `verify`, `publish` y la auditoría
espacial estricta del estudio. Desde la raíz del repositorio:

```bash
.venv/bin/python scripts/package_gemma_bundle.py \
  --bundle webapp/public/data/v1/br/sao_paulo/sao_paulo_distritos \
  --output /mnt/c/Users/AMD_III/Documents/gemma-handoff-sao-paulo.tar
```

El comando vuelve a ejecutar la auditoría espacial estricta local y se niega a
crear el archivo si el bundle no cumple. Copiar el `.tar` mediante la pestaña
**Transferencia de archivos** de AnyDesk. No usar el portapapeles para archivos
grandes.

## En el Mac: validar e instalar

Colocar el archivo, por ejemplo, en `~/Downloads/`, y desde la raíz del clon
que sirve GEMMA ejecutar:

```bash
.venv/bin/python scripts/import_gemma_bundle.py \
  --archive ~/Downloads/gemma-handoff-sao-paulo.tar \
  --inspect-only

.venv/bin/python scripts/import_gemma_bundle.py \
  --archive ~/Downloads/gemma-handoff-sao-paulo.tar
```

El segundo comando escribe únicamente en `webapp/public/data/v1/...` y
regenera `webapp/public/data/catalog.json`. Reiniciar el servidor local de
GEMMA o recargar la aplicación; São Paulo debe aparecer en el selector.

Si el destino ya contiene el mismo `manifest.json`, se informa `already
installed`. Si existe un bundle distinto, el comando se detiene: inspeccionar
primero y usar `--replace` solamente si se aprobó reemplazar la versión local.

## Verificación y recuperación

En el Mac:

```bash
.venv/bin/exposome spatial-audit \
  --bundle webapp/public/data/v1/br/sao_paulo/sao_paulo_distritos --strict
```

Un error de hash, una ruta insegura en el tar o un manifiesto ausente no cambia
la instalación local. Pedir de nuevo el archivo de AnyDesk y repetir la
validación. No intentar reconstruir datos en el Mac como sustituto del bundle.

## Alcance y evolución

Este es un mecanismo local y manual, deliberadamente sin costo ni servicio
externo. Cuando GEMMA deje de ser local, publicar los mismos bundles en un
origen HTTP versionado (por ejemplo R2) y configurar `VITE_DATA_BASE_URL`; no
subir `webapp/public/data` al repositorio Git.
