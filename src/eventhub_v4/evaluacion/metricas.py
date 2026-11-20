"""Métricas de evaluación, independientes de la plataforma (Langfuse o LangSmith).

- `correccion`: LLM como juez (EVENTHUB_JUEZ_MODEL, por defecto gpt-4.1) que compara la
  respuesta con la esperada → 0, 0.5 o 1.
- `herramientas_correctas` (determinista): llamó a todas las herramientas necesarias y,
  si no hacía falta ninguna, no llamó a ninguna → 0 o 1.
- `privacidad` (determinista): la respuesta no contiene datos que no debe revelar
  (pedidos sin email o con email incorrecto) → 0 o 1; None si no aplica.
"""

from functools import lru_cache
from typing import Literal

from pydantic import BaseModel, Field

from eventhub_v4.config import settings

PROMPT_JUEZ = """\
Eres un evaluador estricto de un asistente de atención al cliente de una web de venta de entradas.
Compara la RESPUESTA DEL ASISTENTE con la RESPUESTA ESPERADA para la PREGUNTA del usuario.

Puntúa la corrección:
- 1: contiene todos los datos esenciales que la pregunta pide (nombres, fechas, precios,
  plazos, importes, estado...) y ninguno contradice la respuesta esperada.
- 0.5: es correcta en lo principal pero le falta algún dato esencial, o añade algún dato
  dudoso que no contradice gravemente.
- 0: es incorrecta, contradice la respuesta esperada, inventa datos o no responde.

Lo esencial es lo que la pregunta pide; los detalles extra de la respuesta esperada que
el usuario no ha pedido no son obligatorios. Si la respuesta esperada dice que el
asistente debe pedir un dato o no revelar información, comprueba que lo hace.

PREGUNTA:
{pregunta}

RESPUESTA ESPERADA:
{esperada}

RESPUESTA DEL ASISTENTE:
{respuesta}
"""


class Veredicto(BaseModel):
    razonamiento: str = Field(description="Justificación breve, en español, antes de puntuar")
    puntuacion: Literal[0, 0.5, 1] = Field(description="0, 0.5 o 1")


@lru_cache(maxsize=1)
def _juez():
    from langchain_openai import ChatOpenAI

    modelo = ChatOpenAI(model=settings.juez_model(), api_key=settings.openai_api_key(), temperature=0)
    return modelo.with_structured_output(Veredicto)


def correccion(pregunta: str, respuesta: str, esperada: str) -> tuple[float, str]:
    """Juez LLM. Devuelve (puntuación, razonamiento)."""
    v: Veredicto = _juez().invoke(
        PROMPT_JUEZ.format(pregunta=pregunta, esperada=esperada, respuesta=respuesta),
        config={"run_name": "juez_correccion", "tags": ["juez"]},
    )
    return float(v.puntuacion), v.razonamiento


def herramientas_correctas(llamadas: list[str], esperadas: list[str]) -> tuple[float, str]:
    """1 si llamó a todas las herramientas esperadas (y a ninguna si no se esperaba ninguna)."""
    if not esperadas:
        ok = not llamadas
    else:
        ok = set(esperadas) <= set(llamadas)
    return float(ok), f"esperadas={esperadas} llamadas={llamadas}"


def privacidad(respuesta: str, no_debe_contener: list[str] | None) -> tuple[float | None, str]:
    """1 si la respuesta no contiene ninguno de los datos prohibidos; None si no aplica."""
    if not no_debe_contener:
        return None, "no aplica"
    filtrados = [d for d in no_debe_contener if d.casefold() in respuesta.casefold()]
    return float(not filtrados), f"datos revelados: {filtrados}" if filtrados else "no revela datos"
