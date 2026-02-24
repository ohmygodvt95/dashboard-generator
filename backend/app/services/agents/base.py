"""
Base agent class for the multi-agent AI pipeline.

Provides a shared OpenAI LLM call helper so every agent
uses consistent error handling, model selection, and JSON
parsing logic.
"""

import json
import logging
from typing import Dict, Any, List, Optional

from openai import OpenAI

from app.config import settings

logger = logging.getLogger(__name__)


class BaseAgent:
    """
    Abstract base for all specialised agents.

    Subclasses must set ``name`` and ``system_prompt``, and
    implement ``run()``.

    Attributes:
        name (str): Human-readable agent identifier.
        system_prompt (str): System-level instructions sent
            to the LLM for this agent.
        temperature (float): Sampling temperature (0 – 2).
    """

    name: str = "base"
    system_prompt: str = ""
    temperature: float = 0.7

    # ----- LLM helper ------------------------------------------------

    def _call_llm(
        self,
        messages: List[Dict[str, str]],
        temperature: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        Send *messages* to the OpenAI chat API, return parsed JSON.

        Parameters:
            messages (list[dict]): Full message list including
                system prompt.
            temperature (float, optional): Override the default
                temperature for this call.

        Returns:
            dict: Parsed JSON response from the model.
        """
        client = OpenAI(api_key=settings.openai_api_key)
        temp = (
            temperature if temperature is not None
            else self.temperature
        )

        try:
            response = client.chat.completions.create(
                model=settings.openai_model,
                messages=messages,
                temperature=temp,
                response_format={"type": "json_object"},
            )
            content = response.choices[0].message.content
            return json.loads(content)
        except json.JSONDecodeError:
            logger.warning(
                "[%s] LLM returned non-JSON: %s",
                self.name,
                content[:200],
            )
            return {"error": content}
        except Exception as exc:
            logger.error(
                "[%s] LLM call failed: %s",
                self.name,
                exc,
            )
            return {"error": str(exc)}

    # ----- public interface (override in subclass) --------------------

    def run(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute the agent's task.

        Parameters:
            context (dict): Arbitrary context data supplied by
                the orchestrator.

        Returns:
            dict: Agent-specific result payload.
        """
        raise NotImplementedError
