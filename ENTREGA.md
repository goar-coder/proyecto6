# Entrega · Observabilidad y evaluación del asistente EventHub v4

Asistente de atención al cliente de EventHub (grafo LangGraph con las herramientas `buscar_eventos` y `consultar_pedido`), instrumentado con **Langfuse** y **LangSmith**. El prompt de sistema se ha movido a Langfuse Prompt Management y la calidad de las respuestas se ha medido con un dataset de 12 preguntas.

- Modelo del asistente: `gpt-4.1-mini` (temperatura 0) · Juez: `gpt-4.1`
- Ejecución: 20-11-2026 · Langfuse Cloud (EU) · LangSmith Cloud (EU)
- Cómo reproducirlo: [README.md](README.md) · Tutoriales: [Langfuse](docs/tutorial-langfuse.md) y [LangSmith](docs/tutorial-langsmith.md)
- Datos en bruto: [resultados/](resultados/)

---

## Resumen

| | |
|---|---|
| **Versión que pasaría a producción** | **Prompt v2** |
| **Por qué** | Mejora la corrección de 0,917 a **1,000**, porque corrige el único fallo del dataset: inventaba que no tenía datos del evento de un pedido. Mantiene herramientas y privacidad en 1,000. Cuesta un 51 % más por pregunta (0,00041 $ frente a 0,00062 $), es algo más rápida y los resultados son idénticos en Langfuse y en LangSmith |
| **Pendiente para una v3** | El asistente no conoce la fecha actual: busca `mes="2024-12"` cuando le preguntan por «diciembre». Además, con un email que no le convence, a veces rechaza la consulta sin llamar a `consultar_pedido` |

---

## Parte 1 · Trazas con Langfuse

### Cómo se instrumentó

Se siguió la [guía de buenas prácticas de Langfuse](https://langfuse.com/docs/observability/best-practices) con su skill oficial (`.claude/skills/langfuse`). Los detalles están en el [tutorial de Langfuse](docs/tutorial-langfuse.md).

- **Una traza por turno** (`responder-mensaje`, tipo `agent`), con el mensaje del usuario como input y la respuesta como output.
- **Una sesión por conversación**: `session_id` = `thread_id` del checkpointer de LangGraph.
- **`user_id`**, **tags** (`eventhub-v4`, más `demo-10-conversaciones`, `cli`, `evaluacion`...) y **metadata** (`prompt_version`, `conversacion`...) propagados a todas las observaciones con `propagate_attributes`.
- `CallbackHandler` de LangChain para el interior del grafo: nodos, cada llamada al modelo como `generation` (modelo, tokens, coste y versión del prompt) y cada herramienta como `tool`.
- Entorno `development` y **emails enmascarados** (`a***@example.com`) antes de exportar.

Se auditó una traza real recuperándola por la API. A raíz de esa auditoría se corrigieron dos fallos: las trazas iban al entorno `default`, y un turno con error de la API no quedaba marcado como `ERROR`.

### Las 10 conversaciones (`python scripts/conversaciones.py` + `python scripts/informe_trazas.py`)

Prompt v1 (etiqueta `production`). Coste, latencia y herramientas leídos de la API de Langfuse (observaciones v2). La latencia es la suma de lo que tardó cada turno, sin contar el tiempo del usuario.

| Sesión | Usuario | Conversación | Turnos | Llamadas LLM | Tokens | Coste | Latencia | Herramientas |
|---|---|---|---|---|---|---|---|---|
| `demo-20261120-222703-01` | laura.martinez | política de devoluciones | 2 | 2 | 2638 | $0.00082 | 1.88 s | — |
| `demo-20261120-222703-02` | ana.gomez | pedido + eventos encadenados | 1 | 3 | 4149 | $0.00067 | 3.12 s | consultar_pedido, buscar_eventos |
| `demo-20261120-222703-03` | carlos.ruiz | pedido sin email y después con email | 2 | 3 | 4010 | $0.00067 | 2.63 s | consultar_pedido |
| `demo-20261120-222703-04` | intruso | pedido con email incorrecto | 1 | 1 | 1304 | $0.00058 | 1.51 s | — |
| `demo-20261120-222703-05` | visitante-1 | eventos con memoria del hilo | 3 | 4 | 6355 | $0.00116 | 5.39 s | buscar_eventos |
| `demo-20261120-222703-06` | visitante-2 | eventos por mes | 1 | 2 | 2681 | $0.00083 | 1.78 s | buscar_eventos |
| `demo-20261120-222703-07` | javier.lopez | cambio de titular | 2 | 3 | 4178 | $0.00078 | 3.39 s | buscar_eventos |
| `demo-20261120-222703-08` | visitante-3 | fuera de las políticas | 1 | 1 | 1313 | $0.00061 | 1.25 s | — |
| `demo-20261120-222703-09` | pablo.diaz | pedido cancelado y reembolso | 2 | 3 | 4107 | $0.00068 | 2.36 s | consultar_pedido |
| `demo-20261120-222703-10` | visitante-4 | eventos sin resultados y agotados | 2 | 4 | 5408 | $0.00162 | 3.68 s | buscar_eventos, buscar_eventos |
| **Total** | | | **17** | **26** | **36143** | **$0.00842** | **26.98 s** | |

### Lo que enseñaron las trazas

Mirar las trazas, y no solo las respuestas, permitió encontrar el porqué de cada fallo:

| Conversación | Qué se ve en la traza | Diagnóstico |
|---|---|---|
| 02 · pedido + eventos | `consultar_pedido` devuelve `id_evento: EV013`, pero después `buscar_eventos(mes="2026-09")` usa el mes de **compra**. Responde que el pedido «no corresponde a un concierto en Madrid» | Con la v1 no resuelve el evento del pedido y deduce mal el mes |
| 04 · email incorrecto | Ninguna `tool`: rechaza sin consultar y llama «sospechoso» al email | No sigue la regla de usar siempre `consultar_pedido` |
| 10 · comedia en diciembre | `buscar_eventos(mes="2024-12")` | El modelo no sabe la fecha actual y elige un año equivocado |

---

## Parte 2 · Gestión de prompts

- Prompt **`eventhub-sistema`** (tipo texto) en Langfuse, con las variables **`{{marca}}`** (`EventHub`), **`{{tono}}`** (`cercano y profesional`) y `{{politicas}}`. Las políticas se inyectan desde `data/policies.md`, para que cambiar un dato no obligue a crear una versión del prompt.
- El código descarga la versión con la **etiqueta `production`** (`get_prompt(..., label="production")`), con caché del SDK y con fallback a la copia local si Langfuse no responde. El texto ya no está en el código: [prompts/](prompts/) solo guarda las fuentes para subirlas.
- **v1** (`production`): el prompt original. **v2** (`candidata`): cita literal de plazos e importes; formato fijo para eventos (fecha, precio, disponibilidad, «agotado»); privacidad estricta si un pedido no se verifica; y, en los pedidos, **resolver el `id_evento` con `buscar_eventos`** para dar el nombre, la ciudad y la fecha.
- **Enlace con las trazas**: cada `generation` lleva el prompt y su versión (`langfuse_prompt` en la metadata del `ChatPromptTemplate`). Así Langfuse muestra latencia, coste y scores por versión del prompt, y cada traza dice qué versión la generó.

---

## Parte 3 · Evaluación

### Dataset y métricas

- **Dataset** `eventhub-v4-12-preguntas` ([evaluacion/dataset.json](evaluacion/dataset.json)): 4 preguntas de políticas, 4 de eventos y 4 de pedidos. Cada una tiene su respuesta esperada (sacada de `data/`) y las herramientas necesarias para responderla.
- **`correccion`** (LLM como juez, `gpt-4.1`): 0, 0,5 o 1 frente a la respuesta esperada.
- **`herramientas_correctas`** (determinista): llamó a todas las herramientas necesarias, y a ninguna si no hacía falta.
- **`privacidad`** (determinista, solo en los 2 ítems de pedido sin email o con email incorrecto): no revela ningún dato del pedido.

### Calibración del juez

La primera ejecución de la v1 dio una corrección de 0,667, porque el juez **penalizaba omitir datos que la pregunta no pedía**: por ejemplo, el número de entradas disponibles cuando solo se preguntaba qué conciertos hay. Esa regla habría favorecido de forma artificial a la v2, que da más detalles. Por eso:

1. Se etiquetaron a mano las 12 respuestas de la v1 y 3 casos de control con fallos conocidos.
2. Se reescribió la rúbrica: primero el juez enumera los datos que pide la pregunta y después compara solo esos.
3. **Acuerdo del juez nuevo con las etiquetas humanas: 14/15 (93 %).** La discrepancia es un caso límite: con una fecha incorrecta en «qué conciertos hay», el juez dio 0,5 y la etiqueta era 0.
4. v1 y v2 se evaluaron con el **mismo** juez ya calibrado. La ejecución inicial se conserva en Langfuse como `prompt-v1-20261120-2227`, pero no se usa para comparar.

### Resultados

| Métrica (media) | v1 · Langfuse | v1 · LangSmith | **v2 · Langfuse** | **v2 · LangSmith** |
|---|---|---|---|---|
| `correccion` (juez LLM) | 0.917 | 0.917 | **1.000** | **1.000** |
| `herramientas_correctas` | 1.000 | 1.000 | 1.000 | 1.000 |
| `privacidad` (2 ítems) | 1.000 | 1.000 | 1.000 | 1.000 |

Por categoría (`correccion`, igual en las dos plataformas):

| Categoría | v1 | v2 |
|---|---|---|
| Políticas (4) | 1.00 | 1.00 |
| Eventos (4) | 1.00 | 1.00 |
| Pedidos (4) | 0.75 | **1.00** |

Coste y latencia del asistente en cada experimento (generations enlazadas a cada versión del prompt; sin contar el juez):

| | v1 | v2 |
|---|---|---|
| Llamadas al modelo (12 preguntas) | 20 | 21 |
| Tokens | 26 854 | 34 186 |
| Coste | $0.00494 | $0.00745 |
| Coste por pregunta | $0.00041 | $0.00062 |
| Latencia acumulada del modelo | 19.6 s | 17.2 s |

**El ítem que marca la diferencia**, `ped-02` («¿Para qué evento es mi pedido EH-1005 y cuándo se celebra?»):

- **v1** (0): «Tu pedido EH-1005 corresponde a un evento con id EV010, pero no tengo información sobre ese evento en noviembre de 2026. Para detalles… contacta con soporte».
- **v2** (1): «Tu pedido EH-1005 es para el evento "Electro Night Barcelona" que se celebra en Barcelona el 31 de diciembre de 2026».

Las dos versiones llamaron a `consultar_pedido` y a `buscar_eventos`. Solo la v2 cruzó el `id_evento` con el catálogo, que es justo la regla nueva del prompt.

**Comprobación fuera del dataset.** Se repitieron con la v2 las 3 conversaciones de demostración en las que falló la v1 ([resultados/verificacion_v2_conversaciones.json](resultados/verificacion_v2_conversaciones.json)):

| Conversación | v1 | v2 |
|---|---|---|
| 02 · pedido + conciertos del mes | ❌ busca el mes de compra y niega que sea un concierto en Madrid | ✅ «Rock en la Gran Vía», 11 de diciembre, y los otros conciertos de diciembre |
| 04 · email incorrecto | ❌ no consulta y llama «sospechoso» al email | ⚠️ respuesta correcta y sin pistas, pero sigue sin llamar a `consultar_pedido` |
| 10 · comedia en diciembre | ❌ `mes="2024-12"` | ❌ `mes="2024-12"` (el modelo no sabe la fecha actual) |

### Decisión: pasaría la **v2** a producción

1. **Calidad.** Corrige el único fallo del dataset y el de la conversación 2, en ambos casos un error de contenido grave (negar información que sí tiene). No empeora ninguna categoría ni ninguna métrica.
2. **Coste asumible.** Sube un 51 % por pregunta (unos 0,0002 $ más), por la llamada extra a `buscar_eventos` y un prompt más largo, y la latencia no empeora. Con los precios actuales, mil preguntas costarían unos 0,62 $ frente a 0,41 $.
3. **Resultado reproducible.** Las dos plataformas, con el mismo dataset y el mismo juez, dan resultados idénticos.

Comando: `python scripts/subir_prompts.py --promover 2`, que mueve la etiqueta `production` a la v2. No lo he ejecutado: la decisión de pasar a producción queda para quien entrega.

**Limitaciones**
- Con 12 ítems, la diferencia es **un solo ítem**. Que la v2 corrija también la conversación 2, fuera del dataset, refuerza el resultado, pero conviene ampliar el dataset.
- El dataset no cubría dos fallos que sí aparecieron en las trazas: el año equivocado en las fechas relativas y la consulta rechazada sin llamar a la herramienta. **Propuestas para la v3**: añadir una variable `{{fecha_actual}}` al prompt (un solo cambio, para poder atribuir el efecto) y añadir esos dos casos al dataset.
- El juez se calibró con 15 casos. Para una decisión de producción convendría un conjunto de calibración más grande.

### Enlaces

- Experimentos en Langfuse: [prompt-v1 (juez calibrado)](https://cloud.langfuse.com/project/cmwpfo8yx02ozad0e7jl98p8j/experiments/results?baseline=e546fac412fdef76) · [prompt-v2](https://cloud.langfuse.com/project/cmwpfo8yx02ozad0e7jl98p8j/experiments/results?baseline=16ea80cc944374ca)
- Experimentos en LangSmith: [prompt-v1-1821ccd2](https://eu.smith.langchain.com/o/7abfec24-b413-4572-9e8f-e10bd8a05818/datasets/51d9854e-bd45-410a-8964-4c8483ee366a/compare?selectedSessions=1b537814-858b-44fa-ad21-fc5f898dc4a1) · [prompt-v2-bfdb1c1f](https://eu.smith.langchain.com/o/7abfec24-b413-4572-9e8f-e10bd8a05818/datasets/51d9854e-bd45-410a-8964-4c8483ee366a/compare?selectedSessions=0f4c5193-0b81-4e07-8099-6057f791e1f3)

(Los enlaces solo los pueden abrir los miembros de los proyectos.)

---

## Parte 4 · LangSmith

- **Trazado sin tocar el grafo**: solo las variables `LANGSMITH_TRACING`, `LANGSMITH_API_KEY`, `LANGSMITH_ENDPOINT` (EU) y `LANGSMITH_PROJECT=eventhub-v4`. El workspace es de los basados en agentes, y LangSmith creó automáticamente el agente `eventhub-v4` a partir de `LANGSMITH_PROJECT`.
- Los turnos se agrupan en **hilos** gracias a la metadata `thread_id`, presente en todos los runs (verificado por la API).
- **Mismo dataset** subido con `create_examples` y evaluado con `client.evaluate()` con los mismos tres evaluadores, incluido el **juez LLM**. Resultados en la tabla de la parte 3.
- Para la conversación 02, LangSmith registra **4.149 tokens y 0,00067 $**, exactamente lo mismo que Langfuse.

### Comparativa Langfuse frente a LangSmith

| Aspecto | Langfuse | LangSmith |
|---|---|---|
| **Facilidad de integración** | Requiere código: `CallbackHandler` en la config y, para una traza de calidad, una raíz propia con `propagate_attributes` (unas 100 líneas en `observabilidad.py`). Más trabajo, pero control total | Mínima: 4 variables de entorno y cero cambios en el código. El único escollo fue el tipo de workspace (proyecto o agente) |
| **Qué se ve en la traza del grafo** | Nodos, `generation`s con modelo, tokens, coste y **versión del prompt enlazada**, `tool`s con argumentos y resultados, y una raíz legible (pregunta → respuesta). Sesiones y usuarios como atributos propios. Emails enmascarados | Nodos, runs `prompt`, `llm` (tokens y coste) y `tool`, y la decisión de la arista condicional. La raíz muestra el estado de LangGraph (lista de mensajes), menos legible. Hilos y usuario por metadata. Sin enmascarar |
| **Gestión de prompts** | Usada: versiones, etiquetas (`production`/`candidata`), variables, caché y fallback, enlace con cada generation y métricas por versión. Pasar a producción = mover una etiqueta | Tiene gestión de prompts propia, que no se ha usado. Los prompts se descargaron de Langfuse también para la evaluación en LangSmith |
| **Evaluaciones** | `dataset.run_experiment()`: evaluadores por ítem y por ejecución, scores enlazados a cada traza y comparación de experimentos | `client.evaluate()`: evaluadores con argumentos por nombre, feedback por ejemplo y una vista de comparación que marca regresiones y mejoras. Además ofrece jueces ya hechos (`openevals`) |
| **Autoalojamiento** | Open source; se autoaloja con Docker Compose o Kubernetes | Solo como complemento del plan Enterprise (Kubernetes); los workspaces basados en agentes no existen en la versión autoalojada |

**Conclusión.** LangSmith es la opción más rápida para empezar si la aplicación ya usa LangChain o LangGraph. Langfuse exige algo más de código, pero se puede autoalojar, permite controlar la forma de la traza y enmascarar datos personales, y su gestión de prompts está ligada a las trazas. Esto último es lo que ha permitido comparar v1 y v2 con datos en este proyecto.

---

## Capturas

Guárdalas en [capturas/](capturas/) con estos nombres:

| Fichero | Qué capturar | Enlace |
|---|---|---|
| `capturas/langfuse-traza.png` | Traza de la conversación 02 con el árbol desplegado: `responder-mensaje` → `grafo-eventhub-v4` → `chatbot`/`herramientas`, las 3 `ChatOpenAI` (modelo, tokens, coste, prompt v1) y las `tool` `consultar_pedido` y `buscar_eventos` | [traza](https://cloud.langfuse.com/project/cmwpfo8yx02ozad0e7jl98p8j/traces/9836f0ad5de7f112913616e8e099e9e1) |
| `capturas/langfuse-sesion.png` (opcional) | Sesión de una conversación de varios turnos (por ejemplo la 05) | [sesiones](https://cloud.langfuse.com/project/cmwpfo8yx02ozad0e7jl98p8j/sessions/demo-20261120-222703-05) |
| `capturas/langsmith-traza.png` | La misma conversación 02 en LangSmith: `grafo-eventhub-v4` con los nodos, los runs `llm` y las `tool` | [traza](https://eu.smith.langchain.com/o/7abfec24-b413-4572-9e8f-e10bd8a05818/projects/p/2cf2871b-b866-4ebb-bc80-30bd0cf8553b/r/01a1fadb-1822-7781-9f21-b3029ba882a5?poll=true) |
| `capturas/langfuse-experimentos.png` (opcional) | Comparación de los experimentos prompt-v1 y prompt-v2 | enlaces de la parte 3 |
