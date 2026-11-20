"""Grafo v4 con un modelo falso guionizado: encadenado de herramientas,
límite de pasos, reinicio del contador, errores y diagrama."""

import json

from langchain_core.messages import AIMessage, ToolMessage

from eventhub_v4.grafos import v4_herramientas as v4
from tests.conftest import ModeloGuionizado, llamada

PREGUNTA_ENUNCIADO = ("¿Mi pedido EH-1003 es para un concierto en Madrid? Si es así, "
                      "dime otros conciertos en Madrid ese mes. Mi email es ana.gomez@example.com")


def _sin_tool_calls_huerfanas(mensajes) -> bool:
    respondidas = {m.tool_call_id for m in mensajes if isinstance(m, ToolMessage)}
    pedidas = {tc["id"] for m in mensajes if isinstance(m, AIMessage) for tc in m.tool_calls}
    return pedidas <= respondidas


def test_encadena_dos_herramientas_en_una_respuesta(datos_temporales):
    grafo = v4.construir_grafo(ModeloGuionizado(messages=iter([
        llamada("consultar_pedido", {"id_pedido": "EH-1003", "email": "ana.gomez@example.com"}, "c1"),
        llamada("buscar_eventos", {"ciudad": "Madrid", "categoria": "concierto", "mes": "2026-12"}, "c2"),
        AIMessage("Sí, es Rock en la Gran Vía. Otros conciertos: Coros de Navidad y Sinfonía de Invierno."),
    ])))
    r = v4.enviar(grafo, "h1", PREGUNTA_ENUNCIADO)
    assert [h["nombre"] for h in r["herramientas"]] == ["consultar_pedido", "buscar_eventos"]
    assert r["pasos"] == 2 and r["respuesta"].startswith("Sí, es Rock")

    mensajes = grafo.get_state(v4.config_hilo("h1")).values["messages"]
    assert [m.type for m in mensajes] == ["human", "ai", "tool", "ai", "tool", "ai"]
    pedido = json.loads(mensajes[2].content)
    assert pedido["encontrado"] and pedido["id_evento"] == "EV013"
    eventos = [e["id"] for e in json.loads(mensajes[4].content)]
    assert eventos == ["EV013", "EV014", "EV015"]  # EV016 (enero) queda fuera
    assert "pasos (último turno): 2" in v4.formatear_estado(grafo, "h1")


def test_sin_herramientas_termina_directamente(datos_temporales):
    grafo = v4.construir_grafo(ModeloGuionizado(messages=iter([AIMessage("Necesito tu email.")])))
    r = v4.enviar(grafo, "h2", "¿Cómo va mi pedido EH-1003?")
    assert r == {"respuesta": "Necesito tu email.", "herramientas": [], "pasos": 0}


def test_limite_de_pasos_termina_con_mensaje_amable(datos_temporales):
    bucle = [llamada("buscar_eventos", {"ciudad": "Madrid"}, f"c{i}") for i in range(v4.MAX_PASOS + 1)]
    grafo = v4.construir_grafo(ModeloGuionizado(messages=iter(bucle)))
    r = v4.enviar(grafo, "h3", "busca sin parar")
    assert r["respuesta"] == v4.MENSAJE_LIMITE
    assert r["pasos"] == v4.MAX_PASOS
    mensajes = grafo.get_state(v4.config_hilo("h3")).values["messages"]
    assert _sin_tool_calls_huerfanas(mensajes)
    assert "límite" in mensajes[-2].content  # la tool_call que no se ejecutó tiene su respuesta


def test_contador_se_reinicia_en_cada_turno(datos_temporales):
    grafo = v4.construir_grafo(ModeloGuionizado(messages=iter([
        llamada("buscar_eventos", {}, "c1"), AIMessage("uno"),
        llamada("buscar_eventos", {}, "c2"), AIMessage("dos"),
    ])))
    assert v4.enviar(grafo, "h4", "primero")["pasos"] == 1
    assert v4.enviar(grafo, "h4", "segundo")["pasos"] == 1


def test_hilos_aislados(datos_temporales):
    grafo = v4.construir_grafo(ModeloGuionizado(messages=iter([AIMessage("a"), AIMessage("b")])))
    v4.enviar(grafo, "uno", "hola")
    v4.enviar(grafo, "dos", "hola")
    assert len(grafo.get_state(v4.config_hilo("uno")).values["messages"]) == 2
    assert grafo.get_state(v4.config_hilo("nadie")).values == {}


def test_herramienta_desconocida_y_argumentos_invalidos(datos_temporales):
    ai = AIMessage(content="", tool_calls=[
        {"id": "a", "name": "reservar_entradas", "args": {"id_evento": "EV001", "cantidad": 1}},
        {"id": "b", "name": "consultar_pedido", "args": {"id_pedido": "EH-1001"}},  # falta email
    ])
    grafo = v4.construir_grafo(ModeloGuionizado(messages=iter([ai, AIMessage("ok")])))
    v4.enviar(grafo, "h5", "x")
    tools = [m for m in grafo.get_state(v4.config_hilo("h5")).values["messages"] if isinstance(m, ToolMessage)]
    assert [t.status for t in tools] == ["error", "error"]
    assert "no existe" in tools[0].content


def test_diagrama(tmp_path, monkeypatch):
    monkeypatch.setattr("eventhub_v4.grafos.comun.CARPETA_DIAGRAMAS", tmp_path)
    from eventhub_v4.grafos.comun import guardar_diagrama
    grafo = v4.construir_grafo(ModeloGuionizado(messages=iter([])))
    mermaid = guardar_diagrama(grafo, "v4").read_text(encoding="utf-8")
    assert "herramientas --> chatbot" in mermaid
    assert "chatbot -. &nbsp;usar_herramientas&nbsp; .-> herramientas" in mermaid
    assert "chatbot -. &nbsp;limite_alcanzado&nbsp; .-> limite" in mermaid
    assert "chatbot -. &nbsp;fin&nbsp; .-> __end__" in mermaid
