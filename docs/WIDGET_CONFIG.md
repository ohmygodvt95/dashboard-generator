# Widget Configuration Guide

## How Widget Config is Stored

Each widget's visual representation is stored as a combination of:

1. **`chart_type`** — The type of chart (`bar`, `line`, `pie`, `area`, `doughnut`, `scatter`)
2. **`query_template`** — Jinja2 SQL template with conditional filter blocks
3. **`chart_config`** — JSON object configuring how data maps to the chart
4. **`layout_config`** — JSON object for layout/sizing
5. **`widget_filters`** — Related filter records (6 types) for dynamic parameters
6. **`chat_summary`** — Compressed conversation summary (for long chat histories)

## Chart Types Supported

| Type      | Description                  | Use Case                        |
|-----------|-----------------------------|---------------------------------|
| bar       | Vertical bar chart          | Comparing categories            |
| line      | Line chart                  | Trends over time                |
| pie       | Pie chart                   | Proportions                     |
| doughnut  | Doughnut chart              | Proportions (with center space) |
| area      | Area chart (filled line)    | Volume over time                |
| scatter   | Scatter plot                | Correlation between variables   |

## Multi-Agent AI Chat Workflow

### Step 1: Connect Database
User selects (or creates) a MySQL connection. The system:
- Tests the connection
- Introspects all tables, columns, types, and foreign keys
- Runs the `SchemaAnalyzerAgent` to generate a semantic summary
- Caches the analysis in `schema_analyses` (invalidated on schema changes)

### Step 2: Chat with AI (Multi-Agent Pipeline)
The user's message is processed by a **6-agent pipeline**:

1. **Summarizer** — compresses context if chat history exceeds 64 000 tokens
2. **Request Analyzer** — classifies intent, decides which agents to invoke
3. **Schema Analyzer** — provides semantic DB understanding (cached)
4. **Query Builder** — generates Jinja2 SQL query template
5. **Filter Builder** — defines filter objects matching query parameters
6. **Chart Builder** — picks chart type, axis mapping, colors

Each agent runs independently and results are merged into a single response.

### Real-Time Progress (SSE Streaming)
The preferred chat endpoint (`POST /api/widgets/{id}/chat/stream`) uses Server-Sent Events:

```
event: agent_start
data: {"agent": "request_analyzer", "label": "Analyzing request…", "step": 1}

event: agent_done
data: {"agent": "request_analyzer", "step": 1, "summary": "User wants a bar chart"}

event: agent_start
data: {"agent": "query_builder", "label": "Building SQL query…", "step": 2}

event: agent_done
data: {"agent": "query_builder", "step": 2}

event: result
data: {"message": "...", "widget_update": {...}, "filters": [...]}

event: done
data: {}
```

The frontend displays an `AgentProgress` component with per-agent status (spinner → checkmark).

### Example Conversation

```
User: "Show me the top 10 products by revenue as a bar chart"
AI: Generates Jinja2 SQL + chart config + suggests filters

User: "Add a date range filter and change colors to blue"
AI: Updates query with date parameters + updates colors

User: "Make it a horizontal bar chart instead"
AI: Updates chart config orientation (indexAxis: "y")
```

### Step 3: AI Response Format

The merged pipeline response:
```json
{
  "message": "📊 Query: Fetching top 10 products...\n📈 Chart: Horizontal bar chart\n🔍 Filters: Date range + category",
  "widget_update": {
    "chart_type": "bar",
    "query_template": "SELECT p.name, SUM(o.amount) as revenue\nFROM orders o\nJOIN products p ON o.product_id = p.id\nWHERE 1=1\n{% if date_start %} AND o.created_at >= :date_start {% endif %}\n{% if date_end %} AND o.created_at <= :date_end {% endif %}\nGROUP BY p.name\nORDER BY revenue DESC\nLIMIT 10",
    "chart_config": {
      "x_axis": "name",
      "y_axis": "revenue",
      "colors": ["#3B82F6"],
      "title": { "display": true, "text": "Top 10 Products by Revenue" },
      "indexAxis": "y"
    }
  },
  "filters": [
    {
      "param_name": "date",
      "label": "Date Range",
      "filter_type": "date_range",
      "default_value": null
    }
  ]
}
```

## Jinja2 Query Templates

Query templates use **Jinja2 conditional blocks** so filters are only included when the user provides a value:

```sql
SELECT category, SUM(amount) as total
FROM orders
WHERE 1=1
{% if date_start %} AND created_at >= :date_start {% endif %}
{% if date_end %} AND created_at <= :date_end {% endif %}
{% if status %} AND status = :status {% endif %}
{% if category %} AND category = :category {% endif %}
GROUP BY category
ORDER BY total DESC
{% if limit %} LIMIT :limit {% endif %}
```

**Security:** The query engine passes only **boolean** context to Jinja2 — actual parameter values are never evaluated as Jinja2 expressions. Values are bound via SQLAlchemy's `text()` named parameters.

**Backward compatibility:** Old-style `:param IS NULL OR ...` queries still work. The engine detects whether a template uses Jinja2 syntax and handles both formats.

## Embed Configuration

When embedding, the widget URL supports query parameters for initial filter values:

```html
<iframe
  src="https://app.example.com/widgets/{id}/embed?date_start=2025-01-01&date_end=2025-12-31&status=completed"
  width="600"
  height="400"
  frameborder="0">
</iframe>
```

## Filter Configuration Details

### Select Filter (Dynamic — `source_table`/`source_column`)
```json
{
  "param_name": "category",
  "label": "Category",
  "filter_type": "select",
  "source_table": "categories",
  "source_column": "name",
  "default_value": null,
  "options": null
}
```
Options are dynamically loaded from the target DB via `SELECT DISTINCT`.

### Select Filter (Dynamic — `options_query` with JOINs)
```json
{
  "param_name": "product",
  "label": "Product",
  "filter_type": "select",
  "options_query": "SELECT p.id AS value, CONCAT(p.name, ' (', c.name, ')') AS label FROM products p JOIN categories c ON p.category_id = c.id WHERE p.active = 1 ORDER BY p.name",
  "default_value": null
}
```
Custom SQL allows complex lookups with JOINs. Must be a SELECT statement (validated by regex).

Server-side search is supported: `GET /api/widgets/{id}/filters/{fid}/options?search=term&limit=50`

### Static Select Filter
```json
{
  "param_name": "status",
  "label": "Status",
  "filter_type": "select",
  "source_table": null,
  "source_column": null,
  "default_value": "active",
  "options": [
    {"value": "active", "label": "Active"},
    {"value": "inactive", "label": "Inactive"}
  ]
}
```

### Text Filter
```json
{
  "param_name": "search",
  "label": "Search",
  "filter_type": "text",
  "default_value": null
}
```

### Number Filter
```json
{
  "param_name": "limit",
  "label": "Limit",
  "filter_type": "number",
  "default_value": "10"
}
```
Numeric strings are auto-coerced to `int`/`float` at query time.

### Date Filter
```json
{
  "param_name": "snapshot_date",
  "label": "Snapshot Date",
  "filter_type": "date",
  "default_value": null
}
```

### Date Range Filter
```json
{
  "param_name": "date",
  "label": "Date Range",
  "filter_type": "date_range",
  "default_value": null
}
```
Generates **two** query parameters: `:date_start` and `:date_end`. The query template must use both:
```sql
{% if date_start %} AND created_at >= :date_start {% endif %}
{% if date_end %} AND created_at <= :date_end {% endif %}
```

### Slider Filter
```json
{
  "param_name": "price",
  "label": "Max Price",
  "filter_type": "slider",
  "default_value": "500",
  "config": {
    "min": 0,
    "max": 1000,
    "step": 10
  }
}
```
The `config` field is **required** for slider type and defines the slider bounds and step size.

## Context Summarization

When chat history exceeds the token limit (default: 64 000 tokens), the `SummarizerAgent` compresses the conversation:

1. Estimates token count of full chat history
2. If over limit, calls the AI to generate a concise summary
3. Replaces history with: `[summary message]` + last 4 messages
4. Persists the summary in `Widget.chat_summary` for reuse across sessions

This ensures long-running conversations don't exceed the AI model's context window.
