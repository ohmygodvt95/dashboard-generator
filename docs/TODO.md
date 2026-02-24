# TODO - Chart Widget Builder

## Phase 1: Documentation & Design
- [x] Solution architecture document
- [x] Database schema design
- [x] Widget configuration guide
- [x] TODO task list

## Phase 2: Backend Setup
- [x] Initialize Python project structure
- [x] Setup FastAPI with dependencies (fastapi, uvicorn, sqlalchemy, pymysql)
- [x] Configure SQLite database with SQLAlchemy models
- [x] Implement database migration/init script
- [x] Setup CORS middleware

## Phase 3: Backend API Implementation
- [x] DB Connections CRUD API (`/api/connections`)
- [x] Connection test endpoint (`/api/connections/{id}/test`)
- [x] Schema introspection endpoint (`/api/connections/{id}/schema`)
- [x] Widgets CRUD API (`/api/widgets`)
- [x] Widget data endpoint (`/api/widgets/{id}/data`)
- [x] AI Chat endpoint (`/api/widgets/{id}/chat`)
- [x] Chat history endpoint (`/api/widgets/{id}/chat` GET)
- [x] Widget filters API

## Phase 4: Frontend Setup
- [x] Initialize React 19 + Vite project
- [x] Install and configure Tailwind CSS 4
- [x] Setup React Router v7
- [x] Configure project structure (components, pages, services, hooks)
- [x] Setup API service layer (axios/fetch)

## Phase 5: Frontend Pages
- [x] Widget List page (`/widgets`) — list, create, delete
- [x] Widget Editor page (`/widgets/{id}`) — AI chat + preview + DB config
- [x] Widget Embed page (`/widgets/{id}/embed`) — minimal iframe view
- [x] Chat UI component
- [x] Chart preview component (Chart.js)
- [x] DB connection config form
- [x] Filter components (select, date, date_range, text, number)

## Phase 6: Integration & Polish
- [x] Connect frontend to backend APIs
- [x] End-to-end widget creation flow
- [x] Embed iframe testing
- [x] Error handling and loading states
- [x] Responsive design for embed view

## Phase 7: Dynamic Query Engine
- [x] Implement Jinja2-based query template engine (`query_engine.py`)
- [x] Backward compatibility with old-style `:param IS NULL OR` queries
- [x] Update widget data endpoint to use `render_query()`
- [x] Update AI SYSTEM_PROMPT with Jinja2 template rules & examples
- [x] Verify existing widgets work with the new engine

## Phase 8: Multi-Agent AI Pipeline
- [x] Create `BaseAgent` class with shared OpenAI call logic
- [x] Implement `RequestAnalyzerAgent` — intent classification & routing
- [x] Implement `SchemaAnalyzerAgent` — semantic schema analysis + caching (`schema_analyses` table)
- [x] Implement `QueryBuilderAgent` — Jinja2 SQL template generation
- [x] Implement `FilterBuilderAgent` — filter definitions + query param validation
- [x] Implement `ChartBuilderAgent` — chart type + Chart.js config
- [x] Implement `orchestrator.py` — pipeline coordinator + result merger
- [x] Replace legacy `ai_chat.chat_with_ai()` with orchestrator

## Phase 9: SSE Streaming & Context Summarization
- [x] Implement `orchestrate_chat_stream()` SSE generator in orchestrator
- [x] Add SSE streaming endpoint (`POST /api/widgets/{id}/chat/stream`)
- [x] Fix DB session lifecycle for SSE (manage inside generator, not `Depends`)
- [x] Frontend SSE client in `api.js` (`sendChatMessageStream()`)
- [x] `AgentProgress` component in `ChatPanel.jsx` (spinner → checkmark)
- [x] Implement `SummarizerAgent` — compress context when > 64 000 tokens
- [x] Persist `chat_summary` on Widget model

## Phase 10: Advanced Filters
- [x] Add `slider` filter type with `config` column (min/max/step)
- [x] Add `options_query` column for custom SELECT with JOINs
- [x] Server-side filter options search API (`GET .../filters/{fid}/options?search=`)
- [x] `SearchableSelect` component with server-side search
- [x] `SliderField` component in `FilterBar.jsx`
- [x] Delete individual filter API + UI (`DELETE .../filters/{fid}`)
- [x] Update filter_builder AI prompt with all 6 filter types
- [x] 3-mode filter options in `db_connector.py` (options_query → DISTINCT → static)

## Phase 11: UX & Bug Fixes
- [x] Connection selector with search, filter, delete
- [x] Fix `/data?limit=2` 500 error (`_coerce_numeric` helper)
- [x] Fix `date_range` initialization crash (safe type checking)
- [x] Fix OpenAI 400 error (missing "json" keyword in prompt)
- [x] Refactor chat endpoint to use `_apply_ai_response()` helper
- [x] Security: `query_template` excluded from API responses (`has_query` flag)
- [x] Security: identifier validation regex for dynamic SQL
