"""Consulta de eventos."""

import re
import unicodedata

from eventhub_v4.services.datos import leer_json

ARCHIVO_EVENTOS = "events.json"

# Mes en formato AAAA-MM con mes 01..12, p. ej. "2026-12".
_PATRON_MES = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")


def normalizar(texto: str) -> str:
    """Minúsculas, sin tildes y sin espacios sobrantes: 'Málaga ' → 'malaga'."""
    sin_tildes = unicodedata.normalize("NFKD", texto)
    sin_tildes = "".join(c for c in sin_tildes if not unicodedata.combining(c))
    return sin_tildes.casefold().strip()


def listar_eventos() -> list[dict]:
    return leer_json(ARCHIVO_EVENTOS)


def obtener_evento(id_evento: str) -> dict | None:
    objetivo = normalizar(id_evento)
    return next((e for e in listar_eventos() if normalizar(e["id"]) == objetivo), None)


def buscar_eventos(
    ciudad: str | None = None, categoria: str | None = None, mes: str | None = None
) -> list[dict]:
    """Eventos que cumplen los filtros dados (los vacíos se ignoran), ordenados por fecha.

    `mes` tiene formato "AAAA-MM" (p. ej. "2026-12"); si no lo cumple se lanza ValueError.
    """
    if mes:
        mes = mes.strip()
        if not _PATRON_MES.match(mes):
            raise ValueError(f"Mes no válido: {mes!r}. Usa el formato AAAA-MM, p. ej. '2026-12'.")
    resultado = []
    for e in listar_eventos():
        if mes and not e["fecha"].startswith(mes):
            continue
        if ciudad and normalizar(e["ciudad"]) != normalizar(ciudad):
            continue
        if categoria and normalizar(e["categoria"]) != normalizar(categoria):
            continue
        resultado.append(
            {k: e[k] for k in ("id", "nombre", "ciudad", "categoria", "fecha", "precio", "disponibles")}
        )
    return sorted(resultado, key=lambda e: e["fecha"])
