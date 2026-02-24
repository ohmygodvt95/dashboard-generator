"""
Database connector service for target MySQL databases.

Provides schema introspection and query execution against
user-configured MySQL databases.
"""

import json
import re
from typing import List, Dict, Any, Optional
from urllib.parse import quote_plus
from sqlalchemy import create_engine, text, inspect
from sqlalchemy.orm import Session

from app.models import DBConnection, WidgetFilter

# Strict whitelist: table/column names must be plain
# identifiers (letters, digits, underscores).
_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,63}$")


def _get_mysql_url(conn: DBConnection) -> str:
    """
    Build a MySQL connection URL from a DBConnection model.

    Parameters:
        conn (DBConnection): The database connection configuration.

    Returns:
        str: SQLAlchemy-compatible MySQL connection URL.
    """
    password = quote_plus(conn.password_enc or "")
    return (
        f"mysql+pymysql://{conn.username}:{password}"
        f"@{conn.host}:{conn.port}/{conn.database_name}"
    )


def test_connection(conn: DBConnection) -> Dict[str, Any]:
    """
    Test a MySQL database connection.

    Parameters:
        conn (DBConnection): The connection configuration to test.

    Returns:
        dict: Result with 'success' (bool) and 'message' (str).
    """
    try:
        engine = create_engine(
            _get_mysql_url(conn),
            connect_args={"connect_timeout": 5},
        )
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        engine.dispose()
        return {
            "success": True,
            "message": "Connection successful",
        }
    except Exception as e:
        return {
            "success": False,
            "message": f"Connection failed: {str(e)}",
        }


def get_schema(conn: DBConnection) -> Dict[str, Any]:
    """
    Introspect the target MySQL database schema.

    Reads all tables, columns, their types, nullability,
    and primary key status.

    Parameters:
        conn (DBConnection): The connection configuration.

    Returns:
        dict: Schema info with 'database' and 'tables' keys.
    """
    engine = create_engine(_get_mysql_url(conn))
    try:
        inspector = inspect(engine)
        tables = []
        for table_name in inspector.get_table_names():
            columns = []
            pk_constraint = inspector.get_pk_constraint(table_name)
            pk_columns = (
                pk_constraint.get("constrained_columns", [])
                if isinstance(pk_constraint, dict)
                else []
            )
            for col in inspector.get_columns(table_name):
                columns.append({
                    "name": col["name"],
                    "type": str(col["type"]),
                    "nullable": col.get("nullable", True),
                    "primary_key": col["name"] in pk_columns,
                })

            # Foreign key relationships
            foreign_keys = []
            for fk in inspector.get_foreign_keys(table_name):
                foreign_keys.append({
                    "columns": fk.get(
                        "constrained_columns", []
                    ),
                    "referred_table": fk.get(
                        "referred_table", ""
                    ),
                    "referred_columns": fk.get(
                        "referred_columns", []
                    ),
                })

            tables.append({
                "name": table_name,
                "columns": columns,
                "foreign_keys": foreign_keys,
            })
        return {
            "database": conn.database_name,
            "tables": tables,
        }
    finally:
        engine.dispose()


def execute_query(
    conn: DBConnection,
    query: str,
    params: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    """
    Execute a SQL query against the target MySQL database.

    Parameters:
        conn (DBConnection): The connection configuration.
        query (str): SQL query with named parameters.
        params (dict, optional): Parameter values for the query.

    Returns:
        list[dict]: Query results as a list of dictionaries.
    """
    engine = create_engine(_get_mysql_url(conn))
    try:
        with engine.connect() as connection:
            result = connection.execute(
                text(query),
                params or {},
            )
            columns = list(result.keys())
            rows = [
                dict(zip(columns, row))
                for row in result.fetchall()
            ]
            return rows
    finally:
        engine.dispose()


def get_filter_options(
    conn: DBConnection,
    widget_filter: WidgetFilter,
    search: Optional[str] = None,
    limit: int = 50,
) -> List[Dict[str, str]]:
    """
    Fetch dynamic filter options from the target database.

    Supports three modes:
    1. ``options_query`` — a custom SQL SELECT that returns
       ``value`` and ``label`` columns (may contain JOINs).
    2. ``source_table`` + ``source_column`` — simple
       ``SELECT DISTINCT`` from a single table.
    3. Static ``options`` JSON stored on the filter itself.

    All modes support optional ``search`` filtering and
    ``limit`` capping.

    Parameters:
        conn (DBConnection): The connection configuration.
        widget_filter (WidgetFilter): The filter definition.
        search (str, optional): Search term to filter options.
        limit (int): Maximum number of options to return.

    Returns:
        list[dict]: Options with 'value' and 'label' keys.
    """
    # Cap limit to a reasonable maximum
    limit = min(limit, 500)

    # --- Mode 1: custom options_query ----------------------------
    if widget_filter.options_query:
        return _run_options_query(
            conn, widget_filter.options_query,
            search=search, limit=limit,
        )

    # --- Mode 2: simple source_table / source_column -------------
    if (
        widget_filter.source_table
        and widget_filter.source_column
    ):
        return _run_simple_distinct(
            conn,
            widget_filter.source_table,
            widget_filter.source_column,
            search=search,
            limit=limit,
        )

    # --- Mode 3: static options ----------------------------------
    try:
        options = json.loads(
            widget_filter.options or "[]"
        )
    except (json.JSONDecodeError, TypeError):
        options = []
    if search:
        term = search.lower()
        options = [
            o for o in options
            if term in str(o.get("label", "")).lower()
        ]
    return options[:limit]


# ----- private helpers -----------------------------------------------

# Only SELECT is allowed in options_query.
_OPTIONS_QUERY_BLOCK_RE = re.compile(
    r"\b(DROP|DELETE|TRUNCATE|UPDATE|INSERT|ALTER|CREATE|"
    r"REPLACE|GRANT|REVOKE|EXEC|EXECUTE|CALL|LOAD|"
    r"INTO\s+OUTFILE)\b",
    re.IGNORECASE,
)


def _run_options_query(
    conn: DBConnection,
    options_query: str,
    search: Optional[str] = None,
    limit: int = 50,
) -> List[Dict[str, str]]:
    """
    Execute a custom options_query that returns value/label.

    The query must be a SELECT.  It is wrapped in a subquery
    to apply search and limit safely::

        SELECT value, label FROM (<user_query>) AS _opts
        WHERE label LIKE :search
        ORDER BY label
        LIMIT :limit

    Parameters:
        conn (DBConnection): The connection configuration.
        options_query (str): The raw SQL query template.
        search (str, optional): Search term for LIKE filter.
        limit (int): Maximum rows to return.

    Returns:
        list[dict]: Options with 'value' and 'label' keys.

    Raises:
        ValueError: If the query contains disallowed SQL.
    """
    # Safety: reject non-SELECT queries
    if _OPTIONS_QUERY_BLOCK_RE.search(options_query):
        raise ValueError(
            "options_query contains disallowed SQL"
        )

    # Strip trailing semicolons
    inner = options_query.rstrip(";").strip()

    params: Dict[str, Any] = {"limit": limit}
    where = ""
    if search:
        where = "WHERE _opts.label LIKE :search"
        params["search"] = f"%{search}%"

    query = (
        f"SELECT _opts.value, _opts.label "
        f"FROM ({inner}) AS _opts "
        f"{where} "
        f"ORDER BY _opts.label "
        f"LIMIT :limit"
    )

    rows = execute_query(conn, query, params)
    return [
        {
            "value": str(row.get("value", "")),
            "label": str(row.get("label", "")),
        }
        for row in rows
    ]


def _run_simple_distinct(
    conn: DBConnection,
    table: str,
    column: str,
    search: Optional[str] = None,
    limit: int = 50,
) -> List[Dict[str, str]]:
    """
    Run a simple SELECT DISTINCT for filter options.

    Parameters:
        conn (DBConnection): The connection configuration.
        table (str): Source table name (validated).
        column (str): Source column name (validated).
        search (str, optional): Search term for LIKE filter.
        limit (int): Maximum rows to return.

    Returns:
        list[dict]: Options with 'value' and 'label' keys.

    Raises:
        ValueError: If identifiers fail the whitelist check.
    """
    if not _IDENTIFIER_RE.match(table):
        raise ValueError(
            f"Invalid table name: {table!r}"
        )
    if not _IDENTIFIER_RE.match(column):
        raise ValueError(
            f"Invalid column name: {column!r}"
        )

    params: Dict[str, Any] = {"limit": limit}
    where_clause = ""
    if search:
        where_clause = (
            f"WHERE `{table}`.`{column}` LIKE :search"
        )
        params["search"] = f"%{search}%"

    query = (
        f"SELECT DISTINCT `{table}`.`{column}` "
        f"FROM `{table}` "
        f"{where_clause} "
        f"ORDER BY `{table}`.`{column}` "
        f"LIMIT :limit"
    )

    rows = execute_query(conn, query, params)
    return [
        {
            "value": str(row[column]),
            "label": str(row[column]),
        }
        for row in rows
    ]
