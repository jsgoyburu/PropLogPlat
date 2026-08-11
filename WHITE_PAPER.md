# WHITE_PAPER.md — Marco pedagógico, didáctico y político de IPC-Lógica

> Documento de principios. Establece la fuente de verdad conceptual que orienta las decisiones de diseño, desarrollo y uso del sistema.
> No es un manual técnico. Es el texto que responde a la pregunta: **¿por qué el sistema funciona como funciona?**

---

## Índice

1. [Contexto institucional](#1-contexto-institucional)
2. [El problema que origina el proyecto](#2-el-problema-que-origina-el-proyecto)
3. [Marco teórico](#3-marco-teórico)
4. [La arquitectura híbrida como posición pedagógica](#4-la-arquitectura-híbrida-como-posición-pedagógica)
5. [El error como objeto pedagógico](#5-el-error-como-objeto-pedagógico)
6. [La verificación semántica como decisión didáctica](#6-la-verificación-semántica-como-decisión-didáctica)
7. [La analítica educativa como herramienta de intervención](#7-la-analítica-educativa-como-herramienta-de-investigación)
8. [La lógica como propedéutica epistemológica](#8-la-lógica-como-propedéutica-epistemológica)
9. [Principios políticos del diseño](#9-principios-políticos-del-diseño)
10. [Lo que el sistema deliberadamente no hace](#10-lo-que-el-sistema-deliberadamente-no-hace)
11. [El proyecto como investigación basada en diseño](#11-el-proyecto-como-investigación-basada-en-diseño)

---

## 1. Contexto institucional

### El CBC-UBA y el IPC

El Ciclo Básico Común (CBC) de la Universidad de Buenos Aires es el ciclo de ingreso a todas las carreras de la universidad. No tiene aranceles, no tiene examen de ingreso, y es de acceso público. Recibe anualmente decenas de miles de estudiantes de la región metropolitana —y de todo el país— con trayectorias socioeducativas muy heterogéneas.

Introducción al Pensamiento Científico (IPC) es una materia del CBC que se dicta en este ciclo para todas las carreras. Su función declarada es doble: introducir a los estudiantes en el pensamiento científico como objeto de reflexión epistemológica, y enseñar herramientas formales —entre ellas, lógica proposicional— como instrumentos para ese análisis.

El libro de texto canónico es Irving Copi, *Introduction to Logic*, en la traducción al español. La notación de Copi —punto medio para la conjunción (`·`), herradura para el condicional (`⊃`), tres rayas para el bicondicional (`≡`)— es la que los estudiantes aprenden y usan en el curso.

### Las condiciones de masividad

El IPC se dicta en cientos de comisiones paralelas con miles de estudiantes simultáneos. Esta escala produce condiciones pedagógicas específicas:

- El tiempo de atención docente individual es estructuralmente limitado.
- Los procesos de evaluación son costosos en términos de tiempo y trabajo.
- La diversidad de trayectorias previas (en matemática, filosofía, lógica) es muy amplia.
- El primer examen parcial funciona, en la práctica, como un umbral de continuidad en la carrera.

No se trata de condiciones excepcionales: son las condiciones normales y previsibles de la enseñanza universitaria pública masiva en Argentina. El diseño del sistema parte de asumir estas condiciones como dadas para la enseñaza actual, no como problemas a eliminar por medio de un sistema informático.

---

## 2. El problema que origina el proyecto

### El primer examen como umbral de permanencia

La investigación que origina IPC-Lógica identifica un problema específico: el primer examen parcial —que incluye ejercicios de lógica proposicional— funciona empíricamente como un umbral de continuidad en la cursada.

Los estudiantes que no aprueban ese primer parcial tienen probabilidades significativamente menores de completar el cuatrimestre. Este efecto no se explica únicamente por conocimiento previo insuficiente: también incide la falta de práctica estructurada en el período entre las clases teóricas y el examen.

### El diagnóstico

Entre las clases donde se enseña lógica proposicional y el primer parcial, los estudiantes tienen muy pocas oportunidades de practicar con retroalimentación. Los ejercicios de práctica son costosos de corregir manualmente a escala; los docentes no tienen tiempo para revisar múltiples intentos de cientos de estudiantes. El resultado es que muchos estudiantes llegan al primer parcial habiendo practicado poco y con errores no detectados ni corregidos.

### La hipótesis de intervención

IPC-Lógica parte de una hipótesis específica: **si se aumenta la práctica estructurada con retroalimentación inmediata antes del primer parcial, se reduce la distancia entre lo que los estudiantes saben hacer y lo que el examen requiere**.

Pero esta hipótesis tiene una restricción central: la práctica adicional no debe empobrecerse al punto de convertirse en entrenamiento mecánico. La lógica se enseña en IPC como instrumento de modelización conceptual; la práctica debe reforzar esa capacidad, no reemplazarla con la memorización de algoritmos.

---

## 3. Marco teórico

### 3.1 La Teoría de las Situaciones Didácticas (Brousseau)

El marco teórico central del proyecto es la Teoría de las Situaciones Didácticas (TSD) de Guy Brousseau, desarrollada originalmente para la didáctica de la matemática y adaptada al campo de la lógica por investigadoras argentinas como Gladys Palau y Ana Couló.

#### La situación a-didáctica

En la TSD, una *situación a-didáctica* es aquella en que el estudiante interactúa directamente con el *milieu* (el ambiente, el problema, los materiales) y recibe retroalimentación genuina de ese ambiente, sin mediación docente directa. El estudiante no responde a lo que cree que el docente quiere escuchar: responde a la lógica interna del problema.

Esta distinción es fundamental para el diseño del sistema. La verificación automática de IPC-Lógica está diseñada para crear condiciones de situación a-didáctica: el estudiante envía una fórmula y recibe retroalimentación de la *tabla de verdad*, no de un juicio docente. El feedback viene del milieu lógico-matemático, no de la autoridad pedagógica.

Esto tiene consecuencias concretas: la retroalimentación debe ser informativa, no solo evaluativa. No "incorrecto" sino "tu tabla y la tabla esperada difieren en estas filas". El estudiante puede trabajar con esa información para modificar su comprensión.

#### El contrato didáctico

El *contrato didáctico* es el conjunto de expectativas recíprocas, implícitas y explícitas, que regulan las relaciones entre docente, estudiante y saber. Una característica del contrato didáctico en situaciones de evaluación masiva es que tiende a volverse opaco: los criterios de evaluación no son siempre legibles, los estudiantes no siempre saben qué se espera de ellos, y los docentes no siempre pueden hacer explícito su propio sistema de criterios.

IPC-Lógica busca hacer explícito el contrato didáctico en el dominio de la práctica formal:
- La verificación es por equivalencia semántica, no por coincidencia literal. Esto está documentado y es observable.
- Los criterios de los umbrales analíticos son visibles en pantalla.
- La distinción entre verificación formal y aprobación docente es estructural y explícita.
- El comentario docente es obligatorio cuando se rechaza un intento.

#### La devolución

En la TSD, la *devolución* es el acto por el cual el docente transfiere al estudiante la responsabilidad de resolver el problema. El docente "devuelve" la tarea: el estudiante es responsable de encontrar la solución, no de adivinar lo que el docente piensa.

El desbloqueo secuencial de IPC-Lógica implementa una forma de devolución: el sistema no resuelve el ejercicio ni guía paso a paso; exige que el estudiante encuentre la formalización correcta para avanzar. La pista automática (cuando está disponible) está diseñada como orientación al proceso, no como reducción de la tarea.

#### La institucionalización

La *institucionalización* es el momento en que el docente hace explícito y sistematiza el conocimiento que emergió de la situación. En el contexto de IPC-Lógica, la institucionalización ocurre en el aula: el docente usa los datos del sistema —los errores sistemáticos, los patrones de dificultad, la distribución de intentos— para reflexionar con los estudiantes sobre los obstáculos que encontraron.

El sistema proporciona los datos; la institucionalización es irreductiblemente docente.

#### Los obstáculos epistemológicos

Brousseau, siguiendo a Gaston Bachelard, distingue los *obstáculos epistemológicos*: conocimientos que en un contexto son pertinentes y eficaces, pero que en otro contexto se vuelven resistencias al aprendizaje. No son errores por ignorancia: son errores por conocimiento previo que interfiere.

En lógica proposicional, el lenguaje natural es el obstáculo epistemológico más documentado y relevante.

### 3.2 El lenguaje natural como obstáculo (Palau, Couló, Corbalan)

La investigación argentina sobre didáctica de la lógica —en particular el trabajo de Gladys Palau, Ana Couló, Gustavo Frenkel y colaboradores— identifica el lenguaje natural como el principal obstáculo en el aprendizaje de la formalización lógica.

El problema no es que los estudiantes no conozcan el lenguaje natural: es que lo conocen demasiado bien. Las construcciones del lenguaje cotidiano —"o bien... o bien", "si... entonces", "no es que... sino que"— tienen propiedades pragmáticas y semánticas que no se reducen limpiamente a los conectivos del cálculo proposicional. La conjunción "y" de la coordinación nominal no funciona igual que la conjunción lógica en todos los contextos. El condicional del lenguaje natural tiene implicaturas conversacionales que el condicional material no tiene.

Los errores sistemáticos en formalización no son errores aleatorios: son errores con estructura. Palau y Couló documentan patrones recurrentes que revelan la interferencia del lenguaje natural:
- Invertir el antecedente y el consecuente de un condicional.
- Interpretar la disyunción inclusiva como exclusiva.
- Formalizar una bicondicional como dos condicionales separados con distintas variables.
- Omitir la negación en la antecedente de un condicional negativo.

### 3.3 La didáctica de la lógica como campo (Palau-Frenkel)

El trabajo de Palau y Frenkel sobre "Didáctica de la matemática y didáctica de la lógica" establece un argumento importante: la didáctica de la lógica no puede simplemente importar los instrumentos conceptuales de la didáctica de la matemática sin adaptarlos al carácter específico de la lógica.

La lógica proposicional tiene propiedades que la distinguen de la aritmética o el álgebra:
- La existencia de múltiples formalizaciones igualmente válidas del mismo enunciado.
- La equivalencia semántica como criterio de corrección, independientemente de la forma sintáctica.
- La relación entre argumentos válidos y fórmulas lógicas (inferencia formal vs. argumentación cotidiana).
- El rol de los cuantificadores y las variables en la formalización.

Estas propiedades tienen consecuencias directas para el diseño del sistema de verificación: si hay múltiples formalizaciones correctas, no se puede verificar por coincidencia literal. La equivalencia semántica no es solo una opción técnica; es la única forma de verificación consistente con la naturaleza del objeto matemático.

### 3.4 La enseñanza de la lógica en el contexto de la filosofía de la ciencia (Arca, López, Oller et al.)

IPC/CBC no enseña lógica proposicional como matemática pura ni como técnica autónoma. La enseña como propedéutica de la epistemología: un instrumento para analizar argumentos científicos, comprender la estructura de las teorías, y evaluar la validez de razonamientos.

Este encuadre —que aparece también en los trabajos de Arca, López, Oller, Kakazu y Frenkel sobre cuestiones en torno a la formalización— tiene consecuencias para el diseño pedagógico:

1. Los ejercicios de formalización no son ejercicios de manipulación simbólica abstracta: son ejercicios de *traducción conceptual* entre el lenguaje natural y la forma lógica.
2. El diccionario de variables (la asignación explícita de letras proposicionales a enunciados del lenguaje natural) es parte constitutiva de la formalización, no solo un auxiliar mnemónico.
3. La comprobación de la validez de un argumento es una actividad con sentido: sirve para evaluar si una conclusión se sigue realmente de las premisas, no para ejercitar la memorización de reglas.

---

## 4. La arquitectura híbrida como posición pedagógica

### La máquina no evalúa: verifica

La distinción entre *verificación formal* y *evaluación pedagógica* no es solo una distinción técnica. Es una posición sobre qué puede y qué no puede saber un sistema computacional sobre el aprendizaje.

La verificación automática puede determinar si una fórmula es semánticamente equivalente a la solución del docente. Eso es todo lo que puede determinar. No puede saber si:
- El estudiante comprendió por qué eligió esa formalización.
- Las variables que usó corresponden a los enunciados del enunciado.
- El razonamiento que llevó a la respuesta no fue correcto aunque el resultado lo fuera.
- Un error es un error de comprensión o un error de tipeo.

Estas determinaciones requieren interpretación. Requieren contexto. Requieren juicio pedagógico. Solo el docente puede hacerlas.

Llamar "verificación formal" al proceso automático y "aprobación docente" al proceso humano no es un eufemismo: es una distinción conceptual que el sistema incorpora estructuralmente. Los campos `es_correcto` y `aprobado_docente` son independientes. Un intento puede ser formalmente correcto y no aprobado por el docente (si el proceso fue inadecuado). Un intento puede no ser formalmente correcto y ser aprobado por el docente (si la variante del estudiante es pedagógicamente aceptable por razones que el motor no puede ver).

### La automatización libera tiempo para la intervención

En cursos masivos, los docentes gastan una cantidad enorme de tiempo en tareas repetitivas de verificación formal que no requieren juicio pedagógico. IPC-Lógica automatiza esa verificación no para eliminar el rol docente sino para que el tiempo docente se concentre donde hace diferencia: en la interpretación de los errores, en la devolución argumentada, en el acompañamiento de trayectorias.

Esta es una inversión del argumento común sobre la tecnología educativa: no se automatiza para hacer más con menos docentes, sino para que los docentes hagan mejor lo que solo ellos pueden hacer.

### La devolución docente es obligatoria al rechazar

Cuando un docente rechaza un intento, el sistema exige que ingrese un comentario. Esta restricción es deliberada: no existe el rechazo sin explicación. Si un intento no es pedagógicamente aceptable, el docente debe decir por qué. Esto sirve al estudiante (que necesita orientación) y al docente (que debe explicitar sus criterios).

---

## 5. El error como objeto pedagógico

### El error no es un fallo: es una ventana

Desde la perspectiva de Brousseau, el error en el aprendizaje de la matemática (y por extensión, de la lógica) no es simplemente la ausencia de conocimiento correcto. Es la presencia de un conocimiento previo que, en este contexto, resulta inadecuado. El error tiene estructura: revela qué comprensión está en juego, qué obstáculo está activo.

IPC-Lógica trata el error como un objeto pedagógico valioso. Esto tiene consecuencias concretas:

**El sistema no oculta los errores.** Cuando un intento es incorrecto, el estudiante ve la tabla de verdad de su fórmula junto a la tabla esperada. No se le dice simplemente "incorrecto": se le da la información para que pueda analizar dónde divergen las tablas y reflexionar sobre la causa.

**El sistema preserva todos los intentos.** El historial completo de intentos —con las respuestas enviadas, los resultados y los comentarios docentes— está disponible tanto para el estudiante como para el docente. La trayectoria de aprendizaje es visible.

**El sistema detecta errores compartidos.** El módulo de analíticas identifica respuestas incorrectas que múltiples estudiantes ofrecieron al mismo ejercicio. Cuando muchos estudiantes cometen el mismo error, ese error deja de ser individual: se convierte en una señal de obstáculo pedagógico que merece atención colectiva.

### Los errores sistemáticos como dato de investigación

Los errores compartidos que la plataforma identifica son el equivalente computacional de lo que Palau y Couló documentan en su investigación sobre errores sistemáticos: patrones de error que revelan obstáculos epistemológicos recurrentes en el aprendizaje de la lógica.

Cuando el sistema detecta que el 40% de los estudiantes de una comisión formalizaron el condicional invertido en el mismo ejercicio, eso no es solo un dato de rendimiento: es una señal sobre la estructura del obstáculo que esa consigna activa. El docente puede usar ese dato para una intervención colectiva que aborde el obstáculo, no solo para corregir individualmente.

---

## 6. La verificación semántica como decisión didáctica

### Por qué no se verifica por coincidencia literal

Si la solución de un ejercicio de formalización es `p ⊃ q`, las siguientes fórmulas son semánticamente equivalentes y deben ser aceptadas como correctas:

- `~p ∨ q` (equivalencia del condicional)
- `~(p · ~q)` (De Morgan)
- `~~(~p ∨ q)` (doble negación)

Un sistema que solo acepta la coincidencia literal rechazaría estas formalizaciones. Eso no solo es técnicamente erróneo: es pedagógicamente dañino. Penaliza el conocimiento real del estudiante, desalienta la exploración de equivalencias lógicas, y reduce el aprendizaje a la reproducción de una fórmula canónica.

La verificación por equivalencia semántica —comparación de tablas de verdad— es la forma correcta de verificar formalizaciones proposicionales porque es consistente con la naturaleza del objeto matemático. La validez lógica no depende de la forma sintáctica, depende del valor de verdad.

### La regla didáctica de los paréntesis explícitos

El motor exige paréntesis explícitos cuando se mezclan conectivos binarios distintos al mismo nivel. No acepta `p · q ∨ r`; exige `(p · q) ∨ r` o `p · (q ∨ r)`.

Esta regla no es una limitación técnica: es una decisión didáctica deliberada. La precedencia de los conectivos es una convención que los estudiantes aprenden, pero depender implícitamente de esa precedencia sin que la estructura sea visible produce comprensiones frágiles. Exigir la explicitación de la estructura —mediante paréntesis— refuerza la comprensión de que la fórmula tiene una organización jerárquica que no es arbitraria.

Esta decisión tiene un precedente pedagógico: en los primeros cursos de matemática, se suele exigir la escritura explícita de operaciones que el convenio permitiría omitir, precisamente para que la estructura sea visible antes de que la convención la oculte.

### Las limitaciones conocidas son aceptadas, no inadvertidas

El motor tiene limitaciones documentadas: no puede verificar que el estudiante usó las variables correctas; una tautología se acepta como equivalente a cualquier otra tautología. Estas limitaciones no son bugs: son consecuencias del diseño por equivalencia tabular.

La respuesta del sistema a estas limitaciones no es ocultar la complejidad ni fingir que no existen: es documentarlas explícitamente y señalar que el docente debe complementar la verificación automática con revisión manual cuando esas situaciones son pedagógicamente relevantes.

Esto es coherente con la arquitectura híbrida: el motor hace lo que puede hacer con certeza; el docente hace lo que solo él puede hacer.

---

## 7. La analítica educativa como herramienta de intervención

### La analítica no es vigilancia

El módulo de analíticas está diseñado desde una posición explícita: los datos de uso de la plataforma son para facilitar la intervención pedagógica del docente, no para clasificar ni vigilar a los estudiantes.

Esta posición no es solo ética: es técnica. Los indicadores del sistema están nombrados para evitar el lenguaje de la clasificación normativa:
- "Señales de alerta — estudiantes que podrían necesitar acompañamiento" (no "estudiantes en riesgo").
- "Fallos seguidos" (no "estudiantes con bajo rendimiento").
- Los umbrales son visibles y configurables (no hay una sola definición de qué es "en riesgo").

### Los umbrales son configurables y visibles

Los umbrales analíticos —cuántos fallos consecutivos activan una señal de alerta, cuántos días de silencio ameritan un aviso, qué ratio de intentos por día define "práctica concentrada"— son configurables por el administrador del sitio a través de `ConfigSitio`.

Más importante: los valores activos de esos umbrales se muestran en el dashboard. El docente que lee "3 estudiantes con señal de alerta" también puede leer "criterio: 5 fallos seguidos sin éxito". Los criterios son legibles, no opacos.

Esta transparencia es una aplicación directa del principio de contrato didáctico de Brousseau al contexto de la analítica: los criterios pedagógicos deben ser explícitos y accesibles.

### El módulo de investigación y el consentimiento informado

El proyecto tiene una dimensión de investigación educativa: busca producir conocimiento sobre el aprendizaje de la lógica en contextos masivos. Esta dimensión requiere acceso a datos personales de los estudiantes (trayectoria socioeducativa, situación económica, historial de práctica).

El sistema resuelve esta tensión con consentimiento informado explícito: los estudiantes que participan del proyecto de investigación otorgan un consentimiento pedagógico (para el análisis de su aprendizaje) y un consentimiento de investigación (para el análisis de sus datos socioeducativos). Ningún dato de investigación es accesible sin ese consentimiento.

El flujo de onboarding distingue dos tipos de encuesta:
- Encuesta completa (para comisiones que participan del proyecto de investigación): 48 preguntas sobre trayectoria educativa, situación laboral, acceso a tecnología, secundaria, CBC, lógica previa.
- Encuesta básica (para comisiones regulares): preguntas de contextualización mínima.

Este diseño articula la función pedagógica y la función investigativa del sistema sin subordinar una a la otra.

---

## 8. La lógica como propedéutica epistemológica

### La lógica no es el fin

En el encuadre del IPC, la lógica proposicional no se enseña como disciplina autónoma. Se enseña como herramienta para pensar sobre la ciencia: para analizar argumentos, identificar supuestos, comprender la estructura de las teorías, evaluar la validez de las inferencias.

El marco epistemológico es el de la filosofía de la ciencia de tradición heredada: Hempel, Popper, el problema de la inducción, la distinción entre contexto de descubrimiento y contexto de justificación. La lógica proposicional es la herramienta formal con la que se trabajan esas distinciones.

Esto tiene consecuencias para el diseño de los ejercicios: los enunciados no son formalizaciones abstractas de cadenas de letras; son traducciones de argumentos con contenido científico o cotidiano. El diccionario de variables —que el docente construye y el sistema muestra al estudiante— es parte constitutiva de la formalización, no un adorno.

### El modelizado como objetivo pedagógico

El objetivo pedagógico principal no es que los estudiantes memoricen equivalencias lógicas ni que apliquen mecánicamente las reglas de los conectivos. Es que los estudiantes desarrollen la capacidad de *modelizar*: de traducir un problema expresado en lenguaje natural a una estructura formal, y de razonar con esa estructura.

Esta capacidad de modelización —identificar qué es relevante formalizar, cómo asignar variables, qué tipo de conectivo corresponde a cada relación— es la que transfiere a otros contextos: a la evaluación de argumentos en filosofía, a la comprensión de razonamientos en ciencias, a la lectura crítica de textos.

El sistema refuerza esta capacidad de dos maneras:
1. Aceptando múltiples formalizaciones correctas (hay más de una forma de modelizar bien).
2. Haciendo visible el proceso: el historial de intentos muestra la evolución de las formalizaciones que el estudiante fue construyendo.

---

## 9. Principios políticos del diseño

### La universidad pública como horizonte

IPC-Lógica no es un software comercial ni un producto para ser vendido. Es una herramienta diseñada específicamente para las condiciones de la universidad pública argentina: masividad, diversidad socioeducativa, escasez relativa de recursos, acceso irrestricto.

Ese horizonte tiene consecuencias de diseño concretas:
- Sin costos de acceso para los estudiantes.
- Stack técnico simple y mantenible por equipos pequeños.
- Despliegue en plataformas de bajo costo (Railway).
- Sin dependencias de servicios comerciales para la funcionalidad central (el motor lógico es Python puro; Gemini es opcional).

### La diversidad socioeducativa como punto de partida

El proyecto asume que los estudiantes del CBC tienen trayectorias previas muy distintas: distintas relaciones con la matemática, distintos accesos a tecnología, distintas situaciones laborales y familiares. La plataforma no puede ignorar esas diferencias; debe diseñarse de modo que no las amplifique.

El módulo de investigación existe precisamente para estudiar la relación entre trayectoria socioeducativa y aprendizaje de la lógica: saber si hay grupos de estudiantes que encuentran mayores obstáculos, y poder diseñar intervenciones diferenciadas.

El acceso por link de comisión reduce la fricción de ingreso: los estudiantes no necesitan que el docente les cree una cuenta antes de poder acceder.

### La tecnología no resuelve lo que es político

Una restricción explícita del proyecto: la tecnología no resuelve problemas que son estructuralmente pedagógicos o institucionales. La falta de tiempo docente, la masividad, la diversidad socioeducativa no son bugs que se pueden parchear con un algoritmo mejor. Son condiciones que el sistema debe asumir y dentro de las cuales debe operar.

La automatización está justificada donde reduce trabajo repetitivo sin valor pedagógico agregado. No está justificada donde reemplaza interacción pedagógica valiosa. Esta distinción —que requiere juicio pedagógico, no técnico— está en el centro de las decisiones de diseño.

---

## 10. Lo que el sistema deliberadamente no hace

### No automatiza la evaluación

El sistema nunca declara que un intento está "aprobado" de forma automática. La verificación formal (`es_correcto`) es independiente de la aprobación docente (`aprobado_docente`). Ningún intento puede quedar aprobado sin acción docente explícita.

### No genera rankings ni perfiles normativos

El sistema no ordena estudiantes por rendimiento. No genera scores ni índices de "éxito". Las analíticas son métricas de proceso orientadas a la intervención, no indicadores de clasificación.

### No guía hacia la respuesta correcta

El sistema da retroalimentación (la tabla de verdad diferenciada), no orientación directa ("tu error está en el condicional"). El puntero pedagógico — "encontrá la fila donde tu tabla difiere de la esperada" — orienta el proceso de búsqueda sin resolver el problema. La pista automática (Gemini, opcional) sigue el mismo principio: orienta sin resolver.

### No convierte la práctica en entrenamiento mecánico

Los ejercicios no son objetos genéricos: tienen enunciados en lenguaje natural, diccionarios de variables, y pertenecen a prácticas con descripciones pedagógicas construidas por los docentes. El contexto conceptual es parte constitutiva de la tarea.

### No sustituye la interacción en el aula

El panel de analíticas proporciona datos sobre el proceso de aprendizaje; no proporciona interpretaciones. La interpretación de por qué un grupo de estudiantes cometió un determinado error sistemático, y qué hace el docente con esa información en el aula, es irreductiblemente humana.

---

## 11. El proyecto como investigación basada en diseño

IPC-Lógica no es un producto terminado: es un artefacto de investigación-acción. Sigue una metodología de *design-based research* (investigación basada en diseño): el sistema se diseña, se implementa, se usa en condiciones reales, y los datos del uso informan rediseños sucesivos.

Este enfoque tiene varias implicaciones:

**Los cambios son incrementales y observables.** Antes de implementar una transformación estructural, se implementa una versión mínima que sea evaluable. Las decisiones de rediseño se basan en evidencia empírica del uso, no en intuiciones sobre lo que "debería funcionar".

**Los docentes son investigadores.** Los docentes que usan el sistema son parte de la producción de conocimiento sobre el aprendizaje de la lógica. Sus observaciones, las preguntas que formulan, las interpretaciones que hacen de los datos —todo eso alimenta el ciclo de rediseño.

**El conocimiento producido es transferible.** El objetivo no es solo mejorar la práctica en las comisiones que usan el sistema. Es producir evidencia y herramientas que puedan ser útiles en otros contextos de enseñanza de la lógica en educación superior masiva.

**La tecnología es un instrumento, no el objeto de la investigación.** El objeto de investigación es el aprendizaje de la lógica en el contexto del IPC/CBC-UBA. La tecnología es el instrumento que permite intervenir en ese proceso y observarlo con mayor precisión. Cuando la tecnología se vuelve el foco de atención en sí misma —cuando el diseño técnico desplaza al diseño pedagógico—, el proyecto se desvía de sus objetivos.

---

## Bibliografía de referencia

- Brousseau, G. (2007). *Iniciación al estudio de la teoría de las situaciones didácticas*. Buenos Aires: Libros del Zorzal.
- Palau, G. y Frenkel, G. "Didáctica de la matemática y didáctica de la lógica". En *Cuadernos del Sur – Filosofía*.
- Palau, G. y Couló, A. "Errores sistemáticos en lógica". Texto de referencia para la cátedra.
- Couló, A. "Los obstáculos epistemológicos en la enseñanza de la lógica".
- Corbalan, G. "El lenguaje natural como obstáculo en el aprendizaje de la lógica".
- Oller, Kakazu, Frenkel y Couló. "Algunas cuestiones en torno a la formalización de argumentos".
- Arca. "La enseñanza de la lógica: dificultades y propuestas".
- López. "Aportes teóricos para la enseñanza de la lógica".
- Copi, I. (1953). *Introduction to Logic*. New York: Macmillan. (Traducción al español: Ed. Limusa, varias ediciones.)
- Bachelard, G. (1938). *La formation de l'esprit scientifique*. Paris: Vrin.
