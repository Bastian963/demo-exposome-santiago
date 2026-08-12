# Calor agudo y atenciones cardiovasculares de urgencia en la Región Metropolitana

## Propósito y alcance

Piloto ecológico de serie temporal para decidir si las bases DEIS de atenciones
de urgencia 2020-2025 aportan un desenlace sanitario reproducible al proyecto.
No construye una capa del exposoma ni estima riesgo individual. La unidad de
inferencia es la demanda diaria atendida por establecimientos ubicados en la
Región Metropolitana (RM), no la comuna de residencia del paciente.

**Veredicto de conservación:** `keep_all`. Los datos superaron las puertas de
integridad, cobertura, continuidad temporal y estimabilidad. Este veredicto no
depende de obtener una asociación estadísticamente significativa.

## Datos

### Desenlaces DEIS

- ZIP anuales `AtencionesUrgencia2020.zip` a `AtencionesUrgencia2025.zip`.
- Análisis modelado: 2020-2024; 2025 queda reservado porque la exposición
  climática disponible termina en 2024.
- Ventana primaria: 2023-2024, que contiene región y comuna explícitas.
- Desenlace primario preespecificado: causa 12, total del sistema circulatorio,
  grupo de 65 años o más.
- Secundarios: circulatorio todas las edades, infarto agudo de miocardio
  (causa 13) y accidente vascular encefálico (causa 14).
- Exploratorios: respiratorio, trastornos mentales y autolesiones.

Cada ZIP se lee por streaming sin extraer el CSV nacional. Se agregan por día y
causa los cinco grupos etarios, y se cuenta el número de establecimientos
informantes. Los totales de distintas categorías no se suman entre sí porque
DEIS publica simultáneamente agregados y subcategorías.

### Geografía y crosswalk

En 2023-2025 la región corresponde al establecimiento informante. Para
2020-2022 se construyó un crosswalk desde las IDs observadas en 2023-2025. Solo
se aceptaron IDs con asignación región-comuna estable; 3 de 668 IDs fueron
excluidas por conflicto.

| Año | Filas relevantes mapeadas | Fechas | Inconsistencias total/edad |
|---:|---:|---:|---:|
| 2020 | 97,88% | 366 | 0 |
| 2021 | 98,77% | 365 | 0 |
| 2022 | 99,44% | 365 | 0 |
| 2023 | 100% | 365 | 0 |
| 2024 | 99,91% | 366 | 0 |
| 2025 | 100% | 365 | 0 |

El crosswalk permite una sensibilidad regional; no convierte la ubicación del
establecimiento en residencia del paciente.

### Exposición

Temperatura diaria Open-Meteo 2015-2024 para 52 comunas, ponderada por población
comunal del Censo 2017. La exposición primaria es el exceso de temperatura
máxima sobre el percentil 95 regional (30,94 °C), promediado sobre lag 0-3.
El umbral se calculó sin usar los desenlaces.

## Modelo

- Poisson con efectos fijos `año-mes × día de semana`.
- `offset = log(establecimientos informantes)`.
- Errores HAC con 7 días de rezago.
- RR reportada por +1 °C en el exceso promedio lag 0-3.
- Sensibilidades: binomial negativa, lag 0, temperatura aparente, años por
  separado, extensión 2020-2024, ventana 2022-2024 y placebo con temperatura
  futura a +7 días.
- Benjamini-Hochberg separado para las familias secundaria y exploratoria.

La puerta exigió al menos 99% de días directos, 50 días de calor, estabilidad
diaria de establecimientos ≥90% de la mediana mensual, convergencia y ausencia
de un placebo futuro más fuerte y significativo. Se observaron 63 días de calor
y una razón mínima de reporte de 98,29%; no hubo motivos de bloqueo.

## Resultados

### Cardiovascular primario

| Modelo | RR por +1 °C | IC 95% | p |
|---|---:|---:|---:|
| Poisson HAC, 2023-2024 | 0,976 | 0,958-0,994 | 0,010 |
| Binomial negativa, 2023-2024 | 0,976 | 0,951-1,001 | 0,056 |
| Extensión 2020-2024 | 0,989 | 0,970-1,009 | 0,285 |
| Sensibilidad 2022-2024 | 0,975 | 0,958-0,993 | 0,006 |
| Placebo futuro +7 días | 0,985 | 0,961-1,010 | 0,251 |

La estimación primaria es pequeña e inversa, pero pierde significancia bajo
binomial negativa y desaparece en la extensión 2020-2024. No se interpreta como
un efecto protector del calor. El resultado defendible es **ausencia de evidencia
robusta de aumento cardiovascular** en este piloto de demanda asistencial.

Los desenlaces cardiovasculares secundarios tampoco mostraron asociación tras
FDR: circulatorio todas las edades RR 0,997; infarto RR 0,959; ACV RR 1,008,
todos con `q=0,775` en la familia secundaria.

### Exploratorios

- Respiratorio: RR 0,904, IC 0,808-1,011, `q=0,077`, con sobredispersión extrema
  (156); no es un resultado estable.
- Trastornos mentales: RR 1,032, IC 1,013-1,051, `q=0,0024`.
- Autolesiones: RR 1,089, IC 1,015-1,168, `q=0,0263`.

Las señales de salud mental y autolesiones no fueron la hipótesis primaria y
solo corrigen una familia exploratoria de tres pruebas. Justifican replicación y
un protocolo específico; no constituyen evidencia causal ni deben publicarse
como hallazgo confirmado.

## Interpretación y limitaciones

- La ubicación es la del establecimiento y refleja derivaciones, oferta y áreas
  de captación hospitalaria.
- La ventana primaria directa solo cubre dos años.
- El período 2020-2022 incluye cambios de demanda y reporte asociados a COVID-19.
- No hay ajuste diario por contaminación atmosférica, humedad, feriados o
  movilidad en este piloto.
- El umbral y los lags son simplificaciones frente a un DLNM completo.
- La aparente asociación inversa cardiovascular puede reflejar comportamiento,
  desplazamiento temporal, confusión residual o variación asistencial.

## Reproducibilidad

Desde la raíz, con `.venv`:

```bash
PYTHONPYCACHEPREFIX=/tmp .venv/bin/python \
  scripts/analysis/analyze_emergency_heat.py
```

El script guarda agregados anuales reanudables bajo `cache/emergency_visits/` y
genera:

- `data/processed/analysis/santiago_emergency_visits_daily_2020_2024.csv`;
- `data/processed/analysis/santiago_heat_emergency_results.csv`;
- `data/processed/analysis/santiago_heat_emergency_summary.json`;
- `figures/santiago_heat_emergency_pilot.png`.

Los resultados y figuras son artefactos generados e ignorados por Git; el
código, las pruebas y este documento constituyen la parte versionada.
