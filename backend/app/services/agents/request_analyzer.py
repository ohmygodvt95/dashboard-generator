"""
Request Analyzer agent.

Classifies the user's intent and decides which downstream
agents need to be invoked.  Uses a short, deterministic
prompt so the routing decision is fast and cheap.
"""

from typing import Dict, Any, List

from app.services.agents.base import BaseAgent


PROMPT = """\
You are a request router for a dashboard widget builder.
Analyse the user's message and the current widget state to
decide which specialist agents must run.

Return a JSON object — nothing else:

{
  "intent": "<one of the values below>",
  "needs_schema_analysis": <bool>,
  "needs_query": <bool>,
  "needs_filters": <bool>,
  "needs_chart": <bool>,
  "message": "<short reply ONLY when no agents are needed>",
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

Routing rules:
• create_chart     → all flags true
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
        return {
            "intent": result.get("intent", "create_chart"),
            "needs_schema_analysis": result.get(
                "needs_schema_analysis", False
            ),
            "needs_query": result.get("needs_query", False),
            "needs_filters": result.get("needs_filters", False),
            "needs_chart": result.get("needs_chart", False),
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
