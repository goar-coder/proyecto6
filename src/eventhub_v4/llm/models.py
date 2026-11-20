"""Único punto donde se crea el cliente de OpenAI."""

from langchain_openai import ChatOpenAI

from eventhub_v4.config.settings import openai_api_key, openai_model, openai_temperature


def crear_modelo() -> ChatOpenAI:
    kwargs = {}
    # La temperatura solo se envía si está configurada: algunos modelos
    # (p. ej. los de razonamiento) rechazan este parámetro.
    # Con 0 las respuestas son más deterministas y menos propensas a inventar.
    temperatura = openai_temperature()
    if temperatura is not None:
        kwargs["temperature"] = temperatura
    return ChatOpenAI(model=openai_model(), api_key=openai_api_key(), **kwargs)
