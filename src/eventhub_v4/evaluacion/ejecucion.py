"""Ejecución de una pregunta del dataset contra el grafo y lectura del dataset."""

import json
import uuid

from eventhub_v4.config import settings
from eventhub_v4.grafos.v4_herramientas import construir_grafo, enviar
from eventhub_v4.llm.prompt_gestionado import PromptSistema

NOMBRE_DATASET = "eventhub-v4-12-preguntas"


def cargar_dataset() -> list[dict]:
    ruta = settings.RAIZ_PROYECTO / "evaluacion" / "dataset.json"
    return json.loads(ruta.read_text(encoding="utf-8"))


def responder(pregunta: str, prompt: PromptSistema, id_item: str = "", plataforma: str = "") -> dict:
    """Un hilo nuevo (memoria vacía) por pregunta; devuelve respuesta y herramientas llamadas."""
    grafo = construir_grafo(prompt=prompt)
    hilo = f"eval-{prompt.etiqueta}-{id_item or 'x'}-{uuid.uuid4().hex[:6]}"
    r = enviar(grafo, hilo, pregunta, usuario="evaluador",
               tags=["evaluacion"],
               metadata={"dataset": NOMBRE_DATASET, "item": id_item, "prompt_version": prompt.etiqueta,
                         "plataforma": plataforma})
    return {"respuesta": r["respuesta"], "herramientas": [h["nombre"] for h in r["herramientas"]]}
