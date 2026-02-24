"""
Schema Analyzer agent.

Performs a one-time semantic analysis of the database schema
(table purposes, column meanings, relationships, suggested
metrics) and caches the result in the ``schema_analyses``
table.  Subsequent calls return the cached version unless
the underlying schema has changed (detected via hash).
"""

import hashlib
import json
import logging
from typing import Dict, Any, Optional

from sqlalchemy.orm import Session

from app.models import SchemaAnalysis, generate_uuid, utcnow
from app.services.agents.base import BaseAgent

logger = logging.getLogger(__name__)


PROMPT = """\
You are a database schema analyst for a dashboard / BI tool.
Given the raw schema (tables, columns, types, primary keys,
foreign keys), produce a rich semantic analysis.

Return a JSON object with the following structure:

{
  "tables": [
    {
      "name": "table_name",
      "description": "What this table stores",
      "key_columns": ["col1", "col2"],
      "relationships": [
        {
          "to": "other_table",
          "type": "many-to-one | one-to-many | many-to-many",
          "join": "this.col = other.col"
        }
      ]
    }
  ],
  "join_paths": [
    {
      "description": "Orders with customer info",
      "sql": "orders JOIN customers ON ..."
    }
  ],
  "suggested_metrics": [
    "Total revenue (SUM of order amount)",
    "Order count by status",
    "Monthly new customers"
  ],
  "notes": "Any useful observations about the schema"
}

Be thorough but concise.  Focus on information that helps
build SQL queries and chart visualizations.
"""


class SchemaAnalyzerAgent(BaseAgent):
    """Analyse and cache the semantic meaning of a DB schema."""

    name = "schema_analyzer"
    system_prompt = PROMPT
    temperature = 0.3  # factual — low creativity

    # ----- public API ------------------------------------------------

    def run(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Return a cached or freshly-generated schema analysis.

        Parameters:
            context (dict): Must contain ``schema`` (raw schema
                dict) and ``connection_id``.  Optionally ``db``
                (SQLAlchemy session) for cache read/write.

        Returns:
            dict: Semantic analysis of the database schema.
        """
        schema = context.get("schema")
        if not schema:
            return {"error": "No schema provided"}

        connection_id = context.get("connection_id", "")
        db: Optional[Session] = context.get("db")
        current_hash = _compute_hash(schema)

        # --- try cache first -----------------------------------------
        if db and connection_id:
            cached = self._load_cache(
                db, connection_id, current_hash
            )
            if cached is not None:
                logger.info(
                    "[%s] returning cached analysis for %s",
                    self.name,
                    connection_id,
                )
                return cached

        # --- call LLM ------------------------------------------------
        schema_text = _format_schema(schema)
        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": schema_text},
        ]
        analysis = self._call_llm(messages)

        # --- persist cache -------------------------------------------
        if db and connection_id and "error" not in analysis:
            self._save_cache(
                db, connection_id, current_hash, analysis
            )

        return analysis

    # ----- cache helpers ---------------------------------------------

    @staticmethod
    def _load_cache(
        db: Session,
        connection_id: str,
        expected_hash: str,
    ) -> Optional[Dict[str, Any]]:
        """
        Load cached analysis if the hash still matches.

        Parameters:
            db (Session): Active SQLAlchemy session.
            connection_id (str): DB connection UUID.
            expected_hash (str): SHA-256 of the current schema.

        Returns:
            dict or None: Cached analysis, or None on miss.
        """
        row = (
            db.query(SchemaAnalysis)
            .filter(
                SchemaAnalysis.connection_id == connection_id
            )
            .first()
        )
        if row and row.schema_hash == expected_hash:
            try:
                return json.loads(row.analysis)
            except (json.JSONDecodeError, TypeError):
                return None
        return None

    @staticmethod
    def _save_cache(
        db: Session,
        connection_id: str,
        schema_hash: str,
        analysis: Dict[str, Any],
    ) -> None:
        """
        Upsert a schema analysis row.

        Parameters:
            db (Session): Active SQLAlchemy session.
            connection_id (str): DB connection UUID.
            schema_hash (str): SHA-256 of the raw schema.
            analysis (dict): The analysis payload to store.
        """
        row = (
            db.query(SchemaAnalysis)
            .filter(
                SchemaAnalysis.connection_id == connection_id
            )
            .first()
        )
        analysis_json = json.dumps(analysis)

        if row:
            row.analysis = analysis_json
            row.schema_hash = schema_hash
            row.updated_at = utcnow()
        else:
            row = SchemaAnalysis(
                id=generate_uuid(),
                connection_id=connection_id,
                analysis=analysis_json,
                schema_hash=schema_hash,
            )
            db.add(row)

        db.commit()


# ----- utilities -----------------------------------------------------


def _compute_hash(schema: Dict[str, Any]) -> str:
    """
    Deterministic SHA-256 hash of a raw schema dict.

    Parameters:
        schema (dict): Raw schema from ``db_connector.get_schema``.

    Returns:
        str: Hex-encoded SHA-256 digest.
    """
    canonical = json.dumps(schema, sort_keys=True)
    return hashlib.sha256(canonical.encode()).hexdigest()


def _format_schema(schema: Dict[str, Any]) -> str:
    """
    Format a raw schema dict into a human-readable string.

    Parameters:
        schema (dict): Raw schema dict.

    Returns:
        str: Multi-line textual representation.
    """
    lines = [f"Database: {schema.get('database', '?')}"]
    for table in schema.get("tables", []):
        lines.append(f"\nTable: {table['name']}")
        for col in table.get("columns", []):
            pk = " [PK]" if col.get("primary_key") else ""
            nullable = " NULL" if col.get("nullable") else ""
            lines.append(
                f"  - {col['name']} {col['type']}{pk}{nullable}"
            )
        for fk in table.get("foreign_keys", []):
            cols = ", ".join(fk.get("columns", []))
            ref = fk.get("referred_table", "?")
            ref_cols = ", ".join(
                fk.get("referred_columns", [])
            )
            lines.append(
                f"  FK: ({cols}) → {ref}({ref_cols})"
            )
    return "\n".join(lines)
