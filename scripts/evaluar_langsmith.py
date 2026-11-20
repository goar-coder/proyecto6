"""Sube el mismo dataset a LangSmith y lo evalúa con un juez LLM.

    python scripts/evaluar_langsmith.py             # v1 y v2 del prompt
    python scripts/evaluar_langsmith.py --version 2

El grafo no se toca: LangSmith traza por las variables de entorno LANGSMITH_*.
Las versiones del prompt se descargan de Langfuse (allí está la gestión de prompts),
pero el envío de trazas a Langfuse se desactiva para no duplicar los experimentos.
"""

import argparse
import json
import os
from statistics import mean

os.environ["EVENTHUB_LANGFUSE_TRACING"] = "0"  # antes de importar nada del proyecto

from langsmith import Client  # noqa: E402

from eventhub_v4.config import settings  # noqa: E402  (carga .env)
from eventhub_v4.evaluacion import metricas  # noqa: E402
from eventhub_v4.evaluacion.ejecucion import NOMBRE_DATASET, cargar_dataset, responder  # noqa: E402
from eventhub_v4.llm.prompt_gestionado import obtener_prompt  # noqa: E402


def subir_dataset(client: Client) -> None:
    if client.has_dataset(dataset_name=NOMBRE_DATASET):
        existentes = {e.metadata.get("id") for e in client.list_examples(dataset_name=NOMBRE_DATASET)}
    else:
        client.create_dataset(
            NOMBRE_DATASET,
            description="12 preguntas (4 políticas, 4 eventos, 4 pedidos) con respuesta y herramientas esperadas",
        )
        existentes = set()
    nuevos = [
        {"inputs": i["input"], "outputs": i["expected_output"], "metadata": {**i["metadata"], "id": i["id"]}}
        for i in cargar_dataset() if i["id"] not in existentes
    ]
    if nuevos:
        client.create_examples(dataset_name=NOMBRE_DATASET, examples=nuevos)
        print(f"Subidos {len(nuevos)} ejemplos a {NOMBRE_DATASET}")


# --- Evaluadores (LangSmith inyecta los argumentos por nombre) -----------------

def correccion(inputs: dict, outputs: dict, reference_outputs: dict) -> dict:
    """Juez LLM: corrección frente a la respuesta esperada."""
    score, razon = metricas.correccion(inputs["pregunta"], outputs["respuesta"], reference_outputs["respuesta"])
    return {"key": "correccion", "score": score, "comment": razon}


def herramientas_correctas(outputs: dict, reference_outputs: dict) -> dict:
    score, detalle = metricas.herramientas_correctas(outputs["herramientas"], reference_outputs["herramientas"])
    return {"key": "herramientas_correctas", "score": score, "comment": detalle}


def privacidad(outputs: dict, example) -> dict:
    score, motivo = metricas.privacidad(outputs["respuesta"], (example.metadata or {}).get("no_debe_contener"))
    return {"key": "privacidad", "score": score, "comment": motivo}


def evaluar(client: Client, version: int) -> dict:
    prompt = obtener_prompt(version=version)
    if prompt.version != version:
        raise SystemExit(f"No se pudo descargar la v{version} del prompt de Langfuse")

    def objetivo(inputs: dict) -> dict:
        return responder(inputs["pregunta"], prompt, plataforma="langsmith")

    resultados = client.evaluate(
        objetivo, data=NOMBRE_DATASET,
        evaluators=[correccion, herramientas_correctas, privacidad],
        experiment_prefix=prompt.etiqueta, max_concurrency=4,
        description=f"Prompt {settings.prompt_nombre()} v{version}; juez {settings.juez_model()}",
        metadata={"prompt_version": version, "modelo": settings.openai_model(), "juez": settings.juez_model()},
    )
    puntuaciones: dict[str, list[float]] = {}
    items = []
    for fila in resultados:
        scores = {r.key: r.score for r in fila["evaluation_results"]["results"] if r.score is not None}
        for k, v in scores.items():
            puntuaciones.setdefault(k, []).append(v)
        items.append({"id": fila["example"].metadata.get("id"), **fila["run"].outputs, "scores": scores})
    medias = {f"media_{k}": mean(v) for k, v in puntuaciones.items()}
    print(f"\n{resultados.experiment_name}: {medias}")
    return {"experimento": resultados.experiment_name, "medias": medias, "items": items}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--version", type=int, choices=[1, 2], action="append",
                        help="versión del prompt (se puede repetir); por defecto 1 y 2")
    args = parser.parse_args()
    if not os.getenv("LANGSMITH_API_KEY"):
        raise SystemExit("Falta LANGSMITH_API_KEY en .env")

    client = Client()
    subir_dataset(client)
    for version in args.version or [1, 2]:
        salida = evaluar(client, version)
        ruta = settings.RAIZ_PROYECTO / "resultados" / f"eval_langsmith_v{version}.json"
        ruta.parent.mkdir(exist_ok=True)
        ruta.write_text(json.dumps(salida, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        print(f"Guardado en {ruta}")


if __name__ == "__main__":
    main()
