"""Configuración de la aplicación leída del entorno / fichero .env."""

import os
from pathlib import Path

from dotenv import load_dotenv

# src/eventhub_v4/config/settings.py → parents[3] es la raíz del proyecto (version4/).
RAIZ_PROYECTO = Path(__file__).resolve().parents[3]

# Carga .env (si existe) sin pisar variables ya definidas en el entorno.
load_dotenv(RAIZ_PROYECTO / ".env")

MODELO_POR_DEFECTO = "gpt-4.1-mini"


def openai_api_key() -> str | None:
    return os.getenv("OPENAI_API_KEY")


def openai_model() -> str:
    return os.getenv("OPENAI_MODEL") or MODELO_POR_DEFECTO


def data_dir() -> Path:
    """Carpeta de datos. Se lee en cada llamada para que los tests puedan
    apuntar a una copia temporal con EVENTHUB_DATA_DIR."""
    return Path(os.getenv("EVENTHUB_DATA_DIR") or RAIZ_PROYECTO / "data")


def diagramas_dir() -> Path:
    """Carpeta donde se guardan los diagramas del grafo."""
    return RAIZ_PROYECTO / "diagramas"


def openai_temperature() -> float | None:
    """Temperatura del modelo, o None para no enviarla (modelos que no la admiten)."""
    valor = os.getenv("OPENAI_TEMPERATURE", "").strip()
    return float(valor) if valor else None


# --- Observabilidad y prompts ------------------------------------------------

def prompts_dir() -> Path:
    """Carpeta con las versiones locales del prompt de sistema (fuente para subirlas
    a Langfuse y fallback cuando Langfuse no está disponible, p. ej. en los tests)."""
    return RAIZ_PROYECTO / "prompts"


def langfuse_activo() -> bool:
    """True si hay claves de Langfuse (para descargar prompts y usar su API)."""
    return bool(os.getenv("LANGFUSE_PUBLIC_KEY") and os.getenv("LANGFUSE_SECRET_KEY"))


def langfuse_tracing() -> bool:
    """True si hay claves y no se ha desactivado el envío de trazas a Langfuse."""
    desactivado = os.getenv("EVENTHUB_LANGFUSE_TRACING", "1").strip().lower() in {"0", "false", "no"}
    return langfuse_activo() and not desactivado


def prompt_nombre() -> str:
    return os.getenv("EVENTHUB_PROMPT_NOMBRE") or "eventhub-sistema"


def prompt_label() -> str:
    return os.getenv("EVENTHUB_PROMPT_LABEL") or "production"


def marca() -> str:
    return os.getenv("EVENTHUB_MARCA") or "EventHub"


def tono() -> str:
    return os.getenv("EVENTHUB_TONO") or "cercano y profesional"


def usuario_por_defecto() -> str:
    return os.getenv("EVENTHUB_USUARIO") or "anonimo"


def juez_model() -> str:
    return os.getenv("EVENTHUB_JUEZ_MODEL") or "gpt-4.1"


def langfuse_mask_pii() -> bool:
    """Enmascarar emails en las trazas de Langfuse (por defecto sí)."""
    return os.getenv("EVENTHUB_LANGFUSE_MASK_PII", "1").strip().lower() not in {"0", "false", "no"}
