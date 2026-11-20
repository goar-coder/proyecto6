"""Versión 4: herramientas con un nodo escrito a mano y límite de pasos.

    START → chatbot ─┬─(usar_herramientas)─► herramientas ──► chatbot   (bucle)
                     ├─(limite_alcanzado)──► limite ────────► END
                     └─(fin)───────────────► END

- `chatbot` llama al modelo con las herramientas enlazadas (bind_tools).
- Si la respuesta trae `tool_calls`, la arista condicional va a `herramientas`,
  que las ejecuta y añade un ToolMessage por cada una; después se vuelve al
  chatbot, que puede pedir más herramientas (encadenarlas) o responder.
- `pasos` cuenta las rondas de herramientas del turno actual. Si el modelo
  pide herramientas otra vez con pasos >= MAX_PASOS, se va a `limite`, que
  termina con un mensaje amable en lugar de seguir girando.

Herramientas reutilizadas de la sesión 4: buscar_eventos y consultar_pedido
(eventhub_v4/tools/eventhub_tools.py). El grafo se compila con un checkpointer
InMemorySaver: cada conversación (hilo) guarda su historial con un thread_id.

Observabilidad (sesión 6): el prompt de sistema se descarga de Langfuse Prompt
Management (etiqueta `production`) y cada turno se traza en Langfuse con session_id
(= thread_id), user_id y tags. LangSmith traza solo con sus variables de entorno.

Uso:  python -m eventhub_v4        (o el comando instalado: eventhub-v4)
"""

import json
from typing import Literal

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, MessagesState, StateGraph

from eventhub_v4.config.settings import usuario_por_defecto
from eventhub_v4.grafos.comun import guardar_diagrama
from eventhub_v4.llm.models import crear_modelo
from eventhub_v4.llm.prompt_gestionado import PromptSistema, obtener_prompt
from eventhub_v4.observabilidad import config_langchain, flush, traza_turno
from eventhub_v4.tools.eventhub_tools import buscar_eventos, consultar_pedido

HERRAMIENTAS = [buscar_eventos, consultar_pedido]
HERRAMIENTAS_POR_NOMBRE = {h.name: h for h in HERRAMIENTAS}

MAX_PASOS = 5

MENSAJE_LIMITE = (
    "Lo siento, no he podido completar tu consulta: he alcanzado el límite de "
    f"{MAX_PASOS} consultas seguidas. ¿Puedes reformular la pregunta o dividirla en partes? "
    "Si lo prefieres, escribe a soporte@eventhub.example o llama al +34 900 123 456."
)


def config_hilo(thread_id: str) -> dict:
    """Config de invocación: el checkpointer guarda y recupera el estado por thread_id."""
    return {"configurable": {"thread_id": thread_id}}


class EstadoV4(MessagesState):
    # Rondas de herramientas ejecutadas en el turno actual. No tiene reducer:
    # cada nodo que la devuelve la sustituye, y cada turno empieza con pasos=0.
    pasos: int


def _ultimo_ai(estado: EstadoV4) -> AIMessage | None:
    ultimo = estado["messages"][-1] if estado["messages"] else None
    return ultimo if isinstance(ultimo, AIMessage) else None


def construir_grafo(modelo=None, checkpointer=None, prompt: PromptSistema | None = None):
    """Compila el grafo. `prompt` es el prompt de sistema; si no se pasa, se descarga de
    Langfuse con la etiqueta configurada (por defecto `production`)."""
    prompt = prompt or obtener_prompt()
    modelo_con_herramientas = (modelo or crear_modelo()).bind_tools(HERRAMIENTAS)

    # ChatPromptTemplate (sistema + historial) con `langfuse_prompt` en su metadata: el
    # CallbackHandler de Langfuse enlaza la generation siguiente con la versión del prompt.
    cadena_chatbot = (prompt.plantilla_chat() | modelo_con_herramientas).with_config(
        run_name="generar-respuesta"  # nombre estable y en forma verbal en vez de "RunnableSequence"
    )

    # --- Nodos ---------------------------------------------------------------

    def chatbot(estado: EstadoV4) -> dict:
        respuesta = cadena_chatbot.invoke({"messages": estado["messages"]})
        return {"messages": [respuesta]}

    def herramientas(estado: EstadoV4) -> dict:
        """Nodo de herramientas escrito a mano: ejecuta cada tool_call del último AIMessage."""
        resultados = []
        for llamada in _ultimo_ai(estado).tool_calls:
            herramienta = HERRAMIENTAS_POR_NOMBRE.get(llamada["name"])
            if herramienta is None:
                contenido, estado_msg = json.dumps(
                    {"error": f"La herramienta {llamada['name']!r} no existe."}, ensure_ascii=False
                ), "error"
            else:
                try:
                    contenido, estado_msg = herramienta.invoke(llamada["args"]), "success"
                except Exception as e:  # argumentos inválidos, error de E/S...
                    contenido, estado_msg = json.dumps({"error": str(e)}, ensure_ascii=False), "error"
            # Cada ToolMessage debe llevar el id de su tool_call: así el modelo sabe a qué responde.
            resultados.append(ToolMessage(
                content=contenido, tool_call_id=llamada["id"], name=llamada["name"], status=estado_msg,
            ))
        return {"messages": resultados, "pasos": estado.get("pasos", 0) + 1}

    def limite(estado: EstadoV4) -> dict:
        """Corta el bucle. Responde a las tool_calls pendientes (OpenAI rechaza un AIMessage
        con tool_calls sin sus ToolMessage) y termina con un mensaje amable."""
        pendientes = [
            ToolMessage(
                content=json.dumps({"error": "No ejecutada: límite de pasos alcanzado."}, ensure_ascii=False),
                tool_call_id=llamada["id"], name=llamada["name"], status="error",
            )
            for llamada in _ultimo_ai(estado).tool_calls
        ]
        return {"messages": [*pendientes, AIMessage(MENSAJE_LIMITE)]}

    # --- Arista condicional --------------------------------------------------

    def ruta_tras_chatbot(estado: EstadoV4) -> Literal["usar_herramientas", "limite_alcanzado", "fin"]:
        ultimo = _ultimo_ai(estado)
        if not ultimo or not ultimo.tool_calls:
            return "fin"
        if estado.get("pasos", 0) >= MAX_PASOS:
            return "limite_alcanzado"
        return "usar_herramientas"

    builder = StateGraph(EstadoV4)
    builder.add_node("chatbot", chatbot)
    builder.add_node("herramientas", herramientas)
    builder.add_node("limite", limite)
    builder.add_edge(START, "chatbot")
    builder.add_conditional_edges(
        "chatbot",
        ruta_tras_chatbot,
        {"usar_herramientas": "herramientas", "limite_alcanzado": "limite", "fin": END},
    )
    builder.add_edge("herramientas", "chatbot")  # después de cada herramienta, vuelta al chatbot
    builder.add_edge("limite", END)
    return builder.compile(checkpointer=checkpointer or InMemorySaver())


def _describir(m: BaseMessage) -> str:
    if isinstance(m, AIMessage) and m.tool_calls:
        llamadas = ", ".join(f"{tc['name']}({json.dumps(tc['args'], ensure_ascii=False)})" for tc in m.tool_calls)
        return f"ai (tool_calls): {llamadas}"
    if isinstance(m, ToolMessage):
        return f"tool [{m.name}]: {m.text}"
    return f"{m.type}: {m.text}"


def formatear_estado(grafo, thread_id: str) -> str:
    """Resumen legible de get_state: mensajes (con tool_calls y ToolMessage), pasos y checkpoint."""
    snapshot = grafo.get_state(config_hilo(thread_id))
    mensajes = snapshot.values.get("messages", [])
    lineas = [
        f"get_state(thread_id={thread_id!r})",
        f"  mensajes guardados: {len(mensajes)}",
        f"  pasos (último turno): {snapshot.values.get('pasos')}",
        f"  next: {snapshot.next}  (vacío = el grafo terminó el turno)",
        f"  checkpoint_id: {snapshot.config['configurable'].get('checkpoint_id')}",
    ]
    lineas += [f"  [{i}] {_describir(m)}" for i, m in enumerate(mensajes, 1)]
    return "\n".join(lineas)


def enviar(
    grafo,
    thread_id: str,
    texto: str,
    usuario: str | None = None,
    tags: list[str] | None = None,
    metadata: dict | None = None,
) -> dict:
    """Un turno de conversación. Devuelve la respuesta, las herramientas llamadas
    en este turno (en orden) y cuántas rondas de herramientas hubo.

    Cada turno es una traza `responder-mensaje` (input = texto del usuario, output = respuesta)
    con session_id = thread_id, user_id = usuario y `tags`; la conversación es la sesión."""
    config = config_langchain(thread_id, usuario=usuario, tags=tags, metadata=metadata)
    previos = len(grafo.get_state(config).values.get("messages", []))
    with traza_turno(thread_id, texto, usuario=usuario, tags=tags, metadata=metadata) as raiz:
        # pasos=0 reinicia el contador en cada turno (sin reducer, el valor nuevo sustituye al guardado).
        estado = grafo.invoke({"messages": [HumanMessage(texto)], "pasos": 0}, config)
        nuevos: list[BaseMessage] = estado["messages"][previos:]
        resultado = {
            "respuesta": estado["messages"][-1].text,
            "herramientas": [
                {"nombre": tc["name"], "argumentos": tc["args"]}
                for m in nuevos if isinstance(m, AIMessage) for tc in m.tool_calls
            ],
            "pasos": estado["pasos"],
        }
        if raiz is not None:
            raiz.update(output=resultado["respuesta"], metadata={
                "herramientas": [h["nombre"] for h in resultado["herramientas"]],
                "pasos": resultado["pasos"],
                "limite_alcanzado": resultado["respuesta"] == MENSAJE_LIMITE,
            })
    return resultado


def main() -> None:
    prompt = obtener_prompt()
    grafo = construir_grafo(prompt=prompt)
    print(f"Diagrama guardado en {guardar_diagrama(grafo, 'v4')}")
    hilo, usuario = "hilo-1", usuario_por_defecto()
    print(f"Asistente EventHub (v4, con herramientas, {prompt.etiqueta}). "
          "Comandos: /hilo <id>, /usuario <id>, /historial, salir.")
    try:
        _bucle(grafo, prompt, hilo, usuario)
    finally:
        flush()


def _bucle(grafo, prompt: PromptSistema, hilo: str, usuario: str) -> None:
    while True:
        try:
            texto = input(f"\n[{hilo}] Tú: ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if texto.lower() in {"salir", "exit", "quit"}:
            break
        if texto.startswith("/hilo"):
            hilo = texto.removeprefix("/hilo").strip() or hilo
            print(f"Ahora en el hilo {hilo!r}")
        elif texto.startswith("/usuario"):
            usuario = texto.removeprefix("/usuario").strip() or usuario
            print(f"Usuario de las trazas: {usuario!r}")
        elif texto == "/historial":
            print(formatear_estado(grafo, hilo))
        elif texto:
            r = enviar(grafo, hilo, texto, usuario=usuario, tags=["cli"],
                       metadata={"prompt_version": prompt.etiqueta})
            for h in r["herramientas"]:
                print(f"  ↳ {h['nombre']}({json.dumps(h['argumentos'], ensure_ascii=False)})")
            print(f"Asistente: {r['respuesta']}")


if __name__ == "__main__":
    main()
