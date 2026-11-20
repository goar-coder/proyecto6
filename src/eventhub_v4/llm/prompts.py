"""Textos de sistema compartidos por la cadena y el agente."""

from eventhub_v4.config.settings import data_dir


def cargar_politicas() -> str:
    """Lee el contenido de policies.md."""
    return (data_dir() / "policies.md").read_text(encoding="utf-8")


REGLAS_POLITICAS = """\
Reglas para responder sobre políticas:
- Responde ÚNICAMENTE con la información de las políticas de EventHub que aparecen abajo.
- No inventes plazos, importes, condiciones ni servicios que no estén escritos.
- Si la pregunta no se puede responder con esas políticas, di claramente que no
  tienes esa información y sugiere contactar con soporte (soporte@eventhub.example
  o +34 900 123 456).
- Responde en español, de forma breve y clara."""
