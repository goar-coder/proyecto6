"""Sube el prompt de sistema a Langfuse Prompt Management.

    python scripts/subir_prompts.py              # crea v1 (production) y v2 (candidata) si faltan
    python scripts/subir_prompts.py --promover 2 # mueve la etiqueta production a la v2

Las versiones salen de prompts/eventhub_sistema_v{1,2}.txt, con las variables
{{marca}}, {{tono}} y {{politicas}}.
"""

import argparse

from eventhub_v4.config import settings  # carga .env
from eventhub_v4.llm.prompt_gestionado import texto_local

VERSIONES = {
    1: (["production"], "v1: prompt original de la sesión 5 con variables de marca y tono"),
    2: (["candidata"], "v2: cita plazos/importes, formato fijo de eventos (fecha, precio, "
                       "disponibilidad, «agotado»), privacidad estricta y nombre del evento en pedidos"),
}


def _existente(lf, nombre: str, version: int):
    try:
        return lf.get_prompt(nombre, version=version, type="text", cache_ttl_seconds=0, max_retries=0)
    except Exception:
        return None


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--promover", type=int, help="versión a la que mover la etiqueta production")
    args = parser.parse_args()

    if not settings.langfuse_activo():
        raise SystemExit("Faltan LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY en .env")
    from eventhub_v4.observabilidad import cliente_langfuse

    lf, nombre = cliente_langfuse(), settings.prompt_nombre()

    if args.promover:
        lf.update_prompt(name=nombre, version=args.promover, new_labels=["production"])
        print(f"Etiqueta production → {nombre} v{args.promover}")
        return

    for version, (etiquetas, mensaje) in VERSIONES.items():
        actual = _existente(lf, nombre, version)
        if actual is not None:
            igual = actual.prompt == texto_local(version)
            print(f"{nombre} v{version} ya existe ({'mismo texto' if igual else 'TEXTO DISTINTO al local'})"
                  f", etiquetas {actual.labels}")
            continue
        creado = lf.create_prompt(
            name=nombre, prompt=texto_local(version), type="text", labels=etiquetas,
            tags=["eventhub-v4"], commit_message=mensaje,
            config={"model": settings.openai_model(), "temperature": settings.openai_temperature()},
        )
        print(f"Creado {nombre} v{creado.version} con etiquetas {etiquetas}")
        if creado.version != version:
            print(f"  ¡Atención! Langfuse le ha dado la versión {creado.version}, no la {version}.")


if __name__ == "__main__":
    main()
