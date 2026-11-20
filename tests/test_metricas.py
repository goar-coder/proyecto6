"""Métricas deterministas y forma del dataset (sin red)."""

from collections import Counter

from eventhub_v4.evaluacion import metricas
from eventhub_v4.evaluacion.ejecucion import cargar_dataset


def test_herramientas_correctas():
    assert metricas.herramientas_correctas([], [])[0] == 1
    assert metricas.herramientas_correctas(["buscar_eventos"], [])[0] == 0  # no debía llamar a nada
    assert metricas.herramientas_correctas(["buscar_eventos", "buscar_eventos"], ["buscar_eventos"])[0] == 1
    assert metricas.herramientas_correctas(["consultar_pedido"], ["consultar_pedido", "buscar_eventos"])[0] == 0
    assert metricas.herramientas_correctas(["buscar_eventos", "consultar_pedido"],
                                           ["consultar_pedido", "buscar_eventos"])[0] == 1


def test_privacidad():
    assert metricas.privacidad("Tu pedido está reembolsado", ["reembolsado"])[0] == 0
    assert metricas.privacidad("No se ha podido verificar el pedido", ["reembolsado"])[0] == 1
    assert metricas.privacidad("lo que sea", None)[0] is None


def test_dataset_12_preguntas_4_por_categoria():
    dataset = cargar_dataset()
    assert len(dataset) == 12 and len({i["id"] for i in dataset}) == 12
    assert Counter(i["categoria"] for i in dataset) == {"politicas": 4, "eventos": 4, "pedidos": 4}
    for i in dataset:
        assert i["input"]["pregunta"] and i["expected_output"]["respuesta"]
        assert set(i["expected_output"]["herramientas"]) <= {"buscar_eventos", "consultar_pedido"}
