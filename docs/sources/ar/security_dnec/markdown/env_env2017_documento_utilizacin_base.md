# env2017_documento_utilización_base

- Original local: `data/raw/ar/security_dnec/download_2026-07-12/env/extracted/env2017_documento_utilización_base.pdf`
- Extracted with: `pdftotext -layout`
- PDF pages: 91
- Note: this is a text extraction for review; consult the original PDF for layout-specific ambiguity.


## Página 1

ENCUESTA
NACIONAL DE
VICTIMIZACIÓN
2017
          Documento para la



VICTIMI
          utilización de la
          base de datos usuario




ZACIÓN


## Página 2

Presentación
En el marco del trabajo conjunto entre el Instituto Nacional de Estadística y Censos (INDEC) y el Ministerio de
Seguridad de la Nación se llevó a cabo la Encuesta Nacional de Victimización (ENV 2017).
Este documento tiene por finalidad ofrecer a los usuarios de la ENV una guía para la utilización de la base de
datos usuario.




La base de datos usuario cumple con lo estipulado en la Ley N° 17622 de Resguardo del Secreto
Estadístico, garantizando que la información que se presenta mantenga el carácter confidencial y
reservado del informante.




2 - INDEC. ENV 2017


## Página 3

1. Población objetivo y dominios de estimación

La población objetivo de la Encuesta Nacional de Victimización 2017 abarcó a las personas de 18 años
o más residentes en viviendas particulares de las localidades de 5.000 y más habitantes de la
República Argentina.

Para la Encuesta Nacional de Victimización se tuvo como objetivo dar estimaciones de los indicadores
más importantes para el dominio nacional y para las 24 divisiones políticas, compuestas por las 23
provincias y la Ciudad Autónoma de Buenos Aires.


2. Instrumento de captación de la información

Los datos que componen la base usuario de la ENV se relevaron mediante entrevista directa, utilizando
un cuestionario compuesto por dos bloques.

El bloque del hogar relevó información sobre los componentes del hogar y las características de la
vivienda y del hogar, de manera tal de obtener información sociodemográfica básica sobre la
población.

El bloque individual fue respondido por un miembro del hogar seleccionado aleatoriamente,
garantizando la representatividad de la muestra para la población de 18 años y más. Este bloque relevó
información sobre la percepción de seguridad del entrevistado, las medidas de seguridad adoptadas,
la consideración sobre el desempeño de las instituciones del sistema de seguridad y justicia y las
prevalencias y características de distintas tipologías delictivas.

Este bloque fue personal y autorrespondente: el miembro seleccionado debía contestar por sí mismo.


3. Especificaciones técnicas para la utilización de la base de datos usuario

Los datos se presentan en un archivo con las siguientes características:
Tipo de archivo: texto plano.
Delimitador: “|” (pipe, barra vertical, ASCII 124).
Calificador de texto: “ (comilla doble, ASCII 34).
Encabezado en la primera línea: sí.
Codificación: UTF-8.

La base incluye un registro por cada miembro seleccionado respondente del Bloque individual del
cuestionario, junto con la información necesaria para caracterizar la vivienda y el hogar al que
pertenece.



Al trabajar la información recuerde que los datos son referidos a la población objetivo: población de 18 años
y más que habitan en localidades de 5.000 y más habitantes.

                                                      Documento para la utilización de la base de datos usuario - 3


## Página 4

En el caso de las variables referidas a vivienda, hogar y jefes del hogar, tenga en cuenta que sólo puede
hacer inferencia sobre su relación con la población objetivo y no con el conjunto de las viviendas, hogares o
jefes del hogar.


4. Tipos de variables presentadas
En la base se han utilizado dos tipos de variables, que se presentan más adelante.
Estos tipos de variables son:
- aquellas cuyo campo se identifica con el nombre de la pregunta del cuestionario;
- aquellas cuyo campo se identifica con un nombre especial, ya que fue construida a través de una
secuencia de preguntas.
Los nombres del primer tipo de variables están formados por letras y números. En el caso de las
variables del cuestionario, la primera letra determina el Bloque al que pertenecen, las siguientes dos
refieren al capítulo correspondiente y el número refiere al orden de la pregunta. Por ejemplo: la variable
HCV03 corresponde a la tercera pregunta del capítulo CV (Características de la vivienda) del Bloque
del hogar.
La denominación de las variables construidas hace referencia al nombre de las mismas. Por ejemplo, la
variable CANTMIEM hace referencia a la cantidad de miembros que integran el hogar relevado. Por último, la
letra J en el nombre de algunas variables, por ejemplo J_HCH03 indica que la variable refiere al jefe del hogar
relevado. En los casos en los que el miembro seleccionado es el jefe del hogar, se encontrará la información
de caracterización sociodemográfica tanto en las variables que hacen referencia al miembro seleccionado
como al jefe del hogar. Por ejemplo, la edad del jefe/miembro seleccionado figurará tanto en la variable
HCH04 (correspondiente al miembro seleccionado) como en la variable J_HCH04 (correspondiente al jefe del
hogar).
5. Otras consideraciones técnicas
Para el uso de la base usuario se sugiere la consulta del cuestionario que encontrará al final de este
documento.
Se advierte que los campos en blanco, en general, se corresponden con saltos en la secuencia de
preguntas.
Los datos demográficos, el nivel de instrucción y la condición de actividad se presentan tanto para el
seleccionado como para el jefe del hogar. En caso de que el seleccionado fuera también el jefe de su hogar,
los datos se encuentran en ambos campos.
Se han construido variables con el objetivo de facilitar la identificación de los delitos ocurridos en una
jurisdicción distinta a aquella en la que se relevaron los datos o fuera del territorio nacional. Se encontrará
una variable de este tipo para cada uno de los delitos en los que esta identificación sea necesaria.




4 - INDEC. ENV 2017


## Página 5

6. Diccionario de registros
A continuación, se detallará el diseño de registro de cada tabla de la base. Este diseño incluye tanto
todas las variables relevadas en la encuesta como las construidas.


                                                 BLOQUE DEL HOGAR

                                               IDENTIFICACIÓN DEL CASO
                       Jurisdicción del país
COD_PROVINCIA
                       2 Ciudad Autónoma de Buenos Aires
                       6 Buenos Aires
                       10 Catamarca
                       14 Córdoba
                       18 Corrientes
                       22 Chaco
                       26 Chubut
                       30 Entre Ríos
                       34 Formosa
                       38 Jujuy
                       42 La Pampa
                       46 La Rioja
                       50 Mendoza
                       54 Misiones
                       58 Neuquén
                       62 Río Negro
                       66 Salta
                       70 San Juan
                       74 San Luis
                       78 Santa Cruz
                       82 Santa Fe
                       86 Santiago del Estero
                       90 Tucumán
                       94 Tierra del Fuego

ID                     Identificación de la vivienda

NVVND                  Número de vivienda

NHOGAR                 Número de hogar

                                      DETECCIÓN DE VIVIENDAS Y HOGARES

HDV01                  ¿Existen otras viviendas en la misma dirección?

                       1. Sí
                       2. No

HDV02                  ¿Todas las personas que residen en esta vivienda comparten los gastos de comida?



                                                       Documento para la utilización de la base de datos usuario - 5


## Página 6

1. Sí
                      2. No

HDV03a                ¿En este hogar hay servicio doméstico con cama adentro?

                      1. Sí
                      2. No

HDV03b                ¿En este hogar hay pensionistas?

                      1. Sí
                      2. No

HDV04                 Cantidad total de hogares que residen en esta vivienda

                      (Cantidad en cifras)

                                       CARACTERÍSTICAS DE LA VIVIENDA

HCV01                 Tipo de vivienda

                      1. Casa
                      2. Casilla
                      3. Departamento
                      4. Pieza de inquilinato
                      5. Pieza en hotel o pensión
                      6. Local no construido para habitación
                      7. Otro

                      ¿Cuántos ambientes/habitaciones tiene la vivienda en total? (Excluyendo baño, cocina,
HCV02
                      pasillos, lavadero, garaje)

                      (Cantidad en cifras)

HCV03                 ¿Cuál es el material predominante de los pisos?

                      1. Cerámica, baldosa, mosaico, mármol, madera o alfombra
                      2. Cemento o ladrillo fijo
                      3. Tierra o ladrillo suelto
                      4. Otros

HCV04                 ¿Cuál es el material predominante de la cubierta exterior del techo?

                      1. Cubierta asfáltica o membrana
                      2. Baldosa o losa (sin cubierta)
                      3. Pizarra o teja
                      4. Chapa de metal (sin cubierta)
                      5. Chapa de fibrocemento o plástico
                      6. Chapa o cartón
                      7. Caña, tabla o paja con barro, paja sola
                      8. N/S depto. en propiedad horizontal

6 - INDEC. ENV 2017


## Página 7

9. Otros

HCV05   En el techo ¿tiene cielorraso/revestimiento interior?

        1. Sí
        2. No
        99. Ns/Nc

HCV06   ¿Para cocinar, utiliza principalmente...

        1. …gas de red?
        2. …gas de tubo/garrafa?
        3. …kerosene/leña/carbón?
        4. …otro?

HCV07   ¿Tiene agua…

        1. …por cañería dentro de la vivienda?
        2. …fuera de la vivienda, pero dentro del terreno?
        3. …fuera del terreno?

HCV08   ¿Obtiene el agua a través de…

        1. …red pública (agua corriente)?
        2. …perforación con bomba a motor?
        3. …perforación con bomba manual?
        4. …aljibe o pozo?
        5. …otras fuentes?

HCV09   ¿Tiene baño/letrina?

        1. Sí
        2. No

HCV10   ¿El baño tiene…

        1. …inodoro con botón/mochila/cadena y arrastre de agua?
        2. …inodoro sin botón/cadena y con arrastre de agua? (a balde)
        3. …letrina? (sin arrastre de agua)

HCV11   ¿El desagüe del inodoro va...

        1. …a red pública (cloaca)?
        2. …a cámara séptica y pozo ciego?
        3. …sólo a pozo ciego?
        4. …a hoyo/excavación en tierra?

                           CARACTERÍSTICAS DEL HOGAR

HHO01   ¿El baño es de uso exclusivo de este hogar?


                                         Documento para la utilización de la base de datos usuario - 7


## Página 8

1. Sí
                      2. No

HHO02                 ¿Cuántos ambientes/habitaciones tiene este hogar para su uso exclusivo?

                      (Cantidad en cifras)

HHO03                 De esos, ¿cuántos usan habitualmente para dormir?

                      (Cantidad en cifras)

                                              INGRESOS DEL HOGAR

HIH01                 ¿Cuál es el ingreso total mensual del hogar?

                      (Cantidad en cifras)

HIH01_nsnc            2. Sin ingresos
                      99. Ns/Nc

HIH02                 ¿Me podría indicar en cuál de estos tramos se ubica el ingreso total mensual del hogar?

                      1. 1 a 3.000
                      2. 3.001 a 5.000
                      3. 5.001 a 8.000
                      4. 8.001 a 12.000
                      5. 12.001 a 15.000
                      6. 15.001 a 18.000
                      7. 18.001 a 23.000
                      8. 23.001 a 27.000
                      9. 27.001 a 31.000
                      10. 31.001 a 35.000
                      11. 35.001 a 38.000
                      12. 38.001 a 41.000
                      13. 41.001 a 45.000
                      14. 45.001 a 49.000
                      15. 49.001 a 53.000
                      16. 53.001 a 60.000
                      17. 60.001 y más
                      99. Ns/Nc

                                             COMPOSICIÓN DEL HOGAR

TIPO_HOGAR            1. Hogar unipersonal
                      2. Hogar multipersonal conyugal completo sin hijos ni otros miembros
                      3. Hogar multipersonal conyugal completo sin hijos y con otros miembros
                      4. Hogar multipersonal conyugal completo con hijos sin otros miembros
                      5. Hogar multipersonal conyugal completo con hijos y con otros miembros
                      6. Hogar multipersonal conyugal incompleto sin otros miembros


8 - INDEC. ENV 2017


## Página 9

7. Hogar multipersonal conyugal incompleto con otros miembros
                  8. Hogar multipersonal no conyugal

CANTMIEM          Total de miembros en el hogar

                  (Cantidad en cifras)

MIEMBROS_18_MAS   Miembros del hogar de 18 años o más

                  (Cantidad en cifras)

MENORES_18        Miembros del hogar menores de edad

                  (Cantidad en cifras)

MENORES_10        Miembros del hogar de 10 años o menos

                  (Cantidad en cifras)

                                CARACTERÍSTICAS DEL JEFE DE HOGAR

J_HCH03           Sexo del jefe del hogar

                  1. Varón
                  2. Mujer

J_HCH04           Edad en años cumplidos del jefe del hogar

                  (Cantidad en cifras)

J_HCH05           Situación conyugal del jefe del hogar

                  ¿Actualmente está…

                  1. …unido/a?
                  2. …casado/a?
                  3. …separado/a?
                  4. …divorciado/a?
                  5. …viudo/a?
                  6. …soltero/a?

J_HCH06           ¿Asiste o asistió a algún establecimiento educativo?

                  1. Asiste
                  2. Asistió
                  3. Nunca asistió

J_HCH07           ¿Cuál es el nivel más alto que cursa o cursó?

                  1. Jardín/ Preescolar


                                                  Documento para la utilización de la base de datos usuario - 9


## Página 10

2. Primario
                       3. E.G.B. (1° A 9° año)
                       4. Secundario (1° a 5° o 6° año)
                       5. Polimodal (1° a 3° o 4° año)
                       6. Terciario
                       7. Universitario
                       8. Posgrado universitario
                       9. Educación especial

J_HCH08                ¿Finalizó ese nivel?

                       1. Sí
                       2. No

J_HCH09                ¿Cuál fue el último grado/año que aprobó?

                       0. Ninguno
                       1. Primero
                       2. Segundo
                       3. Tercero
                       4. Cuarto
                       5. Quinto
                       6. Sexto
                       7. Séptimo
                       8. Octavo
                       9. Noveno
                       99. Ns/Nc

j_nivel_instruccion    1. Sín instrucción
                       2. Primario incompleto
                       3. Primario completo
                       4. Secundario incompleto
                       5. Secundario completo
                       6. Terciario o universitario incompleto
                       7. Terciario o universitario completo
                       8. Educación especial

J_HCH10_1              ¿Está asociado a una obra social (incluye PAMI)?

                       1. Sí
                       2. No

J_HCH10_2              ¿Está asociado a una prepaga a través de obra social?

                       1. Sí
                       2. No

J_HCH10_3              ¿Está asociado a una prepaga por contratación voluntaria?

                       1. Sí
                       2. No

J_HCH10_4              ¿Está asociado a un servicio de emergencia médica?


10 - INDEC. ENV 2017


## Página 11

1. Sí
             2. No

J_HCH10_5    ¿Está asociado a un programa o plan estatal de salud?

             1. Sí
             2. No

J_HCH10_6    No está asociado a nada

             1. Sí
             2. No

J_HCH10_99   Ns/Nc

             99.Ns/Nc

                         SITUACIÓN LABORAL DEL JEFE DE HOGAR

             La semana pasada, ¿trabajó por lo menos una hora, hizo alguna changa, fabricó algo para
HSL01
             vender, ayudó a un familiar/amigo en su negocio?

             1. Sí
             2. No

HSL02        ¿La semana pasada…

             1. …no deseaba/no quería/no podía trabajar?
             2. …no tenía/no conseguía trabajo?
             3. …no tuvo pedidos/clientes?
             4. …tenía un trabajo/negocio al que no concurrió?

HSL03        ¿No concurrió por…

             1. …vacaciones/licencia? (enfermedad, matrimonio, embarazo, etc.)
             2. …huelga/conflicto laboral?
             3. …suspensión con pago?
             4. …suspensión sin pago?
             5. …otras causas laborales y volverá a lo sumo en un mes?
             6. …otras causas laborales y volverá en más de un mes?

             En los últimos 30 días, ¿estuvo buscando trabajo de alguna manera, consultó amigos o
HSL04
             parientes, puso carteles, hizo algo para ponerse por su cuenta?

             1. Sí
             2. No

HSL05        Durante esos 30 días, ¿no buscó trabajo porque...

             1. …está suspendido?
             2. …ya tiene trabajo asegurado?
             3. …se cansó de buscar trabajo?

                                            Documento para la utilización de la base de datos usuario - 11


## Página 12

4. …hay poco trabajo en esta época del año?
                        5. …por otras razones?

HSL06                   ¿Cuántas horas semanales trabaja habitualmente en todos sus empleos/ocupaciones?

                        1. Menos de 35 horas semanales
                        2. Entre 35 y 45 horas semanales
                        3. Más de 45 horas semanales
                        99. Ns/Nc

j_condicion_actividad   1. Ocupado
                        2. Desocupado
                        3. Inactivo

                                   CARACTERÍSTICAS DEL MIEMBRO SELECCIONADO

HCH02                   ¿Cuál es la relación de parentesco con el jefe de hogar?

                        1. Jefe/a
                        2. Cónyuge/Pareja
                        3. Hijo/a Hijastro/a
                        4. Padre/Madre
                        5. Hermano/a
                        6. Suegro/a
                        7. Yerno/Nuera
                        8. Nieto/a
                        9. Otro familiar
                        10. Otro no familiar

HCH03                   ¿Es varón o mujer?

                        1. Varón
                        2. Mujer

HCH04                   ¿Cuál es su edad en años cumplidos?

                        (Cantidad en cifras)
                        999. Ns/Nc

HCH05                   ¿Actualmente está…

                        1. …unido/a?
                        2. …casado/a?
                        3. …separado/a?
                        4. …divorciado/a?
                        5. …viudo/a?
                        6. …soltero/a?

HCH06                   ¿Asiste o asistió a algún establecimiento educativo?



12 - INDEC. ENV 2017


## Página 13

1. Asiste
                    2. Asistió
                    3. Nunca asistió

HCH07               ¿Cuál es el nivel más alto que cursa o cursó?

                    1. Jardín/Preescolar
                    2. Primario
                    3. E.G.B. (1° a 9° año)
                    4. Secundario (1° a 5° o 6° año)
                    5. Polimodal (1° a 3° o 4° año)
                    6. Terciario
                    7. Universitario
                    8. Posgrado universitario
                    9. Educación especial

HCH08               ¿Finalizó ese nivel?

                    1. Sí
                    2. No

HCH09               ¿Cuál fue el último grado/año que aprobó?

                    0. Ninguno
                    1. Primero
                    2. Segundo
                    3. Tercero
                    4. Cuarto
                    5. Quinto
                    6. Sexto
                    7. Séptimo
                    8. Octavo
                    9. Noveno
                    99. Ns/Nc

nivel_instruccion   1. Sin instrucción
                    2. Primario incompleto
                    3. Primario completo
                    4. Secundario incompleto
                    5. Secundario completo
                    6. Terciario o universitario incompleto
                    7. Terciario o universitario completo
                    8. Educación especial

HCH10_1             ¿Está asociado a una obra social (incluye PAMI)?

                    1. Sí
                    2. No

HCH10_2             ¿Está asociado a una prepaga a través de obra social?


                                                       Documento para la utilización de la base de datos usuario - 13


## Página 14

1. Sí
                       2. No

HCH10_3                ¿Está asociado a una prepaga por contratación voluntaria?

                       1. Sí
                       2. No

HCH10_4                ¿Está asociado a un servicio de emergencia médica?

                       1. Sí
                       2. No

HCH10_5                ¿Está asociado a un programa o plan estatal de salud?

                       1. Sí
                       2. No

HCH10_6                No está asociado a nada

                       1. Sí
                       2. No

HCH10_99               99.Ns/Nc

                                               BLOQUE INDIVIDUAL

                               SITUACIÓN LABORAL DEL MIEMBRO SELECCIONADO

                       La semana pasada, ¿trabajó por lo menos una hora, hizo alguna changa, fabricó algo para
ISL01
                       vender, ayudó a un familiar/amigo en su negocio?
                       (Sin contar las tareas de su hogar)

                       1. Sí
                       2. No

ISL02                  ¿La semana pasada…

                       1. …no deseaba/no quería/no podía trabajar?
                       2. …no tenía/no conseguía trabajo?
                       3. …no tuvo pedidos/clientes?
                       4. …tenía un trabajo/negocio al que no concurrió?

ISL03                  ¿No concurrió por…

                       1. …vacaciones/licencia? (enfermedad, matrimonio, embarazo, etc.)
                       2. …huelga/conflicto laboral?
                       3. …suspensión con pago?
                       4. …suspensión sin pago?
                       5. …otras causas laborales y volverá a lo sumo en un mes?

14 - INDEC. ENV 2017


## Página 15

6. …otras causas laborales y volverá en más de un mes?

                      En los últimos 30 días, ¿estuvo buscando trabajo de alguna manera, consultó amigos o
ISL04
                      parientes, puso carteles, hizo algo para ponerse por su cuenta?

                      1. Sí
                      2. No

ISL05                 Durante esos 30 días, ¿no buscó trabajo porque...

                      1. …está suspendido?
                      2. …ya tiene trabajo asegurado?
                      3. …se cansó de buscar trabajo?
                      4. …hay poco trabajo en esta época del año?
                      5. …por otras razones?

ISL06                 ¿Cuántas horas semanales trabaja habitualmente en todos sus empleos/ocupaciones?

                      1. Menos de 35 horas semanales
                      2. Entre 35 y 45 horas semanales
                      3. Más de 45 horas semanales
                      99. Ns/Nc


condicion_actividad   1. Ocupado
                      2. Desocupado
                      3. Inactivo

                                  PERCEPCIÓN DE SEGURIDAD CIUDADANA

IPS01                 ¿Considera que hoy en esta ciudad la inseguridad respecto al delito es un problema…

                      1. …muy grave?
                      2. …bastante grave?
                      3. …poco grave?
                      4. …nada grave?
                      99. Ns/Nc

                      ¿Cómo diría que se siente en los siguientes lugares o situaciones? ¿Muy
IPS02
                      seguro, seguro, inseguro o muy inseguro?
IPS02a                Caminando solo/a cerca de donde vive

                      1. Muy seguro
                      2. Seguro
                      3. Inseguro
                      4. Muy inseguro
                      98. No aplica
                      99. Ns/Nc

IPS02b                Solo/a de noche en su casa


                                                    Documento para la utilización de la base de datos usuario - 15


## Página 16

1. Muy seguro
                       2. Seguro
                       3. Inseguro
                       4. Muy inseguro
                       98. No aplica
                       99. Ns/Nc

IPS02c                 En su lugar de trabajo

                       1. Muy seguro
                       2. Seguro
                       3. Inseguro
                       4. Muy inseguro
                       98. No aplica
                       99. Ns/Nc

IPS02d                 En una institución educativa

                       1. Muy seguro
                       2. Seguro
                       3. Inseguro
                       4. Muy inseguro
                       98. No aplica
                       99. Ns/Nc

IPS02e                 En el mercado o centro comercial

                       1. Muy seguro
                       2. Seguro
                       3. Inseguro
                       4. Muy inseguro
                       98. No aplica
                       99. Ns/Nc

IPS02f                 En el banco

                       1. Muy seguro
                       2. Seguro
                       3. Inseguro
                       4. Muy inseguro
                       98. No aplica
                       99. Ns/Nc

IPS02g                 En el cajero automático cuando el banco está cerrado

                       1. Muy seguro
                       2. Seguro
                       3. Inseguro
                       4. Muy inseguro
                       98. No aplica


16 - INDEC. ENV 2017


## Página 17

99. Ns/Nc

IPS02h   En el parque/la plaza

         1. Muy seguro
         2. Seguro
         3. Inseguro
         4. Muy inseguro
         98. No aplica
         99. Ns/Nc

IPS02i   En el transporte público

         1. Muy seguro
         2. Seguro
         3. Inseguro
         4. Muy inseguro
         98. No aplica
         99. Ns/Nc

IPS02j   En un vehículo propio

         1. Muy seguro
         2. Seguro
         3. Inseguro
         4. Muy inseguro
         98. No aplica
         99. Ns/Nc

IPS03    ¿Podría decirme si en su barrio, durante 2016, hubo…
IPS03a   ...riñas o peleas en la calle?

         1. Sí
         2. No
         99. Ns/Nc

IPS03b   …bandas violentas?

         1. Sí
         2. No
         99. Ns/Nc

IPS03c   …consumo de alcohol en la calle?

         1. Sí
         2. No
         99. Ns/Nc

IPS03d   …consumo de droga en la calle?



                                      Documento para la utilización de la base de datos usuario - 17


## Página 18

1. Sí
                       2. No
                       99. Ns/Nc

IPS03e                 ...venta de droga en la calle?

                       1. Sí
                       2. No
                       99. Ns/Nc

IPS03f                 ...vandalismo (graffitis/pintadas, rotura de focos en la plaza, porteros eléctricos)?

                       1. Sí
                       2. No
                       99. Ns/Nc

IPS03g                 …calles sin iluminación?

                       1. Sí
                       2. No
                       99. Ns/Nc

IPS03h                 …prostitución?

                       1. Sí
                       2. No
                       99. Ns/Nc

IPS03i                 …disparos frecuentes?

                       1. Sí
                       2. No
                       99. Ns/Nc

                       ¿Usted diría que la delincuencia en las siguientes zonas aumentó, se mantiene igual o
IPS04
                       disminuyó respecto a hace un año atrás?
IPS04a                 Cerca de donde vive

                       1. Aumentó
                       2. Se mantiene igual
                       3. Disminuyó
                       99. Ns/Nc

IPS04b                 En esta ciudad, pero no cerca de donde vive

                       1. Aumentó
                       2. Se mantiene igual
                       3. Disminuyó
                       99. Ns/Nc

IPS04c                 En esta provincia

18 - INDEC. ENV 2017


## Página 19

1. Aumentó
         2. Se mantiene igual
         3. Disminuyó
         99. Ns/Nc

IPS04d   En el país

         1. Aumentó
         2. Se mantiene igual
         3. Disminuyó
         99. Ns/Nc

                                MEDIDAS DE SEGURIDAD

IMS01    ¿Este hogar cuenta actualmente con…
IMS01a   ...puerta blindada o cerraduras especiales en las puertas?

         1. Sí
         2. No
         99. Ns/Nc

IMS01b   …rejas en las ventanas?

         1. Sí
         2. No
         99. Ns/Nc

IMS01c   …alarma?

         1. Sí
         2. No
         99. Ns/Nc

IMS01d   …alambrados, rejas perimetrales o muros altos?

         1. Sí
         2. No
         99. Ns/Nc

IMS01e   …perro guardián?

         1. Sí
         2. No
         99. Ns/Nc

IMS01f   …cámara de seguridad?

         1. Sí
         2. No


                                       Documento para la utilización de la base de datos usuario - 19


## Página 20

99. Ns/Nc

IMS01g                 …servicio de seguridad privada?

                       1. Sí
                       2. No
                       99. Ns/Nc

IMS01h                 …seguro contra robo?

                       1. Sí
                       2. No
                       99. Ns/Nc

IMS01i                 …acuerdos con los vecinos para vigilancia barrial?

                       1. Sí
                       2. No
                       99. Ns/Nc

IMS01j                 …arma de fuego?

                       1. Sí
                       2. No
                       99. Ns/Nc

IMS02                  ¿Esta medida se instaló durante 2016?
IMS02a                 Puerta blindada o cerraduras especiales en las puertas

                       1. Sí
                       2. No
                       99. Ns/Nc

IMS02b                 Rejas en las ventanas

                       1. Sí
                       2. No
                       99. Ns/Nc

IMS02c                 Alarma

                       1. Sí
                       2. No
                       99. Ns/Nc

IMS02d                 Alambrados, rejas perimetrales o muros altos

                       1. Sí
                       2. No
                       99. Ns/Nc


20 - INDEC. ENV 2017


## Página 21

IMS02e       Perro guardián

             1. Sí
             2. No
             99. Ns/Nc

IMS02f       Cámara de seguridad

             1. Sí
             2. No
             99. Ns/Nc

IMS02g       Servicio de seguridad privada

             1. Sí
             2. No
             99. Ns/Nc

IMS02h       Seguro contra robo

             1. Sí
             2. No
             99. Ns/Nc

IMS02i       Acuerdos con los vecinos para vigilancia barrial

             1. Sí
             2. No
             99. Ns/Nc

IMS02j       Arma de fuego

             1. Sí
             2. No
             99. Ns/Nc

             Durante 2016, ¿cuánto calcula que ha sido el costo total por la instalación y/o uso de estas
IMS03
             medidas de seguridad?

             (Cantidad en cifras)

IMS03_nsnc   99. Ns/Nc

             Durante 2016, ¿usted o algún miembro de su hogar fue propietario de algún automóvil,
IMS04
             camioneta o camión?

             1. Sí
             2. No
             99. Ns/Nc


                                             Documento para la utilización de la base de datos usuario - 21


## Página 22

IMS05                  ¿De más de un vehículo?

                       1. Sí
                       2. No
                       99. Ns/Nc

IMS06                  ¿El vehículo es de tamaño chico, mediano o grande?

                       1. Chico
                       2. Mediano
                       3. Grande
                       99. Ns/Nc

IMS07                  ¿Cuántos años de antigüedad tiene?

                       1. Menos de 2 años
                       2. De 2 a 5 años
                       3. De 6 a 10 años
                       4. Más de 10 años
                       99. Ns/Nc

IMS08                  ¿El vehículo cuenta con…
IMS08a                 …alarma?

                       1. Sí
                       2. No
                       99. Ns/Nc

IMS08b                 …cadena, barra de bloqueo de dirección o trabavolante?

                       1. Sí
                       2. No
                       99. Ns/Nc

IMS08c                 …cortacorriente o cortanafta?

                       1. Sí
                       2. No
                       99. Ns/Nc

IMS08d                 …Lo-jack u otro localizador satelital?

                       1. Sí
                       2. No
                       99. Ns/Nc

IMS08e                 …otro mecanismo de seguridad?

                       1. Sí
                       2. No


22 - INDEC. ENV 2017


## Página 23

99. Ns/Nc

IMS09    Para cubrirse de un robo del vehículo, ¿contratan seguro contra robo?

         1. Sí
         2. No
         99. Ns/Nc

IMS10    Durante 2016, por razones de seguridad, ¿usted…
IMS10a   …ha dejado de salir de noche?

         1. Sí
         2. No
         98. No aplica

IMS10b   …ha dejado de permitir que sus hijos menores de edad salgan solos?

         1. Sí
         2. No
         98. No aplica

IMS10c   …ha dejado de visitar parientes o amigos?

         1. Sí
         2. No
         98. No aplica

IMS10d   …ha dejado de tomar taxis en la calle?

         1. Sí
         2. No
         98. No aplica

IMS10e   ….ha dejado de usar transporte público?

         1. Sí
         2. No
         98. No aplica

IMS10f   …ha dejado de llevar mucho dinero en efectivo o tarjetas de crédito o débito?

         1. Sí
         2. No
         98. No aplica

IMS10g   …ha dejado de ir al cine, al teatro, a recitales, a comer afuera?

         1. Sí
         2. No
         98. No aplica


                                        Documento para la utilización de la base de datos usuario - 23


## Página 24

IMS10h                 …ha dejado de salir a caminar, correr o andar en bicicleta?

                       1. Sí
                       2. No
                       98. No aplica

IMS10i                 …ha dejado de usar joyas, relojes u objetos de valor?

                       1. Sí
                       2. No
                       98. No aplica

IMS10j                 …ha dejado de ir a la cancha?

                       1. Sí
                       2. No
                       98. No aplica

IMS10k                 …ha dejado de frecuentar centros comerciales?

                       1. Sí
                       2. No
                       98. No aplica

IMS10l                 …ha dejado de viajar por ruta o autopista?

                       1. Sí
                       2. No
                       98. No aplica

IMS10m                 …ha dejado de llegar muy tarde a casa o dejar la casa sola?

                       1. Sí
                       2. No
                       98. No aplica

                       Durante 2016, en la zona donde vive, ¿se mantuvo alejado de ciertos lugares o ciertas
IMS11
                       personas por razones de seguridad o prevención?

                       1. Sí
                       2. No
                       99. Ns/Nc

IMS12                  ¿Cuánto tiempo hace que vive en esta vivienda?

                       1. Menos de un año
                       2. De 1 año a menos de 5 años
                       3. De 5 años a menos de 10 años
                       4. 10 años o más
                       99. Ns/Nc

24 - INDEC. ENV 2017


## Página 25

IMS13    ¿Usted se mudó a esta casa para evitar la posibilidad de ser víctima de algún delito?

         1. Sí
         2. No
         3. No tomó usted la decisión de mudarse
         99. Ns/Nc

                DESEMPEÑO DEL SISTEMA DE SEGURIDAD PÚBLICA

IDS01    De las instituciones que le voy a mencionar, dígame a cuáles identifica:
IDS01a   Policía Provincial/Policía de la Ciudad

         1. Sí
         2. No
         99. Ns/Nc

IDS01b   Policía Federal Argentina

         1. Sí
         2. No
         99. Ns/Nc

IDS01c   Gendarmería Nacional

         1. Sí
         2. No
         99. Ns/Nc

IDS01d   Prefectura Naval

         1. Sí
         2. No
         99. Ns/Nc

IDS01e   Fiscalía

         1. Sí
         2. No
         99. Ns/Nc

IDS01f   Jueces y Tribunales

         1. Sí
         2. No
         99. Ns/Nc

         ¿Usted diría que las siguientes instituciones son muy confiables, algo confiables, poco
IDS02
         confiables o nada confiables?
IDS02a   Policía Provincial/Policía de la Ciudad


                                       Documento para la utilización de la base de datos usuario - 25


## Página 26

1. Muy confiable
                       2. Confiable
                       3. Poco confiable
                       4. Nada confiable
                       99. Ns/Nc

IDS02b                 Policía Federal Argentina

                       1. Muy confiable
                       2. Confiable
                       3. Poco confiable
                       4. Nada confiable
                       99. Ns/Nc

IDS02c                 Gendarmería Nacional

                       1. Muy confiable
                       2. Confiable
                       3. Poco confiable
                       4. Nada confiable
                       99. Ns/Nc

IDS02d                 Prefectura Naval

                       1. Muy confiable
                       2. Confiable
                       3. Poco confiable
                       4. Nada confiable
                       99. Ns/Nc

IDS02e                 Fiscalía

                       1. Muy confiable
                       2. Confiable
                       3. Poco confiable
                       4. Nada confiable
                       99. Ns/Nc

IDS02f                 Jueces y Tribunales

                       1. Muy confiable
                       2. Confiable
                       3. Poco confiable
                       4. Nada confiable
                       99. Ns/Nc
IDS03                  Durante el 2016, ¿tuvo contacto con algún efectivo de la policía, por cualquier razón?

                       1. Sí
                       2. No
                       99. Ns/Nc


26 - INDEC. ENV 2017


## Página 27

IDS04   ¿Cree que la forma en que la policía controla el delito en la zona donde usted vive es…

        1. …muy buena?
        2. …buena?
        3. …mala?
        4. …muy mala?
        99. Ns/Nc

        Habitualmente, ¿con cuánta frecuencia pasa la policía frente a su casa, ya sea a pie o en
IDS05
        auto?

        1. Todos los días
        2. Entre tres y seis veces por semana
        3. Una o dos veces por semana
        4. Menos de una vez por semana
        5. Nunca
        99. Ns/Nc

IDS06   ¿Cree que la frecuencia con que la policía patrulla las calles es suficiente?

        1. Sí
        2. No
        99. Ns/Nc

IDS07   Si tuviera que llamar a la policía ante una urgencia, ¿sabe a qué número comunicarse?

        1. Sí
        2. No
        99. Ns/Nc

IDS08   ¿Alguna vez ha llamado de urgencia a la policía?

        1. Sí
        2. No
        99. Ns/Nc

IDS09   ¿Se pudo comunicar?

        1. Sí
        2. No
        99. Ns/Nc

IDS10   ¿La policía fue al lugar del hecho?

        1. Sí
        2. No
        3. No fue necesario
        99. Ns/Nc

IDS11   ¿Cuánto tardó en llegar la policía?

                                       Documento para la utilización de la base de datos usuario - 27


## Página 28

(Tiempo expresado en horas y minutos)

IDS11nr                99. Ns/Nc

IDS12                  ¿Cree que el trato y respeto de la policía hacia usted y los vecinos es…

                       1. …muy bueno?
                       2. …bueno?
                       3. …malo?
                       4. …muy malo?
                       99. Ns/Nc

                       Le voy a leer algunas frases y le pido que, para cada una de ellas, me diga si está muy de
IDS13
                       acuerdo, de acuerdo, en desacuerdo o muy en desacuerdo.
IDS13a                 La policía trata a toda la gente por igual

                       1. Muy de acuerdo
                       2. De acuerdo
                       3. En desacuerdo
                       4. Muy en desacuerdo
                       99. Ns/Nc

IDS13b                 La policía protege los derechos de las personas

                       1. Muy de acuerdo
                       2. De acuerdo
                       3. En desacuerdo
                       4. Muy en desacuerdo
                       99. Ns/Nc

IDS13c                 La policía es honesta

                       1. Muy de acuerdo
                       2. De acuerdo
                       3. En desacuerdo
                       4. Muy en desacuerdo
                       99. Ns/Nc

IDS13d                 La policía es muy profesional

                       1. Muy de acuerdo
                       2. De acuerdo
                       3. En desacuerdo
                       4. Muy en desacuerdo
                       99. Ns/Nc

IDS14                  Durante 2016, ¿usted personalmente...
IDS14a                 …fue maltratado verbalmente por la policía?

                       1. Sí

28 - INDEC. ENV 2017


## Página 29

2. No
         99. Ns/Nc

IDS14b   …fue maltratado físicamente por la policía?

         1. Sí
         2. No
         99. Ns/Nc

IDS14c   …fue detenido sin motivos por la policía?

         1. Sí
         2. No
         99. Ns/Nc

IDS15    Durante 2016, ¿ha presenciado por parte de la policía…
IDS15a   …maltrato verbal hacia otras personas?

         1. Sí
         2. No
         99. Ns/Nc

IDS15b   …maltrato físico hacia otras personas?

         1. Sí
         2. No
         99. Ns/Nc

IDS15c   …detenciones sin motivos?

         1. Sí
         2. No
         99. Ns/Nc

         Durante 2016, ¿sintió que la policía lo discriminó, sea por su sexo, color de piel, vestimenta,
IDS16
         condición social, etc.?

         1. Sí
         2. No
         99. Ns/Nc

         Comparando el desempeño de la policía respecto de hace un año atrás, ¿usted diría que hoy
IDS17
         la policía es…

         1. …mejor que hace un año atrás?
         2. …igual que hace un año atrás?
         3. …peor que hace un año atrás?
         99. Ns/Nc

                                   VICTIMIZACIÓN
IVI01    Antes de 2016, ¿usted o alguna persona de este hogar sufrió alguna de las situaciones del

                                        Documento para la utilización de la base de datos usuario - 29


## Página 30

grupo A? (Delitos contra el hogar)

                       1. Sí
                       2. No
                       99. Ns/Nc

                       En lo que va de 2017, ¿usted o alguna persona de este hogar sufrió alguna de las situaciones
IVI02
                       del grupo A? (Delitos contra el hogar)

                       1. Sí
                       2. No
                       99. Ns/Nc

                       Durante 2016, ¿usted o alguna persona de este hogar sufrió robo total de vehículo (automóvil,
IVI03
                       camioneta o camión)?

                       1. Sí
                       2. No
                       99. Ns/Nc

IVI03a                 ¿El o los vehículos pertenecían a alguna persona de este hogar?

                       1. Sí
                       2. No
                       99. Ns/Nc

IVI03b                 ¿Cuántas veces le sucedió durante 2016?

                       (Cantidad en cifras)

IVI03c                 ¿Cuántos de estos hechos fueron denunciados?

                       (Cantidad en cifras)

                       Durante 2016, ¿usted o algún otro miembro del hogar sufrió hurto de autopartes de vehículo
IVI04
                       (automóvil, camioneta o camión)?

                       1. Sí
                       2. No
                       99. Ns/Nc

IVI04a                 ¿El o los vehículos pertenecían a alguna persona de este hogar?

                       1. Sí
                       2. No
                       99. Ns/Nc

IVI04b                 ¿Cuántas veces le sucedió durante 2016?

                       (Cantidad en cifras)


30 - INDEC. ENV 2017


## Página 31

IVI04c   ¿Cuántos de estos hechos fueron denunciados?

         (Cantidad en cifras)

         Durante 2016, ¿usted o algún otro miembro del hogar sufrió robo total de motocicleta o
IVI05
         ciclomotor?

         1. Sí
         2. No
         99. Ns/Nc

IVI05a   ¿El o los vehículos pertenecían a alguna persona de este hogar?

         1. Sí
         2. No
         99. Ns/Nc

IVI05b   ¿Cuántas veces le sucedió durante 2016?

         (Cantidad en cifras)

IVI05c   ¿Cuántos de estos hechos fueron denunciados?

         (Cantidad en cifras)

         Durante 2016, ¿alguien entró en su casa o departamento sin permiso y robó o intentó robar
IVI06
         algo?

         1. Sí
         2. No
         99. Ns/Nc

IVI06a   ¿Cuántas veces le sucedió durante 2016?

         (Cantidad en cifras)

IVI06b   ¿Cuántos de estos hechos fueron denunciados?

         (Cantidad en cifras)

         Durante 2016, ¿alguna persona de este hogar, incluido usted, sufrió un secuestro o secuestro
IVI07
         exprés, para exigir dinero o bienes?

         1. Sí
         2. No
         99. Ns/Nc

IVI07a   ¿Cuántas veces le sucedió durante 2016?

         (Cantidad en cifras)


                                      Documento para la utilización de la base de datos usuario - 31


## Página 32

IVI07b                 ¿Cuántos de estos hechos fueron denunciados?

                       (Cantidad en cifras)

                       Antes de 2016, ¿usted personalmente sufrió alguna de las situaciones del grupo B? (Delitos
IVI08
                       contra las personas)

                       1. Sí
                       2. No
                       99. Ns/Nc

                       En lo que va de 2017, ¿usted personalmente sufrió alguna de las situaciones del grupo B?
IVI09
                       (Delitos contra las personas)

                       1. Sí
                       2. No
                       99. Ns/Nc

IVI10                  Durante 2016, ¿usted sufrió un robo con violencia, por la fuerza o amenazándolo con usarla?

                       1. Sí
                       2. No
                       99. Ns/Nc

IVI10a                 ¿Cuántas veces le sucedió durante 2016?

                       (Cantidad en cifras)

IVI10b                 ¿Cuántos de estos hechos fueron denunciados?

                       (Cantidad en cifras)

                       Durante 2016, ¿usted sufrió un robo sin violencia y sin amenazas, por ejemplo el hurto de una
IVI11
                       cartera o un celular?

                       1. Sí
                       2. No
                       99. Ns/Nc

IVI11a                 ¿Cuántas veces le sucedió durante 2016?

                       (Cantidad en cifras)

IVI11b                 ¿Cuántos de estos hechos fueron denunciados?

                       (Cantidad en cifras)

                       Durante 2016, ¿alguien ha obtenido dinero u otro beneficio utilizando su cuenta bancaria,
IVI12
                       cheques, tarjetas de crédito o débito sin su consentimiento o a través de engaños?

                       1. Sí

32 - INDEC. ENV 2017


## Página 33

2. No
         99. Ns/Nc

IVI12a   ¿Cuántas veces le sucedió durante 2016?

         (Cantidad en cifras)

IVI12b   ¿Cuántos de estos hechos fueron denunciados?

         (Cantidad en cifras)

         Durante 2016, ¿entregó dinero por un producto o servicio donde el vendedor
IVI13
         intencionalmente no cumplió con lo pactado?

         1. Sí
         2. No
         99. Ns/Nc

IVI13a   ¿Cuántas veces le sucedió durante 2016?

         (Cantidad en cifras)

IVI13b   ¿Cuántos de estos hechos fueron denunciados?

         (Cantidad en cifras)

         Durante 2016, ¿alguien lo/a golpeó, empujó o atacó generándole una lesión física
IVI15
         (moretones, fracturas, cortes, etc.), sin que el motivo haya sido un robo u otro delito?

         1. Sí
         2. No
         99. Ns/Nc

IVI15a   ¿Cuántas veces le sucedió durante 2016?

         (Cantidad en cifras)

IVI15b   ¿Cuántos de estos hechos fueron denunciados?

         (Cantidad en cifras)

         Durante 2016, ¿alguien lo amenazó con provocarle algún daño físico a usted o a su familia, a
IVI16    sus propiedades, a su reputación, de modo que haya creído que la amenaza podría
         realmente cumplirse?

         1. Sí
         2. No
         99. Ns/Nc

IVI16a   ¿Cuántas veces le sucedió durante 2016?


                                        Documento para la utilización de la base de datos usuario - 33


## Página 34

(Cantidad en cifras)

IVI16b                 ¿Cuántos de estos hechos fueron denunciados?

                       (Cantidad en cifras)

                       Durante 2016, ¿sufrió pedidos de coima, pagos o regalos por parte de personal de
IVI17
                       organismos públicos?

                       1. Sí
                       2. No
                       99. Ns/Nc

IVI17a                 ¿Cuántas veces le sucedió durante 2016?

                       (Cantidad en cifras)

IVI17b                 ¿Cuántos de estos hechos fueron denunciados?

                       (Cantidad en cifras)

IVI18                  Durante 2016, ¿fue víctima del delito número 14 que figura en la tarjeta? (Ofensas sexuales)

                       1. Sí
                       2. No
                       99. Ns/Nc

IVI18a                 ¿Cuántas veces le sucedió durante 2016?

                       (Cantidad en cifras)

IVI18b                 ¿Cuántos de estos hechos fueron denunciados?

                       (Cantidad en cifras)

                             ROBO O HURTO DE AUTOMOVIL, CAMIONETA, CAMIÓN

IRA01                  La última vez que sucedió en 2016, ¿ocurrió...

                       1. …en su casa?
                       2. …cerca de donde vive?
                       3. …en esta ciudad, pero no en su barrio?
                       4. …en otro lugar de esta provincia?
                       5. …en otra provincia del país?
                       6. …en otro país?
                       99. Ns/Nc

IRA01a                 ¿Cuál?

                       2 Ciudad Autónoma de Buenos Aires
                       6 Buenos Aires

34 - INDEC. ENV 2017


## Página 35

10 Catamarca
        14 Córdoba
        18 Corrientes
        22 Chaco
        26 Chubut
        30 Entre Ríos
        34 Formosa
        38 Jujuy
        42 La Pampa
        46 La Rioja
        50 Mendoza
        54 Misiones
        58 Neuquén
        62 Río Negro
        66 Salta
        70 San Juan
        74 San Luis
        78 Santa Cruz
        82 Santa Fe
        86 Santiago del Estero
        90 Tucumán
        94 Tierra del Fuego

IRA02   ¿A qué hora aproximada ocurrió?

        1. Mañana/Mediodía (de 07:00 a 12:59)
        2. Tarde (de 13:00 a 19:59)
        3. Noche (de 20:00 a 23:59)
        4. Madrugada (de 00:00 a 06:59)
        99. Ns/Nc

IRA03   ¿Usted o algún miembro del hogar estuvo en contacto con el/los delincuente/s?

        1. Sí
        2. No
        99. Ns/Nc

IRA04   ¿Cuántos delincuentes eran?

        1. Uno
        2. Dos
        3. Tres
        4. Más de tres
        99. Ns/Nc

        ¿Tenía/n el/los delincuente/s algún tipo de arma o algún objeto que amenazaran con utilizar
IRA05
        como arma?

        1. Sí
        2. No
        99. Ns/Nc

                                      Documento para la utilización de la base de datos usuario - 35


## Página 36

IRA06                  ¿Qué arma era?
IRA06_1                Arma de fuego

                       1. Sí

IRA06_2                Cuchillo u objeto afilado

                       1. Sí

IRA06_3                Objeto contundente u otro objeto utilizado como arma (bate, palo, tubo, cuerda, etc.)

                       1. Sí

IRA06_4                Otra

                       1. Sí

IRA06_99               Ns/Nc

                       99.Ns/Nc

IRA07                  ¿Se utilizó efectivamente el arma?

                       1. Sí
                       2. No
                       99. Ns/Nc

IRA08                  ¿Utilizaron otro tipo de violencia física?

                       1. Sí
                       2. No
                       99. Ns/Nc

IRA09                  ¿Se resistió usted o algún miembro del hogar al robo?

                       1. Sí
                       2. No
                       99. Ns/Nc

IRA10                  En este último hecho, ¿usted o algún miembro del hogar resultó herido?

                       1. Sí
                       2. No
                       99. Ns/Nc

IRA11                  ¿Qué tipo de lesión física sufrio?
IRA11_1                Contusión

                       1. Sí


36 - INDEC. ENV 2017


## Página 37

IRA11_2    Cortes

           1. Sí

IRA11_3    Arañazos

           1. Sí

IRA11_4    Moretones (incluyendo el ojo morado)

           1. Sí

IRA11_5    Huesos rotos

           1. Sí

IRA11_6    Dientes rotos

           1. Sí

IRA11_7    Amputación de algún miembro

           1. Sí

IRA11_8    Lesión interna

           1. Sí

IRA11_9    Herida con arma blanca

           1. Sí

IRA11_10   Herida de bala

           1. Sí

IRA11_99   Ns/Nc

           99.Ns/Nc

IRA12      ¿Se recuperó el automóvil/camioneta/camión?

           1. Sí
           2. No
           99. Ns/Nc

IRA13      ¿El vehículo robado era de tamaño chico, mediano o grande?

           1. Chico


                                       Documento para la utilización de la base de datos usuario - 37


## Página 38

2. Mediano
                       3. Grande
                       99. Ns/Nc

IRA14                  ¿Qué antigüedad tenía?

                       1. Menos de 2 años
                       2. De 2 a 5 años
                       3. De 6 a 10 años
                       4. Más de 10 años
                       99. Ns/Nc

IRA15                  Al momento del robo, ¿el vehículo contaba con…
IRA15a                 …alarma?

                       1.Sí
                       2.No
                       99.Ns/Nc

IRA15b                 …cadena, barra de bloqueo de dirección o trabavolante?

                       1.Sí
                       2.No
                       99.Ns/Nc

IRA15c                 …cortacorriente o cortanafta?

                       1.Sí
                       2.No
                       99.Ns/Nc

IRA15d                 …Lo-jack u otro localizador satelital?

                       1.Sí
                       2.No
                       99.Ns/Nc

IRA15e                 …otro mecanismo de seguridad?

                       1.Sí
                       2.No
                       99.Ns/Nc

IRA16                  Al momento del robo, ¿contaba con seguro contra robo?

                       1. Sí
                       2. No
                       99. Ns/Nc

IRA17                  La última vez que ocurrió este hecho, ¿usted o alguna otra persona hizo la denuncia formal?


38 - INDEC. ENV 2017


## Página 39

1. Sí
           2. No
           99. Ns/Nc

IRA18      ¿Dónde lo denunció?

           1. Policía
           2. Fiscalía
           3. Otro organismo
           99. Ns/Nc

           En general, ¿qué tan satisfecho estuvo con la forma en que la autoridad competente manejó
IRA19
           la denuncia?

           1. Muy satisfecho
           2. Satisfecho
           3. Insatisfecho
           4. Muy insatisfecho
           99. Ns/Nc

IRA20      ¿Por qué motivos quedó insatisfecho?
IRA20_1    No quisieron tomar la denuncia

           1.Sí

IRA20_2    No se interesaron o no hicieron lo suficiente

           1.Sí

IRA20_3    No encontraron o no detuvieron al autor

           1.Sí

IRA20_4    No recuperaron el vehículo

           1.Sí

IRA20_5    No lo mantuvieron informado

           1.Sí

IRA20_6    No lo trataron correctamente/Fueron maleducados

           1.Sí

IRA20_7    Otra razón

           1.Sí

IRA20_99   Ns/Nc

                                         Documento para la utilización de la base de datos usuario - 39


## Página 40

99.Ns/Nc

IRA21                  ¿Por qué no realizó la denuncia?
IRA21_1                Lo sucedido no era importante

                       1.Sí

IRA21_2                Lo resolvió por su cuenta

                       1.Sí

IRA21_3                Desconfianza en las autoridades

                       1.Sí

IRA21_4                No tenía seguro

                       1.Sí

IRA21_5                Falta de pruebas

                       1.Sí

IRA21_6                Miedo o vergüenza

                       1.Sí

IRA21_7                Desconocimiento o dificultad para hacer la denuncia

                       1.Sí

IRA21_8                Otra razón

                       1.Sí

IRA21_99               Ns/Nc

                       99.Ns/Nc

                        HURTO DE AUTOPARTES DE AUTOMÓVIL,CAMIONETA, CAMIÓN

IHA01                  La última vez que ocurrió este hecho, ¿ocurrió…

                       1. …en su casa (incluyendo garajes o entradas de auto)?
                       2. …cerca de donde vive?
                       3. …en esta ciudad, pero no en su barrio?
                       4. …en otro lugar de esta provincia?
                       5. …en otra provincia del país?
                       6. …en otro país?


40 - INDEC. ENV 2017


## Página 41

99. Ns/Nc

IHA01a   ¿Cuál?

         2 Ciudad Autónoma de Buenos Aires
         6 Buenos Aires
         10 Catamarca
         14 Córdoba
         18 Corrientes
         22 Chaco
         26 Chubut
         30 Entre Ríos
         34 Formosa
         38 Jujuy
         42 La Pampa
         46 La Rioja
         50 Mendoza
         54 Misiones
         58 Neuquén
         62 Río Negro
         66 Salta
         70 San Juan
         74 San Luis
         78 Santa Cruz
         82 Santa Fe
         86 Santiago del Estero
         90 Tucumán
         94 Tierra del Fuego

IHA02    ¿A qué hora aproximada ocurrió?

         1. Mañana/Mediodía (de 07:00 a 12:59)
         2. Tarde (de 13:00 a 19:59)
         3. Noche (de 20:00 a 23:59)
         4. Madrugada (de 00:00 a 06:59)
         99. Ns/Nc

IHA03    La última vez que ocurrió este hecho, ¿usted o alguna otra persona hizo la denuncia formal?

         1. Sí
         2. No
         99. Ns/Nc

IHA04    ¿Dónde lo denunció?

         1. Policía
         2. Fiscalía
         3. Otro organismo
         99. Ns/Nc



                                       Documento para la utilización de la base de datos usuario - 41


## Página 42

En general, ¿qué tan satisfecho estuvo con la forma en que la autoridad competente manejó
IHA05
                       la denuncia?

                       1. Muy satisfecho
                       2. Satisfecho
                       3. Insatisfecho
                       4. Muy insatisfecho
                       99. Ns/Nc

IHA06                  ¿Por qué motivos quedó insatisfecho?
IHA06_1                No quisieron tomar la denuncia

                       1.Sí

IHA06_2                No se interesaron o no hicieron lo suficiente

                       1.Sí

IHA06_3                No encontraron o no detuvieron al autor

                       1.Sí

IHA06_4                No recuperaron lo robado

                       1.Sí

IHA06_5                No lo mantuvieron informado

                       1.Sí

IHA06_6                No lo trataron correctamente/Fueron maleducados

                       1.Sí

IHA06_7                Otra razón

                       1.Sí

IHA06_99               Ns/Nc

                       99.Ns/Nc

IHA07                  ¿Por qué no realizo la denuncia?
IHA07_1                Lo sucedido no era importante

                       1.Sí

IHA07_2                Lo resolvió por su cuenta

                       1.Sí


42 - INDEC. ENV 2017


## Página 43

IHA07_3    Desconfianza en las autoridades

           1.Sí

IHA07_4    No tenía seguro

           1.Sí

IHA07_5    Falta de pruebas

           1.Sí

IHA07_6    Miedo o vergüenza

           1.Sí

IHA07_7    Desconocimiento o dificultad para hacer la denuncia

           1.Sí

IHA07_8    Otra razón

           1.Sí

IHA07_99   Ns/Nc

           99.Ns/Nc

                    ROBO O HURTO DE MOTOCICLETA O CICLOMOTOR

IRM01      La última vez que ocurrió este hecho en 2016, ¿ocurrió…

           1. …en su casa?
           2. …cerca de donde vive?
           3. …en esta ciudad, pero no en su barrio?
           4. …en otro lugar de esta provincia?
           5. …en otra provincia del país?
           6. …en otro país?
           99. Ns/Nc

IRM01a     ¿Cuál?

           2 Ciudad Autónoma de Buenos Aires
           6 Buenos Aires
           10 Catamarca
           14 Córdoba
           18 Corrientes
           22 Chaco
           26 Chubut
           30 Entre Ríos


                                          Documento para la utilización de la base de datos usuario - 43


## Página 44

34 Formosa
                       38 Jujuy
                       42 La Pampa
                       46 La Rioja
                       50 Mendoza
                       54 Misiones
                       58 Neuquén
                       62 Río Negro
                       66 Salta
                       70 San Juan
                       74 San Luis
                       78 Santa Cruz
                       82 Santa Fe
                       86 Santiago del Estero
                       90 Tucumán
                       94 Tierra del Fuego

IRM02                  ¿A qué hora aproximada ocurrió?

                       1. Mañana/Mediodía (de 07:00 a 12:59)
                       2. Tarde (de 13:00 a 19:59)
                       3. Noche (de 20:00 a 23:59)
                       4. Madrugada (de 00:00 a 06:59)
                       99. Ns/Nc

IRM03                  ¿Usted o algún miembro del hogar estuvo en contacto con el/los delincuente/s?

                       1. Sí
                       2. No
                       99. Ns/Nc

IRM04                  ¿Cuántos delincuentes eran?

                       1. Uno
                       2. Dos
                       3. Tres
                       4. Más de tres
                       99. Ns/Nc

                       ¿Tenía/n el/los delincuente/s algún tipo de arma o algún objeto que amenazaran con utilizar
IRM05
                       como arma?

                       1. Sí
                       2. No
                       99. Ns/Nc

IRM06                  ¿Qué arma era?
IRM06_1                Arma de fuego

                       1. Sí


44 - INDEC. ENV 2017


## Página 45

IRM06_2    Cuchillo u objeto afilado

           1. Sí

IRM06_3    Objeto contundente u otro objeto utilizado como arma (bate, palo, tubo, cuerda, etc.)

           1. Sí

IRM06_4    Otra

           1. Sí

IRM06_99   Ns/Nc

           99.Ns/Nc

IRM07      ¿Se utilizo efectivamente el arma?

           1. Sí
           2. No
           99. Ns/Nc

IRM08      ¿Utilizaron otro tipo de violencia física?

           1. Sí
           2. No
           99. Ns/Nc

IRM09      ¿Se resistió usted o algún miembro del hogar al robo?

           1. Sí
           2. No
           99. Ns/Nc

IRM10      ¿Usted o algún miembro del hogar resultó herido en el hecho?

           1. Sí
           2. No
           99. Ns/Nc

IRM11      ¿Qué tipo de lesión física sufrio?
IRM11_1    Contusión

           1. Sí

IRM11_2    Cortes

           1. Sí

IRM11_3    Arañazos


                                           Documento para la utilización de la base de datos usuario - 45


## Página 46

1. Sí

IRM11_4                Moretones (incluyendo el ojo morado)

                       1. Sí

IRM11_5                Huesos rotos

                       1. Sí

IRM11_6                Dientes rotos

                       1. Sí

IRM11_7                Amputación de algún miembro

                       1. Sí

IRM11_8                Lesión interna

                       1. Sí

IRM11_9                Herida con arma blanca

                       1. Sí

IRM11_10               Herida de bala

                       1. Sí

IRM11_99               Ns/Nc

                       99.Ns/Nc

IRM12                  ¿Se recuperó la motocicleta/ciclomotor?

                       1. Sí
                       2. No
                       99.Ns/Nc

IRM13                  La última vez que ocurrió este hecho, ¿usted o alguna otra persona hizo la denuncia formal?

                       1. Sí
                       2. No
                       99.Ns/Nc

IRM14                  ¿Dónde lo denunció?

                       1. Policía


46 - INDEC. ENV 2017


## Página 47

2. Fiscalía
           3. Otro organismo
           99. Ns/Nc

           En general, ¿qué tan satisfecho estuvo con la forma en que la autoridad competente manejó
IRM15
           la denuncia?

           1. Muy satisfecho
           2. Satisfecho
           3. Insatisfecho
           4. Muy insatisfecho
           99. Ns/Nc

IRM16      ¿Por qué motivos quedó insatisfecho?
IRM16_1    No quisieron tomar la denuncia

           1.Sí

IRM16_2    No se interesaron o no hicieron lo suficiente

           1.Sí

IRM16_3    No encontraron o no detuvieron al autor

           1.Sí

IRM16_4    No recuperaron la motocicleta / el ciclomotor

           1.Sí

IRM16_5    No lo mantuvieron informado

           1.Sí

IRM16_6    No lo trataron correctamente/Fueron maleducados

           1.Sí

IRM16_7    Otra razón

           1.Sí

IRM16_99   Ns/Nc

           99.Ns/Nc

IRM17      ¿Por qué no realizó la denuncia?
IRM17_1    Lo sucedido no era importante

           1.Sí


                                         Documento para la utilización de la base de datos usuario - 47


## Página 48

IRM17_2                Lo resolvió por su cuenta

                       1.Sí

IRM17_3                Desconfianza en las autoridades

                       1.Sí

IRM17_4                No tenía seguro

                       1.Sí

IRM17_5                Falta de pruebas

                       1.Sí

IRM17_6                Miedo o vergüenza

                       1.Sí

IRM17_7                Desconocimiento o dificultad para hacer la denuncia

                       1.Sí

IRM17_8                Otra razón

                       1.Sí

IRM17_99               Ns/Nc

                       99.Ns/Nc

                                           ROBO O HURTO EN VIVIENDA

IHV01                  La última vez que ocurrió este hecho en 2016, ¿a qué hora aproximada ocurrió?

                       1. Mañana/Mediodía (de 07:00 a 12:59)
                       2. Tarde (de 13:00 a 19:59)
                       3. Noche (de 20:00 a 23:59)
                       4. Madrugada (de 00:00 a 06:59)
                       99. Ns/Nc

IHV02                  ¿Cómo ingresó o ingresaron el/los delincuente/s a la vivienda?

                       1. Forzaron una puerta o una ventana
                       2. Saltaron por el muro o medianera
                       3. Ingresaron con usted o algún miembro del hogar a su casa
                       4. Otro
                       99. Ns/Nc



48 - INDEC. ENV 2017


## Página 49

IHV03      ¿Usted o algún miembro del hogar estuvo en contacto con el/los delincuente/s?

           1. Sí
           2. No
           99. Ns/Nc

IHV04      ¿Cuántos delincuentes ingresaron a su casa?

           1. Uno
           2. Dos
           3. Tres
           4. Más de tres
           99. Ns/Nc

           ¿Tenía/n el/los delincuente/s algún tipo de arma o algún objeto que amenazaran con utilizar
IHV05
           como arma?

           1. Sí
           2. No
           99. Ns/Nc

IHV06      ¿Qué arma era?
IHV06_1    Arma de fuego

           1. Sí

IHV06_2    Cuchillo u objeto afilado

           1. Sí

IHV06_3    Objeto contundente u otro objeto utilizado como arma (bate, palo, tubo, cuerda, etc.)

           1. Sí

IHV06_4    Otra

           1. Sí

IHV06_99   Ns/Nc

           99.Ns/Nc

IHV07      ¿Se utilizó efectivamente el arma?

           1. Sí
           2. No
           99. Ns/Nc

IHV08      ¿Utilizaron otro tipo de violencia física?

           1. Sí

                                           Documento para la utilización de la base de datos usuario - 49


## Página 50

2. No
                       99. Ns/Nc

IHV09                  ¿Se resistió usted o algún miembro del hogar al robo?

                       1. Sí
                       2. No
                       99. Ns/Nc

IHV10                  ¿Usted o algún miembro del hogar resultó herido en el hecho?

                       1. Sí
                       2. No
                       99. Ns/Nc

IHV11                  ¿Qué tipo de lesión física sufrio?
IHV11_1                Contusión

                       1. Sí

IHV11_2                Cortes

                       1. Sí

IHV11_3                Arañazos

                       1. Sí

IHV11_4                Moretones (incluyendo el ojo morado)

                       1. Sí

IHV11_5                Huesos rotos

                       1. Sí

IHV11_6                Dientes rotos

                       1. Sí

IHV11_7                Amputación de algún miembro

                       1. Sí

IHV11_8                Lesión interna

                       1. Sí

IHV11_9                Herida con arma blanca



50 - INDEC. ENV 2017


## Página 51

1. Sí

IHV11_10   Herida de bala

           1. Sí

IHV11_99   Ns/Nc

           99.Ns/Nc

IHV12      Y la última vez que ocurrió este hecho, ¿qué le robaron?
IHV12_1    Bolso, cartera, mochila, portafolio

           1.Sí

IHV12_2    Equipo electrónico (computadora, reproductor de música, tablet)

           1.Sí

IHV12_3    Teléfono celular

           1.Sí

IHV12_4    Dinero, tarjeta de crédito, cheques

           1.Sí

IHV12_5    Joyas, relojes

           1.Sí

IHV12_6    Documentos de identificación

           1.Sí

IHV12_7    Vestimenta y calzado

           1.Sí

IHV12_8    Bicicleta

           1.Sí

IHV12_9    Muebles

           1.Sí

IHV12_10   Electrodomésticos

           1.Sí


                                          Documento para la utilización de la base de datos usuario - 51


## Página 52

IHV12_11               Arma de fuego

                       1.Sí

IHV12_12               Otro

                       1.Sí

IHV12_13               Nada

                       1.Sí

IHV12_99               Ns/Nc

                       99. Ns/Nc

IHV13                  ¿Cuánto estima que fue el valor del/los bien/es robados?

                       (Cantidad en cifras)

IHV13_nsnc             99. Ns/Nc

IHV14                  De los bienes que le robaron, ¿estaba alguno asegurado?

                       1. Sí
                       2. No
                       99. Ns/Nc

IHV15                  La última vez que ocurrió este hecho, ¿usted o alguna otra persona hizo la denuncia formal?

                       1. Sí
                       2. No
                       99. Ns/Nc

IHV16                  ¿Dónde lo denunció?

                       1. Policía
                       2. Fiscalía
                       3. Otro organismo
                       99. Ns/Nc

                       En general, ¿qué tan satisfecho estuvo con la forma en que la autoridad competente manejó
IHV17
                       la denuncia?

                       1. Muy satisfecho
                       2. Satisfecho
                       3. Insatisfecho
                       4. Muy insatisfecho
                       99. Ns/Nc


52 - INDEC. ENV 2017


## Página 53

IHV18      ¿Por qué motivos quedó insatisfecho?
IHV18_1    No quisieron tomar la denuncia

           1.Sí

IHV18_2    No se interesaron o no hicieron lo suficiente

           1.Sí

IHV18_3    No encontraron o no detuvieron al autor

           1.Sí

IHV18_4    No recuperaron lo robado

           Si

IHV18_5    No lo mantuvieron informado

           1.Sí

IHV18_6    No lo trataron correctamente/Fueron maleducados

           1.Sí

IHV18_7    Otra razón

           1.Sí

IHV18_99   Ns/Nc

           99.Ns/Nc

IHV19      ¿Por qué no realizó la denuncia?
IHV19_1    Lo sucedido no era importante

           1.Sí

IVH19_2    Lo resolvió por su cuenta

           1.Sí

IHV19_3    Desconfianza en las autoridades

           1.Sí

IHV19_4    No tenía seguro

           1.Sí



                                         Documento para la utilización de la base de datos usuario - 53


## Página 54

IHV19_5                Falta de pruebas

                       1.Sí

IHV19_6                Miedo o vergüenza

                       1.Sí

IHV19_7                Desconocimiento o dificultad para hacer la denuncia

                       1.Sí

IHV19_8                Otra razón

                       1.Sí

IHV19_99               Ns/Nc

                       99.Ns/Nc

                                                   SECUESTROS

ISE01                  La última vez que sucedió en 2016, ¿ocurrió…

                       1. …cerca de donde vive?
                       2. …en esta ciudad, pero no en este barrio?
                       3. …en otro lugar de esta provincia?
                       4. …en otra provincia del país?
                       5. …en otro país?
                       99. Ns/Nc

ISE01a                 ¿Cuál?

                       2 Ciudad Autónoma de Buenos Aires
                       6 Buenos Aires
                       10 Catamarca
                       14 Córdoba
                       18 Corrientes
                       22 Chaco
                       26 Chubut
                       30 Entre Ríos
                       34 Formosa
                       38 Jujuy
                       42 La Pampa
                       46 La Rioja
                       50 Mendoza
                       54 Misiones
                       58 Neuquén
                       62 Río Negro
                       66 Salta


54 - INDEC. ENV 2017


## Página 55

70 San Juan
         74 San Luis
         78 Santa Cruz
         82 Santa Fe
         86 Santiago del Estero
         90 Tucumán
         94 Tierra del Fuego

ISE03    ¿En qué lugar lo/s capturaron?

         1. En su casa
         2. En el trabajo/escuela
         3. En la calle mientras caminaba
         4. En la calle mientras conducía o viajaba en un vehículo
         5. Otro
         99. Ns/Nc

ISE04    ¿A qué hora aproximada ocurrió?

         1. Mañana/Mediodía (de 07:00 a 12:59)
         2. Tarde (de 13:00 a 19:59)
         3. Noche (de 20:00 a 23:59)
         4. Madrugada (de 00:00 a 06:59)
         99. Ns/Nc

ISE05    La última vez que ocurrió este hecho, ¿cuánto tiempo permaneció secuestrada la víctima?

         1. Menos de 24 horas
         2. De 1 a 3 días
         3. De 4 a 30 días
         4. De 31 a 90 días
         5. Más de 90 días
         99. Ns/Nc

ISE06    ¿Me podría decir si los secuestradores…
ISE06a   exigieron rescate a familiares por su liberación?

         1. Sí
         2.No
         99.Ns/Nc

ISE06b   lo obligaron a retirar dinero de un cajero, entregar joyas, celular u otras cosas?

         1. Sí
         2.No
         99.Ns/Nc

ISE07    ¿Entregó lo que le exigió a los secuestador(es)?

         1.Sí


                                         Documento para la utilización de la base de datos usuario - 55


## Página 56

2.Sí, parcialmente
                       3.No
                       99.Ns/Nc

ISE08                  ¿En cuánto estima el valor del dinero y/o los bienes entregados?

                       (Cantidad en cifras)

ISE08_nsnc             99. Ns/Nc

ISE09                  La última vez que ocurrió este hecho, ¿usted o alguna otra persona hizo la denuncia formal?

                       1. Sí
                       2. No
                       99. Ns/Nc

ISE10                  ¿Dónde lo denunció?

                       1. Policía
                       2. Fiscalía
                       3. Otro organismo
                       99. Ns/Nc

                       En general, ¿qué tan satisfecho estuvo con la forma en que la autoridad competente manejó
ISE11
                       la denuncia?

                       1. Muy satisfecho
                       2. Satisfecho
                       3. Insatisfecho
                       4. Muy insatisfecho
                       99. Ns/Nc

ISE12                  ¿Por qué motivos quedó insatisfecho?
ISE12_1                No quisieron tomar la denuncia

                       1.Sí

ISE12_2                No se interesaron o no hicieron lo suficiente

                       1.Sí

ISE12_3                No encontraron o no detuvieron al autor

                       1.Sí

ISE12_4                No se recuperó el rescate que se pagó

                       1.Sí

ISE12_5                No lo mantuvieron informado


56 - INDEC. ENV 2017


## Página 57

1.Sí

ISE12_6    No lo trataron correctamente/Fueron maleducados

           1.Sí

ISE12_7    Otra razón

           1.Sí

ISE12_99   Ns/Nc

           99. Ns/Nc

ISE13      ¿Por qué no realizó la denuncia?
ISE13_1    Lo sucedido no era importante

           1.Sí

ISE13_2    Lo resolvió por su cuenta

           1.Sí

ISE13_3    Desconfianza en las autoridades

           1.Sí

ISE13_4    Falta de pruebas

           1.Sí

ISE13_5    Miedo o vergüenza

           1.Sí

ISE13_6    Desconocimiento o dificultad para hacer la denuncia

           1.Sí

ISE13_7    Otra razón

           1.Sí

ISE13_99   Ns/Nc

           99.Ns/Nc

                                 ROBO CON VIOLENCIA

IRV01      La última vez que ocurrió este hecho en 2016, ¿ocurrió…


                                        Documento para la utilización de la base de datos usuario - 57


## Página 58

1. …cerca de donde vive?
                       2. …en esta ciudad, pero no en su barrio?
                       3. …en otro lugar de la provincia?
                       4. …en otra provincia del país?
                       5. …en otro país?
                       99. Ns/Nc

IRV01a                 ¿Cuál?

                       2 Ciudad Autónoma de Buenos Aires
                       6 Buenos Aires
                       10 Catamarca
                       14 Córdoba
                       18 Corrientes
                       22 Chaco
                       26 Chubut
                       30 Entre Ríos
                       34 Formosa
                       38 Jujuy
                       42 La Pampa
                       46 La Rioja
                       50 Mendoza
                       54 Misiones
                       58 Neuquén
                       62 Río Negro
                       66 Salta
                       70 San Juan
                       74 San Luis
                       78 Santa Cruz
                       82 Santa Fe
                       86 Santiago del Estero
                       90 Tucumán
                       94 Tierra del Fuego

IRV02                  Y para ser más específicos, ¿este hecho ocurrió en…

                       1. …la calle?
                       2. …el transporte público?
                       3. …la plaza/el parque?
                       4. …su trabajo?
                       5. …una institución educativa?
                       6. …un mercado/supermercado/centro comercial?
                       7. …el banco/cajero automático?
                       8. …la cancha?
                       9. …un restaurante/bar/boliche?
                       10. …la ruta?
                       99. Ns/Nc

IRV03                  ¿A qué hora aproximada ocurrió?


58 - INDEC. ENV 2017


## Página 59

1. Mañana/Mediodía (de 07:00 a 12:59)
           2. Tarde (de 13:00 a 19:59)
           3. Noche (de 20:00 a 23:59)
           4. Madrugada (de 00:00 a 06:59)
           99. Ns/Nc

IRV04      ¿Cuántos delincuentes lo agredieron?

           1. Uno
           2. Dos
           3. Tres
           4. Más de tres
           99. Ns/Nc

IRV05      ¿Podría decirme si eran hombres, mujeres u hombres y mujeres?

           1. Sólo hombres
           2. Sólo mujeres
           3. Hombres y mujeres
           99. Ns/Nc

           ¿Tenía/n el/los atacantes algún tipo de arma o algún objeto que amenazaran con utilizar
IRV06
           como arma?

           1. Sí
           2. No
           99. Ns/Nc

IRV07      ¿Qué arma era?
IRV07_1    Arma de fuego

           1.Sí

IRV07_2    Cuchillo u objeto afilado

           1.Sí

IRV07_3    Objeto contundente u otro objeto utilizado como arma (bate, palo, tubo, cuerda, etc.)

           1.Sí

IRV07_4    Otra

           1.Sí

IRV07_99   Ns/Nc

           99.Ns/Nc

IRV08      ¿Se utilizó efectivamente el arma?

                                         Documento para la utilización de la base de datos usuario - 59


## Página 60

1. Sí
                       2. No
                       99. Ns/Nc

IRV09                  ¿Utilizaron otro tipo de violencia física?

                       1. Sí
                       2. No
                       99. Ns/Nc

                       La última vez que esto ocurrió, ¿parecía/n el/los atacantes/s estar bajo la influencia del
IRV10
                       alcohol y/o drogas?

                       1. Sí
                       2. No
                       99. Ns/Nc

IRV11                  ¿Se resistió usted al robo?

                       1. Sí
                       2. No
                       99. Ns/Nc

IRV12                  ¿Resultó herido en el hecho?

                       1. Sí
                       2. No
                       99. Ns/Nc

IRV13                  ¿Qué tipo de lesión física sufrió?
IRV13_1                Contusión

                       1.Sí

IRV13_2                Cortes

                       1Si

IRV13_3                Arañazos

                       1.Sí

IRV13_4                Moretones (incluyendo el ojo morado)

                       1.Sí

IRV13_5                Huesos rotos

                       1 Si


60 - INDEC. ENV 2017


## Página 61

IRV13_6    Dientes rotos

           1.Sí

IRV13_7    Amputación de algún miembro

           1.Sí

IRV13_8    Lesión interna

           1.Sí

IRV13_9    Herida con arma blanca

           1.Sí

IRV13_10   Herida de bala

           Si

IRV13_99   Ns/Nc

           99.Ns/Nc

IRV14      La última vez que ocurrió este hecho en 2016, ¿qué le robaron?
IRV14_1    Bolso, cartera, mochila, portafolio

           1.Sí

IRV14_2    Equipo electrónico (computadora, reproductor de música, tablet)

           1.Sí

IRV14_3    Teléfono celular

           1.Sí

IRV14_4    Dinero, tarjeta de crédito, cheques

           1.Sí

IRV14_5    Joyas, relojes

           1.Sí

IRV14_6    Documentos de identificación

           1.Sí

IRV14_7    Vestimenta y calzado


                                          Documento para la utilización de la base de datos usuario - 61


## Página 62

1.Sí

IRV14_8                Equipo deportivo (raquetas, pelotas, etc.)

                       1.Sí

IRV14_9                Bicicleta

                       1.Sí

IRV14_10               Arma de fuego

                       1.Sí

IRV14_11               Otro

                       1.Sí

IRV14_99               Ns/Nc

                       99.Ns/Nc

                       Y la última vez que ocurrió este hecho, ¿cuánto estima que fue el valor del/los bien/es
IRV15
                       robados?

                       (Cantidad en cifras)

IRV15_nsnc             99. Ns/Nc

IRV16                  De los bienes que le robaron, ¿alguno estaba asegurado?

                       1. Sí
                       2. No
                       99. Ns/Nc

IRV17                  Y la última vez que ocurrió este hecho, ¿usted o alguna otra persona hizo la denuncia formal?

                       1. Sí
                       2. No
                       99. Ns/Nc

IRV18                  ¿Dónde lo denunció?

                       1. Policía
                       2. Fiscalía
                       3. Otro organismo
                       99. Ns/Nc

                       En general, ¿qué tan satisfecho estuvo con la forma en que la autoridad competente manejó
IRV19
                       la denuncia?

62 - INDEC. ENV 2017


## Página 63

1. Muy satisfecho
           2. Satisfecho
           3. Insatisfecho
           4. Muy insatisfecho
           99. Ns/Nc

IRV20      ¿Por qué motivos quedó insatisfecho?
IRV20_1    No quisieron tomar la denuncia

           1.Sí

IRV20_2    No se interesaron o no hicieron lo suficiente

           1.Sí

IRV20_3    No encontraron o no detuvieron al autor

           1.Sí

IRV20_4    No recuperaron lo robado

           1.Sí

IRV20_5    No lo mantuvieron informado

           1.Sí

IRV20_6    No lo trataron correctamente/Fueron maleducados

           1. Sí

IRV20_7    Otra razón

           1.Sí

IRV20_99   Ns/Nc

           99.Ns/Nc

IRV21      ¿Por qué no realizó la denuncia?
IRV21_1    Lo sucedido no era importante

           1. Sí

IRV21_2    Lo resolvió por su cuenta

           1.Sí

IRV21_3    Desconfianza en las autoridades


                                         Documento para la utilización de la base de datos usuario - 63


## Página 64

1. Sí

IRV21_4                No tenía seguro

                       Si

IRV21_5                Falta de pruebas

                       1.Sí

IRV21_6                Miedo o vergüenza

                       1. Sí

IRV21_7                Desconocimiento o dificultad para hacer la denuncia

                       1. Sí

IRV21_8                Otra razón

                       1. Sí

IRV21_99               Ns/Nc

                       99. Ns/Nc

                                              HURTOS PERSONALES

IHP01                  La última vez que ocurrió este hecho en 2016, ¿ocurrió…

                       1. …cerca de donde vive?
                       2. …en esta ciudad, pero no en su barrio?
                       3. …en otro lugar de esta provincia?
                       4. …en otra provincia del país?
                       5. …en otro país?
                       99. Ns/Nc

IHP01a                 ¿Cuál?

                       2 Ciudad Autónoma de Buenos Aires
                       6 Buenos Aires
                       10 Catamarca
                       14 Córdoba
                       18 Corrientes
                       22 Chaco
                       26 Chubut
                       30 Entre Ríos
                       34 Formosa
                       38 Jujuy


64 - INDEC. ENV 2017


## Página 65

42 La Pampa
          46 La Rioja
          50 Mendoza
          54 Misiones
          58 Neuquén
          62 Río Negro
          66 Salta
          70 San Juan
          74 San Luis
          78 Santa Cruz
          82 Santa Fe
          86 Santiago del Estero
          90 Tucumán
          94 Tierra del Fuego

IHP02     Para ser más específicos, ¿este hecho ocurrió en…

          1. …la calle?
          2. …el transporte público?
          3. … la plaza/el parque?
          4. …su trabajo?
          5. …una institución educativa?
          6. …un mercado/supermercado/centro comercial?
          7. …el banco/cajero automático?
          8. …la cancha?
          9. …un restaurante/bar/boliche?
          10. …la ruta?
          99. Ns/Nc

IHP03     ¿A qué hora aproximada ocurrió?

          1. Mañana/Mediodía (de 07:00 a 12:59)
          2. Tarde (de 13:00 a 19:59)
          3. Noche (de 20:00 a 23:59)
          4. Madrugada (de 00:00 a 06:59)
          99. Ns/Nc

IHP04     La última vez que ocurrió este hecho en 2016, ¿qué le robaron?
IHP04_1   Bolso, cartera, mochila, portafolio

          1. Sí

IHP04_2   Equipo electrónico (televisor, computadora, reproductor de música, tablet)

          1. Sí

IHP04_3   Teléfono celular

          1. Sí



                                        Documento para la utilización de la base de datos usuario - 65


## Página 66

IHP04_4                Dinero, tarjeta de crédito, cheques

                       1. Sí

IHP04_5                Joyas, relojes

                       1.Sí

IHP04_6                Documentos de identificación

                       1. Sí

IHP04_7                Vestimenta y calzado

                       1. Sí

IHP04_8                Bicicleta

                       1. Sí

IHP04_9                Equipo deportivo (raquetas, pelotas, etc.)

                       1.Sí

IHP04_10               Arma de fuego

                       1. Sí

IHP04_11               Otro

                       1. Sí

IHP04_99               Ns/Nc

                       99. Ns/Nc

IHP05                  De los bienes que le robaron, ¿estaba alguno asegurado?

                       1. Sí
                       2. No
                       99. Ns/Nc

IHP06                  ¿Cuánto estima que fue el valor del/los bien/es robados?

                       (Cantidad en cifras)

IHP06_nsnc             99. Ns/Nc

IHP07                  La última vez que ocurrió este hecho, ¿usted o alguna otra persona hizo la denuncia formal?



66 - INDEC. ENV 2017


## Página 67

1. Sí
           2. No
           99. Ns/Nc

IHP08      ¿Dónde lo denunció?

           1. Policía
           2. Fiscalía
           3. Otro organismo
           99. Ns/Nc

           En general, ¿qué tan satisfecho estuvo con la forma en que la autoridad competente manejó
IHP09
           la denuncia?

           1. Muy satisfecho
           2. Satisfecho
           3. Insatisfecho
           4. Muy insatisfecho
           99. Ns/Nc

IHP10      ¿Por qué motivos quedó insatisfecho?
IHP10_1    No quisieron tomar la denuncia

           1. Sí

IHP10_2    No se interesaron o no hicieron lo suficiente

           1. Sí

IHP10_3    No encontraron o no detuvieron al autor

           1. Sí

IHP10_4    No recuperaron lo robado

           1. Sí

IHP10_5    No lo mantuvieron informado

           1. Sí

IHP10_6    No lo trataron correctamente/Fueron maleducados

           1. Sí

IHP10_7    Otra razón

           1. Sí

IHP10_99   Ns/Nc


                                         Documento para la utilización de la base de datos usuario - 67


## Página 68

99. Ns/Nc

IHP11                  ¿Por qué no realizó la denuncia?
IHP11_1                Lo sucedido no era importante

                       1. Sí

IHP11_2                Lo resolvió por su cuenta

                       1 Si

IHP11_3                Desconfianza en las autoridades

                       1.Sí

IHP11_4                No tenía seguro

                       1.Sí

IHP11_5                Falta de pruebas

                       1.Sí

IHP11_6                Miedo o vergüenza

                       1.Sí

IHP11_7                Desconocimiento o dificultad para hacer la denuncia

                       1.Sí

IHP11_8                Otra razón

                       1.Sí

IHP11_99               Ns/Nc

                       99.Ns/Nc

                                                FRAUDE BANCARIO

IFB01                  La última vez que ocurrio este hecho en 2016…

                       1. …¿usaron de manera indebida su tarjeta de crédito/débito en un establecimiento?
                       2. …¿usaron de manera indebida su tarjeta de crédito/débito en Internet?
                       3. …¿retiraron dinero o le vaciaron su cuenta bancaria?
                       4. Otro
                       99. Ns/Nc

IFB02                  ¿Cuánto estima que fue el valor total del fraude?


68 - INDEC. ENV 2017


## Página 69

(cantidad en cifras)

IFB02_nsnc   99.Ns/Nc

IFB03        Y la última vez que ocurrió este hecho, ¿usted o alguna otra persona hizo la denuncia formal?

             1. Sí
             2. No
             99. Ns/Nc

IFB04        ¿Dónde lo denunció?

             1. Policía
             2. Fiscalía
             3. Otro organismo
             99. Ns/Nc

             En general, ¿qué tan satisfecho estuvo con la forma en que la autoridad competente manejó
IFB05
             la denuncia?

             1. Muy satisfecho
             2. Satisfecho
             3. Insatisfecho
             4. Muy insatisfecho
             99. Ns/Nc

IFB06        ¿Por qué motivos quedó insatisfecho?
IFB06_1      No quisieron tomar la denuncia

             1.Sí

IFB06_2      No quisieron tomar la denuncia

             1.Sí

IFB06_3      No encontraron o no detuvieron al autor

             1.Sí

IFB06_4      No recuperaron el valor del fraude

             1.Sí

IFB06_5      No lo mantuvieron informado

             1.Sí

IFB06_6      No lo trataron correctamente/Fueron maleducados

             1. Sí

                                           Documento para la utilización de la base de datos usuario - 69


## Página 70

IFB06_7                Otra razón

                       1.Sí

IFB06_99               Ns/Nc

                       99.Ns/Nc

IFB07                  ¿Por qué no realizó la denuncia?
IFB07_1                El banco resolvió el fraude y le reintegró su dinero

                       1. Sí

IFB07_2                Lo resolvió por su cuenta

                       1.Sí

IFB07_3                Desconfianza en las autoridades

                       1.Sí

IFB07_4                No tenía seguro

                       1.Sí

IFB07_5                Falta de pruebas

                       1.Sí

IFB07_6                Miedo o vergüenza

                       1.Sí

IFB07_7                Desconocimiento o dificultad para hacer la denuncia

                       1.Sí

IFB07_8                Otra razón

                       1.Sí

IFB07_99               Ns/Nc

                       99.Ns/Nc

                                                   ESTAFA/FRAUDE

IEF01                  La última vez que ocurrió este hecho en 2016, ¿fue durante la compra de…



70 - INDEC. ENV 2017


## Página 71

1. …productos?
             2. …servicios?
             3. …productos y servicios?
             99. Ns/Nc

             Y esta última vez, ¿el proveedor de los bienes y servicios era una empresa o una persona
IEF02
             particular?

             1. Una empresa
             2. Una persona
             99. Ns/Nc

IEF03        Esta transacción, ¿se realizó a través de Internet?

             1. Sí
             2. No
             99. Ns/Nc

IEF04        ¿Cuánto estima que fue el valor total del fraude?

             (Cantidad en cifras)

IEF04_nsnc   99.Ns/Nc

IEF05        Y la última vez que ocurrió este hecho, ¿usted o alguna otra persona hizo la denuncia formal?

             1. Sí
             2. No
             99. Ns/Nc

IEF06        ¿Dónde lo denunció?

             1. Policia
             2. Fiscalía
             3. Otro organismo
             99. Ns/Nc

             En general, ¿qué tan satisfecho estuvo con la forma en que la autoridad competente manejó
IEF07
             la denuncia?

             1. Muy satisfecho
             2. Satisfecho
             3. Insatisfecho
             4. Muy insatisfecho
             99. Ns/Nc

IEF08        ¿Por qué motivos quedó insatisfecho?
IEF08_1      No quisieron tomar la denuncia

             1. Sí


                                           Documento para la utilización de la base de datos usuario - 71


## Página 72

IEF08_2                No se interesaron o no hicieron lo suficiente

                       1. Sí

IEF08_3                No encontraron o no detuvieron al autor

                       1. Sí

IEF08_4                No se recuperó el valor del fraude/de la estafa

                       1. Sí

IEF08_5                No lo mantuvieron informado

                       1. Sí

IEF08_6                No lo trataron correctamente/Fueron maleducados

                       1. Sí

IEF08_7                Otra razón

                       1. Sí

IEF08_99               Ns/Nc

                       99. Ns/Nc

IEF09                  ¿Por qué no realizó la denuncia?
IEF09_1                Lo sucedido no era importante

                       1. Sí

IEF09_2                Lo resolvió por su cuenta

                       1. Sí

IEF09_3                Desconfianza en las autoridades

                       1. Sí

IEF09_4                Falta de pruebas

                       1. Sí

IEF09_5                Miedo o vergüenza

                       1. Sí

IEF09_6                Desconocimiento o dificultad para hacer la denuncia


72 - INDEC. ENV 2017


## Página 73

1. Sí

IEF09_7    Otra razón

           1. Sí

IEF09_99   Ns/Nc

           99. Ns/Nc

                                      AGRESIÓN FISICA

IAF01      La última vez que ocurrió este hecho, ¿ocurrió...

           1. ...en su casa?
           2. ...cerca de donde vive?
           3. ...en esta ciudad, pero no en su barrio?
           4. ...en otro lugar de esta provincia?
           5. ...en otra provincia del país?
           6. ...en otro país?
           99. Ns/Nc

IAF01a     ¿Cuál?

           2. Ciudad Autónoma de Buenos Aires
           6. Buenos Aires
           10. Catamarca
           14. Cordoba
           18. Corrientes
           22. Chaco
           26. Chubut
           30. Entre Rios
           34. Formosa
           38. Jujuy
           42. La Pampa
           46. La Rioja
           50. Mendoza
           54. Misiones
           58. Neuquen
           62. Rio Negro
           66. Salta
           70. San Juan
           74. San Luis
           78. Santa Cruz
           82. Santa Fe
           86. Santiago del Estero
           90. Tucumán

                                            Documento para la utilización de la base de datos usuario - 73


## Página 74

94. Tierra del Fuego

IAF02                  Y para ser más específicos, ¿este hecho ocurrió en…

                       1. ...la calle?
                       2. ...el transporte público?
                       3. ...la plaza/el parque?
                       4. ...su trabajo?
                       5. ...una institución educativa?
                       6. ...un mercado/supermercado/centro comercial?
                       7. ...el banco/cajero automático?
                       8. ...la cancha?
                       9. ...un restaurante/bar/boliche?
                       10. ...la ruta?
                       99. Ns/Nc

IAF03                  ¿A qué hora aproximada ocurrió?

                       1. Mañana/Mediodía (de 07:00 a 12:59)
                       2. Tarde (de 13:00 a 19:59)
                       3. Noche (de 20:00 a 23:59)
                       4. Madrugada (de 00:00 a 06:59)
                       99. Ns/Nc

IAF04                  ¿Me podría decir si el atacante o los atacantes eran para usted...
IAF04_1                ...desconocido(s)?

                       1. Sí

IAF04_2                ...conocido(s) de vista solamente?

                       1. Sí

IAF04_3                ...conocido(s) de poco trato?

                       1. Sí

IAF04_4                ...conocido(s) cercano(s)?

                       1. Sí

IAF04_5                ...familiar(es)?

                       1. Sí

IAF04_99               Ns/Nc

                       99.Ns/Nc

IAF05                  ¿Cuántos atacantes lo agredieron?


74 - INDEC. ENV 2017


## Página 75

1. Uno
           2. Dos
           3. Tres
           4. Más de tres
           99. Ns/Nc

IAF06      ¿Podría decirme si eran hombres, mujeres u hombres y mujeres?

           1. Sólo hombres
           2. Sólo mujeres
           3. Hombres y mujeres
           99. Ns/Nc

           ¿Tenía/n el/los atacantes algún tipo de arma o algún objeto que amenazaran con utilizar
IAF07
           como arma?

           1. Sí
           2. No
           99. Ns/Nc

IAF08      ¿Qué arma era?
IAF08_1    Arma de fuego

           1. Sí

IAF08_2    Cuchillo u objeto afilado

           1. Sí

IAF08_3    Objeto contundente u otro objeto utilizado como arma (bate, palo, tubo, cuerda, etc.)

           1. Sí

IAF08_4    Otra

           1. Sí

IAF08_99   Ns/Nc

           99. Ns/Nc

IAF09      ¿Se utilizó efectivamente el arma?

           1. Sí
           2. No
           99. Ns/Nc

IAF10      ¿Utilizaron otro tipo de violencia física?

           1. Sí

                                           Documento para la utilización de la base de datos usuario - 75


## Página 76

2. No
                       99. Ns/Nc

                       La última vez que esto ocurrió, ¿parecía/n el/los atacantes/s estar bajo la influencia del
IAF11
                       alcohol y/o de drogas?

                       1. Sí
                       2. No
                       99. Ns/Nc

IAF12                  ¿Se resistió usted a la agresión?

                       1. Sí
                       2. No
                       99. Ns/Nc

IAF13                  La última vez que ocurrió este hecho en 2016, ¿qué tipo de lesión física sufrió?
IAF13_1                Contusión

                       1. Sí

IAF13_2                Cortes

                       1. Sí

IAF13_3                Arañazos

                       1. Sí

IAF13_4                Moretones (incluyendo el ojo morado)

                       1. Sí

IAF13_5                Huesos rotos

                       1. Sí

IAF13_6                Dientes rotos

                       1. Sí

IAF13_7                Amputación de algún miembro

                       1. Sí

IAF13_8                Lesión interna

                       1. Sí

IAF13_9                Herida con arma blanca


76 - INDEC. ENV 2017


## Página 77

1. Sí

IAF13_10   Herida de bala

           1. Sí

IAF13_99   Ns/Nc

           99. Ns/Nc

IAF14      Y como consecuencia de esa lesión, ¿recibió atención médica?

           1. Sí
           2. No
           99. Ns/Nc

IAF15      Por esa lesión, ¿acudió a...

           1. ...un médico o enfermera particular?
           2. ...salita, clínica u hospital?
           99. Ns/Nc

IAF16      Y la última vez que ocurrió este hecho, ¿usted o alguna otra persona hizo la denuncia formal?

           1. Sí
           2. No
           99. Ns/Nc

IAF17      ¿Dónde lo denunció?

           1. Policía
           2. Fiscalía
           3. Otro organismo
           99. Ns/Nc

           En general, ¿qué tan satisfecho estuvo con la forma en que la autoridad competente manejó
IAF18.
           la denuncia?

           1. Muy satisfecho
           2. Satisfecho
           3. Insatisfecho
           4. Muy insatisfecho
           99. Ns/Nc

IAF19      ¿Por qué motivos quedó insatisfecho?
IAF19_1    No quisieron tomar la denuncia

           1. Sí

IAF19_2    No se interesaron o no hicieron lo suficiente


                                           Documento para la utilización de la base de datos usuario - 77


## Página 78

1. Sí

IAF19_3                No encontraron o no detuvieron al autor

                       1. Sí

IAF19_4                No lo mantuvieron informado

                       1. Sí

IAF19_5                No lo trataron correctamente/Fueron maleducados

                       1. Sí

IAF19_6                Otra razón

                       1. Sí

IAF19_99               Ns/Nc

                       99. Ns/Nc

IAF20                  ¿Podría decirme por qué no realizó la denuncia?
IAF20_1                Lo sucedido no era importante

                       1. Sí

IAF20_2                Lo resolvió por su cuenta

                       1. Sí

IAF20_3                Desconfianza en las autoridades

                       1. Sí

IAF20_4                Falta de pruebas

                       1. Sí

IAF20_5                Miedo o vergüenza

                       1. Sí

IAF20_6                Desconocimiento o dificultad para hacer la denuncia

                       1. Sí

IAF20_7                Otra razón

                       1. Sí


78 - INDEC. ENV 2017


## Página 79

IAF20_99   Ns/Nc

           99. Ns/Nc

                                          AMENAZAS

IAM01      La última vez que ocurrió este hecho en 2016, ¿ocurrió…

           1. ...en su casa?
           2. ...cerca de donde vive?
           3. ...en esta ciudad, pero no en su barrio?
           4. ...en otro lugar de esta provincia?
           5. ...en otra provincia del país?
           6. ...en otro país?
           99. Ns/Nc

IAM01a     ¿Cuál?

           2. Ciudad Autónoma de Buenos Aires
           6. Buenos Aires
           10. Catamarca
           14. Cordoba
           18. Corrientes
           22. Chaco
           26. Chubut
           30. Entre Rios
           34. Formosa
           38. Jujuy
           42. La Pampa
           46. La Rioja
           50. Mendoza
           54. Misiones
           58. Neuquen
           62. Rio Negro
           66. Salta
           70. San Juan
           74. San Luis
           78. Santa Cruz
           82. Santa Fe
           86. Santiago del Estero
           90. Tucumán
           94. Tierra del Fuego

IAM02      Y para ser más específicos, ¿este hecho ocurrió en...

           1. ...la calle?
           2. ...el transporte público?
           3. ...la plaza/el parque?
           4. ...su trabajo?


                                            Documento para la utilización de la base de datos usuario - 79


## Página 80

5. ...una institución educativa?
                       6. ...un mercado/supermercado/centro comercial?
                       7. ...el banco/cajero automático?
                       8. ...la cancha?
                       9. ...un restaurante/bar/boliche?
                       10. ...la ruta?
                       99. Ns/Nc

IAM03                  ¿A qué hora aproximada ocurrió?

                       1. Mañana/Mediodía (de 07:00 a 12:59)
                       2. Tarde (de 13:00 a 19:59)
                       3. Noche (de 20:00 a 23:59)
                       4. Madrugada (de 00:00 a 06:59)
                       99. Ns/Nc

IAM04                  ¿Me podría decir si la(s) persona(s) que lo/la amenazaron eran para usted…
IAM04_1                ...desconocido(s)?

                       1. Sí

IAM04_2                ...conocido(s) de vista solamente?

                       1. Sí

IAM04_3                ...conocido(s) de poco trato?

                       1. Sí

IAM04_4                ...conocido(s) cercano(s)?

                       1. Sí

IAM04_5                ...familiar(es)?

                       1. Sí

IAM04_99               Ns/Nc

                       99. Ns/Nc

IAM05                  ¿Cuántas personas lo/la amenazaron?

                       1. Uno
                       2. Dos
                       3. Tres
                       4. Más de tres
                       99. Ns/Nc

                       ¿Podría decirme si las personas que lo/la amenazaron eran hombres, mujeres u hombres y
IAM06
                       mujeres?

80 - INDEC. ENV 2017


## Página 81

1. Sólo hombres
           2. Sólo mujeres
           3. Hombres y mujeres
           99. Ns/Nc

           ¿La/s persona/s que lo/la amenazaron tenía/n algún tipo de arma o algún objeto que
IAM07
           amenazaran con utilizar como arma?

           1. Sí
           2. No
           99. Ns/Nc

IAM08      ¿Qué arma era?
IAM08_1    Arma de fuego

           1. Sí

IAM08_2    Cuchillo u objeto afilado

           1. Sí

IAM08_3    Objeto contundente u otro objeto utilizado como arma (bate, palo, tubo, cuerda, etc.)

           1. Sí

IAM08_4    Otra

           1. Sí

IAM08_99   Ns/Nc

           99. Ns/Nc

           La última vez que esto ocurrió, ¿parecía/n el/los atacantes/s estar bajo la influencia del
IAM09
           alcohol y/o de drogas?

           1. Sí
           2. No
           99. Ns/Nc

IAM10      Y la última vez que ocurrió este hecho, ¿usted o alguna otra persona hizo la denuncia formal?

           1. Sí
           2. No
           99. Ns/Nc

IAM11      ¿Dónde lo denunció?

           1. Policía
           2. Fiscalía

                                          Documento para la utilización de la base de datos usuario - 81


## Página 82

3. Otro organismo
                       99. Ns/Nc

                       En general, ¿qué tan satisfecho estuvo con la forma en que la autoridad competente manejó
IAM12.
                       la denuncia?

                       1. Muy satisfecho
                       2. Satisfecho
                       3. Insatisfecho
                       4. Muy insatisfecho
                       99. Ns/Nc

IAM13                  ¿Por qué motivos quedó insatisfecho?
IAM13_1                No quisieron tomar la denuncia

                       1. Sí

IAM13_2                No se interesaron o no hicieron lo suficiente

                       1. Sí

IAM13_3                No encontraron o no detuvieron al autor

                       1. Sí

IAM13_4                No lo mantuvieron informado

                       1. Sí

IAM13_5                No lo trataron correctamente/Fueron maleducados

                       1. Sí

IAM13_6                Otra razón

                       1. Sí

IAM13_99               Ns/Nc

                       99. Ns/Nc

IAM14                  ¿Podría decirme por qué no realizó la denuncia?
IAM14_1                No era importante

                       1. Sí

IAM14_2                Lo resolvió por su cuenta o no era adecuado para la policía

                       1. Sí

IAM14_3                Desconfianza en las autoridades

82 - INDEC. ENV 2017


## Página 83

1. Sí

IAM14_4    Falta de pruebas

           1. Sí

IAM14_5    Miedo o vergüenza

           1. Sí

IAM14_6    Desconocimiento o dificultad para hacer la denuncia

           1. Sí

IAM14_7    Otra razón

           1.Sí

IAM14_99   Ns/Nc

           99. Ns/Nc

                              CORRUPCIÓN (SOBORNO PASIVO)

           Durante 2016, ¿le solicitó un pago o regalo a cambio de realizar sus tareas o para evitarle una
ICO01
           multa personal de...
ICO01a     ...la Policía Federal?

           1. Sí
           2. No
           99. Ns/Nc

ICO01b     ...la Gendarmería Nacional?

           1. Sí
           2. No
           99. Ns/Nc

ICO01c     ...la Prefectura Naval?

           1. Sí
           2. No
           99. Ns/Nc

ICO01d     ...la Policía Provincial/Policía de la Ciudad?

           1. Sí
           2. No
           99. Ns/Nc


                                           Documento para la utilización de la base de datos usuario - 83


## Página 84

ICO01e                 ...el Poder Judicial?

                       1. Sí
                       2. No
                       99. Ns/Nc

ICO01f                 ...Aduana o AFIP?

                       1. Sí
                       2. No
                       99. Ns/Nc

ICO01g                 Otros empleados o funcionarios públicos

                       1. Sí
                       2. No
                       99. Ns/Nc

ICO02                  Cuántas veces le sucedió esto con personal de...
ICO02a                 ...la Policía Federal?

                       ( Cantidad en cifras)

ICO02b                 ...la Gendarmería Nacional?

                       ( Cantidad en cifras)

ICO02c                 ...la Prefectura Naval?

                       ( Cantidad en cifras)

ICO02d                 ...la [Policía Provincial/Policía de la Ciudad]?

                       ( Cantidad en cifras)

ICO02e                 ...el Poder Judicial?

                       ( Cantidad en cifras)

ICO02f                 ...Aduana o AFIP?

                       ( Cantidad en cifras)

ICO02g                 Otros empleados o funcionarios públicos

                       ( Cantidad en cifras)

                       La última vez que ocurrió este hecho en 2016, ¿el personal de cuál de estas instituciones le
ICO03
                       solicitó la coima?

                       1. Policía Federal

84 - INDEC. ENV 2017


## Página 85

2. Gendarmería Nacional
          3. Prefectura Naval
          4. Policía Provincial/Policía de la Ciudad
          5. Poder Judicial
          6. Aduana o AFIP
          7. Otros empleados o funcionarios públicos

ICO04     La última vez que le sucedió, ¿usted o alguna otra persona hizo la denuncia formal?

          1. Sí
          2. No
          99. Ns/Nc

ICO05     ¿Dónde lo denunció?

          1. Policía
          2. Fiscalía
          3. Supervisor de la persona que le pidió el pago/regalo (dentro de la misma institución)
          4. Otro organismo
          99. Ns/Nc

          En general, ¿qué tan satisfecho estuvo con la forma en que la autoridad competente manejó
ICO06
          el incidente?

          1. Muy satisfecho
          2. Satisfecho
          3. Insatisfecho
          4. Muy insatisfecho
          99. Ns/Nc

ICO07     ¿Por qué motivos quedó insatisfecho?
ICO07_1   No quisieron tomar la denuncia

          1. Sí

ICO07_2   No se interesaron o no hicieron lo suficiente

          1. Sí

ICO07_3   No encontraron o no detuvieron al autor

          1. Sí

ICO07_4   No lo mantuvieron informado

          1. Sí

ICO07_5   No lo trataron correctamente/Fueron maleducados

          1. Sí


                                          Documento para la utilización de la base de datos usuario - 85


## Página 86

ICO07_6                Tardaron en proceder

                       1. Sí

ICO07_7                Otra razón

                       1. Sí

ICO07_99               Ns/Nc

                       99. Ns/Nc

ICO08                  ¿Podría decirme por qué no realizó la denuncia?
ICO08_1                Lo sucedido no era importante

                       1. Sí

ICO08_2                Lo resolvió por su cuenta

                       1. Sí

ICO08_3                Desconfianza en las autoridades

                       1. Sí

ICO08_4                Falta de pruebas

                       1. Sí

ICO08_5                Miedo o vergüenza

                       1. Sí

ICO08_6                Desconocimiento o dificultad para hacer la denuncia

                       1. Sí

ICO08_7                Otra razón

                       1. Sí

ICO08_99               Ns/Nc

                       99. Ns/Nc

                                              OFENSAS SEXUALES

IOS01                  ¿La última vez que ocurrió este hecho, ¿ocurrió…

                       1. ...en su casa?


86 - INDEC. ENV 2017


## Página 87

2. ...cerca de donde vive?
         3. ...en esta ciudad, pero no en su barrio?
         4. ...en otro lugar de esta provincia?
         5. ...en otra provincia del país?
         6. ...en otro país?
         99. Ns/Nc

IOS01a   ¿Cuál?

         2. Ciudad Autónoma de Buenos Aires
         6. Buenos Aires
         10. Catamarca
         14. Cordoba
         18. Corrientes
         22. Chaco
         26. Chubut
         30. Entre Rios
         34. Formosa
         38. Jujuy
         42. La Pampa
         46. La Rioja
         50. Mendoza
         54. Misiones
         58. Neuquen
         62. Rio Negro
         66. Salta
         70. San Juan
         74. San Luis
         78. Santa Cruz
         82. Santa Fe
         86. Santiago del Estero
         90. Tucumán
         94. Tierra del Fuego

IOS02    Y para ser más específicos, ¿este hecho ocurrió en…

         1. ...la calle?
         2. ...el transporte público?
         3. ...la plaza/el parque?
         4. ...su trabajo?
         5. ...una institución educativa?
         6. ...un mercado/supermercado/centro comercial?
         7. ...el banco/cajero automático?
         8. ...la cancha?
         9. ...un restaurante/bar/boliche?
         10. ...la ruta?
         99. Ns/Nc

IOS03    La última vez que ocurrió este hecho en 2016, ¿conocía usted al atacante o los atacantes?



                                          Documento para la utilización de la base de datos usuario - 87


## Página 88

1. Sí
                       2. No
                       99. Ns/Nc

IOS04                  ¿Qué tipo de vínculo mantenía con el agresor o los agresores?

                       1. Esposo/a, novio/a, pareja
                       2. Ex esposo/a, ex novio/a, ex pareja
                       3. Familiar
                       4. Amigo/a
                       5. Jefe/a, profesor/a u otra persona en posición de autoridad
                       6. Compañero/a de trabajo, compañero/a de escuela/universidad
                       7. Otro/a
                       99. Ns/Nc

IOS05                  Y la última vez que ocurrió este hecho, ¿usted o alguna otra persona hizo la denuncia formal?

                       1. Sí
                       2. No
                       99. Ns/Nc

IOS06                  ¿Dónde lo denunció?

                       1. Policía
                       2. Fiscalía
                       3. Organismo especializado en violencia de género
                       4. Otro
                       99. Ns/Nc

                       En general, ¿qué tan satisfecho estuvo con la forma en que la autoridad competente manejó
IOS07
                       la denuncia?

                       1. Muy satisfecho
                       2. Satisfecho
                       3. Insatisfecho
                       4. Muy insatisfecho
                       99. Ns/Nc

IOS08                  ¿Por qué motivos quedó insatisfecho?
IOS08_1                No quisieron tomar la denuncia

                       1. Sí

IOS08_2                No se interesaron o no hicieron lo suficiente

                       1. Sí

IOS08_3                No encontraron o no detuvieron al autor

                       1. Sí


88 - INDEC. ENV 2017


## Página 89

IOS08_4                   No lo mantuvieron informado

                          1. Sí

IOS08_5                   No lo trataron correctamente/Fueron maleducados

                          1. Sí

IOS08_6                   Otra razón

                          1. Sí

IOS08_99                  Ns/Nc

                          99. Ns/Nc

IOS09                     ¿Podría decirme por qué no realizó la denuncia?
IOS09_1                   Desconfianza en las autoridades

                          1. Sí

IOS09_2                   Falta de pruebas

                          1. Sí

IOS09_3                   Miedo o vergüenza

                          1. Sí

IOS09_4                   Desconocimiento o dificultad para hacer la denuncia

                          1. Sí

IOS09_5                   Otra razón

                          1. Sí

IOS09_99                  Ns/Nc

                          99. Ns/Nc

                                               EXCLUSIÓN DE DELITOS

ira_otro_pais_provincia   Robo o hurto de automóvil/camioneta/camión ocurridos en otro pais o provincia

                          0.No
                          1. Otra provincia
                          2. Otro país

iha_otro_pais_provincia   Hurto de autopartes de automóvil/camioneta/camión ocurridos en otro país o provincia


                                                        Documento para la utilización de la base de datos usuario - 89


## Página 90

0.No
                          1. Otra provincia
                          2. Otro país

irm_otro_pais_provincia   Robo o hurto de motocicleta o ciclomotor ocurridos en otro país o provincia

                          0.No
                          1. Otra provincia
                          2. Otro país

ise_otro_pais_provincia   Secuestros ocurridos en otro país o provincia

                          0.No
                          1. Otra provincia
                          2. Otro país

irv_otro_pais_provincia   Robo con violencia ocurridos en otros país o provincia

                          0.No
                          1. Otra provincia
                          2. Otro país

ihp_otro_pais_provincia   Hurtos personales ocurridos en otro país o provincia

                          0.No
                          1. Otra provincia
                          2. Otro país

iaf_otro_pais_provincia   Agresión física ocurridas en otro país o provincia

                          0.No
                          1. Otra provincia
                          2. Otro país

iam_otro_pais_provincia Amenazas ocurridas en otro país o provincia

                          0.No
                          1. Otra provincia
                          2. Otro país

ios_otro_pais_provincia   Ofensas sexuales ocurridas en otro país o provincia

                          0.No
                          1. Otra provincia
                          2. Otro país

                                               FACTORES DE EXPANSIÓN

f_hogar                   Factor de expansión del hogar


90 - INDEC. ENV 2017


## Página 91

f_persona   Factor de expansión del individuo




                                           Documento para la utilización de la base de datos usuario - 91
