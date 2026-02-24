# Chart Widget Builder

An AI-powered application for building embeddable dashboard chart widgets. Connect your MySQL databases, describe the chart you want in natural language, and get a ready-to-embed widget with interactive filters.

## Features

- **AI-Powered Chat** — Describe what you want in plain language; a multi-agent AI pipeline generates the SQL query, chart configuration, and filters automatically
- **6 Chart Types** — Bar, line, pie, doughnut, area, scatter (Chart.js)
- **6 Filter Types** — Select (with server-side search), text, number, date, date range, slider
- **Embeddable Widgets** — Embed any widget via `<iframe>` with zero dependencies
- **Real-Time Progress** — SSE streaming shows each AI agent's status as it works
- **Smart Schema Analysis** — AI analyzes your database structure once and caches it for fast subsequent chats
- **Context Summarization** — Long conversations are automatically compressed so the AI never loses context

## Architecture

```
Frontend (React 19 + Vite)  →  /api proxy  →  Backend (FastAPI + SQLite)
                                                     ↓
                                               Target MySQL DBs
                                               OpenAI API (gpt-4o-mini)
```

- **SQLite** stores app configuration (widgets, connections, chat history, schema analyses)
- **MySQL** is the target database users connect to for chart data
- **Multi-agent pipeline** (6 agents) generates SQL + chart config + filters from natural language

## Tech Stack

| Layer        | Technology                              |
|--------------|-----------------------------------------|
| Frontend     | React 19, Vite, Tailwind CSS 4          |
| Charts       | Chart.js + react-chartjs-2              |
| Routing      | React Router DOM v7                     |
| Backend      | Python 3.13, FastAPI, uvicorn           |
| Config DB    | SQLite (SQLAlchemy 2.0)                 |
| Target DB    | MySQL (PyMySQL)                         |
| Query Engine | Jinja2 (sandboxed)                      |
| AI           | OpenAI API (default: gpt-4o-mini)       |

## Getting Started

### Prerequisites

- Python 3.12+
- Node.js 18+
- A MySQL database to connect to
- An OpenAI API key

### Backend Setup

```bash
cd backend

# Create virtual environment
python -m venv venv
source venv/bin/activate   # Linux/macOS
# venv\Scripts\activate    # Windows

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env       # or create .env manually
```

Create a `.env` file in `backend/` with:

```env
OPENAI_API_KEY=sk-your-key-here
OPENAI_MODEL=gpt-4o-mini          # optional, default: gpt-4o-mini
CONTEXT_TOKEN_LIMIT=64000          # optional, default: 64000
DATABASE_URL=sqlite:///./chart_builder.db  # optional
CORS_ORIGINS=http://localhost:5173 # optional
```

Start the backend:

```bash
uvicorn app.main:app --reload --port 8000
```

API docs available at http://localhost:8000/docs

### Frontend Setup

```bash
cd frontend

# Install dependencies
npm install

# Start dev server (proxies /api → :8000)
npm run dev
```

Open http://localhost:5173

### Production Build

```bash
cd frontend
npm run build   # Output in dist/
```

## Usage

1. **Create a widget** from the widget list page
2. **Add a database connection** — provide your MySQL host, port, credentials, and database name
3. **Chat with the AI** — describe what chart you want:
   > "Show me monthly revenue as a bar chart with a date range filter"
4. **Preview** the chart in real-time as the AI builds it
5. **Embed** the widget anywhere:

```html
<iframe
  src="https://your-host/widgets/{widget-id}/embed"
  width="600"
  height="400"
  frameborder="0">
</iframe>
```

## AI Pipeline

The system uses 6 specialized AI agents coordinated by an orchestrator:

```
User Message → Summarizer → Request Analyzer → Schema Analyzer → Query Builder → Filter Builder → Chart Builder → Response
```

| Agent             | Purpose                                            |
|-------------------|----------------------------------------------------|
| Summarizer        | Compresses long chat history (> 64K tokens)        |
| Request Analyzer  | Classifies intent, decides which agents to invoke  |
| Schema Analyzer   | Semantic DB schema analysis (cached)               |
| Query Builder     | Generates Jinja2 SQL query template                |
| Filter Builder    | Defines filters matching query parameters          |
| Chart Builder     | Picks chart type, axis mapping, colors             |

## Project Structure

```
backend/
├── app/
│   ├── main.py                  # FastAPI app, CORS, router mounts
│   ├── config.py                # Environment settings
│   ├── database.py              # SQLite engine, session
│   ├── models.py                # 6 SQLAlchemy models
│   ├── schemas.py               # Pydantic request/response schemas
│   ├── routes/
│   │   ├── connections.py       # DB connection CRUD
│   │   └── widgets.py           # Widget CRUD, chat, data, filters
│   └── services/
│       ├── db_connector.py      # MySQL introspection & query execution
│       ├── query_engine.py      # Jinja2 SQL template renderer
│       └── agents/
│           ├── base.py          # BaseAgent (shared OpenAI logic)
│           ├── orchestrator.py  # Pipeline coordinator + SSE
│           ├── request_analyzer.py
│           ├── schema_analyzer.py
│           ├── query_builder.py
│           ├── filter_builder.py
│           ├── chart_builder.py
│           └── summarizer.py
└── .env

frontend/
├── src/
│   ├── App.jsx                  # Router setup
│   ├── components/
│   │   ├── ChartPreview.jsx     # Chart.js rendering
│   │   ├── ChatPanel.jsx        # AI chat + agent progress
│   │   ├── FilterBar.jsx        # 6 filter type components
│   │   ├── ConnectionForm.jsx   # DB connection form
│   │   └── Layout.jsx           # Nav bar wrapper
│   ├── pages/
│   │   ├── WidgetListPage.jsx   # Widget list
│   │   ├── WidgetEditorPage.jsx # Main editor with SSE chat
│   │   └── WidgetEmbedPage.jsx  # Minimal iframe view
│   └── services/
│       └── api.js               # axios + SSE streaming client
└── vite.config.js
```

## API Endpoints

### Widgets

| Method | Path                                       | Description                        |
|--------|--------------------------------------------|------------------------------------|
| GET    | `/api/widgets`                             | List all widgets                   |
| POST   | `/api/widgets`                             | Create widget                      |
| GET    | `/api/widgets/{id}`                        | Get widget                         |
| PUT    | `/api/widgets/{id}`                        | Update widget                      |
| DELETE | `/api/widgets/{id}`                        | Delete widget                      |
| GET    | `/api/widgets/{id}/data`                   | Execute query, return data         |
| GET    | `/api/widgets/{id}/chat`                   | Get chat history                   |
| POST   | `/api/widgets/{id}/chat`                   | Send chat message (sync)           |
| POST   | `/api/widgets/{id}/chat/stream`            | Send chat message (SSE)            |
| GET    | `/api/widgets/{id}/filters/{fid}/options`  | Search filter options              |
| DELETE | `/api/widgets/{id}/filters/{fid}`          | Delete a filter                    |

### Connections

| Method | Path                            | Description            |
|--------|---------------------------------|------------------------|
| GET    | `/api/connections`              | List connections       |
| POST   | `/api/connections`              | Create connection      |
| GET    | `/api/connections/{id}`         | Get connection         |
| PUT    | `/api/connections/{id}`         | Update connection      |
| DELETE | `/api/connections/{id}`         | Delete connection      |
| POST   | `/api/connections/{id}/test`    | Test connection        |
| GET    | `/api/connections/{id}/schema`  | Get DB schema          |

## Documentation

- [Architecture & Solution Design](docs/ARCHITECTURE.md)
- [Database Schema](docs/DB_SCHEMA.md)
- [Widget Configuration Guide](docs/WIDGET_CONFIG.md)
- [Development TODO](docs/TODO.md)

## License

MIT
