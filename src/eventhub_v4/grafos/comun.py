"""Piezas compartidas del grafo: prompt de sistema y guardado de diagramas."""

from pathlib import Path

from eventhub_v4.config.settings import diagramas_dir
from eventhub_v4.llm.prompts import REGLAS_POLITICAS, cargar_politicas

CARPETA_DIAGRAMAS = diagramas_dir()

_REGLAS_HERRAMIENTAS = """\
Reglas para usar herramientas:
- Para cualquier dato de eventos (qué hay, fechas, precios, disponibilidad) usa SIEMPRE
  buscar_eventos; no respondas de memoria. Pasa siempre los filtros que conozcas
  (ciudad, categoría y mes) en vez de buscar sin filtros.
- Si la pregunta habla de un mes («en diciembre», «ese mes», «el mismo mes que…»),
  usa SIEMPRE el filtro mes con formato AAAA-MM (p. ej. "2026-12"), deduciéndolo de
  la fecha que ya conozcas si hace falta.
- Para el estado de un pedido usa SIEMPRE consultar_pedido. Necesitas el id del pedido
  (p. ej. EH-1001) y el email de compra; si falta alguno, pídelo antes de llamar.
  Si la herramienta no lo verifica, no des pistas sobre si el pedido existe.
- Puedes encadenar herramientas: por ejemplo, consultar un pedido para saber su evento
  y después buscar otros eventos parecidos.
- Si no tienes una herramienta para algo, dilo y sugiere contactar con soporte."""


def prompt_sistema(con_herramientas: bool = False) -> str:
    """Prompt de sistema de EventHub con las políticas (y, en la v4, las reglas de herramientas)."""
    partes = [
        "Eres el asistente de atención al cliente de EventHub, una plataforma de venta de entradas.",
        "Usa el contexto de la conversación para entender referencias como «esos» o «el más barato».",
        REGLAS_POLITICAS,
    ]
    if con_herramientas:
        partes.append(_REGLAS_HERRAMIENTAS)
    else:
        partes.append(
            "No tienes acceso al catálogo de eventos ni a los pedidos: si te preguntan por ellos, "
            "dilo y sugiere contactar con soporte."
        )
    partes.append(f"=== POLÍTICAS DE EVENTHUB ===\n{cargar_politicas()}\n=== FIN DE LAS POLÍTICAS ===")
    return "\n\n".join(partes)


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
