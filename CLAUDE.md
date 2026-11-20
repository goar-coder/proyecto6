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

# Observability / evaluation (need real Langfuse, LangSmith and OpenAI keys in .env)
python scripts/subir_prompts.py [--promover N]     # upload prompts/ v1 (production) + v2 (candidata)
python scripts/conversaciones.py && python scripts/informe_trazas.py
python scripts/evaluar_langfuse.py --version 1|2
python scripts/evaluar_langsmith.py [--version N]
```

No linter or formatter is configured. Pytest config (in `pyproject.toml`) puts both `src` and `.` on `pythonpath`, so tests import helpers as `from tests.conftest import ...`.

## Architecture

Layering, from bottom to top:

- `config/settings.py` — loads `.env` from the project root (`Path(__file__).parents[3]`) without overriding existing env vars. `data_dir()` is read on every call so tests can redirect it via `EVENTHUB_DATA_DIR`. Empty `OPENAI_TEMPERATURE` means "don't send temperature" (reasoning models reject it).
- `services/` — pure data logic over the JSON files in `data/` (read-only; nothing ever writes data). Event filters normalize case and accents; `mes` must be `AAAA-MM` or `ValueError` is raised. `consultar_pedido` returns the **same generic message** whether the order doesn't exist or the email doesn't match — this is deliberate (don't leak which order IDs exist).
- `tools/eventhub_tools.py` — thin `@tool` wrappers that return JSON strings and convert `ValueError` into `{"error": ...}`. The model sees the name, type hints, and docstring, so docstrings are part of the prompt.
- `llm/` — `crear_modelo()` is the only place the OpenAI client is built; `prompts.py` only reads `data/policies.md`.
- `llm/prompt_gestionado.py` — the system prompt is **not in code**: it lives in Langfuse Prompt Management (`eventhub-sistema`, text prompt with `{{marca}}`, `{{tono}}`, `{{politicas}}`). `obtener_prompt(version=|label=)` returns a `PromptSistema` (compiled text + Langfuse client + `etiqueta` like `prompt-v2`); without Langfuse keys, or on fetch failure, it falls back to `prompts/eventhub_sistema_v{N}.txt`. Edit prompt text in `prompts/` and re-upload as a **new version** with `scripts/subir_prompts.py`; don't put prompt text back into Python.
- `observabilidad.py` — Langfuse tracing per https://langfuse.com/docs/observability/best-practices (the project-level skill in `.claude/skills/langfuse` has the workflow). One turn = one trace, one conversation (`thread_id`) = one session. `traza_turno()` wraps each `enviar()` call in `propagate_attributes(session_id, user_id, tags, metadata, trace_name)` + a root `agent` observation named `NOMBRE_TRAZA` (`responder-mensaje`; treat names as an API, don't rename casually) whose input/output are the user text and the reply. `config_langchain()` builds the LangChain config (checkpointer `thread_id`, `run_name`, tags, metadata for LangSmith) and attaches the `CallbackHandler`, which nests the LangGraph nodes, `generation`s and `tool`s under that root. Always get the client via `cliente_langfuse()` (single client, created with `mask_otel_spans` that masks emails) and keep `public_key` on the handler: with several clients in a process a key-less handler silently stops tracing. LangSmith is enabled purely by `LANGSMITH_*` env vars. `settings.langfuse_activo()` (keys present → may fetch prompts) is deliberately separate from `langfuse_tracing()` (`EVENTHUB_LANGFUSE_TRACING=0` disables traces, used by the LangSmith eval to avoid duplicates). Environment comes from `LANGFUSE_TRACING_ENVIRONMENT`.
- `grafos/comun.py` — saves Mermaid/PNG diagrams.
- `evaluacion/` (package) — `metricas.py`: `correccion` (LLM judge, `EVENTHUB_JUEZ_MODEL`), `herramientas_correctas` (required tools ⊆ called; no tools when none expected), `privacidad` (forbidden strings from item metadata `no_debe_contener`). `ejecucion.responder()` runs one dataset question on a fresh graph/thread. The dataset itself is `evaluacion/dataset.json` at the repo root; script outputs go to `resultados/`.
- `grafos/v4_herramientas.py` — the graph, the per-turn `enviar()` helper, `/historial` formatting, and the terminal loop (`main`).

### Graph

`construir_grafo(modelo=None, checkpointer=None, prompt=None)`; `prompt=None` downloads the `production` prompt.

`START → chatbot → (conditional ruta_tras_chatbot) → herramientas → chatbot` loop, or `→ limite → END`, or `→ END`.

- The `herramientas` node is hand-written (not LangGraph's `ToolNode`): it executes each `tool_call` of the last `AIMessage`, returns a `ToolMessage` per call with matching `tool_call_id`, and turns unknown tools / invalid args into error `ToolMessage`s instead of raising.
- `EstadoV4` extends `MessagesState` with `pasos` (no reducer — last write wins). `enviar()` passes `pasos: 0` on every invocation to reset the counter per turn; `herramientas` increments it.
- When the model requests tools again with `pasos >= MAX_PASOS` (5), `limite` answers every pending tool_call with a "no ejecutada" `ToolMessage` before appending `MENSAJE_LIMITE`. This matters: OpenAI rejects histories containing an `AIMessage` with unanswered tool_calls, which would break the thread on the next turn.
- The `chatbot` node invokes `(PromptSistema.plantilla_chat() | model).with_config(run_name="generar-respuesta")`. `plantilla_chat()` is a `ChatPromptTemplate` (system + `MessagesPlaceholder("messages")`) carrying `metadata={"langfuse_prompt": ...}` — the documented way to link generations to a prompt version. Put `langfuse_prompt` only there, never on the model call.
- `enviar(grafo, thread_id, texto, usuario=None, tags=None, metadata=None)` — one turn = one trace.
- Memory is an `InMemorySaver` checkpointer keyed by `thread_id` (`config_hilo()`); lost on exit.
- `HERRAMIENTAS` is defined in both `tools/eventhub_tools.py` and `v4_herramientas.py`; adding a tool means registering it in the graph module's list (which builds `HERRAMIENTAS_POR_NOMBRE`) and, likely, adding usage rules to `_REGLAS_HERRAMIENTAS` in `comun.py`.
- `main()` regenerates `diagramas/v4.mmd` on startup.

### Tests

`tests/test_trazas_langfuse.py` checks the exported trace shape offline by giving the Langfuse client an `InMemorySpanExporter` (root name/type/IO, propagated session/user, prompt link, `tool` types, masking). Each test uses a unique `LANGFUSE_PUBLIC_KEY` because the SDK reuses its span processor per key.

`tests/conftest.py` provides:
- an autouse fixture that removes Langfuse keys and disables Langfuse/LangSmith tracing, so tests never hit the network even with a real `.env` (the prompt comes from `prompts/`).
- `datos_temporales` fixture — copies `data/` to a tmp dir and sets `EVENTHUB_DATA_DIR`; use it in any test that touches services, tools, or the graph.
- `ModeloGuionizado` — a `GenericFakeChatModel` whose `bind_tools` returns itself; feed it `messages=iter([...])` with scripted `AIMessage`s.
- `llamada(nombre, args, id_)` — builds an `AIMessage` requesting a tool.

Graph tests pass the fake model to `construir_grafo(...)` and assert on `enviar()`'s return value and on `grafo.get_state(config_hilo(...))`.

Regenerating `diagramas/v4.png` requires internet (mermaid.ink); see the command at the end of README.md.
