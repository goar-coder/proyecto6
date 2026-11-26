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
Decide si la RESPUESTA DEL ASISTENTE responde correctamente a la PREGUNTA del usuario, usando la
RESPUESTA DE REFERENCIA como fuente de verdad.

Paso 1. Enumera los datos que la PREGUNTA pide explícitamente (p. ej. «qué conciertos hay» pide
nombre y fecha de cada uno; «cuál es el más barato» pide cuál es y su precio; «quedan entradas»
pide si hay disponibilidad; «estado del pedido» pide el estado). Si la referencia dice que el
asistente debe pedir un dato o no revelar información, eso es lo que se pide.

Paso 2. Compara solo esos datos con la referencia.

Puntuación:
- 1: da correctamente todos los datos pedidos y nada de lo que dice contradice la referencia.
- 0.5: da correctamente parte de los datos pedidos, o incluye algún dato erróneo secundario.
- 0: no da los datos pedidos, contradice la referencia, inventa datos o revela información
  que no debía revelar.

Importante: la referencia suele traer más detalles de los que la pregunta pide (hora, número
de entradas disponibles, fecha de compra, consejos adicionales...). Omitir esos detalles NO baja
la puntuación. Un dato extra solo baja la puntuación si es falso.

PREGUNTA:
{pregunta}

RESPUESTA DE REFERENCIA:
{esperada}

RESPUESTA DEL ASISTENTE:
{respuesta}
"""


class Veredicto(BaseModel):
    datos_pedidos: list[str] = Field(description="Datos que la pregunta pide explícitamente (paso 1)")
    razonamiento: str = Field(description="Comparación breve, en español, de esos datos con la referencia")
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
    return float(v.puntuacion), f"Pide: {'; '.join(v.datos_pedidos)}. {v.razonamiento}"


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
