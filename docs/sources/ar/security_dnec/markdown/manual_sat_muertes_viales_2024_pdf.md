# manual_sat_muertes_viales_2024

- Original local: `data/raw/ar/security_dnec/download_2026-07-12/sat/pdf/manual_sat_muertes_viales_2024.pdf`
- Extracted with: `pdftotext -layout`
- PDF pages: 51
- Note: this is a text extraction for review; consult the original PDF for layout-specific ambiguity.


## Página 1

Manual de usuario de la base

Sistema de Alerta Temprana

          Muertes Viales

              (SAT -MV)




  Dirección Nacional de Estadística Criminal
      Ministerio
  Dirección      de Seguridad
            Nacional          de la Nación
                      de Estadística Criminal
     Ministerio de Seguridad de la Nación


## Página 2

Índice


Introducción                                       3
Bases de datos SAT MV                             4
   Características de la base de datos            4
   Cómo utilizar la base de datos                 4
   Criterios de consistencia                       5
Diccionario de variables                          6
   Definiciones de variables Base SAT MV          6
Anexos                                            25
 Anexo I –Definiciones de variables categóricas   25
 Anexo II – Códigos por Jurisdicción              34
 Anexo III – Códigos por departamento             35




                                                   2


## Página 3

Introducción


El Ministerio de Seguridad de la Nación, a través de la Dirección Nacional de
Estadística Criminal, pone a disposición los registros administrativos del
Sistema de Alerta Temprana de Muertes viales (SAT-MV) del Sistema Nacional
de Información Criminal (SNIC)1. De esta forma, a partir de la difusión y la
mejora en el acceso a la información sobre la temática, se busca promover el
desarrollo de nuevas investigaciones y contribuir al diseño de políticas
públicas basadas en evidencia, además de promover la transparencia en la
gestión, acorde a la Ley Nro. 27.275 de Derecho de Acceso a la Información
Pública y Gobierno Abierto.

En particular, el Sistema de Alerta Temprana de Muertes en Accidentes Viales
releva a nivel de microdato (a partir de la información recabada en sumarios
o preventivos policiales) de los hechos de tránsito o accidentes viales con
víctimas fatales. Permite, a partir de distintas variables, conocer las
características de los hechos y de los involucrados (tanto víctimas como
inculpados).

Los principales datos que releva son: fecha, hora y lugar del hecho, modo de
producción,    motivo     que    origina   el   registro,   condiciones    climáticas,
características del semáforo, edad, sexo y tipo de vehículo de las personas
involucradas. Cada uno de estas variables se encuentra asociada al código del
departamento, seccional y localidad donde ocurrió el hecho. Las bases SAT se
suman a las bases del SNIC actualmente disponibles en la web2.




1
  Para mayor información se recomienda leer el Documento metodológico del Sistema
nacional de información criminal (SNIC) disponible en el sitio web:
https://www.argentina.gob.ar/seguridad/estadisticascriminales
2
   https://www.argentina.gob.ar/seguridad/estadisticascriminales
                                                                                    3


## Página 4

Bases de datos SAT MV

¿Para qué sirve la base SAT-MV?

A partir de los microdatos de las bases SAT-MV es posible calcular la cantidad
de víctimas fatales en incidentes viales y conocer características de las
personas involucradas en el hecho (ver unidad de análisis). También, contiene
información acerca del hecho, que permite realizar una caracterización
general del lugar, momento y condiciones en las que se produjo. Releva, entre
otras cosas: condiciones climáticas, características de los vehículos (tanto del
inculpado como de la víctima), modo de producción del hecho, lugar del
hecho.




Características de la base de datos

La base de datos cuenta con un número identificador por cada hecho. En la
misma base se incluyen los registros correspondientes a todas las víctimas y a
todos los inculpados identificados en cada hecho. Para trabajar con esta base
de datos se debe tener en cuenta la dimensión de la misma ya que contiene
37.533 registros y contiene las variables de caracterización del hecho, de la
víctima y del inculpado. Es recomendable utilizar softwares específicos para la
gestión y análisis de datos.




Cómo utilizar la base de datos

Para utilizar la base SAT-MV es necesario contar con conocimientos de
procesamiento de bases de datos o tablas dinámicas y de realización de filtros.
La base de datos cuenta con un identificador del hecho, para cada hecho se
encuentran en la misma base los registros correspondientes a las víctimas y a
los inculpados (uno/a por fila). Por lo tanto, un mismo hecho se repite para
cada víctima y cada inculpado/a. Para calcular la cantidad de víctimas es
necesario filtrar a los inculpados de la base de datos, es posible contabilizar la

                                                                                4


## Página 5

cantidad de víctimas e inculpados utilizando la variable tipo_persona.
Además, cada variable es exclusiva para un tipo de persona, por lo tanto, tiene
etiquetadas como No corresponde las correspondientes al otro tipo de
persona. Por ejemplo, para calcular la cantidad de víctimas según sexo se
deben filtrar las filas en las que el valor es No corresponde, ya que esas filas
corresponden a los inculpados. Para conocer la cantidad de hechos, se debe
contar una única vez cada ID de hecho.




Criterios de consistencia

      Los datos del SAT MV deben cumplir con criterios de consistencia
según el tipo de variable, los criterios se encuentran explicados en el
diccionario de variables.




                                                                              5


## Página 6

Diccionario de variables
En esta sección se presenta la descripción detallada de las variables (o
campos) que contiene la base usuaria SAT-MV. Se separan en grupos según
correspondan al hecho, víctima o inculpados.



Definiciones de variables Base SAT MV

   1.   id_hecho

Nombre de la variable     id_hecho

Descripción               Código de identificación del hecho

Tipo de variable          Numérica

Comentarios y             Permite identificar a las personas involucradas
                          en un mismo hecho: víctimas e inculpados (o
advertencias
                          involucrados). Al ser identificador no contiene
                          valores perdidos. A partir de esta variable se
                          pueden calcular la cantidad de hechos y de
                          víctimas.



   2. federal
Nombre de la variable     federal
Descripción               Indica si el dato es reportado por una fuerza
                          federal o provincial.
Tipo de variable          Categórica
Valores con los que        Código       Descripción
aparece
                                0      No
                                1      Si
Comentarios y             Permite identificar los hechos que fueron
advertencias              reportados por la fuerza provinciales y las fuerzas
                          federales (GNA, PSA, PFA, PNA y SPF).




                                                                                6


## Página 7

3. tipo_persona
Nombre de la variable   tipo_persona
Descripción             Tipo de persona: víctima o inculpado
Tipo de variable        Categórica
Valores con los que      Código Descripción
aparece                    1     Imputado
                           2     Víctima
Comentarios y           Generada a partir del campo tipo_persona_id.
advertencias


  4. tipo_persona_id
Nombre de la variable   tipo_persona_id
Descripción             Código identificador de la persona involucrada
                        en el hecho
Valores con los que     Por ejemplo:
aparece
                        Imputado idRegistro 13501
                        Víctima idRegistro 16646
Comentarios y           Permite diferenciar en la base a las víctimas y a
advertencias            los inculpados.


  5. provincia_id
Nombre de la variable   provincia_id
Descripción             Código de la provincia donde ocurrió el hecho
Tipo de variable        Categórica
Valores con los que     Ver Anexo II.
aparece
Comentarios y           Los códigos coinciden con los de INDEC, es útil
advertencias            para realizar cruces con bases de datos de
                        población y otras bases de datos que utilicen la
                        codificación de INDEC.


  6. provincia_nombre
Nombre de la variable   provincia_nombre
Descripción             Provincia donde ocurrió el hecho
Tipo de variable        Texto




                                                                            7


## Página 8

7. departamento_id
Nombre de la variable   departamento_id
Descripción             Código de 5 cifras para el departamento y la
                        provincia.
Tipo de variable        Texto
Valores con los que     Ver Anexo III.
aparece
Comentarios y           Cada jurisdicción se divide en departamento, de
advertencias            acuerdo a su división política. En CABA,
                        corresponde a Comunas y en Provincia de
                        Buenos Aires corresponde a Partidos.
                        En general, las Fuerzas Federales registran sus
                        datos en la categoría sin determinar, ya que la
                        información se reporta desde sus unidades
                        operativas cuyo alcance territorial no coincide
                        con la división política de cada jurisdicción.
                        Generado a partir de los códigos de provincia y
                        departamento. Los primeros 2 dígitos
                        corresponden a la provincia y los últimos 3 al
                        departamento. Cuando el departamento es sin
                        determinar el código es el número de la
                        provincia + 999.




  8. departamento_nombre
Nombre de la variable   departamento_nombre
Descripción             Nombre del departamento geográfico donde
                        ocurrió el hecho.
Tipo de variable        Texto


  9. localidad_id
Nombre de la variable   Localidad_id
Descripción             Código de la localidad del hecho
Tipo de variable        Texto
Comentarios y           La localidad sin determinar tiene el prefijo 999-
advertencias            999. Para algunas provincias los códigos de la
                        localidad coinciden con los de INDEC.




                                                                            8


## Página 9

10. localidad_nombre
    Nombre de la variable         Localidad_nombre
    Descripción                   Nombre de la localidad donde ocurrió el hecho
    Tipo de variable              Texto
    Comentarios y                 En general, las Fuerzas Federales registran sus
    advertencias                  datos en la categoría Localidad sin determinar,
                                  ya que la información se reporta desde sus
                                  unidades operativas cuyo alcance territorial no
                                  coincide con la división política de cada
                                  jurisdicción.


       11. latitud
    Nombre de la variable         Latitud
    Descripción                   Latitud del hecho
    Tipo de variable              Numérica
    Comentarios y                 La latitud corresponde a la coordenada
    advertencias                  geográfica del hecho calculada mediante la
                                  información de calle, altura, intersección,
                                  localidad, departamento y provincia reportada,
                                  mediante la utilización de la función geocoding
                                  del paquete “tidygeocoder” del software R3,
                                  desarrollado por Jesse Cambon, Diego
                                  Hernangómez, Christopher Belanger y Daniel
                                  Possenriede. El mismo se basa en los servicios de
                                  Nominatim, que utiliza datos de OpenStreetMap
                                  para encontrar ubicaciones en la Tierra por
                                  nombre y dirección (codificación geográfica).
                                  Por ese motivo, la coordenada geográfica
                                  brindada es una aproximación a la coordenada
                                  real del lugar del hecho y puede no ser exacta.


       12. longitud
    Nombre de la variable         longitud
    Descripción                   Longitud del hecho.
    Tipo de variable              Numérica
    Comentarios y                 La latitud corresponde a la coordenada
    advertencias                  geográfica del hecho calculada mediante la
                                  información de calle, altura, intersección,
                                  localidad, departamento y provincia reportada,
                                  mediante la utilización de la función geocoding
                                  del paquete “tidygeocoder” del software R4,

3
    https://jessecambon.github.io/tidygeocoder/
4
    https://jessecambon.github.io/tidygeocoder/
                                                                                      9


## Página 10

desarrollado por Jesse Cambon, Diego
                        Hernangómez, Christopher Belanger y Daniel
                        Possenriede. El mismo se basa en los servicios de
                        Nominatim, que utiliza datos de OpenStreetMap
                        para encontrar ubicaciones en la Tierra por
                        nombre y dirección (codificación geográfica).
                        Por ese motivo, la coordenada geográfica
                        brindada es una aproximación a la coordenada
                        real del lugar del hecho y puede no ser exacta.


  13. anio
Nombre de la variable   anio
Descripción             Año de ocurrencia del hecho.
Tipo de variable        Numérica
Comentarios y           Valor correspondiente a cada año calendario al
advertencias            que correspondan los hechos reportados. Se
                        valida con la fecha del hecho.


  14. mes
Nombre de la variable   mes
Descripción             Mes de ocurrencia del hecho.
Tipo de variable        Numérica
Comentarios y           Se valida con la fecha del hecho. Valores con los
advertencias            que aparece: 1 a 12.


  15. fecha_hecho
Nombre de la variable   fecha_hecho
Descripción             Fecha de ocurrencia del hecho
Tipo de variable        Fecha. Formato fecha: dd/mm/aaaa.
Comentarios y           Se valida con las variables anio y mes.
advertencias


  16. hora_hecho
Nombre de la variable   hora_hecho
Descripción             Hora del hecho
Tipo de variable        Texto
Valores con los que     Formato hora: hh:mm:ss, desde 00:00:00 a
aparece                 23:59:59.



                                                                            10


## Página 11

Comentarios y              Los registros sin dato tienen hora 11:11:11. En
advertencias               algunos casos la hora 00:00:00 podría indicar sin
                           dato, debido a la inusual frecuencia de los
                           registros en ese horario. Se sugiere revisar este
                           dato por provincia y año.


  17. calle_nombre
Nombre de la variable      calle_nombre
Descripción                Nombre de la calle donde sucedió el hecho
Tipo de variable           Texto
Comentarios y              Los datos registrados en esta variable se
advertencias               encuentran sin modificación es decir que no se
                           han realizado modificaciones a lo que ingresó
                           cada fuerza en este campo, por lo que una
                           misma calle puede estar escrita de manera
                           diferente, por ejemplo, Avda., Av., Avenida.
                           También puede aparecer texto que haga
                           referencia a un faltante de información (s/d, sin
                           dato).


  18. calle_altura
Nombre de la variable      calle_altura
Descripción                Altura de la calle donde sucedió el hecho
Tipo de variable           Numérica
Comentarios y              Esta información no se ha validado con respecto
advertencias               a otras variables de ubicación geográfica.


  19. calle_interseccion
Nombre de la variable      calle_interseccion
Descripción                Corresponde cuando el hecho haya ocurrido en
                           una intersección de calles
Tipo de variable           Categórica
Valores con los que         Código        Descripción
aparece                         1         Sí
                                2         No
                               99         Sin determinar




                                                                               11


## Página 12

20. calle_interseccion_nombre
Nombre de la variable   calle_interseccion_nombre
Descripción             Nombre de la calle de intersección donde ocurrió
                        el hecho
Tipo de variable        Texto
Comentarios y           Los datos registrados en esta variable se
advertencias            encuentran sin modificación es decir que no se
                        han realizado modificaciones a lo que ingresó
                        cada fuerza en este campo, por lo que una
                        misma calle puede estar escrita de manera
                        diferente, por ejemplo, Avda., Av., Avenida.
                        También puede aparecer texto que haga
                        referencia a un faltante de información (s/d, sin
                        dato).


  21. semaforo_estado
Nombre de la variable   semaforo_estado
Descripción             Estado del semáforo
Tipo de variable        Categórica
Valores con los que       Código     Descripción
aparece                      1       Funcionaba
                             2       No funcionaba
                             3       Sin semáforo
                            4        Intermitente
                            99       Sin Determinar




  22. tipo_lugar
Nombre de la variable   tipo_lugar
Descripción             Tipo de lugar donde ocurrió el hecho
Tipo de variable        Categórica
Valores con los que
aparece                  Código       Descripción
                             1        Calle
                             2        Ruta Nacional
                             3        Ruta Provincial
                                      Autopista
                                4     Nacional
                                      Autopista
                                5     Provincial
                                6     Autovía

                                                                            12


## Página 13

99       Sin determinar
Comentarios y           . Cabe destacar que esta variable no se ha
advertencias            validado con el campo calle y altura. Consultar el
                        Anexo I para ver la definición de cada categoría.


  23. modo_produccion_hecho
Nombre de la variable   modo_produccion_hecho
Descripción             Modo de producción del hecho
Tipo de variable        Categórica
Valores con los que      Código      Descripción
aparece                       1      Colisión vehículo / persona
                              2      Colisión vehículo / vehículo
                              3      Colisión vehículo / objeto
                             4       Vuelco / despistes
                              5      Otro (especificar)
                             99      Sin determinar
Comentarios y           Se validó con las variables clase de víctima,
advertencias            vehículo de la víctima/ inculpado y edad de la
                        víctima/ inculpado. Consultar el Anexo I para ver
                        la definición de cada categoría.


  24. modo_produccion_hecho_ampliada
Nombre de la variable   modo_produccion_hecho_ampliada
Descripción             Modo de producción del hecho – categorías
                        adicionales
Tipo de variable        Texto
Valores con los que     Accidente con maquinaria agrícola
aparece                 Aplastamiento
                        Caída del Ocupante
                        Caída del vehículo en movimiento
                        Colisión múltiple
                        Colisión vehículo / Tracción a sangre
                        Colisión vehículo / animal
                        Colisión vehículo / objeto
                        Colisión vehículo / persona
                        Colisión vehículo / vehículo
                        Colisión vehículo / vehículo estacionado
                        Derrape
                        Desperfecto mecánico
                        Desprendimiento
                        Desprendimiento/ Aplastamiento
                        explosión / incendio
                        Otro
                        Vuelco / despistes

                                                                             13


## Página 14

Sin determinar
Comentarios y           Se validó con las variables clase de víctima,
advertencias            vehículo de la víctima/ inculpado y edad de la
                        víctima/ inculpado. Creada posteriormente a la
                        carga a partir de la información cargada por las
                        fuerzas de seguridad en los campos abiertos. Con
                        respecto a la publicación anterior, los casos de
                        aplastamiento se incluyeron dentro de
                        Desprendimiento/ Aplastamiento. Los casos de
                        caída del vehículo en movimiento se incluyeron
                        dentro de la categoría caída del ocupante.


  25. modo_produccion_hecho_otro
Nombre de la variable   modo_produccion_hecho_otro
Descripción             Descripción de otro modo de producción del
                        hecho
Tipo de variable        Texto
Comentarios y           Se contesta sólo en el caso de haber completado
advertencias            otro en el campo modo de producción del hecho.
                        Esta variable se ha adecuado para el uso
                        estadístico.


  26. clima_condicion
Nombre de la variable   clima_condicion
Descripción             Condiciones climáticas presentes al momento
                        del siniestro
Tipo de variable        Categórica
Valores con los que      Código      Descripción
aparece                     1        Bueno
                            2        Nublado
                            3        Lluvia
                            4        Llovizna
                            5        Nieve
                            6        Granizo
                            7        Otra condición
                           99        Sin determinar



  27. clima_otro
Nombre de la variable   clima_otro
Descripción             Descripción de otras condiciones climáticas


                                                                       14


## Página 15

Tipo de variable        Texto
Comentarios y           Se contesta sólo en el caso de haber completado
advertencias            otro en el campo clima_condicion. Esta variable
                        se ha adecuado para el uso estadístico.


  28. motivo_origen_registro
Nombre de la variable   motivo_origen_registro
Descripción             Motivo que origina el registro del hecho
Tipo de variable        Categórica
Valores con los que      Código      Descripción
aparece                     1        Denuncia particular
                            2        Intervención policial
                            3        Orden Judicial
                            4        Otros (especificar)
                           99        Sin determinar



  29. motivo_origen_registro_otro
Nombre de la variable   motivo_origen_registro_otro
Descripción             Descripción de otro motivo que origina el
                        registro del hecho
Tipo de variable        Texto
Comentarios y           Se contesta sólo en el caso de haber completado
advertencias            otro en el campo motivo_origen_registro. Esta
                        variable se ha adecuado para el uso estadístico.


  30. victima_sexo
Nombre de la variable   victima_sexo
Descripción             Sexo de la víctima
Tipo de variable        Categórica
Valores con los que      Código      Descripción
aparece                      0       No corresponde
                              1      Femenino
                              2      Masculino
                             99      Sin determinar
Comentarios y           La categoría no corresponde refiere a los
advertencias            registros de los inculpados y para las frecuencias
                        de las variables de las víctimas no deben tomarse
                        en cuenta.


                                                                         15


## Página 16

31. victima_tr_edad
Nombre de la variable   victima_tr_edad
Descripción             Edad de la víctima en tramos
Tipo de variable        Categórica
Valores con los que
                         Código      Descripción
aparece
                            -99      No corresponde
                             -1      Sin determinar
                              1      4 o menos
                              2      9-5
                              3      10-14
                             4       15-19
                              5      20-24
                              6      25-29
                              7      30-34
                              8      35-39
                              9      40-44
                             10      45-49
                             11      50-54
                             12      55-59
                             13      60-64
                             14      65-69
                             15      70-74
                             16      75-79
                             17      80-84
                             18      85-89
                             19      más de 90
Comentarios y           Se realizó la validación de la edad con la variable
advertencias            victima_clase, en los casos que como clase
                        registra conductor y edad 0 se imputa a valor
                        perdido. Sin embargo, no se registraron casos
                        con edad 0.
                        Además, por la inusual frecuencia de los datos,
                        aquellos registros que figuraban con edad 99
                        fueron imputados como -1 (sin determinar).
                        La categoría no corresponde refiere a los
                        registros de los inculpados y para las frecuencias
                        de las variables de las víctimas no deben tomarse
                        en cuenta.




                                                                              16


## Página 17

32. victima_18_años_o_mas
Nombre de la variable      victima_18_años_o_mas
Descripción                Edad de la víctima- 18 años o más
Tipo de variable           Categórica
Valores con los que
aparece                     Código    Descripción
                               0      No corresponde
                                1     Sí
                                2     No
                               99     Sin determinar
Comentarios y              Generada a partir de la variable Edad que es
advertencias               ingresada por las fuerzas de seguridad.




  33. victima_clase
Nombre de la variable      victima_clase
Descripción                Clase de víctima
Tipo de variable           Categórica
Valores con los que         Código      Descripción
aparece                         0       No corresponde
                                1       Conductor
                                2       Acompañante
                                3       Pasajero
                                4       Peatón
                                5       Otro
                               99       Sin determinar
Comentarios y              Consultar el Anexo I para ver la definición de
advertencias               cada categoría.
                           La categoría No corresponde refiere a los
                           registros de los inculpados y para las frecuencias
                           de las variables de las víctimas no deben tomarse
                           en cuenta.




  34. victima_clase_otro
Nombre de la variable      victima_clase_otro
Descripción                Descripción de otra clase de victima
Tipo de variable           Texto

                                                                            17


## Página 18

Comentarios y            Se contesta sólo en el caso de haber completado
advertencias             otro en el campo victima_clase. Esta variable se
                         ha adecuado para el uso estadístico.


  35. victima_vehiculo
Nombre de la variable    victima_vehiculo
Descripción              Tipo de vehículo de la victima
Tipo de variable         Categórica
Valores con los que       Código      Descripción
aparece                      0        No corresponde
                                      Micro larga
                               1      distancia
                              2       Colectivo
                              3       Camión
                              4       Camioneta
                              5       Automóvil
                              6       Motocicleta
                              7       Ciclomotor
                              8       Bicicleta
                              9       Tren
                             10       Otro
                              11      Peatón
                             99       Sin determinar
Comentarios y            Consultar el Anexo I para ver la definición de
advertencias             cada categoría.
                         La categoría No corresponde refiere a los
                         registros de los inculpados y para las frecuencias
                         de las variables de las víctimas no deben tomarse
                         en cuenta.


  36. victima_vehiculo_ampliado
Nombre de la variable    victima_vehiculo_ampliado
Descripción              Tipo de vehículo de la víctima – categorías
                         adicionales
Tipo de variable         Texto
Valores con los que      Acoplado
aparece                  Ambulancia
                         Arenero/Karting/Buggy
                         Autobomba
                         Automóvil
                         Bicicleta
                         Camioneta
                         Camión

                                                                          18


## Página 19

Ciclomotor
                        Colectivo
                        Cuatriciclo / Triciclo
                        Grúa
                        Maquinaria
                        Micro larga distancia
                        Motocicleta
                        Sin vehículo
                        Tracción a sangre
                        Tractor
                        Tren
                        Otro
                        Sin determinar
                        No corresponde
Comentarios y           Creada posteriormente a la carga a partir de la
advertencias            información cargada por las fuerzas de seguridad
                        en el campo abierto victima_vehiculo_otro.
                        En el caso de que la clase de la víctima es peatón
                        y en el vehículo estaba cargado como sin
                        determinar u otro en esta variable se encuentra
                        en la categoría sin vehículo.
                        La categoría No corresponde refiere a los
                        registros de los inculpados y para las frecuencias
                        de las variables de las víctimas no deben tomarse
                        en cuenta.


  37. victima_vehiculo_otro
Nombre de la variable   victima_vehiculo_otro
Descripción             Detalle de otro vehículo de victima
Tipo de variable        Texto
Comentarios y           Se completa en los casos que se selecciona otro
advertencias            en vehículo de la víctima. Esta variable se ha
                        adecuado para el uso estadístico.


  38. victima_identidad_genero
Nombre de la variable   victima_identidad_genero
Descripción             Identidad de género de la víctima
Tipo de variable        Categórica
Valores con los que      Código Descripción
aparece                    1    Varón
                           2    Mujer
                           3    Varón Trans
                           4    Mujer trans/travestis
                           5    Otro (especificar)
                                                                          19


## Página 20

99    Sin determinar
Comentarios y             De acuerdo a la Ley de Identidad de Género Nro.
advertencias              26.743, se entiende por identidad de género: “la
                          vivencia interna e individual del género tal como
                          cada persona la siente, la cual puede
                          corresponder o no con el sexo asignado a
                          momento del nacimiento, incluyendo la vivencia
                          personal del cuerpo. Esto puede involucrar la
                          modificación de la apariencia o la función
                          corporal a través de medios farmacológicos,
                          quirúrgicos o de otra índole, siempre que ello sea
                          libremente”.
                          Consultar el Anexo I para ver la definición de
                          cada categoría.


  39. inculpado_sexo
Nombre de la variable     inculpado_sexo
Descripción               Sexo del inculpado
Tipo de variable          Categórica
Valores con los que        Código     Descripción
aparece                        0      No corresponde
                               1      Femenino
                               2      Masculino
                              99      Sin determinar
Comentarios y             La categoría No corresponde refiere a los
advertencias              registros de las víctimas, por lo tanto, para las
                          frecuencias de las variables de las víctimas no
                          deben tomarse en cuenta.




  40. inculpado_tr_edad
Nombre de la variable     inculpado_tr_edad
Descripción               Edad de la persona involucrada en el siniestro (en
                          tramos)
Tipo de variable          Categórica
Valores con los que        Código    Descripción
aparece                              No
                             -99     corresponde
                                     Sin
                              -1     determinar
                              2      Menor a 10

                                                                              20


## Página 21

3    10-14
                            4     15-19
                             5    20-24
                             6    25-29
                             7    30-34
                             8    35-39
                             9    40-44
                            10    45-49
                            11    50-54
                            12    55-59
                            13    60-64
                            14    65-69
                            15    70-74
                            16    75-79
                            17    80-84
                            18    85-89
                            19    más de 90
Comentarios y           Generada a partir de la variable edad del
advertencias            inculpado (en años).
                        Debido a la inusual frecuencia, en aquellos
                        registros en los que la edad del inculpado era 99
                        fueron imputadas como -1 (Sin determinar). Así
                        mismo, aquellos registros con edades menores a
                        9 años fueron imputados a “-1” (Sin determinar).
                        Se validó con las variables
                        modo_produccion_hecho y vehiculo_victima.
                        La categoría “no corresponde” refiere a los
                        registros de las víctimas, por lo tanto, para las
                        frecuencias de las variables de las víctimas no
                        deben tomarse en cuenta.




  41. inculpado_18_años_o_mas
Nombre de la variable   inculpado_18_años_o_mas
Descripción             Edad del inculpado- 18 años o más
Tipo de variable        Categórica
Valores con los que
aparece                 Código       Descripción
                           0         No corresponde
                           1         Sí
                           2         No
                          99         Sin determinar



                                                                            21


## Página 22

Comentarios y              Generada a partir de la variable Edad que es
advertencias               ingresada por las fuerzas de seguridad.



  42. inculpado_vehiculo
Nombre de la variable      inculpado_vehiculo
Descripción                Tipo de vehículo del inculpado
Tipo de variable           Categórica
Valores con los que         Código Descripción
aparece                     0        No corresponde
                                     Micro           larga
                            1        distancia
                            2        Colectivo
                            3        Camión
                            4        Camioneta
                            5        Automóvil
                            6        Motocicleta
                            7        Ciclomotor
                            8        Bicicleta
                            9        Tren
                            10       Otro
                            99       Sin determinar
Comentarios y              Consultar el Anexo I para ver la definición de
advertencias               cada categoría.
                           Se validó con modo de producción del hecho.
                           En el caso de que en vehiculo_inculpado_otro
                           figure peatón se imputó valor perdido (vacío).
                           La categoría no corresponde refiere a los
                           registros de las víctimas, por lo tanto, para las
                           frecuencias de las variables de las víctimas no
                           deben tomarse en cuenta.


  43. inculpado_vehículo_ampliado
Nombre de la variable      inculpado_vehículo_ampliado
Descripción                Tipo de vehículo del inculpado – categorías
                           adicionales
Tipo de variable           Categórica
Valores con los que         Acoplado
aparece                     Ambulancia
                            Arenero/Karting/Buggy
                            Autobomba
                            Automóvil

                                                                               22


## Página 23

Bicicleta
                         Camioneta
                         Camión
                         Ciclomotor
                         Colectivo
                         Cuatriciclo
                         Grúa
                         Maquinaria
                         Micro larga distancia
                         Motocicleta
                         Móvil Policial
                         No corresponde
                         Otro
                         Sin determinar
                         Sin vehículo
                         Tracción a sangre
                         Tractor
                         Tractor/ Acoplado
                         Tractor/ Maquinaria
                         Trailer
                         Transporte de pasajeros
                         Tren
Comentarios y           Creada posteriormente a la carga a partir de la
advertencias            información cargada por las fuerzas de seguridad
                        en el campo abierto otro_vehiculo_inculpado.
                        En el caso de que en otro_vehículo_inculpado
                        figure peatón se imputó sin vehículo.
                        La categoría no corresponde refiere a los
                        registros de las víctimas, por lo tanto, para las
                        frecuencias de las variables de las víctimas no
                        deben tomarse en cuenta.




  44. Inculpado _vehiculo_otro
Nombre de la variable   Inculpado_vehiculo_otro
Descripción             Detalle de otro vehículo del inculpado
Tipo de variable        Texto
Comentarios y           Se completa en los casos en que se selecciona
advertencias            "otro" en vehículo del inculpado.
                        Se imputó valor perdido en el caso de que en el
                        modo de producción del hecho sea
                        vehículo/objeto o vehículo/ animal y en
                        otro_vehículo_inculpado figure árbol o animal,
                        por ejemplo. En el caso de que se haya registrado

                                                                            23


## Página 24

a un peatón como inculpado, en este campo se
                          imputa valor perdido.
                          Esta variable se ha adecuado para el uso
                          estadístico en función de las categorías
                          propuestas por la Agencia Nacional de Seguridad
                          Vial.


  45.         inculpado_identidad_genero
Nombre de la variable     inculpado_identidad_genero
Descripción               Identidad de género del inculpado.
Tipo de variable          Categórica
Valores con los que        Código Descripción
aparece                        1    Varón
                               2    Mujer
                               3    Varón Trans
                              4     Mujer trans/travestis
                               5    Otro (especificar)
                              99    Sin determinar
Comentarios y             De acuerdo a la Ley de Identidad de Género Nro.
advertencias              26.743, se entiende por identidad de género: “la
                          vivencia interna e individual del género tal como
                          cada persona la siente, la cual puede
                          corresponder o no con el sexo asignado a
                          momento del nacimiento, incluyendo la vivencia
                          personal del cuerpo. Esto puede involucrar la
                          modificación de la apariencia o la función
                          corporal a través de medios farmacológicos,
                          quirúrgicos o de otra índole, siempre que ello sea
                          libremente”.
                          Consultar el Anexo I para ver la definición de
                          cada categoría.




                                                                           24


## Página 25

Anexos

Anexo I –Definiciones de variables categóricas
En este apartado se presentan las definiciones de las variables categóricas.


Tipo de lugar

Esta variable refiere al lugar en el que se produjo el hecho. Contempla las
siguientes categorías :

1. Calle

Esta categoría comprende el espacio afectado a la vía pública comprendido
entre líneas municipales de propiedades frentistas o espacios públicos en
áreas urbanizadas, vías rurales de circulación y avenidas (permiten mayor
volumen de circulación de vehículos y suelen ser de doble sentido de
circulación).

2. Ruta Nacional

vía pública pavimentada o no, que es camino de comunicación entre pueblos,
localidades y ciudades, se desplaza por zonas urbanas, suburbanas o rurales,
de uno o más carriles por mano, con o sin cruces a nivel y sin límite de acceso
directo desde los predios frentistas lindantes. Se consideran rutas nacionales
aquellas   que     atraviesa más   de   una jurisdicción   provincial   y   cuyo
mantenimiento e infraestructura depende la jurisdicción nacional.

3. Ruta Provincial

vía pública pavimentada o no, que es camino de comunicación entre pueblos,
localidades y ciudades, se desplaza por zonas urbanas, suburbanas o rurales,
de uno o más carriles por mano, con o sin cruces a nivel y sin límite de acceso
directo desde los predios frentistas lindantes. Se consideran rutas provinciales
aquellas que no atraviesan más de una jurisdicción provincial y cuyo
mantenimiento e infraestructura depende de la provincia.

4. Autopista nacional

Vía multicarril sin cruces a nivel con otra arteria o ferrocarril, con calzadas
separadas físicamente y con limitación de ingreso directo desde los predios
                                                                               25


## Página 26

frentistas lindantes, cuyo trazado atraviesa más de una jurisdicción provincial
y mantenimiento y gestión depende de la jurisdicción nacional.

5. Autopista provincial

vía multicarril sin cruces a nivel con otra arteria o ferrocarril, con calzadas
separadas físicamente y con limitación de ingreso directo desde los predios
frentistas lindantes, cuyo trazado no atraviesa más de una jurisdicción
provincial y su mantenimiento y gestión depende de la provincia.

6. Autovía

vía multicarril con calzadas separadas con cruces a nivel con otra arteria o
ferrocarril y sin limitación de ingresos directos desde los predios frentistas
lindantes.

99. Sin determinar

Se utiliza categoría cuando no es posible determinar el tipo de lugar en que
ocurrió el hecho.



Modo de producción del hecho

Este campo hace referencia a la forma en la que se produjo el hecho.
Contempla a las siguientes categorías:

1. Colisión vehículo/persona

Corresponde a aquellos hechos en los que cualquier tipo de vehículo colisiona
con una persona que no se trasladaba en ningún otro tipo de vehículo.

2. Colisión vehículo/vehículo

Corresponde a aquellos hechos en los que colisionan dos o más vehículos, de
cualquier tipo. Se incluye en esta categoría la colisión con vehículos de
tracción a sangre (bicicleta, carros, entre otros) y los casos de choques
múltiples o en cadena. En esos casos, se especifica en la variable abierta de la
categoría Otro.

3. Colisión vehículo/objeto

Corresponde a aquellos hechos en los que uno o más vehículos colisiona/n
contra un objeto. Por ejemplo: un contenedor, un poste, un árbol, etc.
                                                                             26


## Página 27

4. Vuelco/Despistes

Corresponde a aquellos hechos en los que un vehículo sale del camino o
vuelca en su trayectoria, sin que haya chocado con otro vehículo.

5. Otro (Especificar)

Esta categoría incluye aquellos hechos que se produjeron por otros modos no
especificados en las categorías anteriores. Esta categoría incluye, por ejemplo,
la colisión con un animal.

99. Sin determinar

Se utiliza esta categoría cuando no es posible determinar el modo de
producción del hecho.



Condiciones climáticas

Este campo debe completarse con información referida al tipo de clima que
había en el momento del hecho. Este campo es obligatorio. Debe completarse
teniendo en cuenta las siguientes categorías:

1. Bueno

No hay obstáculos para la visibilidad de la persona que conduce.

2. Nublado

En el momento del hecho el cielo está total o parcialmente cubierto de nubes,
de manera tal que la luminosidad del día es inferior a la de un día despejado.

3. Lluvia

En el momento del hecho se producían precipitaciones en el lugar en el que
se produjo el siniestro.

4. Llovizna

En el momento del hecho, se producían precipitaciones leves, que caían
suavemente en el lugar en el que se produjo el siniestro.

5. Nieve

Incluye aquellos hechos en los que se pudo determinar la caída de nieve o la
presencia de la misma en la vía de tránsito en el momento y lugar del siniestro.
                                                                             27


## Página 28

6. Granizo

Se incluye aquellos hechos en los que se pudo determinar caída de
granizo/hielo en el lugar y momento del siniestro.

7. Otra condición

Incluye otras condiciones climáticas no consideradas en las categorías
anteriores. Por ejemplo: neblina, escarcha, vientos, etc.

99. Sin determinar

Se utiliza esta categoría cuando no es posible determinar las condiciones
climáticas en el momento en el que ocurrió el hecho.



Motivo que origina el registro del hecho

Esta variable registra de qué manera las fuerzas policiales intervinientes
tomaron conocimiento del hecho, teniendo en cuenta las siguientes
categorías:

1. Denuncia particular

Corresponde a hechos de los cuales se tomó conocimiento a partir de la
denuncia de una persona, ya sea que se haya radicado en la comisaría, se haya
realizado personalmente a un efectivo en la calle o a través de un sistema
formal de toma de denuncias telefónicas u online.

2. Intervención policial

Corresponde a los hechos en los que se tomó conocimiento a partir de la
intervención de un policía, ya sea que el efectivo se haya encontrado
patrullando, realizando tareas de prevención, o haya intervenido de oficio.

3. Orden judicial

Incluye aquellos hechos de los cuales se tomó conocimiento a partir del
pedido de intervención de la fuerza policial por parte de una institución
judicial.

4. Otros




                                                                              28


## Página 29

Corresponde a los hechos en los que se desconoce el origen o que, por algún
motivo, no puede considerarse dentro de las categorías anteriores

99. Sin determinar

En el caso que se desconozca el origen del registro.



Clase de victima

Esta variable indica el rol de la víctima fatal como usuario de la vía, debiendo
completarse teniendo en cuenta las siguientes categorías:

1. Conductor

Refiere a quien conduce el vehículo (incluye al ciclista).

2. Acompañante

Refiere a quien no conduce el vehículo en el que se desplaza, y este
corresponde a un medio de transporte de uso particular.

3. Pasajero

Refiere a aquellas personas que se trasladan en vehículos con funciones
comerciales (colectivos, micro de larga distancia, tren).

4. Peatón

Son aquellas personas que transitan a pie por la vía pública.

5. Otro

Cuando la víctima del hecho no corresponde con ninguna de las categorías
definidas con anterioridad.

99. Sin determinación

Corresponde utilizar esta categoría cuando no es posible determinar el rol de
la víctima fatal como usuario de la vía.




                                                                             29


## Página 30

Vehículo

En esta variable se especifica el tipo de vehículo/s involucrados en el hecho,
tanto de la víctima como del inculpado, teniendo en cuenta las siguientes
categorías:

1. Micro larga distancia

Transporte de pasajeros de larga distancia o que presta un servicio
interurbano, pudiendo circular por zona rural, ingresando a las zonas urbanas
para ascenso y descenso de pasajeros.

2. Colectivo

Transporte de pasajeros urbano de dos o más secciones con una de ellas
motora y la otra remolcada.

3. Camión

Vehículo destinado a transporte de carga. Incluye el camión tipo chasis (es
decir la caja de carga está adherida al tractor) y camión tipo tractor (aquellos
que arrastran acoplado o semirremolque).

4. Camioneta/Utilitaria

Vehículo automóvil de porte menor que el camión, empleado generalmente
para fines comerciales para el transporte de carga y logística de hasta 3500kg
de peso total (incluye Furgón, Furgoneta, Traffic, etc).

5. Automóvil

Automotor para el transporte de personas de hasta ocho plazas (excluido
conductor) con cuatro o más ruedas, y los de tres ruedas que exceda los mil
kg de peso.

6. Motocicleta

Vehículo de dos ruedas con motor a tracción propia.

7. Ciclomotor

Vehículo de dos ruedas con hasta cincuenta (50) centímetros cúbicos de
cilindrada o hasta mil (1000) Watts de potencia y con capacidad para
desarrollar no más de cincuenta (50) kilómetros por hora de velocidad.


                                                                             30


## Página 31

8. Bicicleta

Vehículo de dos ruedas sin propulsión a motor que es propulsado por
mecanismos con el esfuerzo de quien/es lo utiliza/n.

9. Tren/Ferrocarril

Vehículo constituido por varios vagones arrastrados por una locomotora, que
circula sobre rieles y se utiliza para el transporte de personas o de mercancías.

10. Otro

Incluye todo tipo de vehículo que no se halla especificado y definido en las
categorías anteriores. Por ejemplo: acoplado, ambulancia, semirremolque,
vehículo policial, tracción a sangre (con exclusión de la bicicleta), cuatriciclo,
maquinarias, etc.

99. Sin determinar

Corresponde utilizar esta categoría cuando no es posible determinar el tipo
de vehículo/s involucrados en el hecho.



Identidad de género

De acuerdo a la Ley de Identidad de Género Nro. 26.743, se entiende por
identidad de género: “la vivencia interna e individual del género tal como cada
persona la siente, la cual puede corresponder o no con el sexo asignado a
momento del nacimiento, incluyendo la vivencia personal del cuerpo. Esto
puede involucrar la modificación de la apariencia o la función corporal a través
de medios farmacológicos, quirúrgicos o de otra índole, siempre que ello sea
libremente”. Se debe tener en cuenta para completar esta información. Los
valores posibles son:

1. Varón

Se trata de la persona que, de acuerdo con su sexo asignado al nacer , fue
registrada como varón y que, en la actualidad, se siente y/o autopercibe como
varón.

2. Mujer



                                                                                31


## Página 32

Se trata de la persona que, de acuerdo con su sexo asignado al nacer, fue
registrada como mujer y que, en la actualidad, se siente y/o autopercibe como
mujer.

3. Varón trans

Se trata de la persona que de acuerdo con su sexo asignado al nacer fue
registrada como mujer y que, en la actualidad, se siente y/o autopercibe como
varón trans (independientemente de que haya realizado o no la rectificación
de su DNI y/o alguna intervención sobre su cuerpo).

4. Mujer trans/ travesti

Se trata de la persona que, de acuerdo con su sexo asignado al nacer, fue
registrada como varón y que, en la actualidad, se siente y/o autopercibe como
mujer trans (independientemente de que haya realizado o no la rectificación
de su DNI y/o alguna intervención sobre su cuerpo). Mujer Travesti: se trata de
la persona que se expresa socialmente con un género distinto a su sexo
asignado       al   nacer   y   se   siente   y/o   autopercibe   como   travesti
(independientemente de que haya realizado o no la rectificación de su DNI y/o
alguna intervención sobre su cuerpo).

5. Otro (especificar)

Es aquella persona que se siente y/o autopercibe con una identidad de género
distinta a las mencionadas anteriormente, por ejemplo: intersex, queer, no
binario. Completar con la identidad de género con la que se autopercibe la
persona. En caso de seleccionar esta opción, el campo para especificar es
obligatorio.

99. Sin determinar

Se utiliza esta categoría cuando no se dispone de información suficiente para
determinar la identidad de género de la persona.




                                                                              32


## Página 33

33


## Página 34

Anexo II – Códigos por Jurisdicción


           provincia_id              provincia_nombre
               02         Ciudad de Buenos Aires
               06         Buenos Aires
               10         Catamarca
               14         Córdoba
                18        Corrientes
               22         Chaco
               26         Chubut
               30         Entre Ríos
               34         Formosa
               38         Jujuy
               42         La Pampa
               46         La Rioja
               50         Mendoza
               54         Misiones
               58         Neuquén
               62         Rio Negro
               66         Salta
               70         San Juan
               74         San Luis
               78         Santa Cruz
               82         Santa Fe
               86         Santiago del Estero
               90         Tucumán
                          Tierra del Fuego, Antártida e Islas
               94
                          del Atlántico Sur




                                                                34


## Página 35

Anexo III – Códigos por departamento5


          provin     provincia_nomb          departame        departamento_no
         cia_id            re                 nto_id              mbre
            06        Buenos Aires             06854             25 de Mayo
             06        Buenos Aires             06588              9 de Julio
             06        Buenos Aires             06007            Adolfo Alsina
             06        Buenos Aires             06014          Adolfo Gonzales
                                                                   Chaves
             06        Buenos Aires             06021              Alberti
             06        Buenos Aires             06028          Almirante Brown
             06        Buenos Aires             06077               Arrecifes
             06        Buenos Aires             06035             Avellaneda
             06        Buenos Aires             06042              Ayacucho
             06        Buenos Aires             06049                  Azul
             06        Buenos Aires             06056            Bahía Blanca
             06        Buenos Aires             06063               Balcarce
             06        Buenos Aires             06070               Baradero
             06        Buenos Aires             06084            Benito Juárez
             06        Buenos Aires             06091             Berazategui
             06        Buenos Aires             06098                Berisso
             06        Buenos Aires             06105                Bolívar
             06        Buenos Aires              06112              Bragado
             06        Buenos Aires             06119              Brandsen
             06        Buenos Aires             06126              Campana
             06        Buenos Aires             06134               Cañuelas
             06        Buenos Aires             06140              Capitán
                                                                 Sarmiento
             06        Buenos Aires             06147           Carlos Casares
             06        Buenos Aires             06154           Carlos Tejedor
             06        Buenos Aires             06161         Carmen de Areco
             06        Buenos Aires             06168                Castelli
             06        Buenos Aires             06210             Chacabuco
             06        Buenos Aires             06217             Chascomús
             06        Buenos Aires             06224               Chivilcoy

5
  La siguiente tabla ha sido actualiza en las categorías de desagregación departamental de la
Provincia de La Pampa en el año 2023, para los periodos anteriores corresponde contemplar la
siguiente división político administrativa: Centro (Capital, Catrilo, Loventué y Toay), Norte
(Chapaleufu, Conhelo, Maracó, Quemú, Rancul, Realicó y Trenel), Oeste (Chalileo, Chical Co,
Curacó, Limay Mahuida y Puelén), Sur (Atreucó, Caleu, Guatraché, Hucal, Lihuel Calel y Utracan).

                                                                                             35


## Página 36

06   Buenos Aires   06175         Colon
06   Buenos Aires   06182     Coronel de
                            Marina L. Rosales
06   Buenos Aires   06189   Coronel Dorrego
06   Buenos Aires   06196   Coronel Pringles
06   Buenos Aires   06203    Coronel Suarez
06   Buenos Aires   06231       Daireaux
06   Buenos Aires   06238        Dolores
06   Buenos Aires   06245      Ensenada
06   Buenos Aires   06252       Escobar
06   Buenos Aires   06260       Esteban
                               Echeverría
06   Buenos Aires   06266    Exaltación de la
                                   Cruz
06   Buenos Aires   06270         Ezeiza
06   Buenos Aires   06274   Florencio Varela
06   Buenos Aires   06277     Florentino
                              Ameghino
06   Buenos Aires   06280   General Alvarado
06   Buenos Aires   06287    General Alvear
06   Buenos Aires   06294   General Arenales
06   Buenos Aires   06301   General Belgrano
06   Buenos Aires   06308    General Guido
06   Buenos Aires   06315     General Juan
                               Madariaga
06   Buenos Aires   06322      General La
                                Madrid
06   Buenos Aires   06329   General Las Heras
06   Buenos Aires   06336    General Lavalle
06   Buenos Aires   06343     General Paz
06   Buenos Aires   06351     General Pinto
06   Buenos Aires   06357       General
                              Pueyrredón
06   Buenos Aires   06364       General
                               Rodríguez
06   Buenos Aires   06371     General San
                                 Martin
06   Buenos Aires   06385   General Viamonte
06   Buenos Aires   06392   General Villegas
06   Buenos Aires   06399       Guamini
06   Buenos Aires   06406   Hipólito Yrigoyen
06   Buenos Aires   06408     Hurlingham
06   Buenos Aires   06410       Ituzaingo

                                                36


## Página 37

06   Buenos Aires   06412     José C. Paz
06   Buenos Aires   06413        Junín
06   Buenos Aires   06420       La Costa
06   Buenos Aires   06427     La Matanza
06   Buenos Aires   06441       La Plata
06   Buenos Aires   06434        Lanús
06   Buenos Aires   06448       Laprida
06   Buenos Aires   06455      Las Flores
06   Buenos Aires   06462   Leandro N. Alem
06   Buenos Aires   06466       Lezama
06   Buenos Aires   06469       Lincoln
06   Buenos Aires   06476       Lobería
06   Buenos Aires   06483        Lobos
06   Buenos Aires   06490   Lomas de Zamora
06   Buenos Aires   06497        Lujan
06   Buenos Aires   06505     Magdalena
06   Buenos Aires   06511        Maipú
06   Buenos Aires   06515       Malvinas
                               Argentinas
06   Buenos Aires   06518     Mar Chiquita
06   Buenos Aires   06525     Marcos Paz
06   Buenos Aires   06532      Mercedes
06   Buenos Aires   06539        Merlo
06   Buenos Aires   06547        Monte
06   Buenos Aires   06553   Monte Hermoso
06   Buenos Aires   06560       Moreno
06   Buenos Aires   06568       Morón
06   Buenos Aires   06574       Navarro
06   Buenos Aires   06581      Necochea
06   Buenos Aires   06595      Olavarría
06   Buenos Aires   06602      Patagones
06   Buenos Aires   06609       Pehuajo
06   Buenos Aires   06616      Pellegrini
06   Buenos Aires   06623     Pergamino
06   Buenos Aires   06630         Pila
06   Buenos Aires   06638        Pilar
06   Buenos Aires   06644       Pinamar
06   Buenos Aires   06648   Presidente Perón
06   Buenos Aires   06651        Púan

                                               37


## Página 38

06   Buenos Aires   06655     Punta Indio
06   Buenos Aires   06658       Quilmes
06   Buenos Aires   06665       Ramallo
06   Buenos Aires   06672        Rauch
06   Buenos Aires   06679      Rivadavia
06   Buenos Aires   06686        Rojas
06   Buenos Aires   06693     Roque Pérez
06   Buenos Aires   06700      Saavedra
06   Buenos Aires   06707       Saladillo
06   Buenos Aires   06721      Salliquelo
06   Buenos Aires   06714         Salto
06   Buenos Aires   06728    San Andrés de
                                  Giles
06   Buenos Aires   06735    San Antonio de
                                 Areco
06   Buenos Aires   06742     San Cayetano
06   Buenos Aires   06749    San Fernando
06   Buenos Aires   06756      San Isidro
06   Buenos Aires   06760     San Miguel
06   Buenos Aires   06763     San Nicolás
06   Buenos Aires   06770      San Pedro
06   Buenos Aires   06778     San Vicente
06   Buenos Aires   06999    Sin determinar
06   Buenos Aires   06784      Suipacha
06   Buenos Aires   06791        Tandil
06   Buenos Aires   06798      Tapalqué
06   Buenos Aires   06805         Tigre
06   Buenos Aires   06812       Tordillo
06   Buenos Aires   06819      Tornquist
06   Buenos Aires   06826   Trenque Lauquen
06   Buenos Aires   06833     Tres Arroyos
06   Buenos Aires   06840   Tres de Febrero
06   Buenos Aires   06847     Tres Lomas
06   Buenos Aires   06861    Vicente López
06   Buenos Aires   06868      Villa Gesell
06   Buenos Aires   06875       Villarino
06   Buenos Aires   06882        Zarate
10   Catamarca      10007       Ambato
10   Catamarca      10014       Ancasti
10   Catamarca      10021      Andalgala
                                              38


## Página 39

10   Catamarca   10028   Antofagasta de la
                              Sierra
10   Catamarca   10035        Belén
10   Catamarca   10042       Capayan
10   Catamarca   10049        Capital
10   Catamarca   10056        El Alto
10   Catamarca   10063    Fray Mamerto
                             Esquiu
10   Catamarca   10070        La Paz
10   Catamarca   10077        Paclin
10   Catamarca   10084       Poman
10   Catamarca   10091     Santa María
10   Catamarca   10098      Santa Rosa
10   Catamarca   10999    Sin determinar
10   Catamarca   10105      Tinogasta
10   Catamarca   10112      Valle Viejo
22    Chaco      22036    12 de Octubre
22    Chaco      22126      1º de Mayo
22    Chaco      22039      2 de Abril
22    Chaco      22168      25 de Mayo
22    Chaco      22105      9 de Julio
22    Chaco      22007   Almirante Brown
22    Chaco      22014       Bermejo
22    Chaco      22028      Chacabuco
22    Chaco      22021     Comandante
                            Fernández
22    Chaco      22043   Fray Justo Santa
                           María de Oro
22    Chaco      22049   General Belgrano
22    Chaco      22056   General Donovan
22    Chaco      22063   General Güemes
22    Chaco      22070    Independencia
22    Chaco      22077       Libertad
22    Chaco      22084      Libertador
                           General San
                              Martin
22    Chaco      22091        Maipú
22    Chaco      22098     Mayor Luis J.
                             Fontana
22    Chaco      22112      O' Higgins
22    Chaco      22119   Presidencia de la
                               Plaza

                                             39


## Página 40

22      Chaco       22133      Quitilipi
22      Chaco       22140    San Fernando
22      Chaco       22147    San Lorenzo
22      Chaco       22154   Sargento Cabral
22      Chaco       22999   Sin determinar
22      Chaco       22161     Tapenaga
26     Chubut       26007      Biedma
26     Chubut       26014     Cushamen
26     Chubut       26021      Escalante
26     Chubut       26028     Florentino
                              Ameghino
26     Chubut       26035     Futaleufu
26     Chubut       26042      Gaiman
26     Chubut       26049       Gastre
26     Chubut       26056      Languieo
26     Chubut       26063      Martires
26     Chubut       26070   Paso de Indios
26     Chubut       26077      Rawson
26     Chubut       26084    Rio Senguer
26     Chubut       26091     Sarmiento
26     Chubut       26999   Sin determinar
26     Chubut       26098     Tehuelches
26     Chubut       26105       Telsen
02      Ciudad      02001     Comuna 1
     Autónoma de
     Buenos Aires
02      Ciudad      02010     Comuna 10
     Autónoma de
     Buenos Aires
02      Ciudad      02011     Comuna 11
     Autónoma de
     Buenos Aires
02      Ciudad      02012     Comuna 12
     Autónoma de
     Buenos Aires
02      Ciudad      02013     Comuna 13
     Autónoma de
     Buenos Aires
02      Ciudad      02014     Comuna 14
     Autónoma de
     Buenos Aires
02      Ciudad      02015     Comuna 15
     Autónoma de
     Buenos Aires

                                              40


## Página 41

02      Ciudad      02002      Comuna 2
     Autónoma de
     Buenos Aires
02      Ciudad      02003      Comuna 3
     Autónoma de
     Buenos Aires
02      Ciudad      02004      Comuna 4
     Autónoma de
     Buenos Aires
02      Ciudad      02005      Comuna 5
     Autónoma de
     Buenos Aires
02      Ciudad      02006      Comuna 6
     Autónoma de
     Buenos Aires
02      Ciudad      02007      Comuna 7
     Autónoma de
     Buenos Aires
02      Ciudad      02008      Comuna 8
     Autónoma de
     Buenos Aires
02      Ciudad      02009      Comuna 9
     Autónoma de
     Buenos Aires
02      Ciudad      02999    Sin determinar
     Autónoma de
     Buenos Aires
14     Córdoba      14007     Calamuchita
14     Córdoba      14014       Capital
14     Córdoba      14021        Colon
14     Córdoba      14028     Cruz del Eje
14     Córdoba      14035     General Roca
14     Córdoba      14042     General San
                                Martin
14     Córdoba      14049       Ischilin
14     Córdoba      14056    Juárez Celman
14     Córdoba      14063    Marcos Juárez
14     Córdoba      14070        Minas
14     Córdoba      14077        Pocho
14     Córdoba      14084   Presidente Roque
                               Sáenz Peña
14     Córdoba      14091        Punilla
14     Córdoba      14098      Rio Cuarto
14     Córdoba      14105     Rio Primero
14     Córdoba      14112       Rio Seco
14     Córdoba      14119     Rio Segundo

                                               41


## Página 42

14   Córdoba      14126      San Alberto
14   Córdoba      14133      San Javier
14   Córdoba      14140       San Justo
14   Córdoba      14147     Santa María
14   Córdoba      14999    Sin determinar
14   Córdoba      14154     Sobremonte
14   Córdoba      14161    Tercero Arriba
14   Córdoba      14168        Totoral
14   Córdoba      14175       Tulumba
14   Córdoba      14182        Unión
18   Corrientes   18007      Bella Vista
18   Corrientes   18014   Berón de Astrada
18   Corrientes   18021        Capital
18   Corrientes   18028     Concepción
18   Corrientes   18035    Curuzu Cuatia
18   Corrientes   18042     Empedrado
18   Corrientes   18049       Esquina
18   Corrientes   18056    General Alvear
18   Corrientes   18063     General Paz
18   Corrientes   18070         Goya
18   Corrientes   18077         Itati
18   Corrientes   18084       Ituzaingo
18   Corrientes   18091        Lavalle
18   Corrientes   18098      Mburucuya
18   Corrientes   18105       Mercedes
18   Corrientes   18112    Monte Caseros
18   Corrientes   18119   Paso de los Libres
18   Corrientes   18126        Saladas
18   Corrientes   18133      San Cosme
18   Corrientes   18140     San Luis del
                              Palmar
18   Corrientes   18147     San Martin
18   Corrientes   18154      San Miguel
18   Corrientes   18161      San Roque
18   Corrientes   18168     Santo Tome
18   Corrientes   18175        Sauce
18   Corrientes   18999    Sin determinar
30   Entre Ríos   30008         Colon
30   Entre Ríos   30015      Concordia

                                               42


## Página 43

30   Entre Ríos   30021     Diamante
30   Entre Ríos   30028    Federación
30   Entre Ríos   30035      Federal
30   Entre Ríos   30042      Feliciano
30   Entre Ríos   30049     Gualeguay
30   Entre Ríos   30056   Gualeguaychu
30   Entre Ríos   30063   Islas del Ibicuy
30   Entre Ríos   30070       La Paz
30   Entre Ríos   30077      Nogoya
30   Entre Ríos   30084       Paraná
30   Entre Ríos   30088   San Salvador
30   Entre Ríos   30999   Sin determinar
30   Entre Ríos   30091        Tala
30   Entre Ríos   30098      Uruguay
30   Entre Ríos   30105      Victoria
30   Entre Ríos   30113     Villaguay
34   Formosa      34007      Bermejo
34   Formosa      34014      Formosa
34   Formosa      34021       Laishi
34   Formosa      34028      Matacos
34   Formosa      34035       Patiño
34   Formosa      34042      Pilagas
34   Formosa      34049     Pilcomayo
34   Formosa      34056       Pirane
34   Formosa      34063    Ramón Lista
34   Formosa      34999   Sin determinar
38     Jujuy      38007     Cochinoca
38     Jujuy      38014    Dr. Manuel
                            Belgrano
38     Jujuy      38021    El Carmen
38     Jujuy      38028    Humahuaca
38     Jujuy      38035     Ledesma
38     Jujuy      38042      Palpala
38     Jujuy      38049     Rinconada
38     Jujuy      38056    San Antonio
38     Jujuy      38063     San Pedro
38     Jujuy      38070   Santa Bárbara
38     Jujuy      38077   Santa Catalina
38     Jujuy      38999   Sin determinar

                                             43


## Página 44

38    Jujuy     38084       Susques
38    Jujuy     38094        Tilcara
38    Jujuy     38098      Tumbaya
38    Jujuy     38105     Valle Grande
38    Jujuy     38112         Yavi
42   La Pampa   42007       Atreucó
42   La Pampa   42014     Caleu Caleu
42   La Pampa   42021       Capital
42   La Pampa   42028        Catriló
42   La Pampa   42035       Conhelo
42   La Pampa   42042       Curacó
42   La Pampa   42049       Chalileo
42   La Pampa   42056     Chapaleufú
42   La Pampa   42063       Chicalcó
42   La Pampa   42070      Guatraché
42   La Pampa   42077        Hucal
42   La Pampa   42084     Lihuel Calel
42   La Pampa   42091   Limay Mahuida
42   La Pampa   42098      Loventué
42   La Pampa   42105       Maracó
42   La Pampa   42112       Puelén
42   La Pampa   42119   Quemú Ouemú
42   La Pampa   42126       Rancul
42   La Pampa   42133       Realicó
42   La Pampa   42140         Toay
42   La Pampa   42147        Trenel
42   La Pampa   42154       Utracán
42   La Pampa   42999    Sin determinar
46   La Rioja   46007       Arauco
46   La Rioja   46014       Capital
46   La Rioja   46021    Castro Barros
46   La Rioja   46028      Chamical
46   La Rioja   46035      Chilecito
46   La Rioja   46042    Coronel Felipe
                            Varela
46   La Rioja   46049      Famatina
46   La Rioja   46056   General Ángel V.
                           Peñaloza
46   La Rioja   46063   General Belgrano


                                           44


## Página 45

46   La Rioja   46070    General Juan F.
                            Quiroga
46   La Rioja   46077   General Lamadrid
46   La Rioja   46084   General Ocampo
46   La Rioja   46091      General San
                             Martin
46   La Rioja   46098    Independencia
46   La Rioja   46105     Rosario Vera
                            Peñaloza
46   La Rioja   46112    San Blas de los
                             Sauces
46   La Rioja   46119      Sanagasta
46   La Rioja   46999    Sin determinar
46   La Rioja   46126       Vinchina
50   Mendoza    50007       Capital
50   Mendoza    50014    General Alvear
50   Mendoza    50021     Godoy Cruz
50   Mendoza    50028     Guaymallen
50   Mendoza    50035        Junín
50   Mendoza    50042        La Paz
50   Mendoza    50049      Las Heras
50   Mendoza    50056        Lavalle
50   Mendoza    50063    Lujan de Cuyo
50   Mendoza    50070        Maipú
50   Mendoza    50077      Malargüe
50   Mendoza    50084      Rivadavia
50   Mendoza    50091      San Carlos
50   Mendoza    50098      San Martin
50   Mendoza    50105      San Rafael
50   Mendoza    50112      Santa Rosa
50   Mendoza    50999    Sin determinar
50   Mendoza    50119       Tunuyan
50   Mendoza    50126      Tupungato
54   Misiones   54119     25 de Mayo
54   Misiones   54007      Apóstoles
54   Misiones   54014      Cainguas
54   Misiones   54021      Candelaria
54   Misiones   54028       Capital
54   Misiones   54035     Concepción
54   Misiones   54042      Eldorado


                                           45


## Página 46

54   Misiones    54049   General Manuel
                           Belgrano
54   Misiones    54056      Guaraní
54   Misiones    54063       Iguazú
54   Misiones    54070   Leandro N. Alem
54   Misiones    54077   Libertador Gral.
                           San Martin
54   Misiones    54084     Montecarlo
54   Misiones    54091       Obera
54   Misiones    54098     San Ignacio
54   Misiones    54105     San Javier
54   Misiones    54112     San Pedro
54   Misiones    54999   Sin determinar
58   Neuquén     58084      Ñorquin
58   Neuquén     58014        Añelo
58   Neuquén     58007      Alumine
58   Neuquén     58021      Catan Lil
58   Neuquén     58028     Chos Malal
58   Neuquén     58035     Collon Cura
58   Neuquén     58042     Confluencia
58   Neuquén     58049      Huiliches
58   Neuquén     58056        Lacar
58   Neuquén     58063     Loncopue
58   Neuquén     58070      Los Lagos
58   Neuquén     58077       Minas
58   Neuquén     58091    Pehuenches
58   Neuquén     58098     Picun Leufu
58   Neuquén     58105     Picunches
58   Neuquén     58999   Sin determinar
58   Neuquén     58112       Zapala
62   Rio Negro   62091     25 de Mayo
62   Rio Negro   62049      9 de Julio
62   Rio Negro   62056     Ñorquincó
62   Rio Negro   62007    Adolfo Alsina
62   Rio Negro   62014     Avellaneda
62   Rio Negro   62021      Bariloche
62   Rio Negro   62028       Conesa
62   Rio Negro   62035       El Cuy
62   Rio Negro   62042    General Roca
62   Rio Negro   62063    Pichi Mahuida
                                            46


## Página 47

62   Rio Negro   62070      Pilcaniyeu
62   Rio Negro   62077     San Antonio
62   Rio Negro   62999    Sin determinar
62   Rio Negro   62084       Valcheta
66     Salta     66007         Anta
66     Salta     66014        Cachi
66     Salta     66021       Cafayate
66     Salta     66028       Capital
66     Salta     66035       Cerrillos
66     Salta     66042      Chicoana
66     Salta     66049   General Güemes
66     Salta     66056   Gral. José de San
                               Martin
66     Salta     66063      Guachipas
66     Salta     66070        Iruya
66     Salta     66077      La Caldera
66     Salta     66084    La Candelaria
66     Salta     66091       La Poma
66     Salta     66098       La Viña
66     Salta     66105      Los Andes
66     Salta     66112        Metan
66     Salta     66119       Molinos
66     Salta     66126        Oran
66     Salta     66131      Rivadavia
66     Salta     66138     Rosario de la
                             Frontera
66     Salta     66145   Rosario de Lerma
66     Salta     66152      San Carlos
66     Salta     66159    Santa Victoria
66     Salta     66999    Sin determinar
70   San Juan    70126     25 de Mayo
70   San Juan    70063      9 de Julio
70   San Juan    70007      Albardon
70   San Juan    70014       Angaco
70   San Juan    70021      Calingasta
70   San Juan    70028       Capital
70   San Juan    70035       Caucete
70   San Juan    70042      Chimbas
70   San Juan    70049        Iglesia
70   San Juan    70056        Jachal
                                             47


## Página 48

70   San Juan     70070        Pocito
70   San Juan     70077       Rawson
70   San Juan     70084      Rivadavia
70   San Juan     70091      San Martin
70   San Juan     70098     Santa Lucia
70   San Juan     70105      Sarmiento
70   San Juan     70999    Sin determinar
70   San Juan     70112        Ullum
70   San Juan     70119      Valle Fertil
70   San Juan     70133        Zonda
74    San Luis    74007      Ayacucho
74    San Luis    74014      Belgrano
74    San Luis    74021     Chacabuco
74    San Luis    74028   Coronel Pringles
74    San Luis    74035       General
                             Pedernera
74    San Luis    74042     Gobernador
                              Dupuy
74    San Luis    74049        Junín
74    San Luis    74056      La Capital
74    San Luis    74063      Libertador
                            General San
                               Martin
74    San Luis    74999    Sin determinar
78   Santa Cruz   78007     Corpen Aike
78   Santa Cruz   78014      Deseado
78   Santa Cruz   78021      Güer Aike
78   Santa Cruz   78028   Lago Argentino
78   Santa Cruz   78035     Lago Buenos
                               Aires
78   Santa Cruz   78042      Magallanes
78   Santa Cruz   78049      Rio Chico
78   Santa Cruz   78999    Sin determinar
82   Santa Fe     82077      9 de Julio
82   Santa Fe     82007      Belgrano
82   Santa Fe     82014       Caseros
82   Santa Fe     82021     Castellanos
82   Santa Fe     82028     Constitución
82   Santa Fe     82035        Garay
82   Santa Fe     82042    General López
82   Santa Fe     82049   General Obligado

                                             48


## Página 49

82    Santa Fe      82056       Iriondo
82    Santa Fe      82063      La Capital
82    Santa Fe      82070     Las Colonias
82    Santa Fe      82084       Rosario
82    Santa Fe      82091    San Cristóbal
82    Santa Fe      82098      San Javier
82    Santa Fe      82105    San Jerónimo
82    Santa Fe      82112      San Justo
82    Santa Fe      82119     San Lorenzo
82    Santa Fe      82126     San Martin
82    Santa Fe      82999   Sin determinar
82    Santa Fe      82133        Vera
86   Santiago del   86007       Aguirre
       Estero
86   Santiago del   86014       Alberdi
       Estero
86   Santiago del   86021      Atamisqui
       Estero
86   Santiago del   86028     Avellaneda
       Estero
86   Santiago del   86035       Banda
       Estero
86   Santiago del   86042      Belgrano
       Estero
86   Santiago del   86049       Capital
       Estero
86   Santiago del   86056       Choya
       Estero
86   Santiago del   86063        Copo
       Estero
86   Santiago del   86070      Figueroa
       Estero
86   Santiago del   86077   General Taboada
       Estero
86   Santiago del   86084      Guasayan
       Estero
86   Santiago del   86091      Jiménez
       Estero
86   Santiago del   86105    Juan F. Ibarra
       Estero
86   Santiago del   86112       Loreto
       Estero
86   Santiago del   86119        Mitre
       Estero
86   Santiago del   86126       Moreno
       Estero

                                              49


## Página 50

86     Santiago del      86133    Ojo de Agua
           Estero
86     Santiago del      86140     Pellegrini
           Estero
86     Santiago del      86147    Quebrachos
           Estero
86     Santiago del      86154     Rio Hondo
           Estero
86     Santiago del      86161     Rivadavia
           Estero
86     Santiago del      86168      Robles
           Estero
86     Santiago del      86175      Salavina
           Estero
86     Santiago del      86182    San Martin
           Estero
86     Santiago del      86189     Sarmiento
           Estero
86     Santiago del      86196      Silipica
           Estero
86     Santiago del      86999   Sin determinar
           Estero
94   Tierra del Fuego,   94014    Rio Grande
     Antártida e Islas
     del Atlántico Sur
94   Tierra del Fuego,   94999   Sin determinar
     Antártida e Islas
     del Atlántico Sur
94   Tierra del Fuego,   94021      Ushuaia
     Antártida e Islas
     del Atlántico Sur
90       Tucumán         90007     Burruyacu
90      Tucumán          90014      Capital
90      Tucumán          90021    Chicligasta
90      Tucumán          90028     Cruz Alta
90      Tucumán          90035      Famailla
90      Tucumán          90042     Graneros
90      Tucumán          90049   Juan Bautista
                                    Alberdi
90      Tucumán          90056     La Cocha
90      Tucumán          90063       Leales
90      Tucumán          90070       Lules
90      Tucumán          90077     Monteros
90      Tucumán          90084     Rio Chico
90      Tucumán          90091      Simoca
90      Tucumán          90999   Sin determinar

                                                  50


## Página 51

90   Tucumán   90098   Tafí del Valle
90   Tucumán   90105    Tafí Viejo
90   Tucumán   90112     Trancas
90   Tucumán   90119   Yerba Buena




                                        51
