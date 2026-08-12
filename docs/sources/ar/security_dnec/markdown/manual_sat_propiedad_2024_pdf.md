# manual_sat_propiedad_2024

- Original local: `data/raw/ar/security_dnec/download_2026-07-12/sat/pdf/manual_sat_propiedad_2024.pdf`
- Extracted with: `pdftotext -layout`
- PDF pages: 36
- Note: this is a text extraction for review; consult the original PDF for layout-specific ambiguity.


## Página 1

Manual de usuario de la base:

Sistema de Alerta Temprana

 Delitos contra la propiedad

        (SAT Propiedad)




     Dirección
     Dirección Nacional
                Nacional de
                          de Estadística
                             Estadística Criminal
                                         Criminal
         Ministerio de Seguridad de la Nación
         Ministerio de Seguridad de la Nación


## Página 2

Índice
Introducción                                                         3
Base de datos SAT PROP                                               3
   Características de la base de datos                               3
   Cómo utilizar la base de datos                                    4
   Criterios de consistencia                                         4
Diccionario de variables                                             4
   Identificadores geográficos                                       5
   Identificadores temporales                                        6
   Identificadores de tipo de delito                                 6
   Cantidad de total hechos                                          7
   Cantidad de hechos según inculpados conocidos o desconocidos      7
   Cantidad de hechos según tipo de lugar                            8
   Cantidad de hechos según tipo de arma                             10
   Cantidad de hechos según motivo que origina el registro del hecho 11
   Cantidad de hechos según gravedad                                 13
   Cantidad de inculpados según sexo                                14
   Cantidad de inculpados según rango etario                         15
Anexos                                                              17
 Anexo I – Códigos delictuales del SAT Propiedad                     17
 Anexo II – Códigos por Jurisdicción                                18
 Anexo III – Códigos por departamento                                19




                                                                      2


## Página 3

Introducción
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
nacional de información criminal (SNIC) disponible en el sitio web1.



Base de datos SAT PROP
Características de la base de datos

La base de datos contiene información mensual sobre hechos e inculpados
(en caso de contar con información sobre su edad o sexo), por departamentos,
partidos o comunas (según corresponda) de las 23 provincias y la Ciudad
Autónoma de Buenos Aires según tipo de delitos del SAT Propiedad (8 tipos
de delitos). En la misma base se incluyen los registros correspondientes a
todas las víctimas y a todos los inculpados identificados en cada hecho. Para
trabajar con esta base de datos se debe tener en cuenta la dimensión de la
misma ya que contiene 358.462 registros y 33 variables de caracterización de
los hechos y de los inculpados. Es recomendable utilizar softwares específicos
para la gestión y análisis de datos.




1
  Para mayor información se recomienda leer el Documento metodológico del
Sistema nacional de información criminal (SNIC) disponible en el sitio web:
https://www.argentina.gob.ar/seguridad/estadisticascriminales.
                                                                             3


## Página 4

Cómo utilizar la base de datos

Para utilizar la base SAT Propiedad es necesario contar con conocimientos de
procesamiento de bases de datos o tablas dinámicas y de realización de filtros.

Dentro de la base de datos, cada fila corresponde a la cantidad de hechos
registrados en una unidad de análisis, es decir, un mes, departamento y delito
específico.

Criterios de consistencia

      Los datos del SNIC deben cumplir los siguientes criterios de
consistencia según las siguientes condiciones:
      1) Cantidad de hechos: La cantidad de hechos (Hechos con inculpados
          conocidos + Hechos con inculpados desconocidos) debe ser igual a
          la cantidad de hechos según tipo de lugar (hechos en vía pública +
          hechos en establecimientos comerciales/públicos + hechos en
          domicilio en particular + sin determinar ), a la cantidad de hechos
          según tipo de arma (con arma de fuego + con otra arma + sin arma
          + sin determinar) y a la cantidad de hechos según motivo que
          origina el registro del hecho (Denuncia particular + Intervención
          policial + Orden Judicial + Otros/No consta)
      2) La cantidad de inculpados según sexo (Masculino + Femenino + No
          consta) debe ser igual a la cantidad de inculpados según edades
          (Menores de 16 años + De 16 y 17 años + De 18 años y más + No consta)
          y debe ser mayor o igual a la cantidad de hechos con inculpados
          conocidos.



Diccionario de variables
En esta sección se presenta la descripción detallada de las variables (o
campos) que contienen la base usuaria de SAT Propiedad desagregada por
jurisdicción y/o provincia, departamento y mensual.




                                                                             4


## Página 5

Identificadores geográficos



   1.   provincia_id

Nombre de la variable       provincia_id
Descripción                 Código de la provincia donde ocurrió el hecho
Tipo de variable            Categórica
Comentarios              y Variable construida. Es una variable categórica
advertencias               para la provincia con los códigos INDEC, es útil
                           para realizar cruces con bases de datos de
                           población y otras bases de datos que utilicen la
                           codificación de INDEC. Ver Anexo II.



   2. provincia_nombre

Nombre de la variable       provincia_nombre
Descripción                 Jurisdicción y/o provincia donde ocurrió el hecho
Tipo de variable            Texto
Comentarios              y Ver Anexo II.
advertencias



   3. departamento_id

Nombre de la variable       departamento_id
Descripción                 Código   numérico    del   departamento    donde
                            ocurrió el hecho
Tipo de variable            Texto
Valores con los        que Ver Anexo III.
aparece



   4. departamento_nombre

Nombre de la variable       departamento_nombre
Descripción                 Nombre del departamento geográfico donde
                            ocurrió el hecho
Tipo de variable            Texto

                                                                                5


## Página 6

Valores con los    que Cada jurisdicción se divide en departamento, de
 aparece                acuerdo a su división política. En CABA,
                        corresponde a Comunas y en Provincia de Buenos
                        Aires corresponde a Partidos. Ver valores posibles
                        en Anexo III.


Identificadores temporales



   5. anio

 Nombre de la variable    anio
 Descripción              Año de ocurrencia de los hechos
 Tipo de variable         Numérica
 Valores con los    que Valor correspondiente a cada año calendario al
 aparece                que correspondan los hechos reportados.



   6. mes

 Nombre de la variable    mes
 Descripción            Mes de ocurrencia del hecho
 Tipo de variable       Numérica
 Valores con los    que Valores del 1 al 12 correspondientes a cada mes del
 aparece                año. Valor 99 corresponde a mes sin determinar.



Identificadores de tipo de delito

   7. codigo_delito_sat_prop

 Nombre de la variable    codigo_delito_sat_prop
 Descripción              Código del tipo de delito de SAT Propiedad sobre
                          el que se informan cantidad de hechos e
                          inculpados de un registro correspondiente a una
                          unidad territorial y temporal (departamento -
                          mes).
                          Los tipos delictuales se encuentran descriptos en
                          el en el Anexo I.
 Tipo de variable         Numérica




                                                                          6


## Página 7

8. nombre_delito_sat_prop

Nombre de la variable      nombre_delito_sat_prop
Descripción                Nombre del tipo de delito de SAT Propiedad
                           sobre el que se informan cantidad de hechos e
                           inculpados de un registro correspondiente a una
                           unidad territorial y temporal (departamento -
                           mes).
Tipo de variable           Texto


Cantidad de hechos según sus características

Cantidad de total hechos

   7. cantidad_hechos

Nombre de la variable      cantidad_hechos
Descripción                Contabiliza la cantidad total de hechos de un
                           registro correspondiente a una unidad territorial
                           y temporal (departamento - mes).
Tipo de variable           Numérica
Comentarios y              Se calcula a partir de la suma de hechos según
advertencias               inculpados conocidos y hechos según inculpados
                           desconocidos (únicas variables de reporte
                           obligatorio hasta el año 2023).



Cantidad de hechos según inculpados conocidos o desconocidos

   8. cantidad_hechos_inc_conocido

Nombre de la variable      cantidad_hechos_inc_conocido
Descripción                Esta variable contabiliza la cantidad de hechos
                           con inculpados conocidos de la clasificación de
                           hechos según inculpados conocidos o
                           desconocidos. Es decir, en los que se conozca al
                           presunto inculpado del hecho de un registro
                           correspondiente a una unidad territorial y
                           temporal (departamento - mes). Se considera un
                           hecho con inculpado conocido en aquellos casos
                           en que:
                           - Se dispongan datos filiatorios (nombre y/o DNI)
                           de los presuntos inculpados


                                                                               7


## Página 8

- Se cuente con información contextual o de
                                   testigos que permita contar con información
                                   sobre sexo y/o edad de los presuntos inculpados.
    Tipo de variable               Numérica
    Comentarios y                  Es necesario tener en cuenta que el criterio
    advertencias                   utilizado por cada jurisdicción para el registro de
                                   un hecho con imputados conocidos o
                                   desconocidos puede diferir y ha variado a lo largo
                                   de los años. Por lo tanto, las cantidades
                                   reportadas en esta clasificación deben ser
                                   analizados con precaución.




      9. cantidad_hechos_inc_desconocido

    Nombre de la variable          cantidad_hechos_inc_desconocido
    Descripción                    Esta variable contabiliza la cantidad de hechos
                                   con inculpados desconocidos, de la clasificación
                                   de hechos según inculpados conocidos o
                                   desconocidos. Es decir, en los que no se posea
                                   información vinculada al presunto inculpado del
                                   hecho de un registro correspondiente a una
                                   unidad territorial y temporal (departamento -
                                   mes). Se considera desconocido a aquel
                                   inculpado del cual no se cuente con ningún dato
                                   identificatorio (sexo y edad).
    Tipo de variable               Numérica
    Comentarios y                  Es necesario tener en cuenta que el criterio
    advertencias                   utilizado por cada jurisdicción para el registro de
                                   un hecho con imputados conocidos o
                                   desconocidos puede diferir y ha variado a lo largo
                                   de los años. Por lo tanto, las cantidades
                                   reportadas en esta clasificación deben ser
                                   analizados con precaución.



Cantidad de hechos según tipo de lugar2

      10. cantidad_hechos_lugar_via_publ


2
 Es necesario tener en cuenta que esta variable es de reporte opcional, es por ello que existe una gran
proporción de casos en la categoría sin determinar.
                                                                                                     8


## Página 9

Nombre de la variable   cantidad_hechos_lugar_via_publ
Descripción             Esta variable contabiliza la cantidad de hechos
                        que ocurrieron en vía pública de la clasificación
                        de hechos según tipo de lugar. Hechos que
                        ocurrieron en un espacio público, es decir,
                        aquellos lugares donde las personas tienen el
                        derecho a circular o, en otras palabras, lugares en
                        los que el paso no puede ser restringido por
                        criterios de propiedad privada. No se incluyen
                        hechos ocurridos en establecimiento comercial o
                        público.
Tipo de variable        Numérica



  11. cantidad_hechos_lugar_establec

Nombre de la variable   cantidad_hechos_lugar_establec
Descripción             Esta variable contabiliza la cantidad de hechos
                        que ocurrieron en establecimientos comerciales
                        o públicos de la clasificación de hechos según
                        tipo de lugar. Es decir, un espacio físico como un
                        local/institución donde se ofrecen servicios, ya
                        sea pública o comercial, incluyendo también,
                        actividades relacionadas al ocio, a la educación, a
                        la realización de trámites. Algunos ejemplos
                        serían centros comerciales, lugares de
                        alojamiento (hoteles, albergues transitorios),
                        estacionamientos privados, escuelas, sedes de
                        AFIP o ANSES, entre otros que no sean
                        considerados en las categorías anteriores.
Tipo de variable        Numérica



  12. cantidad_hechos_lugar_dom_part

Nombre de la variable   cantidad_hechos_lugar_dom_part
Descripción             Esta variable contabiliza la cantidad de hechos
                        que ocurrieron en domicilio particular de la
                        clasificación de hechos según tipo de lugar. Es
                        decir, la residencia temporal o permanente,
                        urbana o rural, de cualquier persona involucrada
                        en el evento delictivo (victimas). Se incluyen los
                        casos en los que los hechos se producen en
                        hoteles o habitaciones de alquiler que funcionan
                                                                              9


## Página 10

como lugares de residencia para las personas
                                   que no cuentan con otro domicilio particular. Se
                                   incluye también el edificio en sí como zona
                                   aledaña de la propiedad (patios, pasillos, campos,
                                   etc.)
    Tipo de variable               Numérica



      13. cantidad_hechos_lugar_sd

    Nombre de la variable          cantidad_hechos_lugar_sd
    Descripción                    Esta variable contabiliza la cantidad de hechos
                                   que ocurrieron lugar sin determinar de la
                                   clasificación de hechos según tipo de lugar. Es
                                   decir, en un lugar que no está contemplado en
                                   las categorías anteriores.
    Tipo de variable               Numérica



Cantidad de hechos según tipo de arma3

      14. cantidad_hechos_arma_de_fuego

    Nombre de la variable          cantidad_hechos_arma_de_fuego
    Descripción                    Esta variable contabiliza la cantidad de hechos
                                   en los que se utilizó un arma de fuego de la
                                   clasificación de hechos según tipo de arma. Se
                                   entiende por arma de fuego, la que utiliza la
                                   energía de los gases producidos por la
                                   deflagración de las pólvoras para lanzar un
                                   proyectil a distancia. Esta definición incluye las
                                   armas de fuego de fabricación casera.
    Tipo de variable               Numérica
      15. cantidad_hechos_arma_otra

    Nombre de la variable          cantidad_hechos_arma_otra
    Descripción                    Esta variable contabiliza la cantidad de hechos
                                   en los que se utilizó un tipo de arma que no es de
                                   fuego de la clasificación de hechos según tipo de
                                   arma. Para considerar que intervino un arma,
                                   debe haber un objeto externo a la fisiología
                                   humana, que puede ser desde un arma blanca o

3
 Es necesario tener en cuenta que esta variable es de reporte opcional, por este motivo existe una gran
proporción de casos en la categoría sin determinar.
                                                                                                    10


## Página 11

elemento cortante, hasta cualquier objeto
                                   contundente potencialmente capaz de generar
                                   un daño en la víctima u objeto en ese contexto
                                   determinado.
    Tipo de variable               Numérica



      16. cantidad_hechos_arma_sin_arma

    Nombre de la variable          cantidad_hechos_arma_sin_arma
    Descripción                    Esta variable contabiliza la cantidad de hechos
                                   en los que no intervino ningún tipo de arma de la
                                   clasificación de hechos según tipo de arma.
    Tipo de variable               Numérica



      17. cantidad_hechos_arma_sd

    Nombre de la variable          cantidad_hechos_arma_sd
    Descripción                    Esta variable contabiliza la cantidad de hechos
                                   en los que no se pudo determinar el tipo de arma
                                   empleada de la clasificación de hechos según
                                   tipo de arma.
    Tipo de variable               Numérica



Cantidad de hechos según motivo que origina el registro del hecho4

      18. cantidad_hechos_origen_denuncia

    Nombre de la variable          cantidad_hechos_origen_denuncia
    Descripción                    Esta variable contabiliza la cantidad de hechos
                                   de origen por denuncia particular de la
                                   clasificación de hechos según motivo que origina
                                   el registro del hecho. Es decir, aquellos sobre los
                                   cuales se toma conocimiento a partir de la
                                   denuncia de una persona, ya sea que se haya
                                   radicado en la comisaría (u otra dependencia
                                   que tome denuncias) o se haya realizado
                                   personalmente a un efectivo en la calle o a través
                                   de un sistema formal de toma de denuncias
                                   telefónicas u online.

4
 Es necesario tener en cuenta que esta variable es de reporte opcional, por este motivo existe una gran
proporción de casos en la categoría sin determinar
                                                                                                     11


## Página 12

Tipo de variable        Numérica



  19. cantidad_hechos_origen_intervenc

Nombre de la variable   cantidad_hechos_origen_intervenc
Descripción             Esta variable contabiliza la cantidad de hechos
                        de origen por intervención policial de la
                        clasificación de hechos según motivo que origina
                        el registro del hecho. Es decir, sobre los cuales se
                        toma conocimiento a partir de la intervención
                        directa de un policía, ya sea que el efectivo se
                        haya encontrado patrullando, realizando tareas
                        de prevención o haya intervenido de oficio o en
                        flagrancia.
Tipo de variable        Numérica




  20. cantidad_hechos_origen_orden_jud

Nombre de la variable   cantidad_hechos_origen_orden_jud
Descripción             Esta variable contabiliza la cantidad de hechos
                        de origen por orden judicial de la clasificación de
                        hechos según motivo que origina el registro del
                        hecho. Es decir, sobre los cuales se toma
                        conocimiento a partir del pedido de intervención
                        por parte de la institución judicial.
Tipo de variable        Numérica



  21. cantidad_hechos_origen_otro

Nombre de la variable   cantidad_hechos_origen_otro
Descripción             Esta variable contabiliza la cantidad de hechos
                        de origen por otro motivo o motivo sin
                        determinar de la clasificación de hechos según
                        motivo que origina el registro del hecho. Es decir,
                        en el caso que se desconozca el origen o que, por
                        algún motivo, no pueda considerarse dentro de
                        las categorías anteriores.
Tipo de variable        Numérica


                                                                           12


## Página 13

Cantidad de hechos según gravedad

   22. cant_hechos_agrav_por_lesiones

Nombre de la variable   cant_hechos_agrav_por_lesiones
Descripción             Esta variable contabiliza la cantidad de hechos
                        correspondiente a cada tipo de delito teniendo
                        en cuenta el tipo de gravedad del evento.
                        Contiene el total de hechos agravados el
                        resultado de lesiones graves o gravísimas (art. 166
                        – inc. 1) y/o por la muerte (art. 165):
                        ●       Lesión grave:
                        De acuerdo al artículo 90 del Código Penal, se
                        entiende por lesión grave si la lesión produjere
                        una debilitación permanente de la salud, de un
                        sentido, de un órgano, de un miembro o una
                        dificultad permanente de la palabra o si hubiere
                        puesto en peligro la vida del ofendido, le hubiere
                        inutilizado para el trabajo por más de un mes o le
                        hubiere causado una deformación permanente
                        del rostro.
                        ●       Lesión gravísima:
                        De acuerdo al artículo 91 del Código Penal, se
                        entiende por lesión gravísima: si la lesión
                        produjere una enfermedad mental o corporal,
                        cierta o probablemente incurable, la inutilidad
                        permanente para el trabajo, la pérdida de un
                        sentido, de un órgano, de un miembro, del uso
                        de un órgano o miembro, de la palabra o de la
                        capacidad de engendrar o concebir.
Tipo de variable        Numérica



   23. cant_hechos_agrav_sin_lesiones

Nombre de la variable   cant_hechos_agrav_sin_lesiones
Descripción             Esta variable contabiliza la cantidad de hechos
                        correspondiente a cada tipo de delito teniendo
                        en cuenta el tipo de gravedad del evento.
                        Contiene el total de hechos no agravados el
                        resultado de lesiones graves o gravísimas.
Tipo de variable        Numérica

                                                                          13


## Página 14

Cantidad de inculpados según sus características

Cantidad de inculpados según sexo5

      24. cantidad_inculpados

    Nombre de la variable          cantidad_inculpados
    Descripción                    Esta variable contabiliza la cantidad total de
                                   inculpados.
    Tipo de variable               Numérica


      25. cantidad_inculpados_sexo_masc

    Nombre de la variable          cantidad_inculpados_sexo_masc
    Descripción                    Esta variable contabiliza la cantidad de
                                   inculpados de sexo masculino, de la clasificación
                                   de inculpados según sexo.
    Tipo de variable               Numérica



      26. cantidad_inculpados_sexo_fem

    Nombre de la variable          cantidad_inculpados_sexo_fem
    Descripción                    Esta variable contabiliza la cantidad de
                                   inculpados de sexo femenino, de la clasificación
                                   de inculpados según sexo.
    Tipo de variable               Numérica



      27. cantidad_inculpados_sexo_sd

    Nombre de la variable          cantidad_inculpados_sexo_sd
    Descripción                    Esta variable contabiliza la cantidad de
                                   inculpados de sexo no consta o sin determinar,
                                   de la clasificación de inculpados según sexo.
    Tipo de variable               Numérica




5
 Por inculpados se hace referencia a los presuntos autores de los hechos presuntamente delictivos.
Es necesario tener en cuenta que esta variable es de reporte opcional, por este motivo existe una gran
proporción de casos en la categoría “sexo no consta”. Esta variable debe ser analizada con precaución
debido a que el criterio utilizado por cada jurisdicción para el registro de un hecho con imputados
conocidos o desconocidos puede diferir y ha variado a lo largo de los años.
                                                                                                   14


## Página 15

Cantidad de inculpados según rango etario6

      28. cantidad_inculpados_edad_0_15

    Nombre de la variable             cantidad_inculpados_edad_0_15
    Descripción                       Esta variable contabiliza la cantidad de
                                      inculpados de edad de 0 a 15 años, de la
                                      clasificación de inculpados según edad.
    Tipo de variable                  Numérica



      29. cantidad_inculpados_edad_16_17

    Nombre de la variable             cantidad_inculpados_edad_16_17
    Descripción                       Esta variable contabiliza la cantidad de
                                      inculpados de edad de 16 a 17 años, de la
                                      clasificación de inculpados según edad.
    Tipo de variable                  Numérica



      30. cantidad_inculpados_edad_mas_18

    Nombre de la variable             cantidad_inculpados_edad_mas_18
    Descripción                       Esta variable contabiliza la cantidad de
                                      inculpados de edad de 18 o más años, de la
                                      clasificación de inculpados según edad.
    Tipo de variable                  Numérica
      31. cantidad_inculpados_edad_sd

    Nombre de la variable             cantidad_inculpados_edad_sd
    Descripción                       Esta variable contabiliza la cantidad de
                                      inculpados de edad desconocida, de la
                                      clasificación de inculpados según edad.
    Tipo de variable                  Numérica




6
  Por inculpados se hace referencia a los presuntos autores de los hechos presuntamente delictivos.
La cantidad de inculpados por edad corresponde a los hechos con inculpados conocidos. Es necesario tener
en cuenta que esta variable es de reporte opcional, por este motivo existe una gran proporción de casos en
la variable “edad no consta”. Esta variable debe ser analizada con precaución ya que el criterio utilizado por
cada jurisdicción para el registro de un hecho con imputados conocidos o desconocidos puede diferir y ha
variado a lo largo de los años
                                                                                                           15


## Página 16

Anexos




         16


## Página 17

Anexos
Anexo I – Códigos delictuales del SAT Propiedad


  codigo_delito_satprop_id        codigo_delito_satprop_nombre


             1               Homicidios dolosos
             2               Homicidios dolosos en grado de tentativa
             3               Muertes en Accidentes Viales
             4               Homicidios culposos por otros hechos
             5               Lesiones dolosas
             6               Lesiones culposas en Accidentes Viales
             7               Lesiones culposas por otros hechos
             8               Otros delitos contra las personas




                                                                        17


## Página 18

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
               Tierra del Fuego, Antártida e Islas del Atlántico
94
               Sur




                                                                   18


## Página 19

Anexo III – Códigos por departamento7

provincia_id provincia_nombre                         departamento_id              departamento_nombre
06            Buenos Aires                            06854                        25 de Mayo
06            Buenos Aires                            06588                        9 de Julio
06            Buenos Aires                            06007                        Adolfo Alsina
06            Buenos Aires                            06014                        Adolfo Gonzales Chaves
06            Buenos Aires                            06021                        Alberti
06            Buenos Aires                            06028                        Almirante Brown
06            Buenos Aires                            06077                        Arrecifes
06            Buenos Aires                            06035                        Avellaneda
06            Buenos Aires                            06042                        Ayacucho
06            Buenos Aires                            06049                        Azul
06            Buenos Aires                            06056                        Bahía Blanca
06            Buenos Aires                            06063                        Balcarce
06            Buenos Aires                            06070                        Baradero
06            Buenos Aires                            06084                        Benito Juárez
06            Buenos Aires                            06091                        Berazategui
06            Buenos Aires                            06098                        Berisso
06            Buenos Aires                            06105                        Bolívar
06            Buenos Aires                            06112                        Bragado
06            Buenos Aires                            06119                        Brandsen
06            Buenos Aires                            06126                        Campana
06            Buenos Aires                            06134                        Cañuelas
06            Buenos Aires                            06140                        Capitán Sarmiento
06            Buenos Aires                            06147                        Carlos Casares
06            Buenos Aires                            06154                        Carlos Tejedor
06            Buenos Aires                            06161                        Carmen de Areco
06            Buenos Aires                            06168                        Castelli



       7
        La siguiente tabla ha sido actualiza en las categorías de desagregación departamental de la Provincia
       de La Pampa en el año 2023, para los periodos anteriores corresponde contemplar la siguiente división
       político administrativa: Centro (Capital, Catrilo, Loventué y Toay), Norte (Chapaleufu, Conhelo, Maracó,
       Quemú, Rancul, Realicó y Trenel), Oeste (Chalileo, Chical Co, Curacó, Limay Mahuida y Puelén), Sur
       (Atreucó, Caleu, Guatraché, Hucal, Lihuel Calel y Utracan).

                                                                                                            19


## Página 20

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
06   Buenos Aires   06371   General San Martin
06   Buenos Aires   06385   General Viamonte
06   Buenos Aires   06392   General Villegas

                                               20


## Página 21

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
06   Buenos Aires   06574   Navarro
06   Buenos Aires   06581   Necochea
06   Buenos Aires   06595   Olavarría

                                                21


## Página 22

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
06   Buenos Aires   06784   Suipacha
06   Buenos Aires   06791   Tandil
06   Buenos Aires   06798   Tapalqué

                                               22


## Página 23

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
22   Chaco          22039   2 de Abril
22   Chaco          22168   25 de Mayo
22   Chaco          22105   9 de Julio

                                              23


## Página 24

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
26   Chubut   26056   Languieo
26   Chubut   26063   Martires
26   Chubut   26070   Paso de Indios

                                         24


## Página 25

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
02   Ciudad   Autónoma   de 02007   Comuna 7
     Buenos Aires




                                                     25


## Página 26

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
14   Córdoba                 14168   Totoral
14   Córdoba                 14175   Tulumba

                                                       26


## Página 27

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
30   Entre Ríos   30035   Federal
30   Entre Ríos   30042   Feliciano

                                               27


## Página 28

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

                                             28


## Página 29

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
46   La Rioja   46021   Castro Barros
46   La Rioja   46028   Chamical

                                         29


## Página 30

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
50   Mendoza    50999   Sin determinar
50   Mendoza    50119   Tunuyan

                                           30


## Página 31

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
58   Neuquén    58091   Pehuenches
58   Neuquén    58098   Picun Leufu

                                          31


## Página 32

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
66   Salta       66105   Los Andes
66   Salta       66112   Metan

                                           32


## Página 33

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
74   San Luis   74028   Coronel Pringles
74   San Luis   74035   General Pedernera

                                           33


## Página 34

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
82   Santa Fe     82126   San Martin
82   Santa Fe     82999   Sin determinar

                                             34


## Página 35

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
94   Tierra del Fuego, Antártida 94999   Sin determinar
     e Islas del Atlántico Sur

                                                           35


## Página 36

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




                                                          36
