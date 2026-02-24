# Chart Widget Builder - Copilot Instructions

## Architecture Overview

This is a **two-tier app** for building embeddable chart widgets via AI chat. Users connect MySQL databases, chat with a **multi-agent AI pipeline** to generate SQL queries + Chart.js configs, and embed widgets via iframe.

```
frontend/ (React 19 + Vite + Tailwind 4)  →  /api proxy  →  backend/ (FastAPI + SQLite)
                                                                 ↓
                                                           Target MySQL DBs
                                                           OpenAI API (gpt-4o-mini)
```

- **SQLite** stores app config (widgets, connections, chat history, schema analyses). It is NOT the data source.
- **MySQL** is the target DB users connect to for chart data. All target DB access goes through `backend/app/services/db_connector.py`.
- **Multi-agent pipeline** (`backend/app/services/agents/orchestrator.py`) coordinates 6 specialised agents. The orchestrator returns structured JSON with `widget_update` + `filters` keys that get applied to the widget model.
- **SSE streaming** (`POST /api/widgets/{id}/chat/stream`) provides real-time agent progress to the frontend.

## Development Commands

```bash
# Backend (from backend/)
source venv/bin/activate
uvicorn app.main:app --reload --port 8000    # Swagger at http://localhost:8000/docs

# Frontend (from frontend/)
npm run dev                                   # Vite dev server at :5173, proxies /api → :8000
npm run build                                 # Production build to dist/
```

## Backend Patterns (`backend/`)

- **Route → Service → DB** layering: routes in `app/routes/`, business logic in `app/services/`, models in `app/models.py`
- **JSON-in-TEXT columns**: `chart_config`, `layout_config`, `options`, `config`, `analysis` are stored as JSON strings in SQLite TEXT columns. Serialize with `json.dumps()` before save, parse with `json.loads()` on read. See `_serialize_widget()` in `app/routes/widgets.py` for the pattern.
- **Schema field mismatch**: The API schema uses `password` but the model uses `password_enc`. Map this in route handlers (see `update_connection`).
- **DB sessions**: Always use `db: Session = Depends(get_db)` in route functions. **Exception:** The SSE streaming endpoint manages its own session via `SessionLocal()` inside the generator (because `Depends(get_db)` closes before `StreamingResponse` consumes the iterator).
- **UUID primary keys**: All models use `generate_uuid()` (string UUIDs), not auto-increment integers.
- **Query templates**: Jinja2 conditional blocks with `:param_name` SQLAlchemy named params. Rendered by `query_engine.py` with boolean-only Jinja2 context (security). Date range filters expand `param_name` to `:param_name_start` and `:param_name_end`.
- **Multi-agent pipeline**: 6 agents in `app/services/agents/` — `RequestAnalyzerAgent`, `SchemaAnalyzerAgent` (cached in `schema_analyses` table), `QueryBuilderAgent`, `FilterBuilderAgent`, `ChartBuilderAgent`, `SummarizerAgent`. Coordinated by `orchestrator.py`.
- **Filter options**: 3 modes in priority order — (1) `options_query` (custom SQL with JOINs), (2) `source_table`/`source_column` (simple DISTINCT), (3) static `options` JSON. Safety regex blocks non-SELECT in `options_query`.
- **Security**: `query_template` is excluded from `WidgetResponse` (uses `has_query` bool). Identifier regex validates table/column names. Numeric coercion via `_coerce_numeric()`.

## Frontend Patterns (`frontend/`)

- **API layer**: All backend calls go through `src/services/api.js` (axios instance with `/api` baseURL). SSE streaming uses native `fetch` + `ReadableStream` (`sendChatMessageStream()`). Vite proxies `/api` to the backend.
- **Chart rendering**: `src/components/ChartPreview.jsx` wraps Chart.js via react-chartjs-2. It maps `chart_config.x_axis`/`y_axis` to Chart.js dataset format.
- **AI chat**: `src/components/ChatPanel.jsx` includes `AgentProgress` component showing per-agent status (spinner → checkmark) during SSE streaming.
- **Filter bar**: `src/components/FilterBar.jsx` supports 6 filter types: `select` (with `SearchableSelect` for server-side search), `text`, `number`, `date`, `date_range`, `slider` (with `SliderField`).
- **Embed page** (`/widgets/:id/embed`): Renders **outside** the `<Layout>` component — no nav bar, minimal chrome, designed for iframe embedding.
- **Styling**: Tailwind 4 via `@tailwindcss/vite` plugin. CSS is just `@import "tailwindcss"` in `src/index.css`. No tailwind.config.js needed.
- **Component naming**: PascalCase `.jsx` files. Pages in `src/pages/`, reusable UI in `src/components/`.

## AI Multi-Agent Pipeline

The pipeline is coordinated by `orchestrator.py`. The request analyzer decides which agents to invoke:

```
User Message → [Summarizer] → Request Analyzer → Schema Analyzer → Query Builder → Filter Builder → Chart Builder → Merged Response
```

Each agent inherits from `BaseAgent` with a focused system prompt. The orchestrator merges outputs into the canonical format:
```json
{ "message": "...", "widget_update": { "chart_type": "...", "query_template": "...", "chart_config": {...} }, "filters": [...] }
```

The SSE streaming variant (`orchestrate_chat_stream`) emits `agent_start`/`agent_done` events so the UI shows real-time progress.

**Context summarization:** When chat history exceeds `context_token_limit` (default 64 000 tokens), the `SummarizerAgent` compresses the conversation. The summary is persisted in `Widget.chat_summary`.

## Key Files Reference

| Concern | File |
|---------|------|
| DB models (6 tables) | `backend/app/models.py` |
| API schemas (Pydantic) | `backend/app/schemas.py` |
| App config (env vars) | `backend/app/config.py` |
| MySQL introspection/query | `backend/app/services/db_connector.py` |
| Jinja2 query renderer | `backend/app/services/query_engine.py` |
| Agent orchestrator + SSE | `backend/app/services/agents/orchestrator.py` |
| Agent base class | `backend/app/services/agents/base.py` |
| Request analyzer agent | `backend/app/services/agents/request_analyzer.py` |
| Schema analyzer agent | `backend/app/services/agents/schema_analyzer.py` |
| Query builder agent | `backend/app/services/agents/query_builder.py` |
| Filter builder agent | `backend/app/services/agents/filter_builder.py` |
| Chart builder agent | `backend/app/services/agents/chart_builder.py` |
| Context summarizer agent | `backend/app/services/agents/summarizer.py` |
| Connection CRUD routes | `backend/app/routes/connections.py` |
| Widget CRUD + chat routes | `backend/app/routes/widgets.py` |
| Frontend API client + SSE | `frontend/src/services/api.js` |
| Chart rendering | `frontend/src/components/ChartPreview.jsx` |
| AI chat + agent progress | `frontend/src/components/ChatPanel.jsx` |
| Filter bar (6 types) | `frontend/src/components/FilterBar.jsx` |
| Widget editor (main page) | `frontend/src/pages/WidgetEditorPage.jsx` |
| Embed page (iframe) | `frontend/src/pages/WidgetEmbedPage.jsx` |
