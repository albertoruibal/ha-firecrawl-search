from homeassistant.components.llm import LLMTools
from homeassistant.core import HomeAssistant, callback


@callback
def async_get_tools(hass: HomeAssistant, llm_context, api_id: str):
    """Contribute the Firecrawl web search and page-reading tools to Assist."""
    if api_id != "assist":
        return None
    from .__init__ import (
        FirecrawlReadPageTool,
        FirecrawlSearchTool,
        get_read_page_enabled,
    )

    tools = [FirecrawlSearchTool()]
    prompt = (
        "web_search searches the live web via Firecrawl. For factual or "
        "current questions you cannot answer from your training data, call it, "
        "then answer concisely from the snippets. Cite source domains "
        "naturally when you use them."
    )
    if get_read_page_enabled(hass):
        tools.append(FirecrawlReadPageTool())
        prompt += (
            " When snippets are not enough, call read_page with a result URL "
            "to retrieve the full page text before answering."
        )

    return LLMTools(
        tools=tools,
        prompt=prompt,
    )
