# manual_sat_suicidios_2024

- Original local: `data/raw/ar/security_dnec/download_2026-07-12/sat/pdf/manual_sat_suicidios_2024.pdf`
- Extracted with: `pdftotext -layout`
- PDF pages: 44
- Note: this is a text extraction for review; consult the original PDF for layout-specific ambiguity.


## Página 1

Manual de usuario de la base

Sistema de Alerta Temprana Suicidios

                    (SAT -SS)




       Dirección Nacional de Estadística Criminal
           Ministerio de Seguridad de la Nación

      Dirección Nacional de Estadística Criminal
          Ministerio de Seguridad de la Nación


## Página 2

Índice


Introducción                                       3
Base de datos SAT SS                               3
   Características de la base de datos            4
   Cómo utilizar la base de datos                 4
   Criterios de consistencia                      4
Diccionario de variables                          5
   Definiciones de variables Base SAT SS           5
Anexos                                            18
 Anexo I –Definiciones de variables categóricas   18
 Anexo II – Códigos por Jurisdicción              25
 Anexo III – Códigos por departamento             26




                                                   2


## Página 3

Introducción


El Ministerio de Seguridad de la Nación, a través de la Dirección Nacional de
Estadística Criminal, pone a disposición los registros administrativos del
Sistema de Alerta Temprana de Suicidios (SAT - SS) del Sistema Nacional de
Información Criminal (SNIC)1. De esta forma, a partir de la difusión y la mejora
en el acceso a la información sobre la temática, se busca promover el
desarrollo de nuevas investigaciones y contribuir al diseño de políticas
públicas basadas en evidencia, además de promover la transparencia en la
gestión, acorde a la Ley Nro. 27.275 de Derecho de Acceso a la Información
Pública y Gobierno Abierto.

En particular, el Sistema de Alerta Temprana de Suicidios releva con mayor
grado de detalle (microdatos) la información de los suicidios reportados en
todo el territorio nacional con el objetivo de determinar las características de
los hechos, así como de las personas involucradas, tanto víctimas como
testigos.

Los principales datos que recaba son: fecha, hora y lugar del hecho, tipo de
lugar, modalidad utilizada, motivo que origina el registro, edad, sexo. Cada uno
de estas variables se encuentra asociada al código del departamento y
localidad donde ocurrió el hecho.




Base de datos SAT SS
¿Para qué sirve la base SAT-SS?

A partir de los microdatos de las bases SAT-SS es posible identificar la cantidad
de suicidios consumados, a nivel de evento, con datos sobre contexto,


1
 Para mayor información se recomienda leer el Documento metodológico del Sistema nacional
de información criminal (SNIC) disponible en el sitio web.
                                                                                       3


## Página 4

personas involucradas y modalidades utilizadas. Este tipo de registro habilita
el análisis cualitativo de este fenómeno, además de su cuantificación.

Características de la base de datos

La base de datos cuenta con un número identificador por cada hecho. En la
misma base se incluyen los registros correspondientes a las personas que
cometieron suicidio. Para trabajar con esta base de datos se debe tener en
cuenta la dimensión de la misma; por ejemplo, en el caso de la base que
corresponde a los años 2017-2023 contiene 25.920 registros y las variables de
caracterización del hecho. Es recomendable utilizar softwares específicos para
la gestión y análisis de datos.




Cómo utilizar la base de datos

Para utilizar la base SAT-SS es necesario contar con conocimientos de
procesamiento de bases de datos o tablas dinámicas y de realización de filtros.
La base de datos cuenta con un identificador del hecho, para cada hecho se
encuentran en la misma base los registros correspondientes a las personas
involucradas. En esta base usuaria sólo se incluye información sobre las
víctimas (no sobre testigos); en caso de hechos con más de una víctima los
datos del hecho se repiten para cada víctima. Para conocer la cantidad de
hechos, se debe contar una única vez cada ID de hecho.




Criterios de consistencia

      Los datos del SAT SS deben cumplir con criterios de consistencia según
el tipo de variable, los criterios se encuentran explicados en el diccionario de
variables.




                                                                              4


## Página 5

Diccionario de variables

Definiciones de variables Base SAT SS

En esta sección se presenta la descripción detallada de las variables (o
campos) que contiene la base usuaria SAT-SS.


   1.   id_hecho



Nombre de la variable    id_hecho

Descripción              Código de identificación del hecho

Tipo de variable         Numérica

Comentarios y            Permite identificar a las personas involucradas
                         en un mismo hecho: víctimas e inculpados. Al ser
advertencias
                         identificador no contiene valores perdidos. A
                         partir de esta variable se pueden calcular la
                         cantidad de hechos y de víctimas.



   2. tipo_persona_id

 Nombre de la variable   tipo_persona_id

 Descripción             Código identificador del suicida

 Tipo de variable        Texto

 Valores con los que     Ejemplo:
 aparece                 Suicida idRegistro 20712

 Comentarios y           Permite diferenciar personas en un mismo
                         hecho.
 advertencias




   3. federal

Nombre de la variable    Federal



                                                                            5


## Página 6

Descripción             Indica si el dato es reportado por una fuerza
                        federal o provincial.
Tipo de variable        Categórica
Valores con los que      Código     Descripción
aparece                      0      No
                             1      Si
Comentarios y           Permite identificar los hechos que fueron
advertencias            reportados por la fuerza provinciales y las fuerzas
                        federales (GNA, PSA, PFA, PNA y SPF).



  4. provincia_id

Nombre de la variable   provincia_id

Descripción             Código de la provincia donde ocurrió el hecho

Tipo de variable        Categórica

Valores con los que     Ver Anexo II.
aparece

Comentarios y           Los códigos coinciden con los de INDEC, es útil
                        para realizar cruces con bases de datos de
advertencias
                        población y otras bases de datos que utilicen la
                        codificación de INDEC.



  5. provincia_nombre

Nombre de la variable   provincia_nombre

Descripción             Provincia donde ocurrió el hecho

Tipo de variable        Texto




  6. departamento_id

Nombre de la variable   departamento_id

Descripción             Código de 5 cifras para el departamento y la
                        provincia.
Tipo de variable        Texto




                                                                              6


## Página 7

Valores con los que     Ver Anexo III.
aparece

Comentarios y           Cada jurisdicción se divide en departamento, de
advertencias            acuerdo a su división política. En CABA,
                        corresponde a Comunas y en Provincia de
                        Buenos Aires corresponde a Partidos.
                        Los primeros 2 dígitos corresponden a la
                        provincia y los últimos 3 al departamento.
                        Cuando el departamento es sin determinar el
                        código es el número de la provincia + 999.




  7. departamento_nombre

Nombre de la variable   departamento_nombre

Descripción             Nombre del departamento geográfico donde
                        ocurrió el hecho.
Tipo de variable        Texto

Comentarios y           Ver descripción en Anexo III
advertencias




  8. localidad_id

Nombre de la variable   Localidad

Descripción             Código de la localidad del hecho

Tipo de variable        Texto

Comentarios y           La localidad sin determinar tiene el prefijo 999-
advertencias            999. Para algunas provincias los códigos de la
                        localidad coinciden con los de INDEC.




  9. localidad_nombre

Nombre de la variable   localidad_nombre

Descripción             Nombre de la localidad donde ocurrió el hecho



                                                                            7


## Página 8

Tipo de variable        Texto

Comentarios y           En general, las Fuerzas Federales registran sus
                        datos en la categoría Localidad sin determinar,
advertencias
                        ya que la información se reporta desde sus
                        unidades operativas cuyo alcance territorial no
                        coincide con la división política de cada
                        jurisdicción.


  10. anio

Nombre de la variable   anio

Descripción             Año de ocurrencia del hecho

Tipo de variable        Numérica

Comentarios y           Valor correspondiente a cada año calendario al
                        que correspondan los hechos reportados. Se
advertencias
                        valida con la fecha del hecho.



  11. mes

Nombre de la variable   mes

Descripción             Mes de ocurrencia del hecho.

Tipo de variable        Numérica

Comentarios y           Se valida con la fecha del hecho. Valores con los
advertencias            que aparece: 1 a 12.



  12. fecha_hecho

Nombre de la variable   fecha_hecho

Descripción             Fecha de ocurrencia del hecho

Tipo de variable        Fecha. Formato fecha: dd/mm/aaaa.

Comentarios y           Se valida con las variables anio y mes.
advertencias




                                                                            8


## Página 9

13. hora_hecho

Nombre de la variable   hora_hecho

Descripción             Hora del hecho

Tipo de variable        Texto

Valores con los que     Formato hora: hh:mm:ss , desde 00:00:00 a
                        23:59:59.
aparece

Comentarios y           Los registros sin dato tienen hora 11:11:11. En
                        algunos casos la hora 00:00:00 podría indicar sin
advertencias
                        dato debido a la inusual frecuencia de registros
                        en este horario. Se sugiere revisar este dato por
                        provincia y año.



  14. tipo_lugar

Nombre de la variable   tipo_lugar

Descripción             Lugar de ocurrencia del hecho

Tipo de variable        Categórica

Valores con los que
aparece                     Código Descripción
                                1 Vía publica
                                2 Domicilio particular
                                3 Vías del ferrocarril
                                4 Cárcel o comisaria
                                5 Otro lugar
                               99 Sin Determinar
Comentarios y           Consultar el Anexo I para ver la definición de
                        cada categoría.
advertencias




  15. tipo_lugar_ampliado

Nombre de la variable   tipo_lugar_ampliado

Descripción             Tipo de lugar de ocurrencia del hecho –
                        categorías adicionales
Tipo de variable        Texto



                                                                            9


## Página 10

Valores con los que     Campo/descampado/zona rural
                        Cárcel o comisaría
aparece
                        Domicilio particular
                        Establecimiento comercial
                        Establecimiento de salud/salud mental
                        Geriátrico/Hogar
                        Hotel/Motel/Hospedaje temporario
                        Otro Lugar (Especificar)
                        Río/canal/arroyo/mar/dique
                        Sin determinar
                        Vía pública
                        Vías del FF.CC.
Comentarios y           Tipo de lugar del hecho con mayor cantidad de
advertencias            categorías que en la variable original, construidas
                        a partir de la información disponible en los
                        campos abiertos. Cambios en esta variable con
                        respecto a la publicación anterior: se agregaron
                        las categorías Establecimiento comercial y se
                        juntaron las categorías Establecimiento de salud
                        y Establecimiento de salud mental. Se incluyó
                        dentro de la categoría Geriátrico/Hogar al hogar
                        de niños. Se incorporó el hospedaje temporario a
                        la categoría Hotel/ Motel.



  16. tipo_lugar_otro

Nombre de la variable   tipo_lugar_otro

Descripción             Descripción de otro tipo de lugar

Tipo de variable        Texto

Valores con los que     Variable abierta para los casos en los que el
                        hecho ocurrió en otro lugar no categorizado en la
aparece
                        variable Tipo de lugar, se incluyen sólo los hechos
                        que no pudieron ser recategorizados. Esta
                        variable se ha adecuado para el uso estadístico.



  17. modalidad

Nombre de la variable   modalidad

Descripción             Modalidad utilizada para llevar a cabo el acto

Tipo de variable        Categórica




                                                                          10


## Página 11

Valores con los que
aparece                  Código Descripción
                                  1 Arma de fuego
                                 2 Arma blanca/elemento cortante
                                 3 Sumersión piscina/ mar/ río
                                 4 Envenenamiento
                                 5 Ahorcamiento
                                 6 Se arroja al vacío
                                 7 Se arroja a las vías del ferrocarril
                                 8 Otra modalidad
                                 9 Se incinera
                                99 Sin determinar
Comentarios y           Consultar el Anexo I para ver la definición de
                        cada categoría. La categoría Se incinera ha sido
advertencias
                        incorporada al sistema SNIC- SAT en el año 2021;
                        para los años anteriores se procedió a imputar
                        aquellos registros que correspondan a dicha
                        dimensión de análisis y que se encontraban
                        dentro de la categoría otra_modalidad. Con
                        respecto a la publicación anterior, los casos de
                        asfixia se incluyeron dentro de ahorcamiento (en
                        la publicación anterior estaban en la categoría
                        otros).



  18. modalidad_ampliado

Nombre de la variable   modalidad_ampliado

Descripción             Modalidad utilizada para llevar a cabo el acto –
                        categorías adicionales
Tipo de variable        Texto

Valores con los que     Ahorcamiento/ Asfixia
                        Arma blanca / elemento cortante
aparece
                        Arma de fuego
                        Envenenamiento
                        Otra modalidad
                        Se arroja a las vías de FF.CC.
                        Se arroja al vacío
                        Se arroja bajo rodado
                        (camión/automóvil/colectivo)
                        Se incinera
                        Sin determinar
                        Sumersión en piscina / mar / río
Comentarios y           Creada posteriormente a la carga a partir de la
                        información cargada por las fuerzas de seguridad
advertencias
                        en los campos abiertos. Con respecto a la
                        publicación anterior, los casos de asfixia se
                                                                           11


## Página 12

incluyeron dentro de ahorcamiento (en la
                        publicación anterior estaban en una categoría
                        aparte).



  19. modalidad_otra

Nombre de la variable   modalidad_otra

Descripción             Descripción de otra modalidad utilizada para
                        llevar a cabo el acto
Tipo de variable        Texto

Comentarios y           Esta variable se ha adecuado para el uso
                        estadístico.
advertencias




  20. motivo_origen_registro

Nombre de la variable   motivo_origen_registro

Descripción             Motivo que origina el registro del hecho

Tipo de variable        Categórica

Valores con los que
aparece                  Código      Descripción
                             1       Denuncia particular
                             2       Intervención policial
                             3       Orden Judicial
                            4        Otros (especificar)
                            99       Sin determinar
Comentarios y           Consultar el Anexo I para ver la definición de
                        cada categoría.
advertencias




  21. motivo_origen_registro_otro

Nombre de la variable   motivo_origen_registro_otro

Descripción             Descripción de otro motivo que origina el
                        registro del hecho
Tipo de variable        Texto




                                                                         12


## Página 13

Comentarios y           Se contesta sólo en el caso de haber completado
                        otro en el campo motivo_origen_registro. Esta
advertencias
                        variable se ha adecuado para el uso estadístico.



  22. suicida_sexo

Nombre de la variable   suicida_sexo

Descripción             Sexo del suicida

Tipo de variable        Categórica.

Valores con los que
aparece                  Código       Descripción
                            1         Femenino
                            2         Masculino
                           99         Sin determinar



  23. suicida_tr_edad

Nombre de la variable   Suicida_tr_edad

Descripción             Edad del suicida en tramos

Tipo de variable        Categórica

Valores con los que
aparece                  Código       Descripción
                                      Sin
                            -1        determinar
                             1        4 o menos
                             2        5-9
                             3        10-14
                             4        15-19
                             5        20-24
                             6        25-29
                             7        30-34
                             8        35-39
                             9        40-44
                            10        45-49
                            11        50-54
                            12        55-59
                            13        60-64
                            14        65-69
                            15        70-74

                                                                       13


## Página 14

16      75-79
                             17      80-84
                             18      85-89
                             19      más de 90
Comentarios y           Generada a partir de la variable Edad que es
                        ingresada por las fuerzas de seguridad. Se
advertencias
                        revisan los casos con edad menor a 5 años,
                        recodifican a sin determinar (-1). Sin embargo, no
                        se registraron este tipo de casos.
                        Según estudios específicos en el tema, los casos
                        con edad menor a 5 años no deberían ser
                        considerados suicidios.



  24. suicida_18_años_o_mas

Nombre de la variable   suicida_18_años_o_mas

Descripción             Edad del suicida - 18 años o más

Tipo de variable        Categórica

Valores con los que
aparece                  Código     Descripción
                             1      Sí
                             2      No
                            99      Sin determinar
Comentarios y           Generada a partir de la variable Edad que es
                        ingresada por las fuerzas de seguridad. Se
advertencias
                        revisan los casos con edad menor a 5 años,
                        recodifican a sin determinar (-1). Sin embargo, no
                        se registraron este tipo de casos.
                        Según estudios específicos en el tema, los casos
                        con edad menor a 5 años no deberían ser
                        considerados suicidios.




  25. suicida_clase

Nombre de la variable   suicida_clase

Descripción             Esta variable busca identificar algunos tipos de
                        suicida en función de la relevancia de sus
                        categorías para el análisis de los hechos.
Tipo de variable        Categórica


                                                                           14


## Página 15

Valores con los que         Código Descripción
aparece                        1    Civil
                               3    Policía en servicio
                              4     Seguridad privada
                                    Otra fuerza de
                               5    seguridad
                               6    Civil detenido
                               7    Policía en franco
                               8    Policía retirado
                               9    Policía detenido
                              99    Sin determinación
Comentarios y              Otra fuerza de seguridad incluye: Fuerzas
                           federales de seguridad (Gendarmería Nacional
advertencias
                           Argentina, Policía Federal Argentina, Policía de
                           Seguridad Aeroportuaria y Prefectura Naval
                           Argentina), otras fuerzas de seguridad, personal
                           de custodia o penitenciarios.
                           Consultar el Anexo I para ver la definición de
                           cada categoría.



  26. suicida_clase_otro

Nombre de la variable      suicida_clase_otro

Descripción                Descripción de otra clase de victima

Tipo de variable           Texto

Comentarios y              Se completa sólo en el caso de haber
                           completado "otro" en el campo "suicida_clase".
advertencias
                           Esta variable se ha adecuado para el uso
                           estadístico.




  27. identidad_genero_suicida

Nombre de la variable      Identidad_género_suicida

Descripción                Identidad de género del suicida

Tipo de variable           Categórica.




                                                                              15


## Página 16

Valores con los que
aparece                Código     Descripción
                          1       Varón
                          2       Mujer
                          3       Varón Trans
                                  Mujer
                           4      trans/travestis
                            5     Otro (especificar)
                           99     Sin determinar
Comentarios y         De acuerdo a la Ley de Identidad de Género Nro.
                      26.743, se entiende por identidad de género: “la
advertencias
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
                      Esta variable se incorporó al SNIC en el año 2021
                      en el módulo SAT Homicidios Dolosos y SAT
                      Suicidios. Por lo tanto, para los años 2017-2020 no
                      se cuenta con información para esta variable.




                                                                        16


## Página 17

Anexos




         17


## Página 18

Anexos
Anexo I –Definiciones de variables categóricas

En este apartado se presentan las definiciones de las variables categóricas.



Tipo lugar



1. Vía Pública

Se registran en esta categoría los hechos que ocurrieron en un espacio
público, es decir, aquellos lugares donde las personas tienen el derecho a
circular o, en otras palabras, lugares en los que el paso no puede ser
restringido por criterios de propiedad privada.

No se incluyen en esta categoría los casos en los que no se puede determinar
si se trata de un espacio público o privado, o los casos en los que no se trata
propiamente de un espacio de circulación, como puede suceder con los
descampados, zonas rurales o playas. Tampoco se registran como vía pública
los hechos ocurridos o los hallazgos en ríos, arroyos, lagos o mar. En ambas
situaciones, se registran en Otro lugar especificándolo en el campo siguiente.

2. Domicilio particular

Se considera domicilio particular la residencia temporal o permanente,
urbana o rural, de cualquier persona involucrada en el evento delictivo
(victimas, inculpados o testigos). Se incluyen los casos en los que los hechos
se producen en hoteles o habitaciones de alquiler que funcionan como
lugares de residencia para las personas que no cuentan con otro domicilio
particular. Se incluye también el edificio en sí como zona aledaña de la
propiedad (patios, pasillos, campos, etc.).

3. Vías del ferrocarril

Cuando la muerte se provoca por el arrollamiento del tren.

4. Cárcel o comisaria



                                                                               18


## Página 19

Esta categoría incluye los hechos ocurridos dentro de cualquier tipo de
establecimiento de encierro o privación de la libertad de las personas allí
alojadas. Incluye institutos/centros de detención de personas menores de 18
años.

6. Otro lugar (especificar)

Cuando el hecho ocurrió en un lugar que no está contemplado en las
categorías anteriores. En caso de seleccionar esta opción se debe completar
el campo especificando el lugar.

99. Sin determinar

Esta categoría contempla aquellos casos en los que no se pudo determinar el
lugar en que ocurrió el hecho o se produzco el hallazgo, esto es, que la
información respecto del lugar no fue recolectada.



Modalidad

Esta variable registra el tipo de arma o mecanismo que se utilizó para llevar a
cabo el suicidio pudiendo ser:

1. Arma de fuego

Cuando el hecho es llevado a cabo mediante la utilización de armas de fuego.
Es decir, aquellas armas que tienen propulsión por combustión, como pistola,
revólver, entre otros.

2. Arma blanca/ elemento cortante

Cuando el hecho es llevado a cabo mediante la utilización de elementos corto-
punzantes. Por ejemplo: navaja, cuchillo, entre otros.

3. Sumersión piscina/mar/río

Cuando el hecho es llevado a cabo mediante el ahogamiento.

4. Envenenamiento

Cuando el hecho es llevado a cabo mediante el consumo excesivo de
sustancias potencialmente tóxicas. Entre las posibles sustancias se incluyen
medicamentos, drogas ilegales, gases, productos químicos, venenos, entre
otros.
                                                                             19


## Página 20

5. Ahorcamiento

Cuando el hecho es llevado a cabo mediante la utilización de cualquier
elemento que provoca la muerte por asfixia o falta de aire.

6. Se arroja al vacío

Cuando el hecho es llevado a cabo mediante la precipitación desde una altura
suficiente para provocar la muerte.

7. Se arroja a las vías del ferrocarril

Cuando el hecho es llevado a cabo mediante el arrollamiento del tren.

8. Otra modalidad

Cuando el hecho se produce mediante alguna modalidad no contemplada en
el resto de las categorías. En caso de seleccionar esta opción, es obligatorio
completar el campo especificar.

9. Se incinera

Cuando el hecho es llevado a cabo mediante la utilización de elementos
inflamables que generan quemaduras mortales en la víctima.

99. Sin determinar

Cuando no se conoce el arma o el mecanismo utilizado durante la producción
del hecho delictual.



Motivo que origina el registro del hecho

Se registra en esta variable de qué manera las fuerzas policiales intervinientes
tomaron conocimiento del hecho, pudiendo ser:

1. Denuncia particular

Son aquellos hechos sobre los cuales se toma conocimiento a partir de la
denuncia de una persona, ya sea que se haya radicado en la comisaría o se
haya realizado personalmente a un efectivo en la vía pública o a través de un
sistema formal de toma de denuncias telefónicas u online.

2. Intervención policial



                                                                             20


## Página 21

Son aquellos hechos sobre los cuales se toma conocimiento a partir de la
intervención directa de un policía, ya sea que el efectivo se haya encontrado
patrullando, realizando tareas de prevención o haya intervenido de oficio o en
flagrancia.

3. Orden judicial

Son aquellos hechos sobre los cuales se toma conocimiento a partir del pedido
de intervención por parte de la institución judicial. En el caso de que un hecho
genere más de un pedido de intervención en el marco de una investigación
judicial, solo se registra una vez.

4. Otros

Esta categoría residual se completa en el caso de que, por algún motivo, no
pueda considerarse dentro de las categorías anteriores. En caso de seleccionar
esta opción se especifica el tipo de motivo que origino el registro. Este campo
acepta caracteres alfanuméricos.

99. Sin determinar

En el caso que se desconozca el origen del registro.



Clase

Este campo releva información sobre la condición ciudadana de los suicidas,
en particular la pertenencia a alguna fuerza de seguridad o custodia. En el
caso de que no se pueda determinar que la persona pertenezca o haya
pertenecido a una fuerza de seguridad, entonces se lo considera civil. Para los
civiles se debe identificar si la persona se encontraba detenida o en custodia
del Estado.

En las categorías que refieren a policías, en sus diferentes estados, se
computan los agentes que pertenezcan o hayan pertenecido a una policía
provincial o a la policía de la Ciudad Autónoma de Buenos Aires. Para los
agentes de las fuerzas federales de seguridad (Policía Federal Argentina,
Gendarmería Nacional Argentina, Prefectura Naval Argentina y Policía de
Seguridad Aeroportuaria), otras fuerzas, personal de custodia o penitenciarios,



                                                                              21


## Página 22

se utiliza la categoría “Otra fuerza de seguridad”, y se brinda información
adicional en el campo otro_clase_victima y otro_clase_inculpado.

Se asigna según la categoría correspondiente, pudiendo ser:

      1. Civil
      2. Policía en servicio
      Se debe incluir a cualquier persona que pertenezca a fuerzas policiales
      provinciales y de la CABA.
      4. Seguridad privada
      5. Otra fuerza de seguridad (especificar)
      Fuerzas federales de seguridad (Gendarmería Nacional Argentina,
      Policía Federal Argentina, Policía de Seguridad Aeroportuaria y
      Prefectura Naval Argentina), otras fuerzas de seguridad, personal de
      custodia o penitenciarios. Este campo esta aclarado en el campo
      otro_clase (víctima o inculpado respectivamente).
      6. Civil detenido
      7. Policía en franco
      8. Policía retirado
      9. Policía detenido
      99. Sin determinación



Identidad de género

De acuerdo a la Ley de Identidad de Género Nro. 26.743, se entiende por
identidad de género: “la vivencia interna e individual del género tal como cada
persona la siente, la cual puede corresponder o no con el sexo asignado a
momento del nacimiento, incluyendo la vivencia personal del cuerpo. Esto
puede involucrar la modificación de la apariencia o la función corporal a través
de medios farmacológicos, quirúrgicos o de otra índole, siempre que ello sea
libremente”. Aquí se selecciona según la categoría correspondiente a la tabla
de codificación, pudiendo ser:

1. Varón




                                                                             22


## Página 23

Se trata de la persona que, de acuerdo con su sexo asignado al nacer, fue
registrada como varón y que, en la actualidad, se siente y/o auto percibe como
varón.

2. Mujer

Se trata de la persona que, de acuerdo con su sexo asignado al nacer, fue
registrada como mujer y que, en la actualidad, se siente y/o auto percibe como
mujer.

3. Varón trans

Se trata de la persona que de acuerdo con su sexo asignado al nacer fue
registrada como mujer y que, en la actualidad, se siente y/o auto percibe como
varón trans (independiente de que haya realizado o no la rectificación de su
DNI y/o alguna intervención sobre su cuerpo).

4. Mujer trans o travesti

Mujer trans es aquella que, de acuerdo con su sexo asignado al nacer, fue
registrada como varón y que, en la actualidad, se siente y/o auto percibe como
mujer trans (independientemente de que haya realizado o no la rectificación
de su DNI y/o alguna intervención sobre su cuerpo). Travesti es la persona que
se expresa socialmente con un género distinto a su sexo asignado al nacer y
se siente y/o auto percibe como travesti (independientemente de que haya
realizado o no la rectificación de su DNI y/o alguna intervención sobre su
cuerpo).

5. Otro

Se utiliza esta categoría en el caso de que la persona se siente y/o auto percibe
con una identidad de género distinta a las mencionadas anteriormente. Por
ejemplo: intersexual, queer, no binario. En el campo “Especificar” se debe
indicar la identidad de género con la que se percibe la persona.

99. Sin determinar

Se utiliza cuando no se dispone de información suficiente para determinar la
identidad de género de la persona.




                                                                              23


## Página 24

Para los casos de víctimas de cualquier tipo de muerte violenta, en los que no
puede preguntarse de manera directa por la auto percepción para relevar el
género de la persona, se toma en cuenta:

–     La información provista por el círculo íntimo de la persona (familia,
amigos/as, compañeros/as de trabajo u otros conocidos/as);

–     Su expresión de género: vestimenta que utilizaba, nombre con el que
se identificaba y/o modificaciones corporales.




                                                                           24


## Página 25

Anexo II – Códigos por Jurisdicción

provincia_id   provincia_nombre

02             Ciudad de Buenos Aires

06             Buenos Aires

10             Catamarca

14             Córdoba

18             Corrientes

22             Chaco

26             Chubut

30             Entre Ríos

34             Formosa

38             Jujuy

42             La Pampa

46             La Rioja

50             Mendoza

54             Misiones

58             Neuquén

62             Rio Negro

66             Salta

70             San Juan

74             San Luis

78             Santa Cruz

82             Santa Fe

86             Santiago del Estero

90             Tucumán


                                        25


## Página 26

Tierra del Fuego, Antártida e Islas del Atlántico
           94
                               Sur



       Anexo III – Códigos por departamento2

provincia_id provincia_nombre                     departamento_id            departamento_nombre
06              Buenos Aires                      06854                      25 de Mayo
06              Buenos Aires                      06588                      9 de Julio
06              Buenos Aires                      06007                      Adolfo Alsina
06              Buenos Aires                      06014                      Adolfo Gonzales Chaves
06              Buenos Aires                      06021                      Alberti
06              Buenos Aires                      06028                      Almirante Brown
06              Buenos Aires                      06077                      Arrecifes
06              Buenos Aires                      06035                      Avellaneda
06              Buenos Aires                      06042                      Ayacucho
06              Buenos Aires                      06049                      Azul
06              Buenos Aires                      06056                      Bahía Blanca
06              Buenos Aires                      06063                      Balcarce
06              Buenos Aires                      06070                      Baradero
06              Buenos Aires                      06084                      Benito Juárez
06              Buenos Aires                      06091                      Berazategui
06              Buenos Aires                      06098                      Berisso
06              Buenos Aires                      06105                      Bolívar
06              Buenos Aires                      06112                      Bragado
06              Buenos Aires                      06119                      Brandsen
06              Buenos Aires                      06126                      Campana
06              Buenos Aires                      06134                      Cañuelas
06              Buenos Aires                      06140                      Capitán Sarmiento
06              Buenos Aires                      06147                      Carlos Casares


       2
         La siguiente tabla ha sido actualiza en las categorías de desagregación departamental de la
       Provincia de La Pampa en el año 2023, para los periodos anteriores corresponde contemplar la
       siguiente división político administrativa: Centro (Capital, Catrilo, Loventué y Toay), Norte
       (Chapaleufu, Conhelo, Maracó, Quemú, Rancul, Realicó y Trenel), Oeste (Chalileo, Chical Co,
       Curacó, Limay Mahuida y Puelén), Sur (Atreucó, Caleu, Guatraché, Hucal, Lihuel Calel y Utracan).

                                                                                                    26


## Página 27

06   Buenos Aires   06154   Carlos Tejedor
06   Buenos Aires   06161   Carmen de Areco
06   Buenos Aires   06168   Castelli
06   Buenos Aires   06210   Chacabuco
06   Buenos Aires   06217   Chascomús
06   Buenos Aires   06224   Chivilcoy
06   Buenos Aires   06175   Colon
06   Buenos Aires   06182   Coronel de Marina L. Rosales
06   Buenos Aires   06189   Coronel Dorrego
06   Buenos Aires   06196   Coronel Pringles
06   Buenos Aires   06203   Coronel Suarez
06   Buenos Aires   06231   Daireaux
06   Buenos Aires   06238   Dolores
06   Buenos Aires   06245   Ensenada
06   Buenos Aires   06252   Escobar
06   Buenos Aires   06260   Esteban Echeverría
06   Buenos Aires   06266   Exaltación de la Cruz
06   Buenos Aires   06270   Ezeiza
06   Buenos Aires   06274   Florencio Varela
06   Buenos Aires   06277   Florentino Ameghino
06   Buenos Aires   06280   General Alvarado
06   Buenos Aires   06287   General Alvear
06   Buenos Aires   06294   General Arenales
06   Buenos Aires   06301   General Belgrano
06   Buenos Aires   06308   General Guido
06   Buenos Aires   06315   General Juan Madariaga
06   Buenos Aires   06322   General La Madrid
06   Buenos Aires   06329   General Las Heras
06   Buenos Aires   06336   General Lavalle
06   Buenos Aires   06343   General Paz
06   Buenos Aires   06351   General Pinto
06   Buenos Aires   06357   General Pueyrredón
06   Buenos Aires   06364   General Rodríguez

                                               27


## Página 28

06   Buenos Aires   06371   General San Martin
06   Buenos Aires   06385   General Viamonte
06   Buenos Aires   06392   General Villegas
06   Buenos Aires   06399   Guamini
06   Buenos Aires   06406   Hipólito Yrigoyen
06   Buenos Aires   06408   Hurlingham
06   Buenos Aires   06410   Ituzaingo
06   Buenos Aires   06412   José C. Paz
06   Buenos Aires   06413   Junín
06   Buenos Aires   06420   La Costa
06   Buenos Aires   06427   La Matanza
06   Buenos Aires   06441   La Plata
06   Buenos Aires   06434   Lanús
06   Buenos Aires   06448   Laprida
06   Buenos Aires   06455   Las Flores
06   Buenos Aires   06462   Leandro N. Alem
06   Buenos Aires   06466   Lezama
06   Buenos Aires   06469   Lincoln
06   Buenos Aires   06476   Lobería
06   Buenos Aires   06483   Lobos
06   Buenos Aires   06490   Lomas de Zamora
06   Buenos Aires   06497   Lujan
06   Buenos Aires   06505   Magdalena
06   Buenos Aires   06511   Maipú
06   Buenos Aires   06515   Malvinas Argentinas
06   Buenos Aires   06518   Mar Chiquita
06   Buenos Aires   06525   Marcos Paz
06   Buenos Aires   06532   Mercedes
06   Buenos Aires   06539   Merlo
06   Buenos Aires   06547   Monte
06   Buenos Aires   06553   Monte Hermoso
06   Buenos Aires   06560   Moreno
06   Buenos Aires   06568   Morón

                                                28


## Página 29

06   Buenos Aires   06574   Navarro
06   Buenos Aires   06581   Necochea
06   Buenos Aires   06595   Olavarría
06   Buenos Aires   06602   Patagones
06   Buenos Aires   06609   Pehuajo
06   Buenos Aires   06616   Pellegrini
06   Buenos Aires   06623   Pergamino
06   Buenos Aires   06630   Pila
06   Buenos Aires   06638   Pilar
06   Buenos Aires   06644   Pinamar
06   Buenos Aires   06648   Presidente Perón
06   Buenos Aires   06651   Púan
06   Buenos Aires   06655   Punta Indio
06   Buenos Aires   06658   Quilmes
06   Buenos Aires   06665   Ramallo
06   Buenos Aires   06672   Rauch
06   Buenos Aires   06679   Rivadavia
06   Buenos Aires   06686   Rojas
06   Buenos Aires   06693   Roque Pérez
06   Buenos Aires   06700   Saavedra
06   Buenos Aires   06707   Saladillo
06   Buenos Aires   06721   Salliquelo
06   Buenos Aires   06714   Salto
06   Buenos Aires   06728   San Andrés de Giles
06   Buenos Aires   06735   San Antonio de Areco
06   Buenos Aires   06742   San Cayetano
06   Buenos Aires   06749   San Fernando
06   Buenos Aires   06756   San Isidro
06   Buenos Aires   06760   San Miguel
06   Buenos Aires   06763   San Nicolás
06   Buenos Aires   06770   San Pedro
06   Buenos Aires   06778   San Vicente
06   Buenos Aires   06999   Sin determinar

                                               29


## Página 30

06   Buenos Aires   06784   Suipacha
06   Buenos Aires   06791   Tandil
06   Buenos Aires   06798   Tapalqué
06   Buenos Aires   06805   Tigre
06   Buenos Aires   06812   Tordillo
06   Buenos Aires   06819   Tornquist
06   Buenos Aires   06826   Trenque Lauquen
06   Buenos Aires   06833   Tres Arroyos
06   Buenos Aires   06840   Tres de Febrero
06   Buenos Aires   06847   Tres Lomas
06   Buenos Aires   06861   Vicente López
06   Buenos Aires   06868   Villa Gesell
06   Buenos Aires   06875   Villarino
06   Buenos Aires   06882   Zarate
10   Catamarca      10007   Ambato
10   Catamarca      10014   Ancasti
10   Catamarca      10021   Andalgala
10   Catamarca      10028   Antofagasta de la Sierra
10   Catamarca      10035   Belén
10   Catamarca      10042   Capayan
10   Catamarca      10049   Capital
10   Catamarca      10056   El Alto
10   Catamarca      10063   Fray Mamerto Esquiu
10   Catamarca      10070   La Paz
10   Catamarca      10077   Paclin
10   Catamarca      10084   Poman
10   Catamarca      10091   Santa María
10   Catamarca      10098   Santa Rosa
10   Catamarca      10999   Sin determinar
10   Catamarca      10105   Tinogasta
10   Catamarca      10112   Valle Viejo
22   Chaco          22036   12 de Octubre
22   Chaco          22126   1º de Mayo

                                              30


## Página 31

22   Chaco    22039   2 de Abril
22   Chaco    22168   25 de Mayo
22   Chaco    22105   9 de Julio
22   Chaco    22007   Almirante Brown
22   Chaco    22014   Bermejo
22   Chaco    22028   Chacabuco
22   Chaco    22021   Comandante Fernández
22   Chaco    22043   Fray Justo Santa María de
                      Oro
22   Chaco    22049   General Belgrano
22   Chaco    22056   General Donovan
22   Chaco    22063   General Güemes
22   Chaco    22070   Independencia
22   Chaco    22077   Libertad
22   Chaco    22084   Libertador    General     San
                      Martin
22   Chaco    22091   Maipú
22   Chaco    22098   Mayor Luis J. Fontana
22   Chaco    22112   O' Higgins
22   Chaco    22119   Presidencia de la Plaza
22   Chaco    22133   Quitilipi
22   Chaco    22140   San Fernando
22   Chaco    22147   San Lorenzo
22   Chaco    22154   Sargento Cabral
22   Chaco    22999   Sin determinar
22   Chaco    22161   Tapenaga
26   Chubut   26007   Biedma
26   Chubut   26014   Cushamen
26   Chubut   26021   Escalante
26   Chubut   26028   Florentino Ameghino
26   Chubut   26035   Futaleufu
26   Chubut   26042   Gaiman
26   Chubut   26049   Gastre

                                         31


## Página 32

26   Chubut                 26056   Languieo
26   Chubut                 26063   Martires
26   Chubut                 26070   Paso de Indios
26   Chubut                 26077   Rawson
26   Chubut                 26084   Rio Senguer
26   Chubut                 26091   Sarmiento
26   Chubut                 26999   Sin determinar
26   Chubut                 26098   Tehuelches
26   Chubut                 26105   Telsen
02   Ciudad   Autónoma   de 02001   Comuna 1
     Buenos Aires
02   Ciudad   Autónoma   de 02010   Comuna 10
     Buenos Aires
02   Ciudad   Autónoma   de 02011   Comuna 11
     Buenos Aires
02   Ciudad   Autónoma   de 02012   Comuna 12
     Buenos Aires
02   Ciudad   Autónoma   de 02013   Comuna 13
     Buenos Aires
02   Ciudad   Autónoma   de 02014   Comuna 14
     Buenos Aires
02   Ciudad   Autónoma   de 02015   Comuna 15
     Buenos Aires
02   Ciudad   Autónoma   de 02002   Comuna 2
     Buenos Aires
02   Ciudad   Autónoma   de 02003   Comuna 3
     Buenos Aires
02   Ciudad   Autónoma   de 02004   Comuna 4
     Buenos Aires
02   Ciudad   Autónoma   de 02005   Comuna 5
     Buenos Aires
02   Ciudad   Autónoma   de 02006   Comuna 6
     Buenos Aires


                                                     32


## Página 33

02   Ciudad    Autónoma   de 02007   Comuna 7
     Buenos Aires
02   Ciudad    Autónoma   de 02008   Comuna 8
     Buenos Aires
02   Ciudad    Autónoma   de 02009   Comuna 9
     Buenos Aires
02   Ciudad    Autónoma   de 02999   Sin determinar
     Buenos Aires
14   Córdoba                 14007   Calamuchita
14   Córdoba                 14014   Capital
14   Córdoba                 14021   Colon
14   Córdoba                 14028   Cruz del Eje
14   Córdoba                 14035   General Roca
14   Córdoba                 14042   General San Martin
14   Córdoba                 14049   Ischilin
14   Córdoba                 14056   Juárez Celman
14   Córdoba                 14063   Marcos Juárez
14   Córdoba                 14070   Minas
14   Córdoba                 14077   Pocho
14   Córdoba                 14084   Presidente     Roque   Sáenz
                                     Peña
14   Córdoba                 14091   Punilla
14   Córdoba                 14098   Rio Cuarto
14   Córdoba                 14105   Rio Primero
14   Córdoba                 14112   Rio Seco
14   Córdoba                 14119   Rio Segundo
14   Córdoba                 14126   San Alberto
14   Córdoba                 14133   San Javier
14   Córdoba                 14140   San Justo
14   Córdoba                 14147   Santa María
14   Córdoba                 14999   Sin determinar
14   Córdoba                 14154   Sobremonte
14   Córdoba                 14161   Tercero Arriba


                                                       33


## Página 34

14   Córdoba      14168   Totoral
14   Córdoba      14175   Tulumba
14   Córdoba      14182   Unión
18   Corrientes   18007   Bella Vista
18   Corrientes   18014   Berón de Astrada
18   Corrientes   18021   Capital
18   Corrientes   18028   Concepción
18   Corrientes   18035   Curuzu Cuatia
18   Corrientes   18042   Empedrado
18   Corrientes   18049   Esquina
18   Corrientes   18056   General Alvear
18   Corrientes   18063   General Paz
18   Corrientes   18070   Goya
18   Corrientes   18077   Itati
18   Corrientes   18084   Ituzaingo
18   Corrientes   18091   Lavalle
18   Corrientes   18098   Mburucuya
18   Corrientes   18105   Mercedes
18   Corrientes   18112   Monte Caseros
18   Corrientes   18119   Paso de los Libres
18   Corrientes   18126   Saladas
18   Corrientes   18133   San Cosme
18   Corrientes   18140   San Luis del Palmar
18   Corrientes   18147   San Martin
18   Corrientes   18154   San Miguel
18   Corrientes   18161   San Roque
18   Corrientes   18168   Santo Tome
18   Corrientes   18175   Sauce
18   Corrientes   18999   Sin determinar
30   Entre Ríos   30008   Colon
30   Entre Ríos   30015   Concordia
30   Entre Ríos   30021   Diamante
30   Entre Ríos   30028   Federación

                                               34


## Página 35

30   Entre Ríos   30035   Federal
30   Entre Ríos   30042   Feliciano
30   Entre Ríos   30049   Gualeguay
30   Entre Ríos   30056   Gualeguaychu
30   Entre Ríos   30063   Islas del Ibicuy
30   Entre Ríos   30070   La Paz
30   Entre Ríos   30077   Nogoya
30   Entre Ríos   30084   Paraná
30   Entre Ríos   30088   San Salvador
30   Entre Ríos   30999   Sin determinar
30   Entre Ríos   30091   Tala
30   Entre Ríos   30098   Uruguay
30   Entre Ríos   30105   Victoria
30   Entre Ríos   30113   Villaguay
34   Formosa      34007   Bermejo
34   Formosa      34014   Formosa
34   Formosa      34021   Laishi
34   Formosa      34028   Matacos
34   Formosa      34035   Patiño
34   Formosa      34042   Pilagas
34   Formosa      34049   Pilcomayo
34   Formosa      34056   Pirane
34   Formosa      34063   Ramón Lista
34   Formosa      34999   Sin determinar
38   Jujuy        38007   Cochinoca
38   Jujuy        38014   Dr. Manuel Belgrano
38   Jujuy        38021   El Carmen
38   Jujuy        38028   Humahuaca
38   Jujuy        38035   Ledesma
38   Jujuy        38042   Palpala
38   Jujuy        38049   Rinconada
38   Jujuy        38056   San Antonio
38   Jujuy        38063   San Pedro

                                             35


## Página 36

38   Jujuy      38070   Santa Bárbara
38   Jujuy      38077   Santa Catalina
38   Jujuy      38999   Sin determinar
38   Jujuy      38084   Susques
38   Jujuy      38094   Tilcara
38   Jujuy      38098   Tumbaya
38   Jujuy      38105   Valle Grande
38   Jujuy      38112   Yavi
42   La Pampa   42007   Atreucó
42   La Pampa   42014   Caleu Caleu
42   La Pampa   42021   Capital
42   La Pampa   42028   Catriló
42   La Pampa   42035   Conhelo
42   La Pampa   42042   Curacó
42   La Pampa   42049   Chalileo
42   La Pampa   42056   Chapaleufú
42   La Pampa   42063   Chicalcó
42   La Pampa   42070   Guatraché
42   La Pampa   42077   Hucal
42   La Pampa   42084   Lihuel Calel
42   La Pampa   42091   Limay Mahuida
42   La Pampa   42098   Loventué
42   La Pampa   42105   Maracó
42   La Pampa   42112   Puelén
42   La Pampa   42119   Quemú Ouemú
42   La Pampa   42126   Rancul
42   La Pampa   42133   Realicó
42   La Pampa   42140   Toay
42   La Pampa   42147   Trenel
42   La Pampa   42154   Utracán
42   La Pampa   42999   Sin determinar
46   La Rioja   46007   Arauco
46   La Rioja   46014   Capital

                                         36


## Página 37

46   La Rioja   46021   Castro Barros
46   La Rioja   46028   Chamical
46   La Rioja   46035   Chilecito
46   La Rioja   46042   Coronel Felipe Varela
46   La Rioja   46049   Famatina
46   La Rioja   46056   General Ángel V. Peñaloza
46   La Rioja   46063   General Belgrano
46   La Rioja   46070   General Juan F. Quiroga
46   La Rioja   46077   General Lamadrid
46   La Rioja   46084   General Ocampo
46   La Rioja   46091   General San Martin
46   La Rioja   46098   Independencia
46   La Rioja   46105   Rosario Vera Peñaloza
46   La Rioja   46112   San Blas de los Sauces
46   La Rioja   46119   Sanagasta
46   La Rioja   46999   Sin determinar
46   La Rioja   46126   Vinchina
50   Mendoza    50007   Capital
50   Mendoza    50014   General Alvear
50   Mendoza    50021   Godoy Cruz
50   Mendoza    50028   Guaymallen
50   Mendoza    50035   Junín
50   Mendoza    50042   La Paz
50   Mendoza    50049   Las Heras
50   Mendoza    50056   Lavalle
50   Mendoza    50063   Lujan de Cuyo
50   Mendoza    50070   Maipú
50   Mendoza    50077   Malargüe
50   Mendoza    50084   Rivadavia
50   Mendoza    50091   San Carlos
50   Mendoza    50098   San Martin
50   Mendoza    50105   San Rafael
50   Mendoza    50112   Santa Rosa

                                           37


## Página 38

50   Mendoza    50999   Sin determinar
50   Mendoza    50119   Tunuyan
50   Mendoza    50126   Tupungato
54   Misiones   54119   25 de Mayo
54   Misiones   54007   Apóstoles
54   Misiones   54014   Cainguas
54   Misiones   54021   Candelaria
54   Misiones   54028   Capital
54   Misiones   54035   Concepción
54   Misiones   54042   Eldorado
54   Misiones   54049   General Manuel Belgrano
54   Misiones   54056   Guaraní
54   Misiones   54063   Iguazú
54   Misiones   54070   Leandro N. Alem
54   Misiones   54077   Libertador Gral. San Martin
54   Misiones   54084   Montecarlo
54   Misiones   54091   Obera
54   Misiones   54098   San Ignacio
54   Misiones   54105   San Javier
54   Misiones   54112   San Pedro
54   Misiones   54999   Sin determinar
58   Neuquén    58084   Ñorquin
58   Neuquén    58014   Añelo
58   Neuquén    58007   Alumine
58   Neuquén    58021   Catan Lil
58   Neuquén    58028   Chos Malal
58   Neuquén    58035   Collon Cura
58   Neuquén    58042   Confluencia
58   Neuquén    58049   Huiliches
58   Neuquén    58056   Lacar
58   Neuquén    58063   Loncopue
58   Neuquén    58070   Los Lagos
58   Neuquén    58077   Minas

                                          38


## Página 39

58   Neuquén     58091   Pehuenches
58   Neuquén     58098   Picun Leufu
58   Neuquén     58105   Picunches
58   Neuquén     58999   Sin determinar
58   Neuquén     58112   Zapala
62   Rio Negro   62091   25 de Mayo
62   Rio Negro   62049   9 de Julio
62   Rio Negro   62056   Ñorquincó
62   Rio Negro   62007   Adolfo Alsina
62   Rio Negro   62014   Avellaneda
62   Rio Negro   62021   Bariloche
62   Rio Negro   62028   Conesa
62   Rio Negro   62035   El Cuy
62   Rio Negro   62042   General Roca
62   Rio Negro   62063   Pichi Mahuida
62   Rio Negro   62070   Pilcaniyeu
62   Rio Negro   62077   San Antonio
62   Rio Negro   62999   Sin determinar
62   Rio Negro   62084   Valcheta
66   Salta       66007   Anta
66   Salta       66014   Cachi
66   Salta       66021   Cafayate
66   Salta       66028   Capital
66   Salta       66035   Cerrillos
66   Salta       66042   Chicoana
66   Salta       66049   General Güemes
66   Salta       66056   Gral. José de San Martin
66   Salta       66063   Guachipas
66   Salta       66070   Iruya
66   Salta       66077   La Caldera
66   Salta       66084   La Candelaria
66   Salta       66091   La Poma
66   Salta       66098   La Viña

                                          39


## Página 40

66   Salta      66105   Los Andes
66   Salta      66112   Metan
66   Salta      66119   Molinos
66   Salta      66126   Oran
66   Salta      66131   Rivadavia
66   Salta      66138   Rosario de la Frontera
66   Salta      66145   Rosario de Lerma
66   Salta      66152   San Carlos
66   Salta      66159   Santa Victoria
66   Salta      66999   Sin determinar
70   San Juan   70126   25 de Mayo
70   San Juan   70063   9 de Julio
70   San Juan   70007   Albardon
70   San Juan   70014   Angaco
70   San Juan   70021   Calingasta
70   San Juan   70028   Capital
70   San Juan   70035   Caucete
70   San Juan   70042   Chimbas
70   San Juan   70049   Iglesia
70   San Juan   70056   Jachal
70   San Juan   70070   Pocito
70   San Juan   70077   Rawson
70   San Juan   70084   Rivadavia
70   San Juan   70091   San Martin
70   San Juan   70098   Santa Lucia
70   San Juan   70105   Sarmiento
70   San Juan   70999   Sin determinar
70   San Juan   70112   Ullum
70   San Juan   70119   Valle Fertil
70   San Juan   70133   Zonda
74   San Luis   74007   Ayacucho
74   San Luis   74014   Belgrano
74   San Luis   74021   Chacabuco

                                           40


## Página 41

74   San Luis     74028   Coronel Pringles
74   San Luis     74035   General Pedernera
74   San Luis     74042   Gobernador Dupuy
74   San Luis     74049   Junín
74   San Luis     74056   La Capital
74   San Luis     74063   Libertador      General   San
                          Martin
74   San Luis     74999   Sin determinar
78   Santa Cruz   78007   Corpen Aike
78   Santa Cruz   78014   Deseado
78   Santa Cruz   78021   Güer Aike
78   Santa Cruz   78028   Lago Argentino
78   Santa Cruz   78035   Lago Buenos Aires
78   Santa Cruz   78042   Magallanes
78   Santa Cruz   78049   Rio Chico
78   Santa Cruz   78999   Sin determinar
82   Santa Fe     82077   9 de Julio
82   Santa Fe     82007   Belgrano
82   Santa Fe     82014   Caseros
82   Santa Fe     82021   Castellanos
82   Santa Fe     82028   Constitución
82   Santa Fe     82035   Garay
82   Santa Fe     82042   General López
82   Santa Fe     82049   General Obligado
82   Santa Fe     82056   Iriondo
82   Santa Fe     82063   La Capital
82   Santa Fe     82070   Las Colonias
82   Santa Fe     82084   Rosario
82   Santa Fe     82091   San Cristóbal
82   Santa Fe     82098   San Javier
82   Santa Fe     82105   San Jerónimo
82   Santa Fe     82112   San Justo
82   Santa Fe     82119   San Lorenzo

                                             41


## Página 42

82   Santa Fe                    82126   San Martin
82   Santa Fe                    82999   Sin determinar
82   Santa Fe                    82133   Vera
86   Santiago del Estero         86007   Aguirre
86   Santiago del Estero         86014   Alberdi
86   Santiago del Estero         86021   Atamisqui
86   Santiago del Estero         86028   Avellaneda
86   Santiago del Estero         86035   Banda
86   Santiago del Estero         86042   Belgrano
86   Santiago del Estero         86049   Capital
86   Santiago del Estero         86056   Choya
86   Santiago del Estero         86063   Copo
86   Santiago del Estero         86070   Figueroa
86   Santiago del Estero         86077   General Taboada
86   Santiago del Estero         86084   Guasayan
86   Santiago del Estero         86091   Jiménez
86   Santiago del Estero         86105   Juan F. Ibarra
86   Santiago del Estero         86112   Loreto
86   Santiago del Estero         86119   Mitre
86   Santiago del Estero         86126   Moreno
86   Santiago del Estero         86133   Ojo de Agua
86   Santiago del Estero         86140   Pellegrini
86   Santiago del Estero         86147   Quebrachos
86   Santiago del Estero         86154   Rio Hondo
86   Santiago del Estero         86161   Rivadavia
86   Santiago del Estero         86168   Robles
86   Santiago del Estero         86175   Salavina
86   Santiago del Estero         86182   San Martin
86   Santiago del Estero         86189   Sarmiento
86   Santiago del Estero         86196   Silipica
86   Santiago del Estero         86999   Sin determinar
94   Tierra del Fuego, Antártida 94014   Rio Grande
     e Islas del Atlántico Sur

                                                           42


## Página 43

94   Tierra del Fuego, Antártida 94999   Sin determinar
     e Islas del Atlántico Sur
94   Tierra del Fuego, Antártida 94021   Ushuaia
     e Islas del Atlántico Sur
90   Tucumán                     90007   Burruyacu
90   Tucumán                     90014   Capital
90   Tucumán                     90021   Chicligasta
90   Tucumán                     90028   Cruz Alta
90   Tucumán                     90035   Famailla
90   Tucumán                     90042   Graneros
90   Tucumán                     90049   Juan Bautista Alberdi
90   Tucumán                     90056   La Cocha
90   Tucumán                     90063   Leales
90   Tucumán                     90070   Lules
90   Tucumán                     90077   Monteros
90   Tucumán                     90084   Rio Chico
90   Tucumán                     90091   Simoca
90   Tucumán                     90999   Sin determinar
90   Tucumán                     90098   Tafí del Valle
90   Tucumán                     90105   Tafí Viejo
90   Tucumán                     90112   Trancas
90   Tucumán                     90119   Yerba Buena




                                                          43


## Página 44

44
