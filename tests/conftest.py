import shutil
from pathlib import Path

import pytest
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage

DATA_ORIGINAL = Path(__file__).resolve().parent.parent / "data"


@pytest.fixture(autouse=True)
def sin_observabilidad(monkeypatch):
    """Los tests nunca envían trazas ni descargan prompts, aunque .env tenga claves."""
    monkeypatch.setenv("EVENTHUB_LANGFUSE_TRACING", "0")
    monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
    monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)
    monkeypatch.setenv("LANGSMITH_TRACING", "false")
    monkeypatch.delenv("LANGCHAIN_TRACING_V2", raising=False)


@pytest.fixture
def datos_temporales(tmp_path, monkeypatch):
    """Copia data/ a una carpeta temporal y apunta EVENTHUB_DATA_DIR a ella,
    para que los tests no dependan de los datos reales."""
    destino = tmp_path / "data"
    shutil.copytree(DATA_ORIGINAL, destino)
    monkeypatch.setenv("EVENTHUB_DATA_DIR", str(destino))
    return destino


class ModeloGuionizado(GenericFakeChatModel):
    """Modelo falso que devuelve las respuestas de una lista (sin llamar a OpenAI)."""

    def bind_tools(self, tools, **kwargs):
        return self


def llamada(nombre, args, id_):
    """AIMessage que pide una herramienta."""
    return AIMessage(content="", tool_calls=[{"id": id_, "name": nombre, "args": args}])
