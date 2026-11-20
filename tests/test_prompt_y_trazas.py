"""Prompt gestionado (fallback local), plantilla LangChain y config de las trazas, sin red."""

from langchain_core.messages import HumanMessage

from eventhub_v4.llm import prompt_gestionado as pg
from eventhub_v4.observabilidad import config_langchain, enmascarar_emails, traza_turno


def test_prompt_local_compila_las_tres_variables(datos_temporales, monkeypatch):
    monkeypatch.setenv("EVENTHUB_MARCA", "MiMarca")
    monkeypatch.setenv("EVENTHUB_TONO", "muy formal")
    for version in (1, 2):
        p = pg.obtener_prompt(version=version)
        assert p.version is None and p.etiqueta == "prompt-local"  # sin Langfuse → copia local
        assert "{" not in p.texto
        assert "MiMarca" in p.texto and "muy formal" in p.texto
        assert "14 días antes" in p.texto  # las políticas de data/policies.md se inyectan


def test_plantilla_chat_antepone_el_sistema_y_lleva_metadata(datos_temporales):
    p = pg.obtener_prompt()
    mensajes = p.plantilla_chat().invoke({"messages": [HumanMessage("hola")]}).to_messages()
    assert [m.type for m in mensajes] == ["system", "human"]
    assert mensajes[0].content == p.texto
    assert p.plantilla_chat().config["metadata"]["prompt_version"] == "prompt-local"


def test_a_langchain_escapa_llaves_sueltas():
    assert pg._a_langchain('{{marca}} usa {"json": 1}') == '{marca} usa {{"json": 1}}'


def test_v2_es_distinta_de_v1():
    assert pg.texto_local(1) != pg.texto_local(2)


def test_config_langchain_lleva_hilo_usuario_y_tags():
    c = config_langchain("hilo-x", usuario="ana", tags=["demo"])
    assert c["configurable"]["thread_id"] == "hilo-x"
    assert c["metadata"]["thread_id"] == "hilo-x" and c["metadata"]["user_id"] == "ana"
    assert c["tags"] == ["demo", "eventhub-v4"]
    assert "callbacks" not in c  # Langfuse desactivado en los tests


def test_traza_turno_sin_langfuse_no_hace_nada():
    with traza_turno("h", "hola") as raiz:
        assert raiz is None


def test_enmascarar_emails():
    texto = '{"email": "ana.gomez@example.com"} y Mi email es carlos.ruiz@example.com'
    assert enmascarar_emails(texto) == '{"email": "a***@example.com"} y Mi email es c***@example.com'
