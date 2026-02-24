# Architecture & Solution Design

## Overview

**Chart Widget Builder** is an application that allows users to create embeddable dashboard widgets through an AI-powered chat interface. Users connect to their MySQL databases, chat with a multi-agent AI pipeline that reads database schemas and generates SQL queries, chart configurations, and dynamic filters — all rendered in real-time as Chart.js visualisations.

## System Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                      Frontend (React 19 + Vite)                  │
│  ┌──────────────┐  ┌─────────────────────┐  ┌────────────────┐  │
│  │ Widget List   │  │ Widget Editor       │  │ Widget Embed   │  │
│  │ Page          │  │ + AI Chat (SSE)     │  │ (iframe)       │  │
│  └──────────────┘  └─────────────────────┘  └────────────────┘  │
└────────────────────────────┬─────────────────────────────────────┘
                             │  REST API + SSE streaming
                             │  (Vite proxy /api → :8000)
┌────────────────────────────▼─────────────────────────────────────┐
│                      Backend (FastAPI)                            │
│                                                                  │
│  ┌────────────────┐  ┌──────────────────┐  ┌─────────────────┐  │
│  │ Widget CRUD    │  │ DB Connector      │  │ Multi-Agent AI  │  │
│  │ + Chat Routes  │  │ Service           │  │ Pipeline        │  │
│  └───────┬────────┘  └────────┬─────────┘  └────────┬────────┘  │
│          │                    │                      │           │
│  ┌───────▼────────┐  ┌───────▼──────────┐  ┌────────▼───────┐  │
│  │ SQLite          │  │ Target MySQL     │  │ OpenAI API     │  │
│  │ (Config DB)     │  │ Database(s)      │  │ (gpt-4o-mini)  │  │
│  └────────────────┘  └──────────────────┘  └────────────────┘  │
│                                                                  │
│  ┌────────────────┐  ┌──────────────────┐                        │
│  │ Query Engine   │  │ Schema Analysis  │                        │
│  │ (Jinja2)       │  │ Cache            │                        │
│  └────────────────┘  └──────────────────┘                        │
└──────────────────────────────────────────────────────────────────┘
```

## Key Concepts

### Widget
A single chart/visualization unit that can be:
- Created and edited via AI chat
- Previewed in real-time with Chart.js
- Embedded in external websites via iframe
- Filtered dynamically with 6 filter types

### DB Connection
Configuration for connecting to a target MySQL database. Multiple widgets can share one connection. The backend introspects the schema and caches a semantic AI analysis (`SchemaAnalysis`) so subsequent chats don't need to re-analyse.

### Query Template (Jinja2)
SQL queries use **Jinja2 conditional blocks** for optional filters. This replaced the older `:param IS NULL OR ...` pattern for cleaner, more performant SQL:

```sql
SELECT category, SUM(amount) as total
FROM orders
WHERE 1=1
{% if date_start %} AND created_at >= :date_start {% endif %}
{% if status %} AND status = :status {% endif %}
GROUP BY category
ORDER BY total DESC
{% if limit %} LIMIT :limit {% endif %}
```

The `query_engine.py` service renders templates in a sandboxed Jinja2 environment. Only boolean context is passed to Jinja2 (never raw user input) for security.

### Widget Filter
Dynamic filters that allow end-users to filter chart data. Six types are supported:

| Type         | UI Control            | Query Mapping                        |
|--------------|-----------------------|--------------------------------------|
| `select`     | Dropdown (searchable) | `:param_name`                        |
| `text`       | Free-text input       | `:param_name`                        |
| `number`     | Numeric input         | `:param_name`                        |
| `date`       | Date picker           | `:param_name`                        |
| `date_range` | Two date pickers      | `:param_name_start`, `:param_name_end` |
| `slider`     | Range slider          | `:param_name` (requires `config`)    |

Select filters support three option modes:
1. **`options_query`** — custom SQL (supports JOINs) for complex lookups
2. **`source_table`/`source_column`** — simple `SELECT DISTINCT` from a single table
3. **Static `options`** — hardcoded value/label pairs

### Chart Configuration
JSON config that defines how data maps to a Chart.js visualisation:
- Chart type: `bar`, `line`, `pie`, `area`, `doughnut`, `scatter`
- Axis mappings (`x_axis`, `y_axis`)
- Colors, legend, title
- Chart.js `options` pass-through (e.g. `indexAxis`, scales)

## Multi-Agent AI Pipeline

The AI system uses a **6-agent pipeline** coordinated by an orchestrator. Each agent is a specialised LLM call with a focused prompt.

```
User Message
     │
     ▼
┌─────────────────────┐
│  0. Summarizer      │  ← compresses context when > 64 000 tokens
└─────────┬───────────┘
          ▼
┌─────────────────────┐
│  1. Request Analyzer│  ← classifies intent, decides which agents to invoke
└─────────┬───────────┘
          ▼
┌─────────────────────┐
│  2. Schema Analyzer │  ← semantic analysis of DB schema (cached in SQLite)
└─────────┬───────────┘
          ▼
┌─────────────────────┐
│  3. Query Builder   │  ← generates Jinja2 SQL template
└─────────┬───────────┘
          ▼
┌─────────────────────┐
│  4. Filter Builder  │  ← defines filters matching query params
└─────────┬───────────┘
          ▼
┌─────────────────────┐
│  5. Chart Builder   │  ← picks chart type + Chart.js config
└─────────┬───────────┘
          ▼
    Merged Response
```

**Agent details:**

| Agent              | Purpose                                                    | Cache |
|--------------------|------------------------------------------------------------|-------|
| `SummarizerAgent`  | Compresses long chat history when tokens exceed limit      | No    |
| `RequestAnalyzerAgent` | Classifies intent, decides routing flags              | No    |
| `SchemaAnalyzerAgent`  | Semantic schema summary (tables, relationships, metrics) | Yes — `schema_analyses` table |
| `QueryBuilderAgent`    | Generates Jinja2 SQL query template                    | No    |
| `FilterBuilderAgent`   | Defines filter objects + validates against query params | No    |
| `ChartBuilderAgent`    | Picks chart type, axis mapping, colors                 | No    |

### SSE Streaming

The chat endpoint has a streaming variant (`POST /api/widgets/{id}/chat/stream`) that emits Server-Sent Events:

- `agent_start` — agent begins processing
- `agent_done` — agent finished
- `result` — final merged response
- `done` — stream complete

The frontend displays an `AgentProgress` component showing real-time per-agent status (spinner → checkmark).

**Important:** The SSE endpoint manages its own DB session inside the generator (using `SessionLocal()` + `try/finally/db.close()`) because FastAPI's `Depends(get_db)` cleanup runs before `StreamingResponse` consumes the iterator.

## Data Flow

### Widget Creation Flow
1. User creates a new widget
2. User selects a DB connection (with search/filter/delete support)
3. Backend connects and reads schema (tables, columns, types, FKs)
4. Schema is semantically analysed by AI and cached
5. User chats with AI: "Show me monthly revenue as a bar chart"
6. Multi-agent pipeline generates: SQL template + chart config + filters
7. Frontend renders Chart.js preview in real-time
8. User iterates via chat until satisfied
9. Widget is saved and can be embedded

### Widget Embed Flow
1. External site includes `<iframe src="/widgets/{id}/embed">`
2. Frontend loads minimal embed page (no nav, no chat)
3. Backend renders Jinja2 query template with filter values
4. Query executes against target MySQL DB via `db_connector`
5. Data is rendered as chart with interactive filters
6. Filter changes re-fetch data via the `/data` endpoint

## Technology Stack

| Layer        | Technology                                  |
|--------------|---------------------------------------------|
| Frontend     | React 19.2, Vite 7.3, Tailwind CSS 4.2     |
| Charts       | Chart.js 4.5 + react-chartjs-2             |
| Routing      | React Router DOM v7                         |
| HTTP Client  | axios + native fetch (SSE)                  |
| Backend      | Python 3.13, FastAPI 0.115, uvicorn 0.34    |
| Config DB    | SQLite (via SQLAlchemy 2.0)                 |
| Target DB    | MySQL (via PyMySQL 1.1)                     |
| Query Engine | Jinja2 3.1 (sandboxed)                      |
| AI           | OpenAI API 1.59 (default: gpt-4o-mini)     |
| Validation   | Pydantic 2.10                               |

## API Endpoints

### Widget Endpoints

| Method | Path                                            | Description                             |
|--------|------------------------------------------------|-----------------------------------------|
| GET    | `/api/widgets`                                 | List all widgets                        |
| POST   | `/api/widgets`                                 | Create a new widget                     |
| GET    | `/api/widgets/{id}`                            | Get widget details                      |
| PUT    | `/api/widgets/{id}`                            | Update widget                           |
| DELETE | `/api/widgets/{id}`                            | Delete widget                           |
| GET    | `/api/widgets/{id}/data`                       | Execute query and return data           |
| GET    | `/api/widgets/{id}/chat`                       | Get chat history                        |
| POST   | `/api/widgets/{id}/chat`                       | Send chat message (sync)                |
| POST   | `/api/widgets/{id}/chat/stream`                | Send chat message (SSE streaming)       |
| GET    | `/api/widgets/{id}/filters/{fid}/options`      | Search filter options (server-side)     |
| DELETE | `/api/widgets/{id}/filters/{fid}`              | Delete a single filter                  |

### Connection Endpoints

| Method | Path                              | Description                      |
|--------|----------------------------------|----------------------------------|
| GET    | `/api/connections`               | List DB connections              |
| POST   | `/api/connections`               | Create DB connection             |
| GET    | `/api/connections/{id}`          | Get connection details           |
| PUT    | `/api/connections/{id}`          | Update connection                |
| DELETE | `/api/connections/{id}`          | Delete connection                |
| POST   | `/api/connections/{id}/test`     | Test DB connection               |
| GET    | `/api/connections/{id}/schema`   | Get DB schema (tables, columns)  |

## Project Structure

```
backend/
├── app/
│   ├── main.py              # FastAPI app factory, CORS, router mounts
│   ├── config.py            # pydantic-settings (env vars)
│   ├── database.py          # SQLite engine, SessionLocal, get_db
│   ├── models.py            # SQLAlchemy models (6 tables)
│   ├── schemas.py           # Pydantic request/response schemas
│   ├── routes/
│   │   ├── connections.py   # DB connection CRUD
│   │   └── widgets.py       # Widget CRUD + chat + data + filters
│   └── services/
│       ├── db_connector.py  # MySQL introspection & query execution
│       ├── query_engine.py  # Jinja2 SQL template renderer
│       └── agents/
│           ├── base.py           # BaseAgent (shared OpenAI call logic)
│           ├── orchestrator.py   # Pipeline coordinator + SSE streaming
│           ├── request_analyzer.py
│           ├── schema_analyzer.py
│           ├── query_builder.py
│           ├── filter_builder.py
│           ├── chart_builder.py
│           └── summarizer.py
├── .env                     # OPENAI_API_KEY, OPENAI_MODEL, etc.
└── venv/

frontend/
├── src/
│   ├── main.jsx             # React entry point
│   ├── App.jsx              # Router setup
│   ├── index.css            # Tailwind import
│   ├── components/
│   │   ├── Layout.jsx       # Nav bar wrapper
│   │   ├── ChartPreview.jsx # Chart.js rendering
│   │   ├── ChatPanel.jsx    # AI chat + AgentProgress
│   │   ├── FilterBar.jsx    # All 6 filter type components
│   │   └── ConnectionForm.jsx
│   ├── pages/
│   │   ├── WidgetListPage.jsx
│   │   ├── WidgetEditorPage.jsx  # Main editor (SSE chat integration)
│   │   └── WidgetEmbedPage.jsx   # Minimal iframe view
│   └── services/
│       └── api.js           # axios + SSE streaming client
└── vite.config.js           # Proxy /api → :8000
```

## Security Considerations

- **SQL Injection**: Jinja2 templates use boolean-only context (never raw user input). Actual query parameters are bound via SQLAlchemy `text()` with named params.
- **options_query safety**: Custom filter SQL (`options_query`) is validated with a regex that blocks non-SELECT statements.
- **Identifier validation**: Table/column names in dynamic queries are validated against `^[A-Za-z_][A-Za-z0-9_]{0,63}$`.
- **DB credentials**: Stored in SQLite `password_enc` column (not exposed in API responses).
- **Embed endpoints**: Public by widget UUID — no auth required.
- **CORS**: Configured for embed cross-origin usage.
- **query_template hidden**: The `WidgetResponse` schema excludes `query_template` to avoid exposing raw SQL to the browser. A `has_query` boolean is provided instead.
