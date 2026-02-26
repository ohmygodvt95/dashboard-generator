"""
Request Analyzer agent.

Classifies the user's intent, evaluates a readiness
checklist for chart-creation requests, and decides which
downstream agents need to be invoked.

Uses a short, deterministic prompt so the routing decision
is fast and cheap.
"""

from typing import Dict, Any, List

from app.services.agents.base import BaseAgent


PROMPT = """\
You are a request router for a dashboard widget builder.
Analyse the user's message and the current widget state to
decide which specialist agents must run.

Return a JSON object — nothing else:

{
  "intent": "<one of the intent values below>",
  "needs_schema_analysis": <bool>,
  "needs_query": <bool>,
  "needs_filters": <bool>,
  "needs_chart": <bool>,
  "needs_clarification": <bool>,
  "checklist": {
    "has_data_source": <bool>,
    "has_metric": <bool>,
    "has_dimension": <bool>,
    "has_chart_type": <bool>,
    "has_filters": <bool>,
    "has_time_range": <bool>
  },
  "message": "<reply text — see rules below>",
  "summary": "<1-2 sentence summary of what the user wants>"
}

Possible intent values:
- "create_chart"   → user wants a brand-new chart / widget
- "modify_query"   → change the SQL / data source only
- "modify_chart"   → change visuals (chart type, colours, title…)
- "modify_filters" → add, remove, or tweak filters only
- "modify_all"     → broad change that touches query + chart
- "question"       → user asks a question (no widget change)
- "greeting"       → casual greeting / small talk

─── READINESS CHECKLIST (only evaluate for create_chart) ───

When the intent is "create_chart", evaluate the checklist:

  has_data_source  — is a database connection available?
                     (check the "Database connected" flag)
  has_metric       — did the user specify WHAT to measure?
                     e.g. "revenue", "order count", "users"
  has_dimension    — did the user specify HOW to group/slice?
                     e.g. "by month", "by category", "per region"
  has_chart_type   — did the user specify or imply a chart type?
                     (optional — default bar)
  has_filters      — did the user mention any filters?
                     (optional — none by default)
  has_time_range   — did the user specify a time range?
                     (optional — no constraint by default)

REQUIRED items: has_data_source, has_metric, has_dimension.
OPTIONAL items: has_chart_type, has_filters, has_time_range.

If ANY required item is false → set needs_clarification=true,
set ALL agent flags to false, and write a friendly "message"
that:
  1. Lists what you already understand (✅).
  2. Asks specific questions for ONLY the missing REQUIRED
     items (❓). Keep it concise — ask at most 3 questions.
  3. Optionally mention optional items they could specify.

IMPORTANT: Look at the full conversation history, not just the
latest message.  If a prior message already provided the metric
or dimension, treat it as satisfied even if the current message
does not repeat it.

If ALL required items are satisfied → set needs_clarification
=false and apply the normal routing rules below.

For non-create intents, set needs_clarification=false and
fill checklist with all true values (not relevant).

─── ROUTING RULES ───

• create_chart     → all agent flags true
• modify_query     → needs_query=true, needs_filters=true,
                     needs_chart=true (columns may change)
• modify_chart     → needs_chart=true only
• modify_filters   → needs_filters=true only
• modify_all       → needs_query=true, needs_filters=true,
                     needs_chart=true
• question/greeting→ all flags false, answer in "message"

Set needs_schema_analysis=true whenever needs_query=true
and there is a database connected.
"""


class RequestAnalyzerAgent(BaseAgent):
    """Classify user intent and decide which agents to invoke."""

    name = "request_analyzer"
    system_prompt = PROMPT
    temperature = 0.2  # deterministic routing

    def run(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Analyse a user message and return routing flags.

        When the intent is ``create_chart`` and required
        checklist items are missing, sets
        ``needs_clarification=True`` and returns clarifying
        questions in ``message`` instead of routing to
        downstream agents.

        Parameters:
            context (dict): Must contain ``user_message``,
                ``chat_history``, and optionally ``widget_data``.

        Returns:
            dict: Routing decision with boolean flags per agent
                and a human-readable summary.
        """
        messages = [
            {"role": "system", "content": self.system_prompt},
        ]

        # Provide current widget state so the analyser knows
        # whether queries / charts already exist.
        widget_data = context.get("widget_data")
        if widget_data:
            messages.append({
                "role": "system",
                "content": (
                    "Current widget state:\n"
                    f"{_widget_summary(widget_data)}"
                ),
            })

        has_connection = bool(
            context.get("has_connection", False)
        )
        messages.append({
            "role": "system",
            "content": (
                f"Database connected: {has_connection}"
            ),
        })

        # Recent chat history (last 6 for brevity)
        for msg in context.get("chat_history", [])[-6:]:
            messages.append({
                "role": msg["role"],
                "content": msg["content"],
            })

        messages.append({
            "role": "user",
            "content": context["user_message"],
        })

        result = self._call_llm(messages)

        # Guarantee all expected keys exist
        default_checklist = {
            "has_data_source": True,
            "has_metric": True,
            "has_dimension": True,
            "has_chart_type": True,
            "has_filters": True,
            "has_time_range": True,
        }
        checklist = result.get("checklist", default_checklist)
        # Ensure every key exists in the checklist
        for key in default_checklist:
            checklist.setdefault(key, default_checklist[key])

        return {
            "intent": result.get("intent", "create_chart"),
            "needs_schema_analysis": result.get(
                "needs_schema_analysis", False
            ),
            "needs_query": result.get("needs_query", False),
            "needs_filters": result.get(
                "needs_filters", False
            ),
            "needs_chart": result.get("needs_chart", False),
            "needs_clarification": result.get(
                "needs_clarification", False
            ),
            "checklist": checklist,
            "message": result.get("message", ""),
            "summary": result.get("summary", ""),
        }


def _widget_summary(widget_data: Dict[str, Any]) -> str:
    """
    Build a concise summary string of the widget state.

    Parameters:
        widget_data (dict): Serialised widget data.

    Returns:
        str: Multi-line summary.
    """
    parts: List[str] = []
    if widget_data.get("chart_type"):
        parts.append(f"chart_type: {widget_data['chart_type']}")
    if widget_data.get("query_template"):
        parts.append(
            f"query_template: {widget_data['query_template']}"
        )
    if widget_data.get("chart_config"):
        parts.append(f"chart_config: {widget_data['chart_config']}")
    if widget_data.get("filters"):
        labels = [
            f.get("label", f.get("param_name", "?"))
            for f in widget_data["filters"]
        ]
        parts.append(f"filters: {', '.join(labels)}")
    return "\n".join(parts) if parts else "Empty widget"
