from pathlib import Path

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import llm
from homeassistant.components.llm import LLMTools


@callback
def async_get_tools(hass: HomeAssistant, llm_context, api_id: str):
    """Contribute the Firecrawl web search tool to the Assist LLM API."""
    if api_id != "assist":
        return None
    from .__init__ import FirecrawlSearchTool

    return LLMTools(
        tools=[FirecrawlSearchTool()],
        prompt=(
            "web_search searches the live web via self-hosted Firecrawl. "
            "For factual or current questions you cannot answer from your "
            "training data, call it, then answer concisely from the snippets. "
            "Cite source domains naturally when you use them."
        ),
    )