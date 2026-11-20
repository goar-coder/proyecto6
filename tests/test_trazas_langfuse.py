"""Forma de las trazas de Langfuse, sin red: se capturan en memoria los spans que el SDK
exportaría y se comprueban las buenas prácticas (nombre y I/O de la raíz, atributos
propagados, tipos de observación, enlace con el prompt y emails enmascarados)."""

import json
import uuid

import pytest
from langchain_core.messages import AIMessage
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

import eventhub_v4.observabilidad as obs
from eventhub_v4.grafos import v4_herramientas as v4
from eventhub_v4.llm import prompt_gestionado as pg
from tests.conftest import ModeloGuionizado, llamada


@pytest.fixture
def spans(monkeypatch, datos_temporales):
    from langfuse import Langfuse
    from langfuse.api import Prompt_Text
    from langfuse.model import TextPromptClient

    # Clave distinta por test: el SDK reutiliza el procesador de spans por clave pública.
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", f"pk-lf-test-{uuid.uuid4().hex[:8]}")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-lf-test")
    monkeypatch.setenv("LANGFUSE_BASE_URL", "http://127.0.0.1:9")
    monkeypatch.setenv("EVENTHUB_LANGFUSE_TRACING", "1")
    exportador = InMemorySpanExporter()
    cliente = Langfuse(span_exporter=exportador, mask_otel_spans=obs._mask_otel_spans)
    monkeypatch.setattr(obs, "cliente_langfuse", lambda: cliente)

    lf_prompt = TextPromptClient(Prompt_Text(
        name="eventhub-sistema", version=2, prompt=pg.texto_local(2), labels=[], tags=[], config={}, type="text"))
    prompt = pg.PromptSistema(lf_prompt.get_langchain_prompt(), pg._variables(), version=2, cliente_langfuse=lf_prompt)
    grafo = v4.construir_grafo(ModeloGuionizado(messages=iter([
        llamada("consultar_pedido", {"id_pedido": "EH-1003", "email": "ana.gomez@example.com"}, "c1"),
        AIMessage("Tu pedido EH-1003 está pagado."),
    ])), prompt=prompt)
    v4.enviar(grafo, "hilo-t", "Estado de EH-1003, email ana.gomez@example.com", usuario="ana", tags=["test"])
    cliente.flush()
    return exportador.get_finished_spans()


def _tipo(s):
    return s.attributes.get("langfuse.observation.type")


def test_raiz_con_nombre_estable_e_io_legible(spans):
    raices = [s for s in spans if s.parent is None]
    assert len(raices) == 1
    raiz = raices[0]
    assert raiz.name == obs.NOMBRE_TRAZA and _tipo(raiz) == "agent"
    assert raiz.attributes["langfuse.observation.input"] == "Estado de EH-1003, email a***@example.com"
    assert raiz.attributes["langfuse.observation.output"] == "Tu pedido EH-1003 está pagado."
    assert raiz.attributes["langfuse.trace.name"] == obs.NOMBRE_TRAZA


def test_session_user_y_tags_en_todas_las_observaciones(spans):
    for s in spans:
        assert s.attributes.get("session.id") == "hilo-t", s.name
        assert s.attributes.get("user.id") == "ana", s.name
    assert set(spans[0].attributes["langfuse.trace.tags"]) == {"eventhub-v4", "test"}


def test_generations_enlazadas_al_prompt_y_herramientas_como_tool(spans):
    generaciones = [s for s in spans if _tipo(s) == "generation"]
    assert len(generaciones) == 2
    for g in generaciones:
        assert g.attributes["langfuse.observation.prompt.name"] == "eventhub-sistema"
        assert g.attributes["langfuse.observation.prompt.version"] == 2
    assert [s.name for s in spans if _tipo(s) == "tool"] == ["consultar_pedido"]
    assert not [s for s in spans if s.name == "RunnableSequence"]


def test_ningun_email_sin_enmascarar(spans):
    todo = json.dumps([dict(s.attributes) for s in spans], ensure_ascii=False, default=str)
    assert "ana.gomez@example.com" not in todo and "a***@example.com" in todo
