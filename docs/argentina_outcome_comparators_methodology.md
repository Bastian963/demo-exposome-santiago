# Resultados ecológicos AMBA: suicidios y muertes viales

## Propósito

Estos productos son resultados ecológicos territoriales para contrastar, en
una etapa posterior, el exposoma de AMBA. No son exposomas, no se incorporan
al master ni al EBI. La webapp publica mapas de tasas agregadas y separadas de
las exposiciones; no publica microdatos ni asociaciones que no hayan aprobado
la compuerta estadística.

## Fuentes y conteo

- **Suicidios:** SAT-SS 2017-2024. La base contiene una fila por persona
  suicida; el conteo es `tipo_persona_id` único. `id_hecho` se usa únicamente
  para diagnosticar la diferencia entre hechos y víctimas.
- **Muertes viales:** SAT-MV 2017-2024. Se filtra `tipo_persona = Víctima` y
  luego se cuentan `tipo_persona_id` únicos. Filas de imputados no participan.
- **Denominadores:** estimaciones INDEC por comuna/partido; serie 2010-2025
  para 2017-2021 y serie basada en Censo 2022 para 2022-2024.

La salida interna conserva conteos y tasas anuales, además de un acumulado
2017-2024 calculado como muertes acumuladas por población-persona-año
acumulada. El artefacto web contiene solo la tasa acumulada y ventanas móviles
de tres años (2017–2019 a 2022–2024). Una ventana con menos de cinco eventos se
publica como nula; el recuento que motiva la supresión no se exporta.

## Espacio, privacidad y límites

Se agregan 15 comunas de CABA y 40 partidos bonaerenses. Los registros
`Departamento sin determinar` se excluyen del indicador y permanecen en los
diagnósticos de conservación. Los diagnósticos también separan víctimas
mapeadas y no mapeadas por año.

No se exportan coordenadas, calles, identificadores de hechos o personas,
sexo, edad ni modalidades. Las coordenadas de SAT-MV no se usan porque su
manual las define como aproximadas a la localidad/departamento reportado.

Un cero significa que no hay una víctima registrada en el SAT para esa
unidad-año; no demuestra ausencia real de mortalidad ni cobertura homogénea.
Las tasas no son estimaciones clínicas, causales ni ajustadas por edad.

## Compuerta para asociaciones

Un resultado descriptivo no se convierte automáticamente en una asociación
publicable. La liberación exige, como mínimo:

- covariables Censo 2022 de edad, sexo, densidad y privación, más indicador de
  CABA;
- tasas estandarizadas por edad y sexo;
- modelo de conteo con offset poblacional, error robusto y revisión de
  sobredispersión;
- VIF aceptable, corrección Benjamini–Hochberg y diagnóstico espacial de
  residuos;
- lenguaje explícitamente ecológico, sin inferencia causal ni individual.

En el estado actual faltan covariables censales materializadas y
estandarización por edad/sexo, por lo que la app muestra el control de calidad
cerrado y no una estimación de efecto.
