"""
Chat Context Summarizer agent.

Compresses long chat histories into a concise summary so
downstream agents stay within token limits.  The summary
is stored on the ``Widget.chat_summary`` column and reused
in subsequent requests.

Trigger logic:
    When the estimated token count of the chat history
    exceeds ``settings.context_token_limit``, the summarizer
    runs *before* the main pipeline.  It produces a new
    summary that replaces the old one, and the main pipeline
    receives only ``[summary] + latest_messages`` instead of
    the full history.
"""

from typing import Dict, Any, List

from app.services.agents.base import BaseAgent


PROMPT = """\
You are a conversation summariser.  Given a chat history
between a user and an AI assistant that configures dashboard
widgets, produce a concise summary that preserves:

1. What chart / widget has been configured (type, data source).
2. Key decisions made (query changes, filter additions,
   chart style choices).
3. Any outstanding requests or issues.
4. Important context the assistant would need to continue
   the conversation naturally.

Return a JSON object:
{
  "summary": "<concise summary, max 800 words>"
}

Be thorough but brief.  Do NOT include raw SQL or full
JSON configs — describe them in natural language.
"""

# Rough estimate: 1 token ≈ 4 characters.
_CHARS_PER_TOKEN = 4


def estimate_tokens(messages: List[Dict[str, str]]) -> int:
    """
    Rough token estimate for a list of chat messages.

    Parameters:
        messages (list[dict]): Messages with 'content' keys.

    Returns:
        int: Estimated token count.
    """
    total_chars = sum(
        len(m.get("content", "")) for m in messages
    )
    return total_chars // _CHARS_PER_TOKEN


class SummarizerAgent(BaseAgent):
    """Compress long chat histories into a concise summary."""

    name = "summarizer"
    system_prompt = PROMPT
    temperature = 0.3

    def run(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Summarise the chat history.

        Parameters:
            context (dict): Keys — ``chat_history`` (full
                message list), optionally ``previous_summary``
                (existing summary to incorporate).

        Returns:
            dict: ``{"summary": "..."}``
        """
        chat_history = context.get("chat_history", [])
        previous_summary = context.get(
            "previous_summary", ""
        )

        messages = [
            {"role": "system", "content": self.system_prompt},
        ]

        # If there is a previous summary, include it
        if previous_summary:
            messages.append({
                "role": "system",
                "content": (
                    "Previous conversation summary:\n"
                    f"{previous_summary}"
                ),
            })

        # Build the conversation text to summarise
        conv_parts = []
        for m in chat_history:
            role = m.get("role", "user").upper()
            content = m.get("content", "")
            conv_parts.append(f"{role}: {content}")

        conversation_text = "\n".join(conv_parts)
        messages.append({
            "role": "user",
            "content": (
                "Summarise this conversation:\n\n"
                f"{conversation_text}"
            ),
        })

        result = self._call_llm(messages)
        return {
            "summary": result.get("summary", ""),
        }
