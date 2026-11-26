| Sesión | Usuario | Conversación | Turnos | Llamadas LLM | Tokens | Coste | Latencia | Herramientas |
|---|---|---|---|---|---|---|---|---|
| `demo-20261120-222703-01` | laura.martinez | política de devoluciones | 2 | 2 | 2638 | $0.00082 | 1.88 s | — |
| `demo-20261120-222703-02` | ana.gomez | pedido + eventos encadenados | 1 | 3 | 4149 | $0.00067 | 3.12 s | consultar_pedido, buscar_eventos |
| `demo-20261120-222703-03` | carlos.ruiz | pedido sin email y después con email | 2 | 3 | 4010 | $0.00067 | 2.63 s | consultar_pedido |
| `demo-20261120-222703-04` | intruso | pedido con email incorrecto | 1 | 1 | 1304 | $0.00058 | 1.51 s | — |
| `demo-20261120-222703-05` | visitante-1 | eventos con memoria del hilo | 3 | 4 | 6355 | $0.00116 | 5.39 s | buscar_eventos |
| `demo-20261120-222703-06` | visitante-2 | eventos por mes | 1 | 2 | 2681 | $0.00083 | 1.78 s | buscar_eventos |
| `demo-20261120-222703-07` | javier.lopez | cambio de titular | 2 | 3 | 4178 | $0.00078 | 3.39 s | buscar_eventos |
| `demo-20261120-222703-08` | visitante-3 | fuera de las políticas | 1 | 1 | 1313 | $0.00061 | 1.25 s | — |
| `demo-20261120-222703-09` | pablo.diaz | pedido cancelado y reembolso | 2 | 3 | 4107 | $0.00068 | 2.36 s | consultar_pedido |
| `demo-20261120-222703-10` | visitante-4 | eventos sin resultados y agotados | 2 | 4 | 5408 | $0.00162 | 3.68 s | buscar_eventos, buscar_eventos |
| **Total** | | | | | 36143 | **$0.00842** | **26.98 s** | |
