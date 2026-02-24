"""
Multi-agent AI pipeline for widget configuration.

Each agent has a dedicated prompt and handles one concern:
- RequestAnalyzer  → intent classification & routing
- SchemaAnalyzer   → semantic DB schema analysis (cached)
- QueryBuilder     → Jinja2 SQL query templates
- FilterBuilder    → filter definitions & validation
- ChartBuilder     → chart type & visual config

The orchestrator coordinates agents based on the analysed
intent, merging their outputs into a single response.
"""

from app.services.agents.orchestrator import (
    orchestrate_chat,
    orchestrate_chat_stream,
)

__all__ = ["orchestrate_chat", "orchestrate_chat_stream"]
