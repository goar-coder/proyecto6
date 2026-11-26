# Tutorial: LangSmith en el asistente EventHub v4

Este tutorial explica cómo usa **LangSmith** el asistente de atención al cliente de EventHub (un agente LangGraph con herramientas). Lo usa para dos cosas:

1. **Trazar el grafo** sin cambiar ni una línea de su código: solo con variables de entorno.
2. **Evaluar** las dos versiones del prompt de sistema con el mismo dataset de 12 preguntas, un juez LLM y dos métricas deterministas.

El proyecto usa LangSmith y Langfuse a la vez, para poder compararlos. Este tutorial se centra en LangSmith. El de Langfuse está en [tutorial-langfuse.md](tutorial-langfuse.md), y al final de este hay una tabla comparativa. Las versiones usadas son `langsmith==0.15.1`, `langchain-core==1.7.6` y `langgraph==1.2.20`.

---

## Índice

1. [Conceptos de LangSmith que vas a usar](#1-conceptos-de-langsmith-que-vas-a-usar)
2. [Puesta en marcha: cuenta, región y tipo de workspace](#2-puesta-en-marcha-cuenta-región-y-tipo-de-workspace)
3. [Trazar el grafo solo con variables de entorno](#3-trazar-el-grafo-solo-con-variables-de-entorno)
4. [Qué se ve en una traza del grafo](#4-qué-se-ve-en-una-traza-del-grafo)
5. [Hilos: agrupar los turnos de una conversación](#5-hilos-agrupar-los-turnos-de-una-conversación)
6. [Tags, metadata y nombres](#6-tags-metadata-y-nombres)
7. [Dataset y evaluación con `evaluate()`](#7-dataset-y-evaluación-con-evaluate)
8. [Comparar los experimentos v1 y v2](#8-comparar-los-experimentos-v1-y-v2)
9. [Datos sensibles](#9-datos-sensibles)
10. [Convivencia con Langfuse](#10-convivencia-con-langfuse)
11. [Langfuse frente a LangSmith](#11-langfuse-frente-a-langsmith)
12. [Problemas frecuentes](#12-problemas-frecuentes)
13. [Mapa de ficheros y referencias](#13-mapa-de-ficheros-y-referencias)

---

## 1. Conceptos de LangSmith que vas a usar

| Concepto | Qué es | En este proyecto |
|---|---|---|
| **Run** | Un paso ejecutado: una cadena, un nodo, una llamada al modelo, una herramienta. Tiene un tipo (`chain`, `llm`, `tool`, `prompt`...) | Cada nodo de LangGraph, cada llamada a `ChatOpenAI` y cada herramienta |
| **Traza** | El árbol de runs que cuelga de un run raíz | Un turno: una llamada a `grafo.invoke(...)` |
| **Hilo** (*thread*) | Agrupa varias trazas de la misma conversación mediante la metadata `thread_id` o `session_id` | Una conversación del asistente (el mismo `thread_id` del checkpointer) |
| **Destino de las trazas** | Un **tracing project** (workspaces basados en proyectos) o un **agente** con sus **entornos** (workspaces basados en agentes) | `eventhub-v4` (ver apartado 2.3) |
| **Tags y metadata** | Etiquetas y pares clave-valor para filtrar | Tags `eventhub-v4`, `cli`, `evaluacion`...; metadata `thread_id`, `user_id`, `prompt_version` |
| **Dataset y ejemplos** | Casos de prueba con `inputs`, `outputs` de referencia y `metadata` | `eventhub-v4-12-preguntas` |
| **Experimento** | Una ejecución de la aplicación sobre un dataset, con sus evaluaciones | `prompt-v1-...` y `prompt-v2-...` |
| **Evaluador y feedback** | Función que puntúa un resultado; cada puntuación se guarda como *feedback* con una clave (`key`) | `correccion`, `herramientas_correctas` y `privacidad` |

---

## 2. Puesta en marcha: cuenta, región y tipo de workspace

### 2.1 Cuenta, región y clave

1. Crea una cuenta en LangSmith. Este proyecto usa la región **EU**.
2. Crea una **API key** en la configuración del workspace.
3. La región importa. Si tu cuenta no es de la región US (la que usa por defecto), tienes que indicar el endpoint de la tuya. Si no, la clave no se reconoce y la autenticación falla:

| Región | `LANGSMITH_ENDPOINT` |
|---|---|
| US (por defecto) | `https://api.smith.langchain.com` |
| EU | `https://eu.api.smith.langchain.com` |
| APAC | `https://apac.api.smith.langchain.com` |

### 2.2 Variables de entorno

En `.env` (que nunca se sube al repositorio):

```bash
LANGSMITH_TRACING=true
LANGSMITH_API_KEY=lsv2_...
LANGSMITH_ENDPOINT=https://eu.api.smith.langchain.com
# + el destino de las trazas: ver 2.3
```

`src/eventhub_v4/config/settings.py` carga `.env` con `load_dotenv` al importar el paquete, y LangChain lee estas variables del entorno del proceso.

### 2.3 El destino de las trazas: ¿proyecto o agente?

LangSmith organiza un workspace de una de dos formas, y **de eso depende qué variable usar**:

| Tipo de workspace | Quién lo tiene | Cómo se configura el destino |
|---|---|---|
| **Basado en proyectos** | Workspaces antiguos y **todo LangSmith autoalojado** | `LANGSMITH_PROJECT=eventhub-v4` (el proyecto de trazas se crea solo) |
| **Basado en agentes** | **Organizaciones nuevas de LangSmith Cloud** | Crear una vez el agente `eventhub-v4` y usar `LANGSMITH_AGENT_ID=eventhub-v4` y `LANGSMITH_AGENT_ENVIRONMENT=development` |

Para saber cuál tienes, la documentación da una pista visual: en un workspace basado en agentes, el control de arriba a la izquierda muestra el nombre del workspace; en uno basado en proyectos, muestra el logo de LangSmith y la barra lateral tiene una sección de aplicaciones.

**Si tu workspace es basado en agentes:**

1. **Crea el agente una vez.** Hay dos maneras:
   - Desde la interfaz, con la opción para conectar un agente existente (uno que se ejecuta fuera de LangSmith). Pide un nombre visible y un **Agent ID**, que no se puede cambiar después.
   - Por SDK. Necesita una clave con permiso para crear proyectos; una clave solo de trazado no puede:

     ```python
     from langsmith import Client
     Client().agents.create(id="eventhub-v4", name="EventHub v4", source_type="EXTERNAL")
     ```

   El identificador debe tener entre 1 y 63 caracteres (minúsculas, dígitos y guiones) y empezar por una letra. Cada agente se crea con cuatro entornos: `production`, `staging`, `development` y `local`.
2. **Configura el destino en `.env`** y quita `LANGSMITH_PROJECT`:

   ```bash
   LANGSMITH_AGENT_ID=eventhub-v4
   LANGSMITH_AGENT_ENVIRONMENT=development
   ```

> **Lo que pasó en este proyecto.** El workspace es basado en agentes y estaba vacío. Con solo `LANGSMITH_PROJECT=eventhub-v4` (sin variables de agente), LangSmith **creó automáticamente el agente `eventhub-v4`** y las trazas llegaron, así que la opción de proyecto funciona como configuración de compatibilidad. La de agente es la que recomienda la documentación para workspaces nuevos.

> **No combines las dos opciones.** Si defines a la vez las variables de agente y `LANGSMITH_PROJECT`, la traza tiene dos destinos y el SDK no elige: avisa al arrancar y no traza. La plantilla `.env.example` lleva las dos opciones, con la de agente comentada.

Las variables de agente necesitan `langsmith>=0.14.9`. El proyecto usa la 0.15.1.

---

## 3. Trazar el grafo solo con variables de entorno

Esta es la diferencia principal con Langfuse: **el grafo no importa nada de LangSmith**. Si buscas `langsmith` en `src/eventhub_v4/`, no aparece.

Funciona porque LangGraph está construido sobre LangChain, y LangChain trae de serie un trazador de LangSmith que se activa con `LANGSMITH_TRACING=true`. Cada componente que se ejecuta (el grafo, sus nodos, los prompts, el modelo y las herramientas) genera un run, y los runs se anidan solos porque la config de LangChain pasa de padres a hijos.

Para comprobarlo:

```bash
python -m eventhub_v4
```

```
[hilo-1] Tú: ¿Qué conciertos hay en Valencia?
[hilo-1] Tú: ¿Cuál de esos es el más barato?
[hilo-1] Tú: salir
```

En LangSmith aparecerán dos trazas en el destino configurado (el proyecto o el agente y su entorno), agrupadas en el hilo `hilo-1`.

Para **desactivarlo**, pon `LANGSMITH_TRACING=false`. Los tests ya lo hacen siempre (`tests/conftest.py`), para que `pytest` no envíe nada aunque `.env` tenga una clave real.

---

## 4. Qué se ve en una traza del grafo

Para la pregunta «¿Mi pedido EH-1003 es para un concierto en Madrid? Si es así, dime otros conciertos en Madrid ese mes. Mi email es …», el árbol es este:

```
grafo-eventhub-v4                 chain    raíz: input {"messages": [...], "pasos": 0} · output: estado final
├── chatbot                       chain    nodo
│   ├── generar-respuesta         chain
│   │   ├── preparar-prompt       prompt   prompt de sistema + historial
│   │   └── ChatOpenAI            llm      mensajes, tool_calls, tokens, coste, latencia
│   └── ruta_tras_chatbot         chain    arista condicional → "usar_herramientas"
├── herramientas                  chain    nodo
│   └── consultar_pedido          tool     {"id_pedido": "EH-1003", "email": "..."} → JSON del pedido
├── chatbot
│   ├── generar-respuesta
│   │   └── ChatOpenAI            llm      pide buscar_eventos(ciudad, categoria, mes="2026-12")
│   └── ruta_tras_chatbot                  → "usar_herramientas"
├── herramientas
│   └── buscar_eventos            tool
└── chatbot
    ├── generar-respuesta
    │   └── ChatOpenAI            llm      respuesta final
    └── ruta_tras_chatbot                  → "fin"
```

De dónde sale cada nombre:

| Run | Origen en el código |
|---|---|
| `grafo-eventhub-v4` | `"run_name"` en `config_langchain()` (`src/eventhub_v4/observabilidad.py`). Sin él, la raíz se llamaría `LangGraph` |
| `chatbot`, `herramientas`, `limite` | Los nombres de los nodos en `builder.add_node(...)` |
| `generar-respuesta` | `.with_config(run_name="generar-respuesta")` sobre `plantilla | modelo` en `construir_grafo()` |
| `preparar-prompt` | `PromptSistema.plantilla_chat()` (`src/eventhub_v4/llm/prompt_gestionado.py`) |
| `ruta_tras_chatbot` | La función de la arista condicional; su output dice por qué siguió el grafo |
| `consultar_pedido`, `buscar_eventos` | Las herramientas `@tool`. Aunque el nodo `herramientas` las llama a mano con `herramienta.invoke(...)`, LangChain propaga la config y salen como runs `tool` hijos del nodo |

Qué puedes mirar en cada run:

- **`llm`**: los mensajes que vio el modelo (incluido el prompt de sistema), los `tool_calls` que pidió, los tokens de entrada y salida, la latencia y el **coste**. LangSmith calcula el coste solo para las llamadas de LangChain a los grandes proveedores, a partir de los tokens y de su tabla de precios por modelo.
- **`tool`**: los argumentos exactos y el JSON devuelto. Así se ve, por ejemplo, si el modelo pasó el filtro `mes` con el formato `AAAA-MM`.
- **La raíz**: la latencia total del turno y el coste acumulado de la traza.

**Una diferencia con Langfuse:** la raíz de LangSmith es la ejecución del grafo, así que su input y su output son el estado de LangGraph (la lista de mensajes) y no el texto del usuario y la respuesta. En Langfuse, el proyecto crea a mano una raíz `responder-mensaje` con input y output legibles. Esa raíz no existe en LangSmith, porque el objetivo aquí era no tocar el código.

---

## 5. Hilos: agrupar los turnos de una conversación

Según la [documentación de hilos](https://docs.langchain.com/langsmith/threads), LangSmith agrupa en un hilo las trazas que llevan la misma metadata `session_id` o `thread_id`, **en todos los runs**, incluidos los hijos. Si algún hijo no la lleva, el filtrado y el recuento de tokens del hilo quedan incompletos.

El proyecto la añade en `config_langchain()`:

```python
config = {
    "configurable": {"thread_id": thread_id},     # memoria del checkpointer (LangGraph)
    "run_name": "grafo-eventhub-v4",
    "tags": etiquetas(tags),
    "metadata": {"thread_id": thread_id, "user_id": usuario, **(metadata or {})},
}
```

- `configurable.thread_id` lo usa **LangGraph** para la memoria de la conversación.
- `metadata.thread_id` lo usa **LangSmith** para el hilo. Se pone en la `metadata` de la config de LangChain, que se hereda en todos los runs hijos; así se cumple el requisito de «en todos los runs» sin más código.
- Se usa el mismo valor en los dos sitios: **una conversación es un hilo**, igual que es una sesión en Langfuse.

La documentación recomienda identificadores UUID v7 para los hilos (`from langsmith import uuid7`). El proyecto usa nombres legibles (`hilo-1`, `demo-<fecha>-NN`) porque los elige el usuario del chat con `/hilo <id>` y facilitan las capturas. En producción convendría usar UUID v7.

---

## 6. Tags, metadata y nombres

| Dónde se fija | Tags | Metadata |
|---|---|---|
| Siempre (`config_langchain`) | `eventhub-v4` | `thread_id`, `user_id` |
| Chat (`python -m eventhub_v4`) | `cli` | `prompt_version` (`prompt-v1`, `prompt-v2` o `prompt-local`) |
| `scripts/conversaciones.py` | `demo-10-conversaciones` | `conversacion`, `prompt_version` |
| Evaluación (`evaluacion/ejecucion.py`) | `evaluacion` | `dataset`, `item`, `prompt_version`, `plataforma` |

Sirven para filtrar trazas en LangSmith: por ejemplo, todas las de `prompt_version = prompt-v2`, o todas las de un `user_id`. En este proyecto `user_id` es una clave de metadata más (en Langfuse, en cambio, es un atributo propio de la traza), así que en LangSmith se trabaja con él filtrando por esa clave.

Estos tags y esta metadata son los mismos que recibe Langfuse, porque los dos leen la config de LangChain.

---

## 7. Dataset y evaluación con `evaluate()`

### 7.1 El script

```bash
python scripts/evaluar_langsmith.py               # versiones 1 y 2 del prompt
python scripts/evaluar_langsmith.py --version 2   # solo una
```

`scripts/evaluar_langsmith.py` hace cuatro cosas:

1. Pone `EVENTHUB_LANGFUSE_TRACING=0` **antes de importar nada del proyecto**, para que las ejecuciones de la evaluación no se dupliquen como trazas de Langfuse.
2. Sube el dataset si no existe.
3. Para cada versión del prompt, la descarga de Langfuse (donde vive la gestión de prompts del proyecto) y ejecuta `Client.evaluate(...)`.
4. Imprime las medias y guarda los resultados en `resultados/eval_langsmith_v{N}.json`.

### 7.2 Subir el dataset

Usa el **mismo fichero** que la evaluación de Langfuse, `evaluacion/dataset.json`, con 4 preguntas de políticas, 4 de eventos y 4 de pedidos:

```python
def subir_dataset(client: Client) -> None:
    if client.has_dataset(dataset_name=NOMBRE_DATASET):
        existentes = {e.metadata.get("id") for e in client.list_examples(dataset_name=NOMBRE_DATASET)}
    else:
        client.create_dataset(NOMBRE_DATASET, description="12 preguntas (4 políticas, 4 eventos, 4 pedidos) ...")
        existentes = set()
    nuevos = [
        {"inputs": i["input"], "outputs": i["expected_output"], "metadata": {**i["metadata"], "id": i["id"]}}
        for i in cargar_dataset() if i["id"] not in existentes
    ]
    if nuevos:
        client.create_examples(dataset_name=NOMBRE_DATASET, examples=nuevos)
```

Así queda cada ejemplo en LangSmith:

| Campo | Contenido | Ejemplo |
|---|---|---|
| `inputs` | Lo que recibe la aplicación | `{"pregunta": "¿Qué conciertos hay en Madrid en enero de 2027?"}` |
| `outputs` (referencia) | Respuesta esperada y herramientas necesarias | `{"respuesta": "Solo hay uno: Pop Madrid Live, el 22 de enero...", "herramientas": ["buscar_eventos"]}` |
| `metadata` | `id`, `categoria` y, en pedidos sin email o con email incorrecto, `no_debe_contener` | `{"id": "ev-01-madrid-enero", "categoria": "eventos"}` |

El script es idempotente: usa `metadata.id` para no duplicar ejemplos si lo ejecutas varias veces.

### 7.3 La función objetivo

```python
def objetivo(inputs: dict) -> dict:
    return responder(inputs["pregunta"], prompt, plataforma="langsmith")
```

`responder()` (`src/eventhub_v4/evaluacion/ejecucion.py`) construye un grafo nuevo y usa un hilo nuevo por pregunta, para que no haya memoria entre ejemplos. Devuelve `{"respuesta": ..., "herramientas": [...]}`. Devuelve también las herramientas, y no solo el texto, para que la métrica determinista pueda comprobarlas sin inspeccionar la traza.

`evaluate()` traza cada ejecución de `objetivo` y la asocia al experimento, así que desde cada resultado puedes abrir la traza completa del grafo (apartado 4).

### 7.4 Los evaluadores

LangSmith inyecta los argumentos **por su nombre**. Un evaluador puede pedir cualquier subconjunto de `inputs`, `outputs`, `reference_outputs`, `run` y `example`, y devolver un `bool`, un número o un `dict` con `key`, `score` y `comment`:

```python
def correccion(inputs: dict, outputs: dict, reference_outputs: dict) -> dict:
    """Juez LLM: corrección frente a la respuesta esperada."""
    score, razon = metricas.correccion(inputs["pregunta"], outputs["respuesta"], reference_outputs["respuesta"])
    return {"key": "correccion", "score": score, "comment": razon}


def herramientas_correctas(outputs: dict, reference_outputs: dict) -> dict:
    score, detalle = metricas.herramientas_correctas(outputs["herramientas"], reference_outputs["herramientas"])
    return {"key": "herramientas_correctas", "score": score, "comment": detalle}


def privacidad(outputs: dict, example) -> dict:
    score, motivo = metricas.privacidad(outputs["respuesta"], (example.metadata or {}).get("no_debe_contener"))
    return {"key": "privacidad", "score": score, "comment": motivo}
```

| Clave | Tipo | Qué mide | Valores |
|---|---|---|---|
| `correccion` | **LLM como juez** (`gpt-4.1`, temperatura 0, salida estructurada con razonamiento) | ¿Contiene la respuesta los datos esenciales que pide la pregunta, sin contradecir la referencia? | 0 · 0.5 · 1 |
| `herramientas_correctas` | Determinista | Llamó a todas las herramientas necesarias; si no hacía falta ninguna, no llamó a ninguna | 0 · 1 |
| `privacidad` | Determinista | No revela datos del pedido cuando no debe. `privacidad` pide `example` porque necesita la metadata del ejemplo | 0 · 1, o sin puntuación si no aplica |

La lógica está en `src/eventhub_v4/evaluacion/metricas.py` y es **la misma que usa la evaluación de Langfuse**. Solo cambia la envoltura: LangSmith pasa `inputs`, `outputs` y `reference_outputs`; Langfuse pasa `input`, `output` y `expected_output`. Por eso los números de las dos plataformas son comparables.

El juez se escribe a mano para que sea idéntico en las dos plataformas. LangSmith también ofrece jueces ya hechos en la librería `openevals` y la posibilidad de definir evaluadores desde la interfaz, que el proyecto no usa.

### 7.5 La llamada a `evaluate()`

```python
resultados = client.evaluate(
    objetivo,
    data=NOMBRE_DATASET,
    evaluators=[correccion, herramientas_correctas, privacidad],
    experiment_prefix=prompt.etiqueta,          # "prompt-v1" / "prompt-v2"
    max_concurrency=4,
    description=f"Prompt eventhub-sistema v{version}; juez gpt-4.1",
    metadata={"prompt_version": version, "modelo": ..., "juez": ...},
)
```

- **`experiment_prefix`**: LangSmith añade un sufijo único, así que cada ejecución es un experimento nuevo (`prompt-v1-xxxx`).
- **`metadata` del experimento**: deja constancia de qué prompt, modelo y juez se usaron, para poder filtrar y comparar experimentos después.
- **`max_concurrency=4`**: ejecuta 4 ejemplos en paralelo sin saturar el límite de peticiones de OpenAI.

Después, el script recorre los resultados y calcula las medias:

```python
for fila in resultados:
    scores = {r.key: r.score for r in fila["evaluation_results"]["results"] if r.score is not None}
```

---

## 8. Comparar los experimentos v1 y v2

En LangSmith, los dos experimentos cuelgan del dataset `eventhub-v4-12-preguntas`. Desde ahí puedes:

- Ver la **media de cada clave de feedback** por experimento.
- Abrir la **vista de comparación** con los dos experimentos seleccionados. Muestra, ejemplo a ejemplo, la respuesta de cada versión con sus puntuaciones. Tomando un experimento como referencia (v1), marca en rojo los ejemplos que **empeoran** en alguna clave de feedback y en verde los que **mejoran**, cuenta cuántos hay de cada en cada columna y permite filtrar solo las regresiones o solo las mejoras ([cómo comparar experimentos](https://docs.langchain.com/langsmith/compare-experiment-results)).
- Abrir la **traza** de cualquier ejemplo para ver por qué falló: qué herramientas llamó y con qué argumentos.
- Leer el **comentario** del juez (su razonamiento) en cada puntuación de `correccion`.

Criterios para elegir la versión que pasa a producción:

1. Las medias de las tres métricas.
2. El desglose por categoría (la metadata `categoria` del ejemplo): una versión puede mejorar en eventos y empeorar en políticas.
3. Coste y latencia: la v2 puede hacer una llamada extra a `buscar_eventos` en los pedidos.
4. Con 12 ejemplos, la diferencia de un solo ejemplo es ruido. Busca diferencias consistentes, y si dudas repite la evaluación.

La etiqueta `production` del prompt se mueve en Langfuse, donde vive la gestión de prompts: `python scripts/subir_prompts.py --promover N`.

---

## 9. Datos sensibles

Las preguntas sobre pedidos incluyen emails. **En LangSmith no se enmascaran**: el enmascarado del proyecto (`mask_otel_spans`) solo actúa sobre los datos que van a Langfuse.

Según la [documentación de LangSmith](https://docs.langchain.com/langsmith/mask-inputs-outputs), hay dos niveles:

| Opción | Cómo | Efecto |
|---|---|---|
| Ocultar todo | `LANGSMITH_HIDE_INPUTS=true` y `LANGSMITH_HIDE_OUTPUTS=true` (y `LANGSMITH_HIDE_METADATA=true`) | Las trazas se guardan sin inputs ni outputs. Es seguro, pero pierdes casi toda la capacidad de depurar |
| Enmascarado por reglas | Un `Client` con `hide_inputs` y `hide_outputs`, o con el anonimizador del SDK (`langsmith.anonymizer.create_anonymizer`) y expresiones regulares | Se oculta solo lo que coincide, por ejemplo los emails |

La segunda opción exige configurar un cliente de LangSmith en el código. Este proyecto no lo hace, para mantener la regla de «sin tocar el código del grafo». En un despliegue real con datos de clientes habría que activarla. Mientras tanto, usa en las pruebas los emails de ejemplo de `data/orders.json`.

---

## 10. Convivencia con Langfuse

Los dos sistemas trazan el mismo grafo a la vez sin estorbarse:

| | LangSmith | Langfuse |
|---|---|---|
| Cómo recibe los datos | Trazador de LangChain activado por `LANGSMITH_TRACING` | `CallbackHandler` en `config["callbacks"]` + SDK de Langfuse (OpenTelemetry) |
| Cambios en el código | Ninguno | `observabilidad.py` y `enviar()` |
| Raíz de la traza | `grafo-eventhub-v4` | `responder-mensaje` (creada a mano, con input y output legibles) |
| Conversación | Hilo (metadata `thread_id`) | Sesión (`session_id`) |
| Usuario | Metadata `user_id` | `user_id` de primera clase |
| Emails | Sin enmascarar | Enmascarados |
| Dataset y experimentos | `scripts/evaluar_langsmith.py` | `scripts/evaluar_langfuse.py` |

Para no duplicar los experimentos, cada script de evaluación desactiva la otra plataforma cuando hace falta. `evaluar_langsmith.py` pone `EVENTHUB_LANGFUSE_TRACING=0`. Aun así sigue descargando los prompts de Langfuse, porque «hay claves de Langfuse» (`settings.langfuse_activo()`) y «enviar trazas a Langfuse» (`settings.langfuse_tracing()`) son interruptores distintos.

---

## 11. Langfuse frente a LangSmith

Comparación basada en cómo se ha integrado cada uno en este proyecto y en su documentación actual:

| Aspecto | Langfuse | LangSmith |
|---|---|---|
| **Facilidad de integración** | Pide código: pasar el `CallbackHandler` en la config y, para seguir sus buenas prácticas, una raíz propia con `propagate_attributes`. Es más trabajo, pero te da control total sobre la forma de la traza | Mínima con LangChain y LangGraph: cuatro variables de entorno y cero cambios en el código. Ojo con el tipo de workspace (proyecto o agente) |
| **Qué se ve en la traza del grafo** | Nodos, `generation`s con modelo, tokens, coste y **versión del prompt enlazada**, `tool`s, y la raíz `responder-mensaje` con I/O legibles. Sesiones y usuarios como atributos propios de la traza | Nodos, runs `prompt` y `llm` (tokens, coste), `tool`s y la arista condicional. La raíz muestra el estado de LangGraph. Hilos y usuario por metadata |
| **Gestión de prompts** | Usada en el proyecto: versiones, etiquetas (`production`), variables `{{...}}`, caché y fallback, enlace con cada generation y métricas por versión | Tiene gestión de prompts propia, que este proyecto **no usa** (los prompts viven en Langfuse) |
| **Evaluaciones** | `dataset.run_experiment()` con evaluadores por item y por ejecución; scores enlazados a cada traza; comparación de experimentos | `client.evaluate()` con evaluadores que reciben argumentos por nombre; feedback por ejemplo; vista de comparación; jueces ya hechos (`openevals`) y evaluadores desde la interfaz |
| **Autoalojamiento** | Open source, y se puede autoalojar con Docker Compose o Kubernetes | Solo como complemento del plan **Enterprise**, en Kubernetes. Además, los workspaces basados en agentes no existen en la versión autoalojada |
| **Datos sensibles** | `mask_otel_spans` antes de exportar (activado en el proyecto) | Ocultar todo por variables de entorno, o enmascarado por reglas con un cliente configurado en el código (no activado) |

---

## 12. Problemas frecuentes

| Síntoma | Causa probable | Solución |
|---|---|---|
| No aparece ninguna traza | `LANGSMITH_TRACING` no es `true`, o `.env` no se cargó | Ejecuta desde el paquete instalado; comprueba la variable con `python -c "import os; from eventhub_v4.config import settings; print(os.getenv('LANGSMITH_TRACING'))"` |
| Error de autenticación con una clave correcta | Región equivocada | Pon `LANGSMITH_ENDPOINT` de tu región (EU: `https://eu.api.smith.langchain.com`) |
| Aviso al arrancar y ninguna traza | Están definidos a la vez `LANGSMITH_AGENT_ID`/`LANGSMITH_AGENT_ENVIRONMENT` y `LANGSMITH_PROJECT` | Deja solo una de las dos opciones (apartado 2.3) |
| Workspace basado en agentes y las trazas no aparecen donde esperas | Hay otro agente o entorno con el mismo nombre, o la clave es de otro workspace | Revisa qué agente se creó a partir de `LANGSMITH_PROJECT`, o crea el agente y usa las variables de agente |
| El agente no se puede crear por SDK | La clave es solo de trazado | Usa una clave con permiso para crear proyectos, o créalo desde la interfaz |
| Un hilo no agrupa todos los turnos | Algún turno se lanzó sin la metadata `thread_id` | Invoca siempre el grafo con `config_langchain()` (lo hace `enviar()`) |
| La evaluación aparece también en Langfuse | Se ejecutó otro script sin desactivar Langfuse | Usa `scripts/evaluar_langsmith.py`, que lo desactiva |
| `No se pudo descargar la vN del prompt de Langfuse` | La versión no existe en Langfuse | `python scripts/subir_prompts.py` |
| Errores 429 durante la evaluación | Límite de peticiones de OpenAI | Baja `max_concurrency` en `evaluar_langsmith.py` |
| `pytest` envía trazas | No debería: el fixture automático pone `LANGSMITH_TRACING=false` | Ejecuta los tests desde la raíz del proyecto para que se cargue `tests/conftest.py` |

---

## 13. Mapa de ficheros y referencias

### Ficheros del proyecto

| Fichero | Papel para LangSmith |
|---|---|
| `.env` / `.env.example` | `LANGSMITH_TRACING`, `LANGSMITH_API_KEY`, `LANGSMITH_ENDPOINT` y el destino (proyecto o agente) |
| `src/eventhub_v4/observabilidad.py` | `config_langchain()`: `run_name`, tags y metadata (`thread_id`, `user_id`) que lee LangSmith |
| `src/eventhub_v4/grafos/v4_herramientas.py` | El grafo; los nombres de nodos y de `generar-respuesta` son los de los runs |
| `src/eventhub_v4/llm/prompt_gestionado.py` | La plantilla `preparar-prompt` |
| `evaluacion/dataset.json` | El dataset (compartido con Langfuse) |
| `src/eventhub_v4/evaluacion/metricas.py` | Las métricas (compartidas con Langfuse) |
| `src/eventhub_v4/evaluacion/ejecucion.py` | `responder()`: una pregunta en un hilo nuevo |
| `scripts/evaluar_langsmith.py` | Dataset, evaluadores y `client.evaluate()` |
| `tests/conftest.py` | Desactiva LangSmith en los tests |

### Orden recomendado

```bash
pytest                                  # 1. todo en verde sin red
# 2. comprueba el tipo de workspace y configura el destino (apartado 2.3)
python -m eventhub_v4                   # 3. una conversación a mano; revisa la traza y el hilo
python scripts/subir_prompts.py         # 4. los prompts v1 y v2 deben existir en Langfuse
python scripts/evaluar_langsmith.py     # 5. dataset + experimentos prompt-v1 y prompt-v2
```

### Documentación oficial

- [Trazar agentes LangGraph](https://docs.langchain.com/langsmith/trace-with-langgraph) · [Trazar con LangChain](https://docs.langchain.com/langsmith/trace-with-langchain)
- [Enviar trazas a un agente](https://docs.langchain.com/langsmith/log-traces-to-agent) · [Crear un agente](https://docs.langchain.com/langsmith/create-an-agent) · [Workspaces basados en agentes](https://docs.langchain.com/langsmith/migrate-to-agent-based-workspaces)
- [Hilos](https://docs.langchain.com/langsmith/threads) · [Metadata y tags](https://docs.langchain.com/langsmith/add-metadata-tags) · [Seguimiento de costes](https://docs.langchain.com/langsmith/cost-tracking)
- [Conceptos de evaluación](https://docs.langchain.com/langsmith/evaluation-concepts) · [Evaluar un grafo](https://docs.langchain.com/langsmith/evaluate-graph) · [Evaluadores de código](https://docs.langchain.com/langsmith/code-evaluator-sdk) · [LLM como juez](https://docs.langchain.com/langsmith/llm-as-judge-sdk)
- [Gestionar datasets por código](https://docs.langchain.com/langsmith/manage-datasets-programmatically) · [Comparar experimentos](https://docs.langchain.com/langsmith/compare-experiment-results)
- [Ocultar datos sensibles](https://docs.langchain.com/langsmith/mask-inputs-outputs) · [LangSmith autoalojado](https://docs.langchain.com/langsmith/self-hosted)
