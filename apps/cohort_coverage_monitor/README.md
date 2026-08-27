# BrainLat Coverage Monitor

Aplicación Streamlit independiente para monitorear el estado operativo y cobertura de la cohorte LATAM (2026-07). Esta aplicación no forma parte de GEMMA y está diseñada para ser desplegada en Streamlit Community Cloud de forma autónoma, usando un snapshot de datos agregados pre-generado.

## Requisitos y Privacidad
Esta aplicación **no contiene, lee ni expone datos privados** de los participantes (como coordenadas, IDs o direcciones). 

Para lograr esto, existe un paso previo local (`snapshot_builder.py`) que debe ser ejecutado por un administrador con acceso a los datos crudos locales. Este script lee el CSV privado y los manifests del catálogo de GEMMA, calcula los agregados y genera un archivo público `cohort_public_snapshot.json` que luego es consumido por la aplicación.

## 1. Actualización de Datos (Local)
Cada vez que haya actualizaciones en la cohorte, en los estados operativos (`config/operations/cohort_latam_report.yaml`) o en los exposomas publicados (manifests), debes regenerar el snapshot.

Desde la raíz del repositorio de BrainLat, ejecuta:
```bash
.venv/bin/python apps/cohort_coverage_monitor/services/snapshot_builder.py
```

Revisa que el archivo se generó correctamente:
```bash
cat apps/cohort_coverage_monitor/data/cohort_public_snapshot.json
```
Asegúrate de que no contenga datos individuales (solo agregados y centroides de la ciudad). Luego, realiza un commit y push a GitHub:
```bash
git add apps/cohort_coverage_monitor/data/cohort_public_snapshot.json
git commit -m "Update cohort coverage public snapshot"
git push
```

## 2. Ejecución Local de la App
Para probar la aplicación localmente, activa el entorno y ejecuta Streamlit:
```bash
pip install -r apps/cohort_coverage_monitor/requirements.txt
streamlit run apps/cohort_coverage_monitor/app.py
```

## 3. Despliegue en Streamlit Community Cloud
La aplicación está estructurada para un despliegue sin fricciones (gratuito) en Streamlit Cloud.

1. Entra a [share.streamlit.io](https://share.streamlit.io/).
2. Conecta tu cuenta de GitHub y autoriza el repositorio de BrainLat.
3. Haz clic en **Create app** -> **Deploy a public app from GitHub**.
4. Llena el formulario con:
   - **Repository:** `Bastian963/demo-exposome-santiago` (o el correspondiente)
   - **Branch:** `main` (o la rama donde estés trabajando)
   - **Main file path:** `apps/cohort_coverage_monitor/app.py`
5. Haz clic en **Deploy**. Streamlit leerá automáticamente el archivo `apps/cohort_coverage_monitor/requirements.txt` y lanzará la aplicación.

No se requieren variables de entorno, secretos (Secrets) ni credenciales de API para esta primera versión.

## Tests
Para correr los tests unitarios de las métricas puras y lógica de la aplicación:
```bash
PYTHONPYCACHEPREFIX=/tmp .venv/bin/python -m unittest discover -s apps/cohort_coverage_monitor/tests
```
