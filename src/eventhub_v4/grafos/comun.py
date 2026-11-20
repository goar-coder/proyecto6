"""Piezas compartidas del grafo: guardado de diagramas.

El prompt de sistema está en Langfuse (ver eventhub_v4/llm/prompt_gestionado.py)."""

from pathlib import Path

from eventhub_v4.config.settings import diagramas_dir

CARPETA_DIAGRAMAS = diagramas_dir()


def guardar_diagrama_png(grafo, nombre: str) -> Path:
    """Guarda el diagrama como imagen en diagramas/<nombre>.png.

    Usa draw_mermaid_png(), que por defecto renderiza el texto Mermaid con el
    servicio en línea mermaid.ink: necesita conexión a internet."""
    CARPETA_DIAGRAMAS.mkdir(exist_ok=True)
    ruta = CARPETA_DIAGRAMAS / f"{nombre}.png"
    ruta.write_bytes(grafo.get_graph().draw_mermaid_png())
    return ruta


def guardar_diagrama(grafo, nombre: str) -> Path:
    """Guarda el diagrama Mermaid del grafo compilado en diagramas/<nombre>.mmd."""
    CARPETA_DIAGRAMAS.mkdir(exist_ok=True)
    ruta = CARPETA_DIAGRAMAS / f"{nombre}.mmd"
    ruta.write_text(grafo.get_graph().draw_mermaid(), encoding="utf-8")
    return ruta
