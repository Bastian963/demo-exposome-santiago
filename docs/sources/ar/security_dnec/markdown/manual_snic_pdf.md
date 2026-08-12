# manual_snic

- Original local: `data/raw/ar/security_dnec/download_2026-07-12/snic/pdf/manual_snic.pdf`
- Extracted with: `pdftotext -layout`
- PDF pages: 43
- Note: this is a text extraction for review; consult the original PDF for layout-specific ambiguity.


## Página 1

Manual de usuario de la base:

    Sistema Nacional de
Información Criminal (SNIC)



    Dirección Nacional de Estadística Criminal
         Ministerio de Seguridad Nacional




    Dirección Nacional de Estadística Criminal
       Ministerio de Seguridad de la Nación


## Página 2

Índice
Introducción                                                      3
   Consideraciones iniciales                                      3
Bases de datos SNIC                                               3
   Características de la base de datos                            3
   Cómo utilizar la base de datos                                 5
   Criterios de consistencia                                      5
Diccionario de variables                                         7
   Descripción gráfica de variables según tipo de Base SNIC       7
   Definiciones de variables Base SNIC.                           7
Anexos                                                           14
 Anexo I – Metodología de trabajo SNIC                           14
   Cambios en el reporte a SNIC                                  14
   Reconstrucción de series históricas                           14
   Proceso de la reconstrucción de series históricas             15
 Anexo II – Códigos delictuales del SNIC y reporte de víctimas   19
 Anexo III – Códigos por Jurisdicción                            22
 Anexo IV – Códigos por departamento                             23
 Anexo V- Poblaciones                                            39
 Anexo VI- Estimación de tasas nacionales                        42




                                                                  2


## Página 3

Introducción
Consideraciones iniciales

El SNIC es un sistema de recolección y consolidación de datos para el análisis
de información estadística criminal en la Argentina, que tiene como objeto
brindar información sobre hechos presuntamente delictuosos registrados por
las fuerzas policiales provinciales, fuerzas federales de seguridad y otras
entidades oficiales de recepción de denuncias, en todo el ámbito del territorio
de la República Argentina.

El módulo de SNIC-Total de hechos delictuosos releva información agregada
sobre 66 hechos delictuosos, tomando en consideración los tipos delictivos
establecidos por Código Penal de la Nación y Leyes Especiales. Para mayor
información se recomienda leer el Documento metodológico del Sistema
nacional de información criminal (SNIC) disponible en el sitio web1, donde
encontrarán todas las definiciones conceptuales de relevancia para
comprender el funcionamiento operativo del mismo y los criterios
metodológicos sobre las unidades de análisis y el reporte de las mismas.



Bases de datos SNIC
Características de la base de datos

A partir de la base SNIC se elaboran 4 bases con distinto nivel de
desagregación. A continuación, se detallan las características de cada base de
datos, así como su dimensión (en cantidad de registros):

     ●   Base SNIC – Agregado país:
          -   Contiene la información anual sobre hechos y víctimas para el
              total país según tipo de delito (32 tipos delitos para el periodo
              2000-2016; 56 tipos de delitos junto a las agregaciones para el
              periodo 2017-2022 y 66 tipos de delitos para el periodo 2023) y
              sexo de las víctimas.

1
 Para más información se recomienda leer el Documento metodológico del Sistema nacional
de información criminal (SNIC) disponible en el sitio web:
https://www.argentina.gob.ar/seguridad/estadisticascriminales
                                                                                      3


## Página 4

-    Se encuentra publicada para los años 2000-2024.


    ●   Base SNIC – Agregación provincial:
          -    Contiene la información anual sobre hechos y víctimas por
               jurisdicción (para las 23 provincias y la Ciudad Autónoma de
               Buenos Aires) según tipo de delito (32 tipos delitos para el
               periodo 2000-2016; 56 tipos de delitos junto a las agregaciones
               para el periodo 2017-2022 y 66 tipos de delitos para el periodo
               2023) y sexo de las víctimas.
          -    Se encuentra publicada para los años 2000-2024.


    ●   Base SNIC – Agregación departamental:
          -    Contiene la información anual sobre hechos y víctimas por
               departamentos, partidos o comunas (según corresponda) de las
               23 provincias y la Ciudad Autónoma de Buenos Aires según tipo
               de delitos (32 tipos delitos para el periodo 2000-2016; 56 tipos de
               delitos junto a las agregaciones para el periodo 2017-2022 y 66
               tipos de delitos para el periodo 2023) y sexo de las víctimas.
          -    Se encuentra publicada para los años 2000-2024.


    ●   Base SNIC – Agregación departamental con desagregaciones por
        mes:
          -    Contiene la información mensual sobre hechos y víctimas por
               departamentos, partidos o comunas (según corresponda) de las
               23 provincias y la Ciudad Autónoma de Buenos Aires según tipo
               de delitos (32 tipos delitos para el periodo 2000-2016; 56 tipos de
               delitos junto a las agregaciones para el periodo 2017-2022 y 66
               tipos de delitos para el periodo 2023) y sexo de las víctimas.
          -    Se encuentra publicada para los años 2000-2024.



Debido a las dimensiones de las bases, especialmente para las bases con
mayor desagregación, es recomendable utilizar softwares específicos para la
gestión y análisis de datos.


                                                                                4


## Página 5

Cómo utilizar la base de datos

Para utilizar la base SNIC es necesario contar con conocimientos de
procesamiento de bases de datos, manejo de tablas dinámicas y aplicación de
filtros.

La base de datos cuenta con un identificador por año (y mes en caso de la
base de agregación departamental con desagregaciones por mes y sexo), y
delimitación geográfica (país, jurisdicción y departamento de acuerdo al nivel
de desagregación) (uno/a por fila).

Para evitar el doble conteo es importante tener en cuenta que la información
correspondiente al periodo 2017-2023 está contabilizada tanto a nivel de tipo
delictual agregado como desagregado. A modo de ejemplo, partir del año
2017 se desagregó el tipo delictual “14 – Otros delitos contra la libertad” en
“14_1 - Trata de personas simple”, “14_2 - Trata de personas agravado” y “14_3
– Otros delitos contra la libertad n.c.p”. Por ello, si en un año se registraron 10
hechos del tipo delictual 14_1, 20 hechos del tipo delictual 14_2 y 30 hechos del
tipo       delictual   14_3,    también   se   exponen   la   cantidad   de   hechos
correspondientes a tipo delictual 14–Otros delitos contra la libertad con la
suma agregada de los 3 tipos delictuales desagregados (es decir, 60 hechos).
Si se realiza la suma total de hechos y de víctimas sin tener esto en cuenta, se
incurriría en un error, ya que se contabilizarían 120 hechos en lugar de 60. Lo
mismo ocurre con los tipos delictuales 11, 14, 21, 22, 28 y 29.

También es importante tener en cuenta que la cantidad de hechos y de
víctimas a nivel país fue estimada debido a que todavía se registran faltantes
de información para ciertas jurisdicciones. Se realizó para cada una de estas
provincias una interpolación lineal2 para cada delito entre los extremos para
los que sí contaban con datos. Por ese motivo, la suma de las cantidades de
hechos y víctimas de la base a nivel provincial no coincidirá con el total
nacional para ciertos tipos delictuales.

Criterios de consistencia

Los datos del SNIC deben cumplir los siguientes criterios de consistencia
según tres condiciones:

2
    Para más detalle, ver anexo V.
                                                                                   5


## Página 6

1) Completitud territorial: para que los datos sean correctos, todas las
               seccionales de las jurisdicciones y/o provincias deben reportar
               información cada mes, incluso si no hubo delitos. Si no hubo
               ninguno, las seccionales aparecerán con 0 (ceros absolutos).
          2) Cantidad de hechos: todas las seccionales de las jurisdicciones y/o
               provincias deben reportar información sobre los hechos delictivos
               cada mes, incluso si no hubo delitos.
          3) Cantidad de víctimas: todas las seccionales de las jurisdicciones y/o
               provincias deben reportar información cada mes, para aquellos
               delitos que reportan víctimas.3




3
    Para más detalle, ver anexo II.
                                                                                6


## Página 7

Diccionario de variables
En esta sección se presenta la descripción detallada de las variables (o
campos) que contienen las bases usuarias SNIC.

Descripción gráfica de variables según tipo de Base SNIC




Definiciones de variables Base SNIC.

   1.   provincia_id

Nombre de la variable     provincia_id
Descripción               Código de la provincia del hecho
Tipo de variable          Categórica
Comentarios             y Variable construida. Es una variable categórica
advertencias              para la provincia con los códigos INDEC, es útil
                          para realizar cruces con bases de datos de
                          población y otras bases de datos que utilicen la
                          codificación de INDEC. Ver Anexo III.

   2. provincia_nombre

Nombre de la variable     provincia_nombre
Descripción               Jurisdicción y/o provincia donde ocurrió el hecho


                                                                              7


## Página 8

Tipo de variable           Texto
Comentarios             y Ver Anexo III.
advertencias

  3. departamento_id

Nombre de la variable      departamento_id
Descripción                Código    numérico     del      departamento      donde
                           ocurrió el hecho
Tipo de variable           Texto
Valores   con los   que Ver Anexo IV.
aparece



  4. departamento_nombre

Nombre de la variable      Departamento
Descripción                Nombre del departamento geográfico donde
                           ocurrió el hecho
Tipo de variable           Texto
Valores   con los   que Cada jurisdicción se divide en departamento, de
aparece                    acuerdo    a    su   división    política.   En   CABA,
                           corresponde a Comunas y en Provincia de Buenos
                           Aires corresponde a Partidos. Ver valores posibles
                           en Anexo IV.


  5. anio

Nombre de la variable      Anio
Descripción                Año de ocurrencia de los hechos
Tipo de variable           Numérica
Valores   con los   que Valor correspondiente a cada año calendario al
aparece                    que correspondan los hechos reportados.




                                                                                 8


## Página 9

6. mes

Nombre de la variable       Mes
Descripción                 Mes de ocurrencia del hecho
Tipo de variable            Numérica
Valores   con los   que Valores del 1 al 12 correspondientes a cada mes del
aparece                     año. Valor 99 corresponde a mes sin determinar.
Comentarios             y En los casos en que la jurisdicción envió
advertencias                información rectificada a nivel total provincial sin
                            desagregación mensual, departamental y/o por
                            sexo, se asignaron las cantidades de hechos y
                            víctimas    a   mes,     departamento        y   sexo   sin
                            determinar.



  7. codigo_delito_snic_id

Nombre de la variable       codigo_delito_snic_id
Descripción                 Código del tipo de delito sobre el que se informan
                            cantidad de hechos y víctimas de un registro
                            correspondiente a una unidad territorial y temporal (en
                            este caso país y año).
                            Los tipos delictuales en el Anexo Ii.
Tipo de variable            Numérica
Comentarios             y   Se calcula a partir del reporte de las fuentes sobre la
advertencias                cantidad de hechos por motivo que origina el registro,
                            pudiendo    ser:   denuncia    particular,   intervención
                            policial, orden judicial u otro/no consta.




  8. codigo_delito_snic_nombre

Nombre de la variable       codigo_delito_snic_nombre
Descripción                 Código del tipo de delito sobre el que se informan
                            cantidad de hechos y víctimas de un registro

                                                                                      9


## Página 10

correspondiente        a   una     unidad     territorial    y
                                 temporal (en este caso país y año).
                                 Los tipos delictuales se encuentran en el Anexo II.
    Tipo de variable             Texto
    Comentarios              y Se calcula a partir del reporte de las fuentes sobre
    advertencias                 la cantidad de hechos por motivo que origina el
                                 registro,    pudiendo       ser:   denuncia      particular,
                                 intervención policial, orden judicial u otro/no
                                 consta.



      9. cantidad_hechos4

    Nombre de la variable        cantidad_hechos
    Descripción                  Contabiliza la cantidad de hechos de un registro
                                 correspondiente        a   una     unidad     territorial    y
                                 temporal (en este caso país y año).
    Tipo de variable             Numérica
    Comentarios              y Se calcula a partir del reporte de las fuentes sobre
    advertencias                 la cantidad de hechos por motivo que origina el
                                 registro,    pudiendo       ser:   denuncia      particular,
                                 intervención policial, orden judicial u otro/no
                                 consta.



      10. cantidad_victimas5

    Nombre de la variable        cantidad_victimas
    Descripción                  Contabiliza la cantidad de víctimas de un registro
                                 correspondiente        a   una     unidad     territorial    y
                                 temporal (en este caso país y año).
    Tipo de variable             Numérica


4
  La cantidad de hechos a nivel país fue estimada mediante interpolación para ciertos tipos
delictuales para la provincia de Buenos Aires en los años 2009 a 2013 y para la provincia de
Córdoba en los años 2012 y 2013. Por ese motivo, la suma de los totales provinciales no es igual
al total nacional en estos años para ciertos tipos delictuales.
5
  Ver Anexo II.
                                                                                              10


## Página 11

Comentarios             y Se calcula a partir del reporte de las fuentes sobre
advertencias               la cantidad de víctimas por sexo, pudiendo ser:
                           masculino, femenino o no consta. Para más
                           información ver en el Anexo II.



  11. cantidad_victimas_masc

Nombre de la variable      cantidad_victimas_masc
Descripción                Contabiliza la cantidad de víctimas de sexo
                           masculino de un registro correspondiente a una
                           unidad territorial y temporal (en este caso país y
                           año).
Tipo de variable           Numérica



  12. cantidad_victimas_fem

Nombre de la variable      cantidad_victimas_fem
Descripción                Contabiliza la cantidad de víctimas de sexo
                           femenino de un registro correspondiente a una
                           unidad territorial y temporal (en este caso país y
                           año).
Tipo de variable           Numérica



  13. cantidad_victimas_sd

Nombre de la variable      cantidad_victimas_sd
Descripción                Contabiliza la cantidad de víctimas de sexo “no
                           consta” o    “sin determinar” de un registro
                           correspondiente    a   una   unidad   territorial   y
                           temporal (en este caso país y año).
Tipo de variable           Numérica




                                                                               11


## Página 12

14. tasa_hechos6

    Nombre de la variable       tasa_hechos
    Descripción                 Contabiliza la tasa cada 100.000 habitantes de
                                hechos de un registro correspondiente a una
                                unidad territorial y temporal (en este caso país y
                                año).
    Tipo de variable            Numérica



      15. tasa_victimas7

    Nombre de la variable       tasa_victimas
    Descripción                 Contabiliza la tasa cada 100.000 habitantes de
                                víctimas de un registro correspondiente a una
                                unidad territorial y temporal (en este caso país y
                                año).
    Tipo de variable            Numérica



      16. tasa_victimas_masc

    Nombre de la variable       tasa_victimas_masc
    Descripción                 Contabiliza la tasa cada 100.000 habitantes
                                varones de víctimas de sexo masculino de un
                                registro correspondiente a una unidad territorial y
                                temporal (en este caso país y año).
    Tipo de variable            Numérica



      17. tasa_victimas_fem

    Nombre de la variable       tasa_victimas_fem
    Descripción                 Contabiliza la tasa cada 100.000 habitantes
                                mujeres de víctimas de sexo femenino de un



6
    Ver Anexo V- Poblaciones.
7
    Ver Anexo V- Poblaciones.
                                                                                  12


## Página 13

registro correspondiente a una unidad territorial y
                   temporal (en este caso país y año).
Tipo de variable   Numérica




                                                                     13


## Página 14

Anexos
Anexo I – Metodología de trabajo SNIC

Cambios en el reporte a SNIC

Desde su creación en el año 2000 el SNIC experimentó cambios que
impactaron en el reporte de la información:

       Los 32 tipos de delitos originales se desagregaron en 66 categorías8.
       Las exigencias de completitud y consistencia entre módulos fueron
        cada vez más estrictas.
       Los controles de consistencia interna entre hechos y víctimas se
        volvieron más estrictos.
En la presente etapa, la DNEC trabajó en la reconstrucción de la base histórica
del SNIC con el mayor grado de desagregación posible (desagregación de las
bases históricas a nivel departamento, mes y sexo de las víctimas), y de
consistencia (corregir inconsistencias internas y entre módulos).

Reconstrucción de series históricas

La Dirección Nacional de Estadística Criminal (DNEC) está a cargo de la
revisión, validación y análisis de los datos reportados al Sistema Nacional de
Estadística Criminal. En ese marco, durante 2022-2023 se llevó a cabo un
proceso de revisión de las series históricas del SNIC correspondientes al
periodo que va desde el año 2000-2023, con el objetivo de lograr la publicación
de la serie SNIC 2000-2023 consistente, con desagregación por mes,
departamento y sexo de las víctimas para un mayor número de delitos que los
actualmente publicados.

Cabe destacar que la concreción de esta tarea con la publicación de series de
datos representa un gran avance a para el Sistema Nacional de Información
Criminal, logrando que las bases de datos publicadas cuenten con
información mensual, por departamento, mes y sexo. Sólo en los casos en que
la jurisdicción envió información rectificada a nivel anual, agregada
provincialmente o sin desagregación por sexo, las cantidades fueron

8
  A partir de 2023 se incorporan 10 categorías más, desagregaciones de 2 categorías,
completando así 66 categorías.
                                                                                 14


## Página 15

asignadas a departamento, mes y sexo sin determinar según el caso a los fines
de representar la información lo más actualizada posible, sin perder por eso,
la granularidad de la información de las jurisdicciones restantes.

A continuación, se hace breve repaso de los cambios que experimentó el
reporte a SNIC y se detalla el proceso que se llevó a cabo para la
reconstrucción de la base.

Proceso de la reconstrucción de series históricas

El trabajo de reconstrucción constó de varias etapas. En primer lugar, se
recopilaron todas las bases disponibles y se realizó una comparación a los fines
de evaluar cuál base resultaba más idónea para la reconstrucción de la serie
histórica desagregada. Luego, se analizaron las bases y se corrigieron los datos
inconsistentes. Finalmente, se reconstruyó la base desagregada ya lista para
la consulta a las jurisdicciones y publicación.

      -   Etapa 1

      Se indagaron las distintas bases disponibles y las variables que
      contenían cada una. Se evaluaron los desvíos respecto a los totales
      publicados, y la completitud de cada base.

      En términos generales, las bases coincidían entre sí, por lo que se utilizó
      la base que se identificó como más completa, que coincidía en gran
      medida con los totales publicados (para la etapa en que se publicaba)
      o los informes finales por provincia (no publicados).

      Los controles de confiabilidad consistieron en comparar los totales de
      hechos y víctimas de la base más completa con la base publicada. Esto
      solo pudo hacerse para los tipos de delitos que habían sido publicados.
      Además, se controlaron los totales que arrojaron las bases SAT
      Homicidios dolosos con los totales de SNIC.

      -   Etapa 2

      Determinadas qué bases eran las confiables, se construyeron las
      primeras versiones de bases reconstruidas.

      Sobre esas bases reconstruidas se realizó un proceso de revisión y
      corrección de inconsistencias:

                                                                               15


## Página 16

   Inconsistencias internas de hechos y victimas

    Las inconsistencias controladas a nivel departamento y sus
    correcciones fueron:

       o   Cuando la cantidad de hechos era mayor que la cantidad
           de víctimas.

           En este caso, se añadieron las cantidades de víctimas con
           sexo sin determinar necesarias para igualar la cantidad de
           hechos con la cantidad de víctimas.

       o   Cuando la cantidad de víctimas era positiva y la cantidad
           de hechos era cero.

           En este caso, se añadieron las cantidades de hechos con
           origen sin determinar necesarios para igualar la cantidad
           de hechos y víctimas.

       o   Cuando la cantidad de hechos era positiva y la cantidad
           de víctimas era cero.

           En este caso, se añadieron las cantidades de víctimas de
           sexo sin determinar necesarias para igualar la cantidad de
           hechos y víctimas.

   Inconsistencias entre módulos

    Previo a 2017 no era considerado una inconsistencia que la
    cantidad de hechos y víctimas reportada en SAT Homicidios
    dolosos, SAT Muertes viales y SAT Suicidios no coincida con la
    cantidad reportada en los tipos delictuales correspondientes en
    SNIC (delitos de códigos 1, 3 y 31 respectivamente). Para el
    periodo 2000-2011, en los casos donde la base reconstruida
    presentaba menos hechos o víctimas que la publicación, se optó
    por añadir los hechos y víctimas faltantes a un departamento,
    mes y sexo específico en caso de poder ser identificado o, en caso
    contrario, se añadió a un departamento, mes y sexo sin
    determinar.



                                                                    16


## Página 17

-    Etapa 3

        Finalizada la etapa de reconstrucción de las bases se las envió a cada
        jurisdicción y fuerza federal para la revisión y validación de las mismas.
        Luego de esta validación se realizó la consolidación final para la
        publicación.

        Cabe aclarar que la mayor parte de las jurisdicciones no disponía de
        acceso, por diversos motivos, a las bases solicitadas. De forma que en
        muchos casos no se pudo responder a las consultas realizadas.

        -    Etapa 4

        Se procedió al armado de las bases usuarias a nivel país, provincia,
        departamento y mes-departamento, así como el armado y publicación
        del informe correspondiente.

        En los años en los que había faltantes de información se estimaron los
        totales nacionales a partir de la interpolación de los datos en las
        provincias con faltantes:

                No se contaba con información de la provincia de Córdoba para
                 los años 2012 y 2013, por lo que se interpolaron utilizando los
                 valores de 2011 y 20149.
                No se contaba con información de la provincia de Buenos Aires
                 de ciertos delitos para los años 2009 a 2013 por lo que se
                 interpolaron utilizando los valores de 2008 y 201410.

        Cabe aclarar que los totales provinciales estimados para dichos años
        solo fueron calculados a los fines de estimar un total nacional y no
        fueron publicados como totales provinciales en las bases de provincias
        y en la base de departamentos.




9
   Se interpolaron las cantidades de hechos y de víctimas correspondientes a todos los códigos
delictuales de la provincia de provincia de Córdoba para completar los años señalados (2012 y
2013), mientras que los códigos 1 (Homicidios dolosos), 5 (Lesiones dolosas), 13 (Amenazas) y 15,
16, 17 y 18 agrupados (robos y tentativas agrupados), fueron estimados en el año 2018, por lo que
se mantuvieron las estimaciones realizadas.
10
    Se interpolaron las cantidades de hechos y de víctimas correspondientes a los códigos
delictuales 4, 6, 7, 9, 11, 12, 14, 24, 25, 29, 30, y 31 de la provincia de Buenos Aires para completar
los años señalados (2009-2013).
                                                                                                    17


## Página 18

Próximas etapas

La reconstrucción de las series del SNIC tiene como objetivo principal
generar una serie histórica consistente y completa, que sirva como
insumo para análisis posteriores. Este proceso se enmarca dentro de
una estrategia de mejora continua de la calidad de los datos del
sistema. Aquellas jurisdicciones cuyos datos en SNIC tienen valores
atípicos, saltos de nivel y/o faltantes de información se encuentran
trabajando en la reconstrucción de la información, así como en su
desagregación por departamentos, mes y sexo, la cual será incorporada
en las próximas publicaciones.

Por otra parte, es importante continuar trabajando en la reconstrucción
de las series históricas de los restantes módulos del sistema: SAT
Homicidios dolosos, SAT Suicidios, SAT Muertes viales y SAT Delitos
contra la propiedad.




                                                                    18


## Página 19

Anexo II – Códigos delictuales del SNIC y reporte de víctimas

codigo_deli                     codigo_delito_snic_nombre                             Reportan
to_snic_id                                                                            víctimas
     1                                Homicidios dolosos                                 Si

     2                    Homicidios dolosos en grado de tentativa                       Si

     3                           Muertes en Accidentes Viales                            Si

     4                      Homicidios culposos por otros hechos                         Si

     5                                  Lesiones dolosas                                 Si

     6                      Lesiones culposas en Accidentes Viales                       Si

     7                        Lesiones culposas por otros hechos                         Si

     8                         Otros delitos contra las personas                         Si

     9                              Delitos contra el honor                              Si

    10                                    Violaciones                                    Si

     11          Otros delitos contra la integridad sexual (total agrupado)              Si

    11_1                 Tentativa de abuso sexual con acceso carnal                     Si

   11_2                               Abuso sexual simple                                Si

   11_3                             Abuso sexual agravado                                Si

   11_4                   Ciberdelitos sexuales vinculados a menores                     Si

   11_5                    Otros delitos contra la integridad sexual                     Si

    12                            Delitos contra el estado civil                         ///

    13                                     Amenazas                                      ///

    14                Otros delitos contra la libertad (total agrupado)                  Si

   14_1                            Trata de personas simple                              Si

   14_2                           Trata de personas agravado                             Si

   14_3                         Otros delitos contra la libertad                         Si

    15           Robos (excluye los agravados por el resultado de lesiones y/o           ///
                                            muertes)
    16        Tentativas de robo (excluye las agravadas por el res. de lesiones y/o      ///
                                            muerte)
    17            Robos agravados por el resultado de lesiones y/o muertes               ///

    18           Tentativas de robo agravado por el resultado de lesiones y/o            ///
                                            muertes
    19                                       Hurtos                                      ///


                                                                                         19


## Página 20

20                           Tentativas de hurto                          ///

 21          Otros delitos contra la propiedad (total agrupado)            ///

21_1                              Extorsiones                              ///

21_2                         Secuestros extorsivos                         ///

21_3         Estafas y defraudaciones (no incluye virtuales) y usura       ///

21_4            Estafas y defraudaciones asistidas virtualmente            ///

21_5                    Daños (no incluye informáticos)                    ///

21_6      Acceso ilegal a sistemas informáticos y daños informáticos       ///

21_7                   Otros delitos contra la propiedad                   ///

 22         Delitos contra la seguridad pública (total agrupado)           ///

22_1    Fabricación adquisición transferencia y tenencia de explosivos y   ///
                          otros materiales peligrosos
22_2                   Tenencia ilegal de armas de fuego                   ///

22_3                  Portación ilegal de armas de fuego                   ///

22_4       Acopio y fabricación ilegal de armas piezas y municiones        ///

22_5         Entrega y comercialización ilegal de armas de fuego           ///

22_6             Omisión adulteración y supresión de marcaje               ///

22_7               Otros delitos contra la seguridad pública               ///

 23                     Delitos contra el orden público                    ///

 24                 Delitos contra la seguridad de la nación               ///

 25       Delitos contra los poderes públicos y el orden constitucional    ///

 26                 Delitos contra la administración pública               ///

 27                        Delitos contra la fe pública                    ///

 28             Ley 23.737 (estupefacientes- total agrupado)               ///

28_1               Siembra y producción de estupefacientes                 ///

28_10                Otros delitos previstos en la ley 23.737              ///

28_2            Comercialización y entrega de estupefacientes              ///

28_3           Tenencia o entrega atenuada de estupefacientes              ///

28_4               Desvío de Importación de estupefacientes                ///

28_5            Organización y financiación de estupefacientes             ///

28_6                  Tenencia simple de estupefacientes                   ///

28_7    Tenencia simple atenuada para uso personal de estupefacientes      ///

28_8                   Confabulación de estupefacientes                    ///


                                                                           20


## Página 21

28_9                          Contrabando de estupefacientes                 ///

29            Otros delitos previstos en leyes especiales (total agrupado)   ///

29_1                              Ley de residuos peligrosos                 ///

29_2                                       Ley de fauna                      ///

29_3                                    Delitos migratorios                  ///

29_4                          Obstrucción del código aduanero                ///

29_5                                   Contrabando Simple                    ///

29_6                                  Contrabando Agravado                   ///

29_7        Contrabando de elementos nucleares agresivos químicos armas y    ///
                                           municiones
29_8                     Otros delitos previstos en leyes especiales         ///

30                                       Contravenciones                     ///

 31                                   Suicidios (consumados)                 Si

 32                   Delitos contra el orden económico y financiero         ///



  Referencias: /// (no corresponde)




                                                                             21


## Página 22

Anexo III – Códigos por Jurisdicción

provincia_id provincia_nombre

02          Ciudad de Buenos Aires

06          Buenos Aires

10          Catamarca

14          Córdoba

18          Corrientes

22          Chaco

26          Chubut

30          Entre Ríos

34          Formosa

38          Jujuy

42          La Pampa

46          La Rioja

50          Mendoza

54          Misiones

58          Neuquén

62          Rio Negro

66          Salta

70          San Juan

74          San Luis

78          Santa Cruz

82          Santa Fe

86          Santiago del Estero

90          Tucumán

94          Tierra del Fuego, Antártida e Islas del Atlántico Sur




                                                                    22


## Página 23

Anexo IV – Códigos por departamento11

provincia_id provincia_nombre              departamento_id             departamento_nombre
06              Buenos Aires               06854                       25 de Mayo
06              Buenos Aires               06588                       9 de Julio
06              Buenos Aires               06007                       Adolfo Alsina
06              Buenos Aires               06014                       Adolfo Gonzales Chaves
06              Buenos Aires               06021                       Alberti
06              Buenos Aires               06028                       Almirante Brown
06              Buenos Aires               06077                       Arrecifes
06              Buenos Aires               06035                       Avellaneda
06              Buenos Aires               06042                       Ayacucho
06              Buenos Aires               06049                       Azul
06              Buenos Aires               06056                       Bahía Blanca
06              Buenos Aires               06063                       Balcarce
06              Buenos Aires               06070                       Baradero
06              Buenos Aires               06084                       Benito Juárez
06              Buenos Aires               06091                       Berazategui
06              Buenos Aires               06098                       Berisso
06              Buenos Aires               06105                       Bolívar
06              Buenos Aires               06112                       Bragado
06              Buenos Aires               06119                       Brandsen
06              Buenos Aires               06126                       Campana
06              Buenos Aires               06134                       Cañuelas
06              Buenos Aires               06140                       Capitán Sarmiento
06              Buenos Aires               06147                       Carlos Casares
06              Buenos Aires               06154                       Carlos Tejedor
06              Buenos Aires               06161                       Carmen de Areco
06              Buenos Aires               06168                       Castelli
06              Buenos Aires               06210                       Chacabuco
06              Buenos Aires               06217                       Chascomús
06              Buenos Aires               06224                       Chivilcoy
06              Buenos Aires               06175                       Colon


  11
    La siguiente tabla ha sido actualiza en las categorías de desagregación departamental de la
  Provincia de La Pampa en el año 2023, para los periodos anteriores corresponde contemplar la
  siguiente división político administrativa: Centro (Capital, Catrilo, Loventué y Toay), Norte
  (Chapaleufu, Conhelo, Maracó, Quemú, Rancul, Realicó y Trenel), Oeste (Chalileo, Chical Co,
  Curacó, Limay Mahuida y Puelén), Sur (Atreucó, Caleu, Guatraché, Hucal, Lihuel Calel y Utracan).

                                                                                               23


## Página 24

Coronel de Marina L.
06   Buenos Aires   06182
                            Rosales
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

                                                    24


## Página 25

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

                                                  25


## Página 26

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

                                                  26


## Página 27

10   Catamarca   10035   Belén
10   Catamarca   10042   Capayan
10   Catamarca   10049   Capital
10   Catamarca   10056   El Alto
10   Catamarca   10063   Fray Mamerto Esquiu
10   Catamarca   10070   La Paz
10   Catamarca   10077   Paclin
10   Catamarca   10084   Poman
10   Catamarca   10091   Santa María
10   Catamarca   10098   Santa Rosa
10   Catamarca   10999   Sin determinar
10   Catamarca   10105   Tinogasta
10   Catamarca   10112   Valle Viejo
22   Chaco       22036   12 de Octubre
22   Chaco       22126   1º de Mayo
22   Chaco       22039   2 de Abril
22   Chaco       22168   25 de Mayo
22   Chaco       22105   9 de Julio
22   Chaco       22007   Almirante Brown
22   Chaco       22014   Bermejo
22   Chaco       22028   Chacabuco
22   Chaco       22021   Comandante Fernández
                         Fray Justo Santa María de
22   Chaco       22043
                         Oro
22   Chaco       22049   General Belgrano
22   Chaco       22056   General Donovan
22   Chaco       22063   General Güemes
22   Chaco       22070   Independencia
22   Chaco       22077   Libertad
                         Libertador General San
22   Chaco       22084
                         Martin
22   Chaco       22091   Maipú
22   Chaco       22098   Mayor Luis J. Fontana
22   Chaco       22112   O' Higgins
22   Chaco       22119   Presidencia de la Plaza
22   Chaco       22133   Quitilipi
22   Chaco       22140   San Fernando

                                              27


## Página 28

22   Chaco                22147   San Lorenzo
22   Chaco                22154   Sargento Cabral
22   Chaco                22999   Sin determinar
22   Chaco                22161   Tapenaga
26   Chubut               26007   Biedma
26   Chubut               26014   Cushamen
26   Chubut               26021   Escalante
26   Chubut               26028   Florentino Ameghino
26   Chubut               26035   Futaleufu
26   Chubut               26042   Gaiman
26   Chubut               26049   Gastre
26   Chubut               26056   Languieo
26   Chubut               26063   Martires
26   Chubut               26070   Paso de Indios
26   Chubut               26077   Rawson
26   Chubut               26084   Rio Senguer
26   Chubut               26091   Sarmiento
26   Chubut               26999   Sin determinar
26   Chubut               26098   Tehuelches
26   Chubut               26105   Telsen
     Ciudad Autónoma de
02                        02001   Comuna 1
     Buenos Aires
     Ciudad Autónoma de
02                        02010   Comuna 10
     Buenos Aires
     Ciudad Autónoma de
02                        02011   Comuna 11
     Buenos Aires
     Ciudad Autónoma de
02                        02012   Comuna 12
     Buenos Aires
     Ciudad Autónoma de
02                        02013   Comuna 13
     Buenos Aires
     Ciudad Autónoma de
02                        02014   Comuna 14
     Buenos Aires
     Ciudad Autónoma de
02                        02015   Comuna 15
     Buenos Aires
     Ciudad Autónoma de
02                        02002   Comuna 2
     Buenos Aires



                                                    28


## Página 29

Ciudad Autónoma de
02                        02003   Comuna 3
     Buenos Aires
     Ciudad Autónoma de
02                        02004   Comuna 4
     Buenos Aires
     Ciudad Autónoma de
02                        02005   Comuna 5
     Buenos Aires
     Ciudad Autónoma de
02                        02006   Comuna 6
     Buenos Aires
     Ciudad Autónoma de
02                        02007   Comuna 7
     Buenos Aires
     Ciudad Autónoma de
02                        02008   Comuna 8
     Buenos Aires
     Ciudad Autónoma de
02                        02009   Comuna 9
     Buenos Aires
     Ciudad Autónoma de
02                        02999   Sin determinar
     Buenos Aires
14   Córdoba              14007   Calamuchita
14   Córdoba              14014   Capital
14   Córdoba              14021   Colon
14   Córdoba              14028   Cruz del Eje
14   Córdoba              14035   General Roca
14   Córdoba              14042   General San Martin
14   Córdoba              14049   Ischilin
14   Córdoba              14056   Juárez Celman
14   Córdoba              14063   Marcos Juárez
14   Córdoba              14070   Minas
14   Córdoba              14077   Pocho
                                  Presidente Roque Sáenz
14   Córdoba              14084
                                  Peña
14   Córdoba              14091   Punilla
14   Córdoba              14098   Rio Cuarto
14   Córdoba              14105   Rio Primero
14   Córdoba              14112   Rio Seco
14   Córdoba              14119   Rio Segundo
14   Córdoba              14126   San Alberto
14   Córdoba              14133   San Javier
14   Córdoba              14140   San Justo

                                                       29


## Página 30

14   Córdoba      14147   Santa María
14   Córdoba      14999   Sin determinar
14   Córdoba      14154   Sobremonte
14   Córdoba      14161   Tercero Arriba
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

                                                30


## Página 31

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
38   Jujuy        38070   Santa Bárbara
38   Jujuy        38077   Santa Catalina
38   Jujuy        38999   Sin determinar
38   Jujuy        38084   Susques

                                                31


## Página 32

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
46   La Rioja   46021   Castro Barros
46   La Rioja   46028   Chamical
46   La Rioja   46035   Chilecito
46   La Rioja   46042   Coronel Felipe Varela
46   La Rioja   46049   Famatina
                        General Ángel V.
46   La Rioja   46056
                        Peñaloza
46   La Rioja   46063   General Belgrano

                                            32


## Página 33

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

                                             33


## Página 34

54   Misiones    54056   Guaraní
54   Misiones    54063   Iguazú
54   Misiones    54070   Leandro N. Alem
                         Libertador Gral. San
54   Misiones    54077
                         Martin
54   Misiones    54084   Montecarlo
54   Misiones    54091   Obera
54   Misiones    54098   San Ignacio
54   Misiones    54105   San Javier
54   Misiones    54112   San Pedro
54   Misiones    54999   Sin determinar
58   Neuquén     58084   Ñorquin
58   Neuquén     58014   Añelo
58   Neuquén     58007   Alumine
58   Neuquén     58021   Catan Lil
58   Neuquén     58028   Chos Malal
58   Neuquén     58035   Collon Cura
58   Neuquén     58042   Confluencia
58   Neuquén     58049   Huiliches
58   Neuquén     58056   Lacar
58   Neuquén     58063   Loncopue
58   Neuquén     58070   Los Lagos
58   Neuquén     58077   Minas
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

                                                34


## Página 35

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
66   Salta       66105   Los Andes
66   Salta       66112   Metan
66   Salta       66119   Molinos
66   Salta       66126   Oran
66   Salta       66131   Rivadavia
66   Salta       66138   Rosario de la Frontera
66   Salta       66145   Rosario de Lerma
66   Salta       66152   San Carlos
66   Salta       66159   Santa Victoria
66   Salta       66999   Sin determinar
70   San Juan    70126   25 de Mayo
70   San Juan    70063   9 de Julio
70   San Juan    70007   Albardon
70   San Juan    70014   Angaco
70   San Juan    70021   Calingasta
70   San Juan    70028   Capital
70   San Juan    70035   Caucete
70   San Juan    70042   Chimbas

                                              35


## Página 36

70   San Juan     70049   Iglesia
70   San Juan     70056   Jachal
70   San Juan     70070   Pocito
70   San Juan     70077   Rawson
70   San Juan     70084   Rivadavia
70   San Juan     70091   San Martin
70   San Juan     70098   Santa Lucia
70   San Juan     70105   Sarmiento
70   San Juan     70999   Sin determinar
70   San Juan     70112   Ullum
70   San Juan     70119   Valle Fertil
70   San Juan     70133   Zonda
74   San Luis     74007   Ayacucho
74   San Luis     74014   Belgrano
74   San Luis     74021   Chacabuco
74   San Luis     74028   Coronel Pringles
74   San Luis     74035   General Pedernera
74   San Luis     74042   Gobernador Dupuy
74   San Luis     74049   Junín
74   San Luis     74056   La Capital
                          Libertador General San
74   San Luis     74063
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

                                              36


## Página 37

82   Santa Fe              82042   General López
82   Santa Fe              82049   General Obligado
82   Santa Fe              82056   Iriondo
82   Santa Fe              82063   La Capital
82   Santa Fe              82070   Las Colonias
82   Santa Fe              82084   Rosario
82   Santa Fe              82091   San Cristóbal
82   Santa Fe              82098   San Javier
82   Santa Fe              82105   San Jerónimo
82   Santa Fe              82112   San Justo
82   Santa Fe              82119   San Lorenzo
82   Santa Fe              82126   San Martin
82   Santa Fe              82999   Sin determinar
82   Santa Fe              82133   Vera
86   Santiago del Estero   86007   Aguirre
86   Santiago del Estero   86014   Alberdi
86   Santiago del Estero   86021   Atamisqui
86   Santiago del Estero   86028   Avellaneda
86   Santiago del Estero   86035   Banda
86   Santiago del Estero   86042   Belgrano
86   Santiago del Estero   86049   Capital
86   Santiago del Estero   86056   Choya
86   Santiago del Estero   86063   Copo
86   Santiago del Estero   86070   Figueroa
86   Santiago del Estero   86077   General Taboada
86   Santiago del Estero   86084   Guasayan
86   Santiago del Estero   86091   Jiménez
86   Santiago del Estero   86105   Juan F. Ibarra
86   Santiago del Estero   86112   Loreto
86   Santiago del Estero   86119   Mitre
86   Santiago del Estero   86126   Moreno
86   Santiago del Estero   86133   Ojo de Agua
86   Santiago del Estero   86140   Pellegrini
86   Santiago del Estero   86147   Quebrachos
86   Santiago del Estero   86154   Rio Hondo
86   Santiago del Estero   86161   Rivadavia
86   Santiago del Estero   86168   Robles

                                                      37


## Página 38

86   Santiago del Estero     86175   Salavina
86   Santiago del Estero     86182   San Martin
86   Santiago del Estero     86189   Sarmiento
86   Santiago del Estero     86196   Silipica
86   Santiago del Estero     86999   Sin determinar
     Tierra del Fuego,
94   Antártida e Islas del   94014   Rio Grande
     Atlántico Sur
     Tierra del Fuego,
94   Antártida e Islas del   94999   Sin determinar
     Atlántico Sur
     Tierra del Fuego,
94   Antártida e Islas del   94021   Ushuaia
     Atlántico Sur
90   Tucumán                 90007   Burruyacu
90   Tucumán                 90014   Capital
90   Tucumán                 90021   Chicligasta
90   Tucumán                 90028   Cruz Alta
90   Tucumán                 90035   Famailla
90   Tucumán                 90042   Graneros
90   Tucumán                 90049   Juan Bautista Alberdi
90   Tucumán                 90056   La Cocha
90   Tucumán                 90063   Leales
90   Tucumán                 90070   Lules
90   Tucumán                 90077   Monteros
90   Tucumán                 90084   Rio Chico
90   Tucumán                 90091   Simoca
90   Tucumán                 90999   Sin determinar
90   Tucumán                 90098   Tafí del Valle
90   Tucumán                 90105   Tafí Viejo
90   Tucumán                 90112   Trancas
90   Tucumán                 90119   Yerba Buena




                                                         38


## Página 39

Anexo V- Poblaciones

Para la publicación del presente informe, así como de las bases usuarias a nivel
país, provincia y departamento anual, se realizó el cálculo de las tasas 12 cada
100 mil habitantes:




La población total es publicada por el Instituto Nacional de Estadística y
Censos (INDEC) a partir de proyecciones realizadas de forma posterior a cada
censo poblacional.

Es importante resaltar que dicho organismo no cuenta con una serie
publicada de población total por año para el periodo considerado.

Las últimas proyecciones de población realizadas por el INDEC fueron las
siguientes:

        Proyección de población 1990. Publicado en 1995 y 1996, basada en
         censo 1991.

        Proyección de población 2001. Publicado en 2005, basada en censo
         2001.

        Proyección de población 2010. Publicado en 2014, basada en censo
         2010.




12
  No son calculadas las tasas correspondientes al tipo delictual 31 - Suicidios consumados,
debido a que no se cuenta con la proyección de población por departamento de población
mayor a 5 años.
En el caso de departamentos, partidos o comunas con una población menor a 50.000
habitantes, la tasa debe ser analizada con precaución, a fin de evitar distorsiones en la
interpretación de los datos.
                                                                                        39


## Página 40

Gráfico 1. Comparación de proyecciones de población. República
Argentina. Años 1990-2025.

 50.000.000               Proyección 1990         Proyección 2001        Proyección 2010

 48.000.000      Censo 1991                 Censo 2001              Censo 2010
 46.000.000
 44.000.000
 42.000.000
 40.000.000
 38.000.000
 36.000.000
 34.000.000
 32.000.000
 30.000.000   1990
                1991
               1992
               1993
               1994
               1995
               1996
               1997
              1998
               1999
              2000
               2001
              2002
              2003
              2004
              2005
              2006
              2007
              2008
              2009
               2010
                2011
               2012
               2013
               2014
               2015
               2016
               2017
               2018
               2019
              2020
               2021
               2022
               2023
              2024
              2025


Fuente: DNEC sobre la base de INDEC.

Producto de distintos factores, tales como los movimientos migratorios,
cambios en las tasas de fecundidad, mortalidad, entre otros, las poblaciones
proyectadas difieren de las poblaciones efectivamente medidas en los censos
de población posteriores. Este problema se acrecienta cuando se analizan
subdivisiones administrativas y en grupos particulares de la población. Es
decir, las proyecciones de población resultan inconsistentes entre sí.

Por ese motivo, a los fines de evitar saltos discretos en las tasas delictivas
producto de las inconsistencias entre las proyecciones poblacionales, la DNEC
realizó un empalme de las series poblacionales a nivel país, provincia y
departamento con desagregación por grupo etario y sexo:

      Para la serie de población del periodo 2000-2009 se realizó un
       empalme entre las poblaciones base de las proyecciones de población
       1991, 2001 y 2010.
      Para la serie de población del periodo 2010-2023 se utilizó la proyección
       de población 2010-2040 publicada por INDEC.
Para este empalme se realizó una interpolación para cada una de las
subdivisiones administrativas (país, provincia y departamento) y, para grupo
particular de población necesario para el cálculo de tasas (a nivel país y



                                                                                           40


## Página 41

provincia, grupos de varones, de mujeres y de mayores de 5 años)13, se calculó
la población de cada año suponiendo una tasa de variación constante entre
las poblaciones base de cada proyección. De forma que cada población base
de una proyección alcanza la próxima población base evolucionando a una
tasa de evolución constante. Además, se verificó la consistencia del empalme.

Gráfico 2. Serie de población empalmada y proyecciones. República
Argentina. Años 1991-2025.

     50.000.000
                           Proyección 1990   Proyección 2001   Proyección 2010   Serie empalmada
     48.000.000
     46.000.000
     44.000.000
     42.000.000
     40.000.000
     38.000.000
     36.000.000
     34.000.000
     32.000.000
     30.000.000   1990
                    1991
                   1992
                   1993
                   1994
                   1995
                   1996
                   1997
                  1998
                   1999
                  2000
                   2001
                  2002
                  2003
                  2004
                  2005
                  2006
                  2007
                  2008
                  2009
                   2010
                    2011
                   2012
                   2013
                   2014
                   2015
                   2016
                   2017
                   2018
                   2019
                  2020
                   2021
                   2022
                   2023
                  2024
                  2025


Fuente: DNEC sobre la base de INDEC.




 La desagregación a nivel departamental por grupo etario y sexo se publicó por primera vez a
13

partir de la proyección 2010-2040, por lo que no se cuenta con este nivel de desagregación para
años previos a 2010.
                                                                                              41


## Página 42

Anexo VI- Estimación de tasas nacionales

Como se mencionó previamente, todavía se registran faltantes de
información para ciertas jurisdicciones.

Para los códigos 1 (Homicidios dolosos), 5 (Lesiones dolosas), 13 (Amenazas) y
15, 16, 17 y 18 agrupados (robos y tentativas agrupados), reconstruidos en el año
2018, se cuenta con información completa a nivel provincial para todas las
jurisdicciones.

Para el resto de los códigos la información no es completa para el total de las
jurisdicciones. En particular, la información faltante es la correspondiente a:

      Provincia de Buenos Aires. Años 2009 a 2013. Algunos códigos fueron
       informados el año 2019 a nivel departamental por año, mientras que,
       para otros (códigos 4, 6, 7, 9, 11, 12, 14, 24, 25, 29, 30, y 31), solo se cuenta
       con la información aportada por las Fuerzas Federales.
      Provincia de Córdoba. Años 2012 y 2013. Solo se cuenta con información
       parcial (algunos meses del año) de dicho periodo y de Fuerzas
       Federales de todo el año.
Debido a la importante participación de estas jurisdicciones en el total
nacional, los faltantes de información para cada delito provocaban saltos
discretos en el agregado nacional que podían dificultar el análisis. Por esta
razón, y debido a que no se pudo obtener por parte de las provincias
involucradas los faltantes de información, se realizó para cada una de estas
provincias una interpolación lineal para cada delito entre los extremos para los
que sí contaban con datos, a los fines de estimar el total de hechos y de
víctimas a nivel país, junto a su correspondiente tasa.

Es importante aclarar que la interpolación de la cantidad de hechos y de
víctimas fue realizada a nivel provincial, solo a los fines de estimar una tasa
nacional, y no será publicada dentro de la serie provincial (ya que sólo se
publica para cada provincia la información reportada por las mismas,
consolidada y revisada por la DNEC, y posteriormente validada por cada
jurisdicción).

Finalmente, destacar que la Provincia de Buenos Aires se encuentra
trabajando en la reconstrucción de esta información faltante.

                                                                                     42


## Página 43

43
