# Metodología: temperatura superficial (LST) ECOSTRESS a 70 m

Capa `climate_lst_ecostress`. Producto: `ECO_L2T_LSTE` **v002**, NASA LP DAAC
(doi:10.5067/ECOSTRESS/ECO_L2T_LSTE.002).

## Qué mide, y qué no

ECOSTRESS mide **temperatura radiativa de superficie** ("piel") con cinco
bandas en el infrarrojo térmico (8–12,5 µm), separando temperatura y
emisividad con el algoritmo TES.

**No es temperatura del aire.** La capa `climate_heat` publica T2M de
ERA5-Land: temperatura del aire a 2 m, a 11.132 m de resolución. Son
cantidades físicas distintas. Sobre superficie construida y en horas de sol la
LST corre varios kelvin por encima de T2M. Las dos capas son complementarias:
`climate_heat` describe el aire que respira la población, `climate_lst_ecostress`
describe el ambiente térmico de las superficies que lo calientan. **Ninguna
sustituye a la otra**, y el visor nunca debe presentarlas como intercambiables.

## Por qué ECOSTRESS y no otro sensor térmico

Dos razones, y la segunda es la que no se puede reemplazar.

1. **Resolución.** 70 m, contra 11.132 m de ERA5-Land y 1.000 m de MODIS
   MOD11A1. Es la única fuente térmica que resuelve la variación intra-comunal.

2. **Muestreo del ciclo diurno.** ECOSTRESS va montado en la Estación Espacial
   Internacional, cuya órbita precesa. Las adquisiciones caen a **horas solares
   locales variables**, incluidas la tarde de máximo calor y la madrugada. Los
   sensores heliosincrónicos no pueden hacer esto: MODIS pasa siempre a
   ~10:30 y ~13:30 (Terra/Aqua) y Landsat a ~10:00. Para isla de calor urbana
   —donde el contraste nocturno es tanto o más informativo que el diurno— esa
   propiedad es el aporte central de la capa.

Earth Engine aloja `ECO_L2T_LSTE`, pero **solo ha ingerido teselas del área
metropolitana de Los Ángeles**, de modo que ninguna ciudad latinoamericana se
puede servir desde ahí. Esta es la única capa del pipeline que va a un
proveedor fuera de GEE. Ver `docs/evaluacion_fuentes_nasa.md`.

## Procedimiento

### 1. Selección de granulos

Búsqueda en el catálogo CMR de NASA por `short_name=ECO_L2T_LSTE`, versión y
bounding box del estudio. Los granulos L2T vienen en teselas MGRS de
109,8 × 109,8 km. Un estudio grande cruza varias teselas y **varias zonas UTM**
—`santiago_communes` abarca 180 × 151 km, unas 12 teselas entre las zonas 18 y
19—, lo que obliga a un reproyectado explícito (paso 4).

### 2. Binning por hora solar local

Para cada granulo se calcula la hora solar local a partir del instante UTC de
adquisición y la longitud representativa del estudio:

```
hora_solar_local = (hora_UTC + longitud / 15) mod 24
```

Se usa el desfase por longitud y **no** la zona horaria civil, porque el
binning es sobre posición del sol, no sobre relojes ni horario de verano. Se
usa la longitud del estudio y no el centroide de cada tesela, para que todas
las teselas de una misma pasada caigan en la misma ventana: si no, el mosaico
quedaría cosido con regímenes diurnos distintos.

Ventanas por defecto:

| Ventana | Horas solares | Para qué |
|---|---|---|
| `day` | 10–16 | Máximo de isla de calor superficial diurna |
| `night` | 22–5 | Isla de calor nocturna |

Las horas entre ventanas se descartan a propósito: un promedio en hora de
transición mezcla régimen de calentamiento con régimen de enfriamiento.

### 3. Enmascarado

Se descarta un píxel si cae en cualquiera de estos casos:

- valor de relleno o no finito;
- banda `cloud` marcada;
- banda `water` marcada;
- bits obligatorios de calidad (0–1) de la banda `QC` por sobre el nivel
  configurado (`0` = mejor, `1` = nominal);
- temperatura fuera del rango plausible −50 °C a 80 °C, que atrapa
  recuperaciones malas que el QC no marcó.

### 4. Reproyectado a la grilla del estudio

Cada granulo enmascarado se reproyecta a una grilla fija definida en el CRS
métrico del estudio, **a 70 m**. El reproyectado aquí no degrada resolución
—preserva los 70 m del producto— y es la única forma de acumular teselas que
llegan en zonas UTM distintas. Se usa vecino más cercano: una vez removidos
nube y agua, la LST es un campo enmascarado y discontinuo, y una interpolación
bilineal arrastraría bordes enmascarados hacia píxeles válidos.

### 5. Reducción por acumuladores en streaming

Los granulos se transmiten y se pliegan al vuelo en acumuladores por píxel
(suma, conteo y máximo por ventana solar). **No se almacenan los granulos.**
La razón es de volumen medido, no de estilo: sobre el footprint de
`santiago_communes` el CMR reporta ~400 granulos por mes, y cachear recortes
por granulo llegaría a cientos de GB dentro de un repositorio sincronizado con
Dropbox.

Los acumuladores se guardan como checkpoint `.npz` cada N granulos, de modo que
una corrida interrumpida se reanuda sin volver a descargar. La escritura es
atómica para que un checkpoint truncado no envenene el reinicio.

**Los percentiles por píxel no se acumulan**, y es una decisión deliberada:
requerirían un histograma por píxel (del orden de terabytes a esta resolución y
extensión). Los percentiles se calculan entre los píxeles de cada unidad
espacial al momento de agregar, a partir del compuesto, que además es la forma
estándar de reportar estadística de isla de calor superficial.

### 6. Salidas

Un COG con, por ventana solar, tres bandas:

| Banda | Contenido |
|---|---|
| `lst_<ventana>_mean_c` | Media de cielo despejado, °C |
| `lst_<ventana>_max_c` | Máximo observado, °C |
| `lst_<ventana>_n_obs` | Conteo de observaciones válidas |

La banda de conteo es parte del producto, no un extra: sin ella no se puede
distinguir un píxel frío de un píxel poco observado.

Además se cachea una fila por granulo y por unidad espacial (media, máximo,
conteo de píxeles). Es diminuta y preserva el registro a nivel de observación,
de modo que el producto tabular se puede redefinir sin volver a descargar nada.

## Dónde vive el código

| Pieza | Archivo |
|---|---|
| Acceso al proveedor (CMR, lectura, máscara, grilla, acumuladores) | `src/exposome/climate/fetch_ecostress.py` |
| Orquestación de la capa (búsqueda → pliegue → COG + metadata) | `src/exposome/climate/ecostress_layer.py` |
| CLI | `scripts/run_climate_lst_ecostress.py` |
| Registro como runner in-process | `src/exposome/runners.py`, `config/runner_parity.yaml` |

La orquestación vive en `src/exposome/` y no en el script porque el catálogo
exige que toda capa tenga un runner importable (`tests/test_runners.py`), y
porque así la lógica es testeable sin subproceso.

## Precisión reportada

La validación de referencia (Hulley et al. 2022, IEEE TGRS,
doi:10.1109/TGRS.2021.3079879) reporta contra estaciones terrestres en 14
sitios globales, con 1.139 observaciones de cielo despejado entre agosto de
2018 y marzo de 2020:

- RMSE **1,07 K**
- MAE **0,40 K**
- R² **> 0,988**

El mismo trabajo documenta un **sesgo frío por debajo de 295 K** atribuido a
calibración. El producto es entonces más confiable en el rango cálido, que es
justamente el de interés para isla de calor.

## Limitaciones

- **No es temperatura del aire** (ver arriba). Es la confusión más costosa
  posible con esta capa.
- **Solo cielo despejado.** En ciudades de nubosidad persistente el número de
  adquisiciones utilizables puede caer a un dígito anual. Bajo la garúa del
  Pacífico, Lima registra 76 granulos en 2024 contra 324 de Santiago, *antes*
  de enmascarar nubes; puede resultar un hueco permanente y documentado, no un
  error a depurar.
- **Huecos del instrumento.** El proveedor documenta pérdidas observacionales
  permanentes entre 2018 y 2023 por fallas de la unidad de almacenamiento
  masivo, bandeo en la banda 4 (febrero 2020) y operación en modo TES de 3
  bandas entre mayo 2019 y abril 2023. Obstrucciones de los paneles solares de
  la Estación afectan la calidad y su campo de metadatos fue poco confiable
  antes de octubre de 2024.
- **Serie corta.** Empieza en 2019 (primer año completo). Es más corta que las
  series climáticas desde 2015 y **no debe rellenarse** para igualarlas.
- **Serie anual no garantizada.** Por ADR 0007 una serie anual es atómica: si
  se declara `required_for_production: true`, cada año debe publicar su propio
  COG o falla la publicación completa. Dado que los conteos por año son
  desparejos, la capa sale como compuesto de período
  (`required_for_production: false`) y solo se promueve a serie anual después
  de validar conteos de cielo despejado por ciudad y año.

## Verificación al correr

Tres chequeos que sí discriminan, en orden:

1. **Contra `climate_heat`, con umbral falsable.** En ventana de verano y sobre
   superficie construida, `LST_diurna − T2M` debe caer aproximadamente entre
   **+5 y +15 K**, y la nocturna comprimirse hacia **0–3 K**. Si el diurno
   vuelve en ~1 K, cero o negativo, es un error en la máscara o en la
   conversión de kelvin a °C, no un hallazgo: no publicar.
2. **Contra la literatura de isla de calor de la ciudad.** Para Santiago, el
   contraste nocturno debe ser más intenso en el sector oriente, donde coincide
   con nivel socioeconómico alto y mayor superficie verde. Es un anclaje
   externo, no autoconsistencia.
3. **Conteo de observaciones por píxel.** Revisar que no haya huecos
   sistemáticos por nubosidad antes de declarar publicable cualquier año.
