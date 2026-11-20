"""Evalúa una versión del prompt con el dataset de 12 preguntas en Langfuse.

    python scripts/evaluar_langfuse.py --version 1
    python scripts/evaluar_langfuse.py --version 2

Sube (o actualiza) el dataset `eventhub-v4-12-preguntas`, ejecuta cada pregunta con un
hilo nuevo usando esa versión del prompt (descargada de Langfuse) y registra un
experimento `prompt-vN-<fecha>` con tres scores por item: correccion (juez LLM),
herramientas_correctas y privacidad (deterministas). Las trazas quedan enlazadas al
experimento y cada generación a su versión del prompt.
"""

import argparse
import json
from datetime import datetime
from statistics import mean

from eventhub_v4.config import settings
from eventhub_v4.evaluacion import metricas
from eventhub_v4.evaluacion.ejecucion import NOMBRE_DATASET, cargar_dataset, responder
from eventhub_v4.llm.prompt_gestionado import obtener_prompt

METRICAS = ["correccion", "herramientas_correctas", "privacidad"]


def subir_dataset(lf) -> None:
    try:
        lf.get_dataset(NOMBRE_DATASET)
    except Exception:
        lf.create_dataset(
            name=NOMBRE_DATASET,
            description="12 preguntas (4 políticas, 4 eventos, 4 pedidos) con respuesta y herramientas esperadas",
        )
        print(f"Dataset {NOMBRE_DATASET} creado")
    for item in cargar_dataset():
        lf.create_dataset_item(  # mismo id → se actualiza en vez de duplicarse
            dataset_name=NOMBRE_DATASET, id=f"{NOMBRE_DATASET}-{item['id']}",
            input=item["input"], expected_output=item["expected_output"],
            metadata={**item["metadata"], "id": item["id"]},
        )


def evaluador(*, input, output, expected_output, metadata=None, **kwargs):
    metadata = metadata or {}
    c, razon = metricas.correccion(input["pregunta"], output["respuesta"], expected_output["respuesta"])
    h, detalle = metricas.herramientas_correctas(output["herramientas"], expected_output["herramientas"])
    evaluaciones = [
        {"name": "correccion", "value": c, "comment": razon},
        {"name": "herramientas_correctas", "value": h, "comment": detalle},
    ]
    p, motivo = metricas.privacidad(output["respuesta"], metadata.get("no_debe_contener"))
    if p is not None:
        evaluaciones.append({"name": "privacidad", "value": p, "comment": motivo})
    return evaluaciones


def medias(*, item_results, **kwargs):
    salida = []
    for nombre in METRICAS:
        valores = [e.value for r in item_results for e in r.evaluations if e.name == nombre]
        if valores:
            salida.append({"name": f"media_{nombre}", "value": mean(valores),
                           "comment": f"{len(valores)} items"})
    return salida


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--version", type=int, required=True, choices=[1, 2])
    args = parser.parse_args()
    if not settings.langfuse_tracing():
        raise SystemExit("Hacen falta las claves de Langfuse y EVENTHUB_LANGFUSE_TRACING distinto de 0")
    from eventhub_v4.observabilidad import cliente_langfuse

    lf = cliente_langfuse()
    prompt = obtener_prompt(version=args.version)
    if prompt.version != args.version:
        raise SystemExit(f"No se pudo descargar la v{args.version} del prompt (¿has ejecutado subir_prompts.py?)")

    subir_dataset(lf)
    dataset = lf.get_dataset(NOMBRE_DATASET)

    def tarea(*, item, **kwargs):
        return responder(item.input["pregunta"], prompt, id_item=item.metadata.get("id", ""), plataforma="langfuse")

    run_name = f"{prompt.etiqueta}-{datetime.now():%Y%m%d-%H%M}"
    resultado = dataset.run_experiment(
        name=f"EventHub v4 · {prompt.etiqueta}", run_name=run_name,
        description=f"Prompt {settings.prompt_nombre()} v{prompt.version}; juez {settings.juez_model()}",
        task=tarea, evaluators=[evaluador], run_evaluators=[medias], max_concurrency=4,
        metadata={"prompt_version": str(prompt.version), "modelo": settings.openai_model(),
                  "juez": settings.juez_model()},
    )
    lf.flush()

    filas = []
    for r in resultado.item_results:
        scores = {e.name: e.value for e in r.evaluations}
        filas.append({"id": r.item.metadata.get("id"), "categoria": r.item.metadata.get("categoria"),
                      "pregunta": r.item.input["pregunta"], **r.output, "scores": scores,
                      "comentarios": {e.name: e.comment for e in r.evaluations}})
    resumen = {e.name: e.value for e in resultado.run_evaluations}
    print(f"\nExperimento {run_name}: {resultado.experiment_url or '(sin URL)'}")
    for f in sorted(filas, key=lambda f: f["id"]):
        print(f"  {f['id']:<26} " + "  ".join(f"{k}={v:g}" for k, v in f["scores"].items()))
    print("Medias:", {k: round(v, 3) for k, v in resumen.items()})

    ruta = settings.RAIZ_PROYECTO / "resultados" / f"eval_langfuse_v{args.version}.json"
    ruta.parent.mkdir(exist_ok=True)
    ruta.write_text(json.dumps({"run_name": run_name, "url": resultado.experiment_url, "medias": resumen,
                                "items": filas}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Guardado en {ruta}")


if __name__ == "__main__":
    main()
