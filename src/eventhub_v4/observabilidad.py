"""Trazas del grafo con Langfuse, siguiendo https://langfuse.com/docs/observability/best-practices

Estructura de cada traza (un turno de conversación = una traza, una conversación = una sesión):

    responder-mensaje  (agent)     input = mensaje del usuario, output = respuesta del asistente
    └── LangGraph                  ← CallbackHandler de LangChain: nodos chatbot / herramientas / limite,
        ├── chatbot                  cada llamada al modelo como `generation` (modelo, tokens, coste,
        │   └── ChatOpenAI           versión del prompt enlazada) y cada herramienta como `tool`
        ├── herramientas
        │   └── consultar_pedido
        └── ...

- `session_id` = thread_id, `user_id`, `tags` y metadata se propagan con `propagate_attributes`
  a todas las observaciones, así el coste por sesión y por usuario incluye las generations.
- El entorno sale de LANGFUSE_TRACING_ENVIRONMENT (development por defecto; los experimentos
  usan su propio entorno) para no mezclar pruebas con producción.
- Los emails se enmascaran antes de exportar (`mask_otel_spans`): «a***@example.com».

LangSmith no necesita nada aquí: LangChain lo activa solo con las variables de entorno
LANGSMITH_*. Los `tags` y la `metadata` de la config de LangChain los recogen las dos plataformas.
"""

import os
import re
from contextlib import contextmanager, nullcontext
from functools import lru_cache
from typing import Iterator, Optional

from eventhub_v4.config import settings

NOMBRE_TRAZA = "responder-mensaje"  # estable: evaluadores, dashboards y filtros lo referencian
TAGS_BASE = ["eventhub-v4"]

_EMAIL = re.compile(r"\b([A-Za-z0-9])[A-Za-z0-9._%+-]*@([A-Za-z0-9.-]+\.[A-Za-z]{2,})\b")


def enmascarar_emails(texto: str) -> str:
    """'ana.gomez@example.com' → 'a***@example.com' (se conserva el dominio para depurar)."""
    return _EMAIL.sub(r"\1***@\2", texto)


def _mask_otel_spans(*, params):
    """Hook de exportación de Langfuse: enmascara emails en todos los atributos de texto."""
    from langfuse.types import MaskOtelSpansResult, OtelSpanPatch

    parches = {}
    for identificador, span in params.spans.items():
        cambios = {}
        for clave, valor in span.attributes.items():
            if isinstance(valor, str):
                enmascarado = enmascarar_emails(valor)
                if enmascarado != valor:
                    cambios[clave] = enmascarado
        if cambios:
            parches[identificador] = OtelSpanPatch(set_attributes=cambios)
    return MaskOtelSpansResult(span_patches=parches)


@lru_cache(maxsize=1)
def cliente_langfuse():
    """Cliente único de Langfuse (lo reutilizan get_client() y el CallbackHandler).

    Lee LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY / LANGFUSE_BASE_URL y
    LANGFUSE_TRACING_ENVIRONMENT del entorno (ya cargado desde .env por settings)."""
    from langfuse import Langfuse

    # Sin LANGFUSE_TRACING_ENVIRONMENT las trazas irían al entorno "default"; usamos
    # "development" para que las pruebas locales nunca se mezclen con producción.
    os.environ.setdefault("LANGFUSE_TRACING_ENVIRONMENT", "development")
    return Langfuse(mask_otel_spans=_mask_otel_spans if settings.langfuse_mask_pii() else None)


def handler_langfuse():
    """CallbackHandler de Langfuse, o None si el trazado está desactivado o no hay claves."""
    if not settings.langfuse_tracing():
        return None
    cliente_langfuse()  # inicializa el cliente con la máscara antes que el handler
    from langfuse.langchain import CallbackHandler

    # public_key explícita: si hubiera varios clientes en el proceso, un handler sin ella
    # dejaría de trazar en silencio para evitar mezclar proyectos.
    return CallbackHandler(public_key=os.environ["LANGFUSE_PUBLIC_KEY"])


def config_langchain(
    thread_id: str,
    usuario: str | None = None,
    tags: list[str] | None = None,
    metadata: dict | None = None,
) -> dict:
    """Config de invocación del grafo: thread_id para el checkpointer, callbacks de Langfuse,
    y tags/metadata que también ve LangSmith (que agrupa en hilos por `thread_id`)."""
    config = {
        "configurable": {"thread_id": thread_id},
        "run_name": "grafo-eventhub-v4",
        "tags": etiquetas(tags),
        "metadata": {"thread_id": thread_id, "user_id": usuario or settings.usuario_por_defecto(),
                     **(metadata or {})},
    }
    handler = handler_langfuse()
    if handler is not None:
        config["callbacks"] = [handler]
    return config


def etiquetas(tags: list[str] | None) -> list[str]:
    return sorted(set(TAGS_BASE + (tags or [])))


@contextmanager
def traza_turno(
    thread_id: str,
    texto: str,
    usuario: str | None = None,
    tags: list[str] | None = None,
    metadata: dict | None = None,
) -> Iterator[Optional[object]]:
    """Observación raíz de un turno. Devuelve la observación (para `update(output=...)`)
    o None si Langfuse está desactivado."""
    if not settings.langfuse_tracing():
        with nullcontext():
            yield None
        return

    from langfuse import propagate_attributes

    lf = cliente_langfuse()
    # propagate_attributes envuelve la creación de la raíz: así todas las observaciones
    # (incluidas las generations con coste) llevan session_id, user_id, tags y metadata.
    with propagate_attributes(
        trace_name=NOMBRE_TRAZA,
        session_id=thread_id,
        user_id=usuario or settings.usuario_por_defecto(),
        tags=etiquetas(tags),
        metadata={k: str(v) for k, v in (metadata or {}).items()},
    ):
        with lf.start_as_current_observation(as_type="agent", name=NOMBRE_TRAZA, input=texto) as raiz:
            try:
                yield raiz
            except Exception as e:
                # Un turno que falla (p. ej. error de la API del modelo) queda marcado como ERROR
                # con el motivo, en vez de parecer una traza normal con output vacío.
                raiz.update(level="ERROR", status_message=f"{type(e).__name__}: {e}"[:500])
                raise


def flush() -> None:
    """Envía las trazas pendientes (llamar antes de que termine un proceso corto)."""
    if settings.langfuse_tracing():
        cliente_langfuse().flush()
