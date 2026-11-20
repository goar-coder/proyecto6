"""Lanza 10 conversaciones guionizadas contra el grafo v4 y las traza en Langfuse
(y en LangSmith si LANGSMITH_TRACING=true). Cada conversación es un hilo propio.

    python scripts/conversaciones.py

Guarda los session_id en resultados/conversaciones.json para scripts/informe_trazas.py.
"""

import json
import time
from datetime import datetime

from eventhub_v4.config import settings
from eventhub_v4.grafos.v4_herramientas import construir_grafo, enviar
from eventhub_v4.llm.prompt_gestionado import obtener_prompt
from eventhub_v4.observabilidad import flush

# (usuario, descripción, turnos)
CONVERSACIONES = [
    ("laura.martinez", "política de devoluciones", [
        "¿Hasta cuándo puedo devolver mis entradas?",
        "¿Y me devuelven también los gastos de gestión?",
    ]),
    ("ana.gomez", "pedido + eventos encadenados", [
        "¿Mi pedido EH-1003 es para un concierto en Madrid? Si es así, dime otros conciertos "
        "en Madrid ese mes. Mi email es ana.gomez@example.com",
    ]),
    ("carlos.ruiz", "pedido sin email y después con email", [
        "¿Cómo va mi pedido EH-1002?",
        "Mi email es carlos.ruiz@example.com",
    ]),
    ("intruso", "pedido con email incorrecto", [
        "Quiero saber el estado del pedido EH-1004, mi email es hacker@example.com",
    ]),
    ("visitante-1", "eventos con memoria del hilo", [
        "¿Qué conciertos hay en Valencia?",
        "¿Cuál de esos es el más barato?",
        "¿Y quedan entradas para la Gran Gala Sinfónica?",
    ]),
    ("visitante-2", "eventos por mes", [
        "¿Qué conciertos hay en Madrid en enero de 2027?",
    ]),
    ("javier.lopez", "cambio de titular", [
        "¿Puedo cambiar el nombre de la persona que va a usar la entrada?",
        "¿Y para el partido de baloncesto Valencia Basket vs. Real Madrid?",
    ]),
    ("visitante-3", "fuera de las políticas", [
        "¿Puedo llevar a mi perro al concierto?",
    ]),
    ("pablo.diaz", "pedido cancelado y reembolso", [
        "Mi pedido EH-1006 (pablo.diaz@example.com), ¿en qué estado está?",
        "Si el organizador lo canceló, ¿cuándo me devuelven el dinero?",
    ]),
    ("visitante-4", "eventos sin resultados y agotados", [
        "¿Hay algo de comedia en Barcelona en diciembre?",
        "¿Y qué eventos de deporte hay en Madrid?",
    ]),
]


def main() -> None:
    if not settings.langfuse_activo():
        print("Aviso: Langfuse no está configurado; las conversaciones no se trazarán en Langfuse.")
    prompt = obtener_prompt()
    grafo = construir_grafo(prompt=prompt)
    sello = datetime.now().strftime("%Y%m%d-%H%M%S")
    sesiones = []
    for n, (usuario, descripcion, turnos) in enumerate(CONVERSACIONES, 1):
        hilo = f"demo-{sello}-{n:02d}"
        print(f"\n=== {n:02d} · {descripcion} · hilo {hilo} · usuario {usuario} ===")
        inicio = time.perf_counter()
        herramientas = []
        for texto in turnos:
            r = enviar(grafo, hilo, texto, usuario=usuario,
                       tags=["demo-10-conversaciones"],
                       metadata={"conversacion": descripcion, "prompt_version": prompt.etiqueta})
            herramientas += [h["nombre"] for h in r["herramientas"]]
            print(f"Tú: {texto}")
            for h in r["herramientas"]:
                print(f"  ↳ {h['nombre']}({json.dumps(h['argumentos'], ensure_ascii=False)})")
            print(f"Asistente: {r['respuesta']}")
        sesiones.append({
            "session_id": hilo, "usuario": usuario, "descripcion": descripcion,
            "turnos": len(turnos), "herramientas_local": herramientas,
            "segundos_local": round(time.perf_counter() - inicio, 2), "prompt": prompt.etiqueta,
        })
    flush()
    settings.RAIZ_PROYECTO.joinpath("resultados").mkdir(exist_ok=True)
    ruta = settings.RAIZ_PROYECTO / "resultados" / "conversaciones.json"
    ruta.write_text(json.dumps(sesiones, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nSesiones guardadas en {ruta}")


if __name__ == "__main__":
    main()
