# Database Schema

## Overview

The application uses **SQLite** to store widget configurations, DB connections, chat history, filter definitions, widget styles, and cached schema analyses. The target databases (MySQL) are connected at runtime to fetch chart data.

There are **6 tables** in total, all using UUID string primary keys (`generate_uuid()`).

## ER Diagram

```
┌──────────────────┐       ┌──────────────────────────┐
│  db_connections   │       │         widgets           │
├──────────────────┤       ├──────────────────────────┤
│ id (PK, UUID)    │◄──┬───│ connection_id (FK)        │
│ name             │   │   │ id (PK, UUID)             │
│ host             │   │   │ name                      │
│ port             │   │   │ description               │
│ username         │   │   │ chart_type                │
│ password_enc     │   │   │ query_template            │
│ database_name    │   │   │ chart_config (JSON)       │
│ created_at       │   │   │ layout_config (JSON)      │
│ updated_at       │   │   │ is_active                 │
└──────────────────┘   │   │ chat_summary              │
                       │   │ created_at                │
         ┌─────────────┘   │ updated_at                │
         │                 └────────────┬──────────────┘
         │                              │
         │        ┌─────────────────────┼───────────────────┐
         │        │                     │                   │
         │  ┌─────▼───────────┐  ┌──────▼────────┐  ┌──────▼─────────┐
         │  │ widget_filters   │  │ chat_messages  │  │ widget_styles   │
         │  ├─────────────────┤  ├───────────────┤  ├────────────────┤
         │  │ id (PK, UUID)   │  │ id (PK, UUID) │  │ id (PK, UUID)  │
         │  │ widget_id (FK)  │  │ widget_id (FK)│  │ widget_id (FK) │
         │  │ param_name      │  │ role          │  │ theme (JSON)   │
         │  │ label           │  │ content       │  │ custom_css     │
         │  │ filter_type     │  │ metadata_json │  │ created_at     │
         │  │ source_table    │  │  (JSON)       │  │ updated_at     │
         │  │ source_column   │  │ created_at    │  └────────────────┘
         │  │ options_query   │  └───────────────┘
         │  │ default_value   │
         │  │ config (JSON)   │
         │  │ options (JSON)  │
         │  │ is_required     │
         │  │ sort_order      │
         │  │ created_at      │
         │  │ updated_at      │
         │  └─────────────────┘
         │
   ┌─────▼──────────────┐
   │  schema_analyses    │
   ├────────────────────┤
   │ id (PK, UUID)      │
   │ connection_id (FK, │
   │   unique)          │
   │ analysis (JSON)    │
   │ schema_hash        │
   │ created_at         │
   │ updated_at         │
   └────────────────────┘
```

## Table Definitions

### `db_connections`

Stores MySQL connection configurations.

| Column        | Type         | Default     | Description                          |
|--------------|--------------|-------------|--------------------------------------|
| id           | TEXT (UUID)   | `uuid4()`   | Primary key                          |
| name         | TEXT(255)     |             | Display name for the connection      |
| host         | TEXT(255)     | `localhost` | MySQL host address                   |
| port         | INTEGER       | `3306`      | MySQL port                           |
| username     | TEXT(255)     |             | MySQL username                       |
| password_enc | TEXT          | `""`        | Password (stored as-is, not exposed in API) |
| database_name| TEXT(255)     |             | Target database name                 |
| created_at   | DATETIME      | `utcnow()`  | Record creation timestamp            |
| updated_at   | DATETIME      | `utcnow()`  | Last update timestamp (auto-update)  |

**Relationships:** Has many `widgets`, has one `schema_analyses`.

### `widgets`

Main widget configuration table.

| Column         | Type         | Default    | Description                                  |
|---------------|--------------|------------|----------------------------------------------|
| id            | TEXT (UUID)   | `uuid4()`  | Primary key                                  |
| connection_id | TEXT (UUID)   | `NULL`     | FK to `db_connections`                       |
| name          | TEXT(255)     |            | Widget display name                          |
| description   | TEXT          | `""`       | Widget description                           |
| chart_type    | TEXT(50)      | `"bar"`    | Chart type: bar, line, pie, area, doughnut, scatter |
| query_template| TEXT          | `""`       | Jinja2 SQL query template                    |
| chart_config  | TEXT (JSON)   | `"{}"`     | Chart.js configuration object                |
| layout_config | TEXT (JSON)   | `"{}"`     | Layout settings (width, height, padding)     |
| is_active     | BOOLEAN       | `false`    | Whether widget is active/published           |
| chat_summary  | TEXT          | `NULL`     | Compressed chat history summary (for long conversations) |
| created_at    | DATETIME      | `utcnow()` | Record creation timestamp                    |
| updated_at    | DATETIME      | `utcnow()` | Last update timestamp (auto-update)          |

**Relationships:** Belongs to `db_connections`. Has many `widget_filters`, `chat_messages`. Has one `widget_styles`.

**Note:** `query_template` is **not** exposed in the API response (`WidgetResponse` schema). A `has_query` boolean is provided instead to prevent raw SQL from reaching the browser.

#### `chart_config` JSON Structure

```json
{
  "x_axis": "category",
  "y_axis": "total",
  "colors": ["#3B82F6", "#EF4444", "#10B981"],
  "legend": { "display": true, "position": "top" },
  "title": { "display": true, "text": "Monthly Revenue" },
  "options": {}
}
```

#### `layout_config` JSON Structure

```json
{
  "width": "100%",
  "height": "400px",
  "padding": "16px",
  "background_color": "#ffffff"
}
```

### `widget_filters`

Defines dynamic filters for each widget. Filters correspond to parameters in the Jinja2 `query_template`.

| Column        | Type         | Default  | Description                                          |
|--------------|--------------|----------|------------------------------------------------------|
| id           | TEXT (UUID)   | `uuid4()`| Primary key                                          |
| widget_id    | TEXT (UUID)   |          | FK to `widgets`                                      |
| param_name   | TEXT(100)     |          | Parameter name matching query placeholder            |
| label        | TEXT(255)     |          | Display label for the filter                         |
| filter_type  | TEXT(50)      | `"text"` | Type: `select`, `text`, `number`, `date`, `date_range`, `slider` |
| source_table | TEXT(255)     | `NULL`   | Table to fetch options from (for simple select)      |
| source_column| TEXT(255)     | `NULL`   | Column to fetch options from                         |
| options_query| TEXT          | `NULL`   | Custom SQL for options (supports JOINs)              |
| default_value| TEXT          | `NULL`   | Default value for the filter                         |
| config       | TEXT (JSON)   | `"{}"`   | Type-specific config (e.g. slider min/max/step)      |
| options      | TEXT (JSON)   | `"[]"`   | Static options array                                 |
| is_required  | BOOLEAN       | `false`  | Whether filter is required                           |
| sort_order   | INTEGER       | `0`      | Display order                                        |
| created_at   | DATETIME      | `utcnow()`| Record creation timestamp                           |
| updated_at   | DATETIME      | `utcnow()`| Last update timestamp (auto-update)                 |

#### Filter Types

- **`select`**: Dropdown populated dynamically. Options fetched via:
  1. `options_query` — custom SQL (e.g. `SELECT id AS value, name AS label FROM categories WHERE active = 1`)
  2. `source_table` + `source_column` — simple `SELECT DISTINCT source_column FROM source_table`
  3. Static `options` JSON array — `[{"value": "a", "label": "A"}, ...]`
  
  Supports server-side search via `GET /api/widgets/{id}/filters/{fid}/options?search=term`.

- **`text`**: Free text input → `:param_name`
- **`number`**: Numeric input → `:param_name`. Strings are coerced to int/float at query time.
- **`date`**: Single date picker → `:param_name`
- **`date_range`**: Two date pickers → `:param_name_start` and `:param_name_end`. One filter entry, two query params.
- **`slider`**: Range slider → `:param_name`. Requires `config` JSON:
  ```json
  { "min": 0, "max": 1000, "step": 10 }
  ```

#### Filter Option Modes (Select Type)

| Priority | Source          | Description                                      |
|----------|-----------------|--------------------------------------------------|
| 1        | `options_query` | Custom SQL query (must be SELECT-only, validated) |
| 2        | `source_table`/`source_column` | Auto-generates `SELECT DISTINCT ...`  |
| 3        | `options` (JSON)| Static value/label pairs stored in the filter    |

### `chat_messages`

Stores AI chat conversation history per widget.

| Column       | Type         | Default    | Description                                    |
|-------------|--------------|------------|------------------------------------------------|
| id          | TEXT (UUID)   | `uuid4()`  | Primary key                                    |
| widget_id   | TEXT (UUID)   |            | FK to `widgets`                                |
| role        | TEXT(20)      |            | Message role: `user`, `assistant`, `system`    |
| content     | TEXT          |            | Message content                                |
| metadata_json| TEXT (JSON)  | `"{}"`     | Extra data (applied changes, agent outputs)    |
| created_at  | DATETIME      | `utcnow()` | Message timestamp                              |

### `widget_styles`

Optional custom styling for widgets.

| Column     | Type         | Default    | Description                     |
|-----------|--------------|------------|---------------------------------|
| id        | TEXT (UUID)   | `uuid4()`  | Primary key                     |
| widget_id | TEXT (UUID)   |            | FK to `widgets` (unique)        |
| theme     | TEXT (JSON)   | `"{}"`     | Theme configuration             |
| custom_css| TEXT          | `""`       | Custom CSS for the widget       |
| created_at| DATETIME      | `utcnow()` | Record creation timestamp       |
| updated_at| DATETIME      | `utcnow()` | Last update timestamp           |

### `schema_analyses`

Cached AI-generated semantic analysis of a database schema. Invalidated when the underlying schema changes (via `schema_hash`).

| Column        | Type         | Default    | Description                                    |
|--------------|--------------|------------|------------------------------------------------|
| id           | TEXT (UUID)   | `uuid4()`  | Primary key                                    |
| connection_id| TEXT (UUID)   |            | FK to `db_connections` (unique)                |
| analysis     | TEXT (JSON)   | `"{}"`     | AI-generated schema summary (tables, relationships, metrics) |
| schema_hash  | TEXT(64)      |            | Hash of the raw schema for cache invalidation  |
| created_at   | DATETIME      | `utcnow()` | Record creation timestamp                      |
| updated_at   | DATETIME      | `utcnow()` | Last update timestamp                          |

## Query Template System

Query templates use **Jinja2 conditional blocks** with `:param_name` SQLAlchemy-style named parameters:

```sql
-- Example: Sales by category with optional filters
SELECT
    category,
    SUM(amount) as total_sales
FROM orders
WHERE 1=1
{% if date_start %} AND created_at >= :date_start {% endif %}
{% if date_end %} AND created_at <= :date_end {% endif %}
{% if status %} AND status = :status {% endif %}
GROUP BY category
ORDER BY total_sales DESC
{% if limit %} LIMIT :limit {% endif %}
```

The `query_engine.py` service:
1. Passes **boolean-only** context to Jinja2 (security: user input is never evaluated as Jinja2 expressions)
2. Renders the template to strip unused conditional blocks
3. Extracts `:param_name` placeholders from the rendered SQL
4. Returns only the params that appear in the final SQL (with numeric coercion)

The corresponding `widget_filters` would define:
- `date_range` filter with `param_name: "date"` → generates `date_start` and `date_end`
- `select` filter with `param_name: "status"`, `source_table: "orders"`, `source_column: "status"`

## Schema Introspection & Caching

When a DB connection is established, the backend:
1. Reads all table names, column names/types/nullable/PKs, and foreign key relationships
2. The `SchemaAnalyzerAgent` generates a semantic analysis (table descriptions, relationships, suggested metrics)
3. The analysis is stored in `schema_analyses` with a `schema_hash`
4. Subsequent chat sessions reuse the cached analysis if the schema hasn't changed
