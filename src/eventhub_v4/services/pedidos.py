"""Consulta del estado de pedidos."""

from eventhub_v4.services.datos import leer_json

ARCHIVO_PEDIDOS = "orders.json"

# Mismo mensaje si el pedido no existe o si el email no coincide, para no
# revelar a un tercero qué identificadores de pedido existen.
MENSAJE_PEDIDO_NO_VERIFICADO = (
    "No se ha encontrado ningún pedido con ese identificador y email. "
    "Revisa los datos o contacta con soporte."
)


def consultar_pedido(id_pedido: str, email: str) -> dict:
    """Devuelve {"encontrado": True, ...datos} o {"encontrado": False, "mensaje": ...}."""
    id_buscado = id_pedido.strip().upper()
    email_buscado = email.strip().casefold()
    for p in leer_json(ARCHIVO_PEDIDOS):
        if p["id_pedido"].upper() == id_buscado and p["email"].casefold() == email_buscado:
            return {
                "encontrado": True,
                "id_pedido": p["id_pedido"],
                "id_evento": p["id_evento"],
                "cantidad": p["cantidad"],
                "estado": p["estado"],
                "fecha_compra": p["fecha_compra"],
            }
    return {"encontrado": False, "mensaje": MENSAJE_PEDIDO_NO_VERIFICADO}
