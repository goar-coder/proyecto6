"""Lectura de los ficheros JSON de data/ (la v4 solo consulta, no escribe)."""

import json
from pathlib import Path
from typing import Any

from eventhub_v4.config.settings import data_dir


def ruta(nombre: str) -> Path:
    return data_dir() / nombre


def leer_json(nombre: str) -> Any:
    with ruta(nombre).open(encoding="utf-8") as f:
        return json.load(f)
