# Protocolo de extensión de controles negativos annual-v2.1

## Objetivo

Esta extensión agrega modelos BYM2 del desenlace de control negativo
`injury_poisoning` para las ocho exposiciones primarias de annual-v2.0 y sus dos
alineaciones temporales. No modifica, copia ni vuelve a vincular las 142 trazas
congeladas de v2.0.

## Registro cerrado

- Línea base exigida: fingerprint
  `452459e12737f8c4ce135155c0551707e53d1701ae6c31ecef9cd1fd7f28bc38`.
- Exposiciones: PM2.5, ALAN, calor, verde, precipitación, viento, incendios y
  metales pesados.
- Tiempos: mismo año y rezago de un año.
- Desenlace: lesiones y envenenamientos (CIE-10 S00–T98).
- Total: 16 modelos nuevos.

Los modelos usan el panel materializado, la geometría, la ventana primaria, las
reglas de estimabilidad, el modelo binomial negativo BYM2, los diagnósticos, el
ROPE y PSIS-LOO de v2.0. La semilla de la extensión y todo el código transitivo
forman parte de su fingerprint propio.

## Regla del control bayesiano

Un control se considera limpio si el modelo pasa diagnósticos y no satisface al
mismo tiempo las dos condiciones de apoyo direccional: probabilidad posterior
de dirección al menos 0,975 e HDI 95% completamente a un lado de RR=1. Un
modelo ausente o con diagnósticos fallidos no se considera limpio.

La extensión es ecológica, no causal, y sólo sirve como gate de robustez para
las asociaciones primarias emparejadas por exposición y tiempo.

## Finalización

`finalize` debe rechazar la corrida antes de escribir resultados si no existen
exactamente los 16 sidecars registrados, si alguno no termina con estado `ok`,
si una traza no cumple su contrato NetCDF o si su SHA-256 difiere del sidecar.

