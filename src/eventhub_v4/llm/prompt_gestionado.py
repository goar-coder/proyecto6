"""Prompt de sistema gestionado en Langfuse Prompt Management.

El texto ya no está en el código: se descarga de Langfuse (por defecto la versión
con la etiqueta `production`). Si Langfuse no está configurado o no responde, se usa
la copia local `prompts/eventhub_sistema_v{N}.txt` (así funcionan los tests sin red).

Variables del prompt: {{marca}}, {{tono}} y {{politicas}} (las políticas siguen en
data/policies.md y se inyectan al compilar, así cambiarlas no exige otra versión).

Para enlazar cada generation con su versión, el grafo construye un ChatPromptTemplate
con `metadata={"langfuse_prompt": ...}` (https://langfuse.com/docs/prompt-management/features/link-to-traces).
"""

import re
from dataclasses import dataclass, field
from typing import Any

from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from eventhub_v4.config import settings
from eventhub_v4.llm.prompts import cargar_politicas

_VARIABLE = re.compile(r"({{\s*\w+\s*}})")


def texto_local(version: int = 1) -> str:
    """Texto de una versión del prompt guardada en prompts/ (fuente para subirla a Langfuse)."""
    return (settings.prompts_dir() / f"eventhub_sistema_v{version}.txt").read_text(encoding="utf-8")


def _a_langchain(texto: str) -> str:
    """{{var}} (Langfuse) → {var} (LangChain), escapando cualquier otra llave."""
    partes = _VARIABLE.split(texto)
    return "".join(
        "{" + p.strip("{} ") + "}" if _VARIABLE.fullmatch(p) else p.replace("{", "{{").replace("}", "}}")
        for p in partes
    )


@dataclass
class PromptSistema:
    """Prompt listo para el grafo.

    `plantilla` está en formato LangChain ({var}); `variables` son los valores de marca,
    tono y políticas; `cliente_langfuse` es el TextPromptClient (None si es copia local)."""

    plantilla: str
    variables: dict = field(default_factory=dict)
    version: int | None = None  # None = copia local (fallback)
    cliente_langfuse: Any = None

    @property
    def etiqueta(self) -> str:
        return f"prompt-v{self.version}" if self.version else "prompt-local"

    @property
    def texto(self) -> str:
        """Prompt de sistema compilado."""
        return self.plantilla.format(**self.variables)

    def plantilla_chat(self) -> ChatPromptTemplate:
        """Mensaje de sistema + historial. Lleva `langfuse_prompt` en la metadata (solo aquí,
        no en la llamada al modelo) para que Langfuse enlace las generations con esta versión."""
        metadata = {"prompt_version": self.etiqueta}
        if self.cliente_langfuse is not None:
            metadata["langfuse_prompt"] = self.cliente_langfuse
        plantilla = ChatPromptTemplate(
            [("system", self.plantilla), MessagesPlaceholder("messages")],
        ).partial(**self.variables)
        return plantilla.with_config(run_name="preparar-prompt", metadata=metadata)


def _variables(**extra) -> dict:
    valores = {"marca": settings.marca(), "tono": settings.tono(), "politicas": cargar_politicas()}
    valores.update(extra)
    return valores


def obtener_prompt(version: int | None = None, label: str | None = None, **variables) -> PromptSistema:
    """Descarga el prompt de Langfuse (por `version` o por `label`, por defecto `production`).

    Sin claves de Langfuse, o si falla la descarga, devuelve la copia local."""
    valores = _variables(**variables)
    local = texto_local(version or 1)
    if not settings.langfuse_activo():
        return PromptSistema(_a_langchain(local), valores)

    from eventhub_v4.observabilidad import cliente_langfuse

    kwargs = {"version": version} if version else {"label": label or settings.prompt_label()}
    prompt = cliente_langfuse().get_prompt(settings.prompt_nombre(), type="text", fallback=local, **kwargs)
    if prompt.is_fallback:
        return PromptSistema(_a_langchain(local), valores)
    return PromptSistema(prompt.get_langchain_prompt(), valores, version=prompt.version, cliente_langfuse=prompt)
