# Tutorial: Langfuse en el asistente EventHub v4

Este tutorial explica cómo usa **Langfuse** el asistente de atención al cliente de EventHub (un agente LangGraph con herramientas) para tres cosas:

1. **Ver qué pasa dentro del agente** en cada conversación: qué nodos se ejecutaron, qué herramientas se llamaron, cuánto tardó y cuánto costó.
2. **Gestionar el prompt de sistema** fuera del código, con versiones y etiquetas.
3. **Medir la calidad de las respuestas** con un dataset y experimentos, para saber si un cambio de prompt mejora o empeora el asistente.

Cada apartado explica el concepto, enseña el código del proyecto que lo implementa y dice cómo comprobarlo. Las versiones usadas son `langfuse==5.2.0` (SDK de Python), `langchain-core==1.7.6` y `langgraph==1.2.20`.

---

## Índice

1. [Conceptos de Langfuse que vas a usar](#1-conceptos-de-langfuse-que-vas-a-usar)
2. [Puesta en marcha](#2-puesta-en-marcha)
3. [Trazas del grafo LangGraph](#3-trazas-del-grafo-langgraph)
4. [Enmascarado de datos personales](#4-enmascarado-de-datos-personales)
5. [Gestión del prompt de sistema](#5-gestión-del-prompt-de-sistema)
6. [Lanzar conversaciones y leer coste, latencia y herramientas](#6-lanzar-conversaciones-y-leer-coste-latencia-y-herramientas)
7. [Datasets, experimentos y métricas](#7-datasets-experimentos-y-métricas)
8. [Probar el trazado sin red](#8-probar-el-trazado-sin-red)
9. [Convivencia con LangSmith](#9-convivencia-con-langsmith)
10. [Problemas frecuentes](#10-problemas-frecuentes)
11. [Mapa de ficheros y referencias](#11-mapa-de-ficheros-y-referencias)

---

## 1. Conceptos de Langfuse que vas a usar

| Concepto | Qué es | En este proyecto |
|---|---|---|
| **Observación** | Un paso concreto: una llamada al modelo, una herramienta, un nodo del grafo. Tiene un **tipo** (`agent`, `chain`, `generation`, `tool`, `span`...) | Cada nodo de LangGraph, cada llamada a `ChatOpenAI` y cada herramienta |
| **Traza** | Un árbol de observaciones que representa una unidad de trabajo completa | **Un turno** de conversación: el usuario escribe un mensaje y el asistente responde |
| **Sesión** | Agrupa varias trazas relacionadas mediante un `session_id` | **Una conversación** (un hilo). `session_id` = `thread_id` del checkpointer |
| **Usuario** | `user_id` asociado a la traza; permite ver coste y uso por usuario | El usuario del chat (`/usuario <id>`) o el de cada conversación guionizada |
| **Tags** | Etiquetas cortas e independientes para filtrar | `eventhub-v4`, `cli`, `demo-10-conversaciones`, `evaluacion` |
| **Metadata** | Pares clave-valor con contexto (mejor que tags para atributos con nombre) | `prompt_version`, `conversacion`, `dataset`, `item`, herramientas usadas, `pasos` |
| **Entorno** | Separa datos de `development`, `staging`, `production`... | `LANGFUSE_TRACING_ENVIRONMENT=development`; los experimentos usan su propio entorno |
| **Prompt** | Plantilla versionada en Langfuse Prompt Management, con **versiones** (1, 2, 3...) y **etiquetas** (`production`, `candidata`...) | `eventhub-sistema`, de tipo texto, con variables `{{marca}}`, `{{tono}}` y `{{politicas}}` |
| **Dataset** | Conjunto de casos de prueba (`input`, `expected_output`, `metadata`) | `eventhub-v4-12-preguntas`: 4 de políticas, 4 de eventos y 4 de pedidos |
| **Experimento** | Una ejecución de la aplicación sobre todos los items de un dataset | `prompt-v1-<fecha>` y `prompt-v2-<fecha>` |
| **Score** | Una puntuación asociada a una traza u observación | `correccion`, `herramientas_correctas` y `privacidad` |

La regla que sigue el proyecto, tomada de la guía oficial [¿Cómo es una buena traza?](https://langfuse.com/docs/observability/best-practices), es: **en un chatbot, una traza por turno y una sesión por conversación**. No sabes de antemano cuándo termina una conversación, y con trazas por turno el árbol de cada traza se mantiene pequeño y fácil de leer.

---

## 2. Puesta en marcha

### 2.1 Crear el proyecto y las claves

1. Crea una cuenta en [Langfuse Cloud](https://langfuse.com/cloud). El plan gratuito basta para este proyecto. Elige la región (este proyecto usa **EU**).
2. Crea un proyecto y, en la configuración del proyecto, genera un par de claves de API: una pública (`pk-lf-...`) y una secreta (`sk-lf-...`).

### 2.2 Configurar `.env`

Copia la plantilla y rellena las claves. **No pegues las claves en chats ni las subas al repositorio**; `.env` ya está en `.gitignore`.

```bash
cp .env.example .env
```

Variables relacionadas con Langfuse:

```bash
# Conexión
LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_SECRET_KEY=sk-lf-...
LANGFUSE_BASE_URL=https://cloud.langfuse.com     # EU; US: https://us.cloud.langfuse.com
LANGFUSE_TRACING_ENVIRONMENT=development         # no mezcla pruebas con producción

# Comportamiento del proyecto
EVENTHUB_LANGFUSE_TRACING=1        # 0 = no enviar trazas aunque haya claves
EVENTHUB_LANGFUSE_MASK_PII=1       # enmascarar emails en las trazas
EVENTHUB_PROMPT_NOMBRE=eventhub-sistema
EVENTHUB_PROMPT_LABEL=production   # qué versión del prompt descarga la aplicación
EVENTHUB_MARCA=EventHub            # variable {{marca}} del prompt
EVENTHUB_TONO=cercano y profesional  # variable {{tono}} del prompt
EVENTHUB_USUARIO=anonimo           # user_id por defecto
EVENTHUB_JUEZ_MODEL=gpt-4.1        # modelo juez de la evaluación
```

> `LANGFUSE_HOST` es el nombre antiguo de `LANGFUSE_BASE_URL`. El SDK todavía lo acepta, pero está obsoleto.

`src/eventhub_v4/config/settings.py` carga `.env` con `load_dotenv` **antes** de que se cree el cliente de Langfuse. El orden importa: si el cliente se crea antes de cargar las variables, arranca sin credenciales.

### 2.3 Instalar y comprobar la conexión

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

python -c "from eventhub_v4.observabilidad import cliente_langfuse; print(cliente_langfuse().auth_check())"
# True → las claves y la región son correctas
```

---

## 3. Trazas del grafo LangGraph

### 3.1 Qué se ve en una traza

Cada turno produce un árbol como este (ejemplo: «¿Mi pedido EH-1003 es un concierto en Madrid? Mi email es …»):

```
responder-mensaje                  agent       input: mensaje del usuario · output: respuesta
└── grafo-eventhub-v4              chain       (ejecución del grafo LangGraph)
    ├── chatbot                    chain       nodo
    │   ├── generar-respuesta      chain
    │   │   ├── preparar-prompt    chain       prompt de sistema + historial
    │   │   └── ChatOpenAI         generation  modelo, tokens, coste, versión del prompt
    │   └── ruta_tras_chatbot      chain       decisión de la arista: usar_herramientas | limite_alcanzado | fin
    ├── herramientas               chain       nodo
    │   └── consultar_pedido       tool        argumentos y resultado JSON
    ├── chatbot                    chain
    │   └── ...                                segunda llamada al modelo
    ├── herramientas
    │   └── buscar_eventos         tool
    └── chatbot
        └── ...                                respuesta final (ruta_tras_chatbot = fin)
```

Con este árbol puedes responder preguntas como estas:

- **¿Qué herramientas llamó y con qué argumentos?** Mira las observaciones `tool`.
- **¿Qué decidió el modelo después de cada resultado?** Cada llamada al modelo es su propia `generation`, intercalada con las herramientas. Nunca hay una sola generation que envuelva el bucle entero.
- **¿Por qué terminó?** El output de `ruta_tras_chatbot` dice si fue `fin` o `limite_alcanzado`.
- **¿Qué paso es lento o caro?** Cada observación tiene su latencia, y cada `generation` sus tokens y su coste.
- **¿Qué versión del prompt produjo esta respuesta?** La `generation` está enlazada al prompt `eventhub-sistema` y a su versión.

### 3.2 Cómo se construye: dos piezas que encajan

El trazado combina las dos formas de integración que documenta Langfuse para [LangChain y LangGraph](https://langfuse.com/integrations/frameworks/langchain):

| Pieza | Qué aporta | Dónde |
|---|---|---|
| **SDK de Langfuse** (`propagate_attributes` y `start_as_current_observation`) | La raíz `responder-mensaje` con input y output legibles, y los atributos de traza (`session_id`, `user_id`, tags, metadata) | `traza_turno()` en `src/eventhub_v4/observabilidad.py` |
| **`CallbackHandler` de LangChain** | Todo lo de dentro: nodos, `generation`s con modelo, tokens y coste, y `tool`s | `handler_langfuse()` y `config_langchain()` en el mismo fichero |

Las dos piezas se usan juntas en `enviar()` (`src/eventhub_v4/grafos/v4_herramientas.py`), la función que ejecuta un turno:

```python
def enviar(grafo, thread_id, texto, usuario=None, tags=None, metadata=None) -> dict:
    config = config_langchain(thread_id, usuario=usuario, tags=tags, metadata=metadata)
    previos = len(grafo.get_state(config).values.get("messages", []))
    with traza_turno(thread_id, texto, usuario=usuario, tags=tags, metadata=metadata) as raiz:
        estado = grafo.invoke({"messages": [HumanMessage(texto)], "pasos": 0}, config)
        ...
        if raiz is not None:
            raiz.update(output=resultado["respuesta"], metadata={
                "herramientas": [...], "pasos": ..., "limite_alcanzado": ...,
            })
    return resultado
```

### 3.3 La raíz de la traza: `traza_turno()`

```python
@contextmanager
def traza_turno(thread_id, texto, usuario=None, tags=None, metadata=None):
    if not settings.langfuse_tracing():
        yield None          # sin Langfuse no hace nada
        return
    from langfuse import propagate_attributes
    lf = cliente_langfuse()
    with propagate_attributes(
        trace_name=NOMBRE_TRAZA,             # "responder-mensaje"
        session_id=thread_id,
        user_id=usuario or settings.usuario_por_defecto(),
        tags=etiquetas(tags),                # siempre incluye "eventhub-v4"
        metadata={k: str(v) for k, v in (metadata or {}).items()},
    ):
        with lf.start_as_current_observation(as_type="agent", name=NOMBRE_TRAZA, input=texto) as raiz:
            yield raiz
```

Cada decisión tiene un motivo:

- **`propagate_attributes` envuelve la creación de la raíz.** Así todas las observaciones que se crean dentro, incluidas las `generation`s que llevan el coste, heredan `session_id` y `user_id`. Si se llamara más tarde, las observaciones anteriores no entrarían en las agregaciones de coste por sesión o por usuario.
- **Tipo `agent`.** Un turno es una ejecución del agente. Usar el tipo más específico, en lugar de un `span` genérico, mejora la vista de grafo de agentes de Langfuse.
- **Nombre estable y en forma verbal (`responder-mensaje`).** Los evaluadores, dashboards y filtros guardados apuntan a observaciones por nombre, así que hay que tratar los nombres como una API. Por eso no lleva valores dinámicos (nada de `responder-mensaje-hilo-3`) ni el nombre del modelo.
- **Input = texto del usuario y output = respuesta.** La tabla de trazas, los evaluadores y la comparación de experimentos leen el input y el output de la raíz. Sin esta raíz, el input sería el estado completo del grafo, con todo el historial en JSON.
- **La metadata de la raíz** (herramientas, pasos, límite alcanzado) permite filtrar, por ejemplo, los turnos que agotaron el límite de pasos.

### 3.4 El interior: `CallbackHandler` y la config de LangChain

```python
@lru_cache(maxsize=1)
def cliente_langfuse():
    from langfuse import Langfuse
    return Langfuse(mask_otel_spans=_mask_otel_spans if settings.langfuse_mask_pii() else None)


def handler_langfuse():
    if not settings.langfuse_tracing():
        return None
    cliente_langfuse()          # primero el cliente (con la máscara), luego el handler
    from langfuse.langchain import CallbackHandler
    return CallbackHandler(public_key=os.environ["LANGFUSE_PUBLIC_KEY"])


def config_langchain(thread_id, usuario=None, tags=None, metadata=None) -> dict:
    config = {
        "configurable": {"thread_id": thread_id},   # memoria del checkpointer
        "run_name": "grafo-eventhub-v4",
        "tags": etiquetas(tags),
        "metadata": {"thread_id": thread_id, "user_id": usuario or ..., **(metadata or {})},
    }
    handler = handler_langfuse()
    if handler is not None:
        config["callbacks"] = [handler]
    return config
```

- **Un solo cliente** (`cliente_langfuse()`, cacheado). Lo crea el proyecto con la configuración de enmascarado, y el `CallbackHandler` y los scripts reutilizan esa misma instancia.
- **`public_key` explícita en el handler.** Si en el proceso hay varios clientes de Langfuse, un `CallbackHandler()` sin clave **deja de trazar sin avisar** para no mezclar proyectos. Lo detectó un test del proyecto (apartado 8).
- **El handler va en `config["callbacks"]`.** LangGraph pasa la config a cada nodo, y LangChain la propaga a las llamadas internas, así que las herramientas invocadas dentro del nodo `herramientas` también aparecen como `tool` sin código adicional.
- **`tags` y `metadata` de la config** los ve también LangSmith (apartado 9).

### 3.5 Probarlo a mano

```bash
python -m eventhub_v4
```

```
[hilo-1] Tú: /usuario ana.gomez
[hilo-1] Tú: ¿Mi pedido EH-1003 es para un concierto en Madrid? Mi email es ana.gomez@example.com
[hilo-1] Tú: ¿Y qué otros conciertos hay ese mes?
[hilo-1] Tú: /hilo hilo-2          ← nueva conversación = nueva sesión
[hilo-2] Tú: salir                 ← al salir se llama a flush()
```

En Langfuse verás dos trazas `responder-mensaje` agrupadas en la sesión `hilo-1`, con `user_id` `ana.gomez`. Abre la sesión para ver la conversación completa en orden.

> **`flush()`.** El SDK envía los datos en segundo plano y por lotes. En procesos cortos (el chat al salir, los scripts) el proyecto llama a `observabilidad.flush()` antes de terminar. Sin esa llamada, las últimas trazas pueden no llegar nunca.

---

## 4. Enmascarado de datos personales

Las preguntas sobre pedidos incluyen el email del cliente, que acaba en el mensaje del usuario, en los argumentos de `consultar_pedido` y en el historial que ve el modelo. Para no guardar ese dato personal en Langfuse, el cliente se crea con `mask_otel_spans`, el mecanismo que la [documentación de masking](https://langfuse.com/docs/observability/features/masking) recomienda para el SDK de Python v5:

```python
_EMAIL = re.compile(r"\b([A-Za-z0-9])[A-Za-z0-9._%+-]*@([A-Za-z0-9.-]+\.[A-Za-z]{2,})\b")

def enmascarar_emails(texto: str) -> str:
    return _EMAIL.sub(r"\1***@\2", texto)      # ana.gomez@example.com → a***@example.com

def _mask_otel_spans(*, params):
    from langfuse.types import MaskOtelSpansResult, OtelSpanPatch
    parches = {}
    for identificador, span in params.spans.items():
        cambios = {k: enmascarar_emails(v) for k, v in span.attributes.items()
                   if isinstance(v, str) and enmascarar_emails(v) != v}
        if cambios:
            parches[identificador] = OtelSpanPatch(set_attributes=cambios)
    return MaskOtelSpansResult(span_patches=parches)
```

- La máscara actúa **justo antes de exportar**, sobre todos los atributos de texto, así que cubre también lo que genera el `CallbackHandler`.
- **La aplicación no cambia.** El modelo y la herramienta reciben el email real; solo se enmascara la copia que va a Langfuse.
- Se conserva la inicial y el dominio (`a***@example.com`) para poder seguir depurando.
- `EVENTHUB_LANGFUSE_MASK_PII=0` la desactiva.
- Afecta **solo a Langfuse**. LangSmith recibe sus propios datos sin enmascarar.

---

## 5. Gestión del prompt de sistema

### 5.1 Por qué sacar el prompt del código

Con el prompt en Langfuse puedes cambiarlo sin desplegar código, tener versiones con historial, decidir con una **etiqueta** qué versión usa producción y ver en cada traza qué versión generó cada respuesta. Eso último es lo que permite comparar versiones con datos.

### 5.2 Cómo está organizado

| Elemento | Valor |
|---|---|
| Nombre del prompt | `eventhub-sistema` (tipo **texto**) |
| Variables | `{{marca}}`, `{{tono}}`, `{{politicas}}` |
| Versión 1 | El prompt original. Etiqueta `production` |
| Versión 2 | La mejora: cita literal de plazos e importes, formato fijo para eventos (fecha, precio, disponibilidad, «agotado»), privacidad estricta en pedidos no verificados y nombre del evento en los pedidos. Etiqueta `candidata` |
| Copias locales | `prompts/eventhub_sistema_v1.txt` y `prompts/eventhub_sistema_v2.txt` |

**¿Por qué `{{politicas}}` es una variable?** Las políticas siguen en `data/policies.md` y se inyectan al compilar el prompt. Así, cambiar una política (un dato) no exige una versión nueva del prompt (una instrucción), y las versiones del prompt solo reflejan cambios de comportamiento.

Las copias locales son la fuente de la que se suben las versiones y el **fallback** cuando Langfuse no está disponible, por ejemplo en los tests.

### 5.3 Subir las versiones

```bash
python scripts/subir_prompts.py
# Creado eventhub-sistema v1 con etiquetas ['production']
# Creado eventhub-sistema v2 con etiquetas ['candidata']
```

El script (`scripts/subir_prompts.py`) llama a `create_prompt(name=..., prompt=..., type="text", labels=[...], commit_message=..., config={...})` por cada versión. Es idempotente: si la versión ya existe, no la duplica y avisa si su texto difiere del fichero local. En `config` guarda el modelo y la temperatura con los que se pensó el prompt.

### 5.4 Descargar el prompt en la aplicación

`src/eventhub_v4/llm/prompt_gestionado.py`:

```python
def obtener_prompt(version=None, label=None, **variables) -> PromptSistema:
    valores = _variables(**variables)               # marca, tono y politicas
    local = texto_local(version or 1)
    if not settings.langfuse_activo():              # sin claves → copia local
        return PromptSistema(_a_langchain(local), valores)
    kwargs = {"version": version} if version else {"label": label or settings.prompt_label()}
    prompt = cliente_langfuse().get_prompt(settings.prompt_nombre(), type="text", fallback=local, **kwargs)
    if prompt.is_fallback:                          # Langfuse no respondió
        return PromptSistema(_a_langchain(local), valores)
    return PromptSistema(prompt.get_langchain_prompt(), valores,
                         version=prompt.version, cliente_langfuse=prompt)
```

- **Por defecto se pide la etiqueta `production`**, nunca un número de versión. Así, para cambiar la versión que usa el asistente basta con mover la etiqueta. La evaluación sí pide versiones concretas (`version=1`, `version=2`).
- **`fallback`**: si Langfuse no responde y no hay nada en caché, el SDK devuelve el texto local con `is_fallback=True`. El asistente sigue funcionando, aunque esa traza no quede enlazada a ninguna versión.
- **Caché**: el SDK guarda el prompt en memoria (60 segundos por defecto), así que no añade latencia a cada turno.
- **`get_langchain_prompt()`** convierte `{{variable}}` (formato de Langfuse) en `{variable}` (formato de LangChain).

### 5.5 Enlazar cada generation con su versión

Para que la `generation` muestre qué prompt usó, la [documentación](https://langfuse.com/docs/prompt-management/features/link-to-traces) indica pasar el prompt de Langfuse en la metadata de la **plantilla** de LangChain, con la clave `langfuse_prompt`:

```python
def plantilla_chat(self) -> ChatPromptTemplate:
    metadata = {"prompt_version": self.etiqueta}
    if self.cliente_langfuse is not None:
        metadata["langfuse_prompt"] = self.cliente_langfuse
    plantilla = ChatPromptTemplate(
        [("system", self.plantilla), MessagesPlaceholder("messages")],
    ).partial(**self.variables)
    return plantilla.with_config(run_name="preparar-prompt", metadata=metadata)
```

Y en el grafo:

```python
cadena_chatbot = (prompt.plantilla_chat() | modelo_con_herramientas).with_config(run_name="generar-respuesta")

def chatbot(estado):
    return {"messages": [cadena_chatbot.invoke({"messages": estado["messages"]})]}
```

El `CallbackHandler` registra el prompt cuando arranca `preparar-prompt` y lo asocia a la siguiente `generation` de la misma cadena. **`langfuse_prompt` debe ir solo en la plantilla**, no en la llamada al modelo ni en otros puntos de la cadena.

### 5.6 Comparar versiones y pasar una a producción

1. En Langfuse, la página del prompt tiene una pestaña de métricas por versión (latencia, coste, scores) calculadas a partir de las generations enlazadas, y otra con las generations que usaron cada versión. Desde una generation, el distintivo del prompt lleva directamente a su versión.
2. La evaluación del apartado 7 compara v1 y v2 sobre el mismo dataset.
3. Cuando decidas, mueve la etiqueta:

```bash
python scripts/subir_prompts.py --promover 2      # production → v2
```

El asistente empezará a usar la v2 en cuanto caduque su caché, sin tocar código ni reiniciar. También puedes mover la etiqueta desde la interfaz de Langfuse.

---

## 6. Lanzar conversaciones y leer coste, latencia y herramientas

### 6.1 Diez conversaciones guionizadas

```bash
python scripts/conversaciones.py
```

`scripts/conversaciones.py` ejecuta 10 conversaciones de 1 a 3 turnos. Cada una tiene su hilo (`demo-<fecha>-NN`) y su usuario, y entre todas cubren:

| # | Caso | Qué debería verse en la traza |
|---|---|---|
| 1 | Política de devoluciones (2 turnos) | Sin herramientas |
| 2 | Pedido + otros conciertos del mismo mes | `consultar_pedido` → `buscar_eventos` encadenadas |
| 3 | Pedido sin email y después con email | Turno 1 sin herramientas; turno 2 con `consultar_pedido` |
| 4 | Pedido con email incorrecto | `consultar_pedido` devuelve «no verificado» y la respuesta no da pistas |
| 5 | «¿Cuál de esos es el más barato?» | Uso de la memoria del hilo |
| 6 | Conciertos en Madrid en enero de 2027 | `buscar_eventos` con `mes="2027-01"` |
| 7 | Cambio de titular y caso deportivo | Sin herramientas (políticas) |
| 8 | Pregunta fuera de las políticas | Responde que no tiene esa información y remite a soporte |
| 9 | Pedido cancelado y reembolso | Herramienta + políticas |
| 10 | Sin resultados y evento agotado | `buscar_eventos` con lista vacía; «agotado» |

Todas llevan el tag `demo-10-conversaciones` y la metadata `conversacion` y `prompt_version`. Los `session_id` se guardan en `resultados/conversaciones.json`.

### 6.2 Informe por sesión con la API

```bash
python scripts/informe_trazas.py
```

`scripts/informe_trazas.py` consulta la **API de observaciones v2**, que es la vía de lectura en tiempo real recomendada (el endpoint antiguo de trazas está obsoleto), filtrando por `session_id`:

```python
lf.api.observations.get_many(session_id=session_id, fields="core,basic,usage,metrics", limit=100, cursor=cursor)
```

- **`fields` debe incluir `usage`**: la respuesta por defecto (`core,basic`) no trae `totalCost`.
- **Coste de la conversación** = suma de `total_cost` de las observaciones `GENERATION`.
- **Latencia de la conversación** = suma, por traza (`trace_id`), del tiempo entre la primera observación que empieza y la última que termina. No cuenta lo que tarda el usuario en escribir.
- **Herramientas** = nombres de las observaciones `TOOL`, en orden.
- La paginación es por cursor: se encadena `meta.cursor` hasta que no queda nada.

El resultado es una tabla Markdown, guardada también en `resultados/informe_trazas.md`:

```
| Sesión | Usuario | Conversación | Turnos | Llamadas LLM | Tokens | Coste | Latencia | Herramientas |
```

> Si una sesión sale vacía, espera unos segundos y repite: la ingesta tarda un poco.
> El coste solo aparece si Langfuse reconoce el modelo (`gpt-4.1-mini` está en su tabla de precios). Si usas un modelo que no conoce, verás tokens pero coste 0.

### 6.3 Lo mismo en la interfaz

- **Trazas**: filtra por el tag `demo-10-conversaciones` o por el nombre `responder-mensaje`.
- **Sesiones**: cada `demo-...-NN` es una conversación completa.
- **Usuarios**: coste y número de trazas por `user_id`.

> Los nombres exactos de menús y columnas pueden cambiar entre versiones de Langfuse. Guíate por los conceptos (trazas, sesiones, usuarios, prompts, datasets, experimentos), no por un texto concreto de la interfaz.

---

## 7. Datasets, experimentos y métricas

### 7.1 El dataset

`evaluacion/dataset.json` tiene 12 items, 4 por categoría. Cada item separa bien las tres partes:

```json
{
  "id": "ped-02-evento-del-pedido",
  "categoria": "pedidos",
  "input": {"pregunta": "¿Para qué evento es mi pedido EH-1005 y cuándo se celebra? Mi email es marta.sanchez@example.com"},
  "expected_output": {
    "respuesta": "El pedido EH-1005 (pagado, 2 entradas) es para Electro Night Barcelona, en Barcelona, el 31 de diciembre de 2026 a las 23:00.",
    "herramientas": ["consultar_pedido", "buscar_eventos"]
  },
  "metadata": {"categoria": "pedidos"}
}
```

- `input`: solo lo que recibe la aplicación.
- `expected_output`: la respuesta de referencia y las herramientas **necesarias** para responder bien.
- `metadata`: contexto para los evaluadores. Por ejemplo, `no_debe_contener` lista los datos que no se pueden revelar en los casos de pedido sin email o con email incorrecto.

Las respuestas esperadas se han sacado de `data/policies.md`, `data/events.json` y `data/orders.json`. **Revísalas antes de fiarte de la evaluación**: una respuesta esperada mal escrita invalida la métrica del juez.

### 7.2 Las métricas

`src/eventhub_v4/evaluacion/metricas.py` define tres, independientes de la plataforma:

| Score | Tipo | Cómo se calcula | Valores |
|---|---|---|---|
| `correccion` | LLM como juez (`gpt-4.1`, temperatura 0, salida estructurada con razonamiento) | Compara la respuesta con la esperada: ¿contiene los datos esenciales que pide la pregunta sin contradecirla? | 0 · 0.5 · 1 |
| `herramientas_correctas` | Determinista | Llamó a **todas** las herramientas esperadas; si no se esperaba ninguna, no llamó a ninguna. Se permiten llamadas extra | 0 · 1 |
| `privacidad` | Determinista | La respuesta no contiene ningún dato de `no_debe_contener`. Solo en los items que lo definen | 0 · 1 |

El juez usa un modelo más potente que el asistente, para que no se juzgue a sí mismo, y escribe su razonamiento antes de puntuar. Ese razonamiento se guarda como comentario del score.

### 7.3 Ejecutar el experimento

```bash
python scripts/evaluar_langfuse.py --version 1
python scripts/evaluar_langfuse.py --version 2
```

`scripts/evaluar_langfuse.py` sigue el patrón del [experiment runner del SDK](https://langfuse.com/docs/evaluation/experiments/experiments-via-sdk):

```python
subir_dataset(lf)                                   # create_dataset + create_dataset_item(id=...) idempotente
dataset = lf.get_dataset("eventhub-v4-12-preguntas")
prompt = obtener_prompt(version=args.version)       # versión exacta del prompt

def tarea(*, item, **kwargs):                       # un hilo nuevo por pregunta
    return responder(item.input["pregunta"], prompt, id_item=item.metadata["id"], plataforma="langfuse")

def evaluador(*, input, output, expected_output, metadata=None, **kwargs):
    return [{"name": "correccion", "value": ..., "comment": razonamiento_del_juez},
            {"name": "herramientas_correctas", "value": ..., "comment": ...},
            {"name": "privacidad", "value": ...}]   # solo si aplica

def medias(*, item_results, **kwargs):              # evaluador de ejecución (run-level)
    return [{"name": "media_correccion", "value": ...}, ...]

resultado = dataset.run_experiment(
    name=f"EventHub v4 · prompt-v{N}", run_name=f"prompt-v{N}-<fecha>",
    task=tarea, evaluators=[evaluador], run_evaluators=[medias], max_concurrency=4,
    metadata={"prompt_version": ..., "modelo": ..., "juez": ...},
)
```

Qué hace el runner:

- Ejecuta `tarea` para cada item y **crea una traza por item**, enlazada al experimento. Dentro va la traza normal del asistente (`responder-mensaje`, nodos, herramientas), así que puedes depurar cualquier respuesta mal puntuada.
- Guarda cada evaluación como **score** de esa traza, y las medias como scores del experimento.
- Aísla los fallos: si un item falla, el resto sigue.
- Usa su propio entorno, así que las trazas de evaluación no se mezclan con las de `development`.

La tarea devuelve `{"respuesta", "herramientas"}` y no solo el texto. Así la métrica determinista puede comprobar las herramientas sin volver a leer la traza.

El script imprime las puntuaciones por item, las medias y la URL del experimento, y guarda todo en `resultados/eval_langfuse_v{N}.json`.

### 7.4 Comparar v1 y v2

En la vista de experimentos del dataset puedes comparar las dos ejecuciones item a item, con las respuestas lado a lado y las medias de cada score ([guía de comparación](https://langfuse.com/docs/evaluation/experiments/compare-experiments)).

Para decidir qué versión pasa a producción:

1. Compara las **medias** de las tres métricas.
2. Mira **por categoría**. Una versión puede mejorar en eventos y empeorar en políticas.
3. Abre las trazas de los items donde las versiones difieren y lee el razonamiento del juez.
4. Ten en cuenta coste y latencia: la v2 puede hacer una llamada extra a `buscar_eventos` en los pedidos.
5. Con 12 items, una diferencia de un solo item es ruido. Busca diferencias consistentes.

Después, `python scripts/subir_prompts.py --promover N`.

---

## 8. Probar el trazado sin red

### 8.1 Los tests nunca llaman a Langfuse

`tests/conftest.py` tiene un fixture automático que, en cada test, borra las claves de Langfuse y desactiva el trazado de Langfuse y de LangSmith. Así:

- `obtener_prompt()` usa la copia local de `prompts/`.
- `traza_turno()` no hace nada y `config_langchain()` no añade callbacks.
- `pytest` funciona sin claves ni conexión, aunque tu `.env` tenga claves reales.

### 8.2 Comprobar la forma de la traza con un exportador en memoria

`tests/test_trazas_langfuse.py` comprueba que la traza cumple las buenas prácticas **sin enviar nada**. Para ello crea el cliente con un `InMemorySpanExporter` de OpenTelemetry y un modelo falso con respuestas guionizadas:

```python
exportador = InMemorySpanExporter()
cliente = Langfuse(span_exporter=exportador, mask_otel_spans=obs._mask_otel_spans)
monkeypatch.setattr(obs, "cliente_langfuse", lambda: cliente)
...
v4.enviar(grafo, "hilo-t", "Estado de EH-1003, email ana.gomez@example.com", usuario="ana", tags=["test"])
cliente.flush()
spans = exportador.get_finished_spans()
```

Y verifica:

- Hay una sola raíz `responder-mensaje` de tipo `agent`, con el texto del usuario (enmascarado) como input y la respuesta como output.
- **Todas** las observaciones llevan `session.id` y `user.id`.
- Las `generation`s están enlazadas a `eventhub-sistema` v2.
- La herramienta es de tipo `tool` y no quedan nombres genéricos como `RunnableSequence`.
- Ningún atributo exportado contiene el email sin enmascarar.

Detalle práctico: cada test usa una `LANGFUSE_PUBLIC_KEY` distinta, porque el SDK reutiliza su procesador de spans por clave pública. Con la misma clave, el segundo cliente se quedaría con el exportador del primero.

Este método sirve para cualquier cambio en el trazado: **antes de mirar la interfaz, comprueba la forma de la traza con un test**.

---

## 9. Convivencia con LangSmith

LangSmith se activa **solo con variables de entorno**, sin tocar el código del grafo:

```bash
LANGSMITH_TRACING=true
LANGSMITH_API_KEY=lsv2_...
LANGSMITH_ENDPOINT=https://eu.api.smith.langchain.com
LANGSMITH_PROJECT=eventhub-v4
```

| | Langfuse | LangSmith |
|---|---|---|
| Cómo recibe los datos | `CallbackHandler` + SDK (OpenTelemetry) | Trazador de LangChain activado por entorno |
| Raíz de la traza | `responder-mensaje` (la crea `traza_turno`) | `grafo-eventhub-v4` (el `run_name` de la config) |
| Agrupación por conversación | `session_id` | metadata `thread_id` (en `config_langchain`) |
| Enmascarado de emails | Sí (`mask_otel_spans`) | No |

Las dos plataformas pueden trazar a la vez. Para la evaluación en LangSmith, `scripts/evaluar_langsmith.py` pone `EVENTHUB_LANGFUSE_TRACING=0` y así no duplica los experimentos en Langfuse. Aun así descarga los prompts de Langfuse, porque `langfuse_activo()` (hay claves y se pueden pedir prompts) y `langfuse_tracing()` (se envían trazas) son interruptores distintos.

---

## 10. Problemas frecuentes

| Síntoma | Causa probable | Solución |
|---|---|---|
| No aparece ninguna traza | No se llamó a `flush()` antes de terminar el proceso | Sal del chat con `salir` o Ctrl+D; en tus scripts llama a `observabilidad.flush()` |
| `auth_check()` da `False` | Claves de otro proyecto o región equivocada | Revisa `LANGFUSE_BASE_URL` (EU frente a US) y las claves |
| Las trazas no tienen nodos ni herramientas, solo la raíz | El `CallbackHandler` no está en `config["callbacks"]`, o hay varios clientes y el handler no lleva `public_key` | Usa `config_langchain()` y `handler_langfuse()` |
| Aviso «multiple langfuse clients are instantiated» | Se ha creado otro `Langfuse(...)` con otra clave en el mismo proceso | Usa siempre `cliente_langfuse()` |
| La generation no muestra el prompt | El prompt vino del fallback local (`prompt-local`), o `langfuse_prompt` está fuera de la plantilla | Ejecuta `subir_prompts.py`; mira `prompt.etiqueta` al arrancar el chat |
| `No se pudo descargar la vN del prompt` | La versión no existe en Langfuse | `python scripts/subir_prompts.py` |
| Coste 0 con tokens > 0 | Langfuse no reconoce el nombre del modelo | Usa un modelo de su tabla de precios o defínelo en la configuración de modelos del proyecto |
| Una sesión del informe sale vacía | La ingesta aún no ha terminado | Espera unos segundos y repite `informe_trazas.py` |
| Aviso «not able to parse the LLM model» en los tests | El modelo falso no tiene nombre de modelo | Es normal en los tests; con `ChatOpenAI` no aparece |
| Ves emails completos en LangSmith | La máscara es solo de Langfuse | Esperado; configura el enmascarado de LangSmith aparte si lo necesitas |

---

## 11. Mapa de ficheros y referencias

### Ficheros del proyecto

| Fichero | Papel |
|---|---|
| `src/eventhub_v4/observabilidad.py` | Cliente único, `CallbackHandler`, `traza_turno()`, `config_langchain()`, enmascarado, `flush()` |
| `src/eventhub_v4/grafos/v4_herramientas.py` | El grafo; `enviar()` une la raíz de la traza con la ejecución del grafo |
| `src/eventhub_v4/llm/prompt_gestionado.py` | Descarga del prompt, fallback y plantilla con `langfuse_prompt` |
| `src/eventhub_v4/config/settings.py` | Variables de entorno; `langfuse_activo()` y `langfuse_tracing()` |
| `prompts/eventhub_sistema_v{1,2}.txt` | Fuente de las versiones del prompt |
| `evaluacion/dataset.json` | Dataset de 12 preguntas |
| `src/eventhub_v4/evaluacion/` | Métricas y ejecución de una pregunta |
| `scripts/subir_prompts.py` | Crea v1 y v2; `--promover N` mueve `production` |
| `scripts/conversaciones.py` | 10 conversaciones trazadas |
| `scripts/informe_trazas.py` | Coste, latencia y herramientas por sesión (API de observaciones v2) |
| `scripts/evaluar_langfuse.py` | Dataset + experimento + scores |
| `scripts/evaluar_langsmith.py` | Lo mismo en LangSmith |
| `tests/test_trazas_langfuse.py` | Forma de la traza sin red |
| `.claude/skills/langfuse/` | Skill oficial de Langfuse para Claude Code (buenas prácticas para agentes) |

### Orden recomendado para reproducir todo

```bash
pytest                                        # 1. todo en verde sin red
python scripts/subir_prompts.py               # 2. prompts v1 (production) y v2 (candidata)
python -m eventhub_v4                         # 3. una conversación a mano; revisa la traza
python scripts/conversaciones.py              # 4. 10 conversaciones
python scripts/informe_trazas.py              # 5. coste, latencia y herramientas
python scripts/evaluar_langfuse.py --version 1
python scripts/evaluar_langfuse.py --version 2  # 6. comparar experimentos
python scripts/subir_prompts.py --promover N  # 7. promover la versión ganadora
```

### Documentación oficial

- [¿Cómo es una buena traza? (buenas prácticas)](https://langfuse.com/docs/observability/best-practices)
- [Integración con LangChain y LangGraph](https://langfuse.com/integrations/frameworks/langchain) · [Ejemplo con LangGraph](https://langfuse.com/integrations/frameworks/langgraph)
- [Tipos de observación](https://langfuse.com/docs/observability/features/observation-types) · [Sesiones](https://langfuse.com/docs/observability/features/sessions) · [Entornos](https://langfuse.com/docs/observability/features/environments) · [Masking](https://langfuse.com/docs/observability/features/masking)
- [Enlazar prompts con trazas](https://langfuse.com/docs/prompt-management/features/link-to-traces)
- [Experimentos con el SDK](https://langfuse.com/docs/evaluation/experiments/experiments-via-sdk) · [Comparar experimentos](https://langfuse.com/docs/evaluation/experiments/compare-experiments)
- [API pública (incluye la API de observaciones v2)](https://langfuse.com/docs/api-and-data-platform/features/public-api)
