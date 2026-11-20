"""Servicios de consulta (eventos y pedidos) y la herramienta buscar_eventos."""

import json

import pytest

from eventhub_v4.services import eventos, pedidos
from eventhub_v4.tools.eventhub_tools import buscar_eventos as herramienta_buscar


# --- eventos ---------------------------------------------------------------

def test_filtro_por_ciudad_y_categoria(datos_temporales):
    resultado = eventos.buscar_eventos(ciudad="Valencia", categoria="concierto")
    assert {e["id"] for e in resultado} == {"EV001", "EV002", "EV003", "EV004"}
    assert all(set(e) >= {"id", "nombre", "fecha", "precio", "disponibles"} for e in resultado)


def test_filtro_sin_mayusculas_ni_tildes(datos_temporales):
    assert eventos.buscar_eventos(ciudad="MALAGA") == eventos.buscar_eventos(ciudad="Málaga")
    assert len(eventos.buscar_eventos(ciudad="  málaga ")) == 1
    assert eventos.buscar_eventos(categoria="Concierto") == eventos.buscar_eventos(categoria="concierto")


def test_sin_filtros_devuelve_todo_y_ciudad_inexistente_nada(datos_temporales):
    assert len(eventos.buscar_eventos()) == 16
    assert eventos.buscar_eventos(ciudad="Bilbao") == []


def test_incluye_evento_agotado(datos_temporales):
    agotados = [e for e in eventos.buscar_eventos(ciudad="valencia") if e["disponibles"] == 0]
    assert [e["id"] for e in agotados] == ["EV003"]


def test_filtro_por_mes_con_ciudad_y_categoria(datos_temporales):
    resultado = eventos.buscar_eventos(ciudad="Madrid", categoria="concierto", mes="2026-12")
    assert [e["id"] for e in resultado] == ["EV013", "EV014", "EV015"]  # EV016 es de enero


def test_filtro_por_mes_solo(datos_temporales):
    resultado = eventos.buscar_eventos(mes="2027-01")
    assert resultado and all(e["fecha"].startswith("2027-01") for e in resultado)
    assert "EV016" in {e["id"] for e in resultado}


@pytest.mark.parametrize("mes", ["diciembre", "2026-13", "2026-1", "12-2026"])
def test_filtro_por_mes_invalido(datos_temporales, mes):
    with pytest.raises(ValueError, match="AAAA-MM"):
        eventos.buscar_eventos(mes=mes)


def test_herramienta_buscar_eventos_mes_invalido_devuelve_error(datos_temporales):
    assert "error" in json.loads(herramienta_buscar.invoke({"mes": "diciembre"}))


# --- pedidos ---------------------------------------------------------------

def test_pedido_email_correcto(datos_temporales):
    r = pedidos.consultar_pedido("EH-1001", "laura.martinez@example.com")
    assert r["encontrado"] is True and r["estado"] == "pagado"


def test_pedido_email_correcto_sin_distinguir_mayusculas(datos_temporales):
    r = pedidos.consultar_pedido(" eh-1001 ", "Laura.Martinez@Example.com")
    assert r["encontrado"] is True


def test_pedido_email_incorrecto_e_inexistente_dan_el_mismo_mensaje(datos_temporales):
    incorrecto = pedidos.consultar_pedido("EH-1001", "otra@example.com")
    inexistente = pedidos.consultar_pedido("EH-9999", "laura.martinez@example.com")
    assert incorrecto == inexistente
    assert incorrecto == {"encontrado": False, "mensaje": pedidos.MENSAJE_PEDIDO_NO_VERIFICADO}
    assert "estado" not in incorrecto
