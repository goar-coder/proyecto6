"""Lectura de las políticas que se inyectan en el prompt de sistema.

El texto del prompt ya no vive en el código: está en Langfuse Prompt Management
(copias locales en prompts/). Ver eventhub_v4/llm/prompt_gestionado.py."""

from eventhub_v4.config.settings import data_dir


def cargar_politicas() -> str:
    """Lee el contenido de policies.md."""
    return (data_dir() / "policies.md").read_text(encoding="utf-8")
