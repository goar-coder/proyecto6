# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

EventHub v4: a terminal customer-support assistant for a ticketing platform, built with LangGraph + `ChatOpenAI`. All code, identifiers, docstrings, prompts, and user-facing text are in **Spanish** — keep new code consistent with that. The README refers to the project root as `version4/`; here it is the repo root.

## Commands

```bash
pip install -e ".[dev]"          # editable install is required: settings.py locates .env, data/ and diagramas/ relative to the source tree
cp .env.example .env             # needs OPENAI_API_KEY only to run the assistant, not for tests

python -m eventhub_v4            # run the chat (or: eventhub-v4)
pytest                           # all tests; no API key or network needed
pytest tests/test_v4_herramientas.py::test_limite_de_pasos_termina_con_mensaje_amable   # single test
```

No linter or formatter is configured. Pytest config (in `pyproject.toml`) puts both `src` and `.` on `pythonpath`, so tests import helpers as `from tests.conftest import ...`.

## Architecture

Layering, from bottom to top:

- `config/settings.py` — loads `.env` from the project root (`Path(__file__).parents[3]`) without overriding existing env vars. `data_dir()` is read on every call so tests can redirect it via `EVENTHUB_DATA_DIR`. Empty `OPENAI_TEMPERATURE` means "don't send temperature" (reasoning models reject it).
- `services/` — pure data logic over the JSON files in `data/` (read-only; nothing ever writes data). Event filters normalize case and accents; `mes` must be `AAAA-MM` or `ValueError` is raised. `consultar_pedido` returns the **same generic message** whether the order doesn't exist or the email doesn't match — this is deliberate (don't leak which order IDs exist).
- `tools/eventhub_tools.py` — thin `@tool` wrappers that return JSON strings and convert `ValueError` into `{"error": ...}`. The model sees the name, type hints, and docstring, so docstrings are part of the prompt.
- `llm/` — `crear_modelo()` is the only place the OpenAI client is built; `prompts.py` holds policy rules and reads `data/policies.md`.
- `grafos/comun.py` — builds the system prompt (persona + policy rules + tool rules + full `policies.md` inlined) and saves Mermaid/PNG diagrams.
- `grafos/v4_herramientas.py` — the graph, the per-turn `enviar()` helper, `/historial` formatting, and the terminal loop (`main`).

### Graph (`construir_grafo(modelo=None, checkpointer=None)`)

`START → chatbot → (conditional ruta_tras_chatbot) → herramientas → chatbot` loop, or `→ limite → END`, or `→ END`.

- The `herramientas` node is hand-written (not LangGraph's `ToolNode`): it executes each `tool_call` of the last `AIMessage`, returns a `ToolMessage` per call with matching `tool_call_id`, and turns unknown tools / invalid args into error `ToolMessage`s instead of raising.
- `EstadoV4` extends `MessagesState` with `pasos` (no reducer — last write wins). `enviar()` passes `pasos: 0` on every invocation to reset the counter per turn; `herramientas` increments it.
- When the model requests tools again with `pasos >= MAX_PASOS` (5), `limite` answers every pending tool_call with a "no ejecutada" `ToolMessage` before appending `MENSAJE_LIMITE`. This matters: OpenAI rejects histories containing an `AIMessage` with unanswered tool_calls, which would break the thread on the next turn.
- Memory is an `InMemorySaver` checkpointer keyed by `thread_id` (`config_hilo()`); lost on exit.
- `HERRAMIENTAS` is defined in both `tools/eventhub_tools.py` and `v4_herramientas.py`; adding a tool means registering it in the graph module's list (which builds `HERRAMIENTAS_POR_NOMBRE`) and, likely, adding usage rules to `_REGLAS_HERRAMIENTAS` in `comun.py`.
- `main()` regenerates `diagramas/v4.mmd` on startup.

### Tests

`tests/conftest.py` provides:
- `datos_temporales` fixture — copies `data/` to a tmp dir and sets `EVENTHUB_DATA_DIR`; use it in any test that touches services, tools, or the graph.
- `ModeloGuionizado` — a `GenericFakeChatModel` whose `bind_tools` returns itself; feed it `messages=iter([...])` with scripted `AIMessage`s.
- `llamada(nombre, args, id_)` — builds an `AIMessage` requesting a tool.

Graph tests pass the fake model to `construir_grafo(...)` and assert on `enviar()`'s return value and on `grafo.get_state(config_hilo(...))`.

Regenerating `diagramas/v4.png` requires internet (mermaid.ink); see the command at the end of README.md.
