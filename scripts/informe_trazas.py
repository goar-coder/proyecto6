"""Lee de Langfuse las trazas de las 10 conversaciones y saca, por sesión, el coste,
la latencia y las herramientas llamadas (tabla Markdown lista para ENTREGA.md).

    python scripts/informe_trazas.py            # usa resultados/conversaciones.json
    python scripts/informe_trazas.py demo-...   # o session_id concretos

Usa el endpoint de observaciones v2 (lectura en tiempo real). Si una sesión sale
vacía, espera unos segundos a que Langfuse termine de ingerirla y repite.
"""

import json
import sys
from collections import defaultdict

from eventhub_v4.config import settings


def observaciones(lf, session_id: str) -> list:
    todas, cursor = [], None
    while True:
        r = lf.api.observations.get_many(
            session_id=session_id, fields="core,basic,usage,metrics", limit=100, cursor=cursor
        )
        todas += r.data
        cursor = getattr(r.meta, "cursor", None)
        if not cursor or not r.data:
            return todas


def resumen(obs: list) -> dict:
    por_traza = defaultdict(list)
    for o in obs:
        por_traza[o.trace_id].append(o)
    # Latencia de la conversación = suma de lo que tardó cada turno (cada turno es una traza),
    # sin contar el tiempo que el usuario tarda en escribir.
    latencia = sum(
        (max(o.end_time or o.start_time for o in grupo) - min(o.start_time for o in grupo)).total_seconds()
        for grupo in por_traza.values()
    )
    generaciones = [o for o in obs if o.type == "GENERATION"]
    herramientas = [o.name for o in sorted(obs, key=lambda o: o.start_time) if o.type == "TOOL"]
    return {
        "turnos": len(por_traza),
        "llamadas_llm": len(generaciones),
        "coste_usd": sum(o.total_cost or 0 for o in generaciones),
        "tokens": sum((o.usage_details or {}).get("total", 0) for o in generaciones),
        "latencia_s": latencia,
        "herramientas": herramientas,
    }


def main() -> None:
    if not settings.langfuse_activo():
        raise SystemExit("Faltan LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY en .env")
    from eventhub_v4.observabilidad import cliente_langfuse

    if len(sys.argv) > 1:
        sesiones = [{"session_id": s, "descripcion": "", "usuario": ""} for s in sys.argv[1:]]
    else:
        ruta = settings.RAIZ_PROYECTO / "resultados" / "conversaciones.json"
        sesiones = json.loads(ruta.read_text(encoding="utf-8"))

    lf = cliente_langfuse()
    filas, totales = [], {"coste_usd": 0.0, "latencia_s": 0.0, "tokens": 0}
    for s in sesiones:
        r = resumen(observaciones(lf, s["session_id"]))
        for k in totales:
            totales[k] += r[k]
        filas.append(
            f"| `{s['session_id']}` | {s.get('usuario', '')} | {s.get('descripcion', '')} | {r['turnos']} "
            f"| {r['llamadas_llm']} | {r['tokens']} | ${r['coste_usd']:.5f} | {r['latencia_s']:.2f} s "
            f"| {', '.join(r['herramientas']) or '—'} |"
        )
    tabla = "\n".join([
        "| Sesión | Usuario | Conversación | Turnos | Llamadas LLM | Tokens | Coste | Latencia | Herramientas |",
        "|---|---|---|---|---|---|---|---|---|",
        *filas,
        f"| **Total** | | | | | {totales['tokens']} | **${totales['coste_usd']:.5f}** "
        f"| **{totales['latencia_s']:.2f} s** | |",
    ])
    print(tabla)
    salida = settings.RAIZ_PROYECTO / "resultados" / "informe_trazas.md"
    salida.parent.mkdir(exist_ok=True)
    salida.write_text(tabla + "\n", encoding="utf-8")
    print(f"\nGuardado en {salida}")


if __name__ == "__main__":
    main()
