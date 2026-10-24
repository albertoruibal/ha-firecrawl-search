"""Assist LLM tool: web search via local Firecrawl (http://192.168.0.11:3002)."""
from __future__ import annotations

import logging
import re

import probatio
import aiohttp
from homeassistant.core import HomeAssistant
from homeassistant.helpers import llm as _llm
from homeassistant.helpers.aiohttp_client import async_get_clientsession

_LOGGER = logging.getLogger(__name__)

DOMAIN = "firecrawl_search"
SEARCH_URL = "http://192.168.0.11:3002/v2/search"
TIMEOUT = aiohttp.ClientTimeout(total=15)
_TAG_RE = re.compile(r"<[^>]+>")


class FirecrawlSearchTool(_llm.Tool):
    """Search the web with the self-hosted Firecrawl stack."""

    name = "web_search"
    title = "Web search"
    integration = DOMAIN
    description = (
        "Search the web for current information. Returns the top results as "
        "title, url and snippet. Use for questions about current events, "
        "news, prices, weather, sports, or anything outside the home, or when "
        "your knowledge may be out of date, or when the user asks you to "
        "search / look up / google something."
    )
    annotations = _llm.ToolAnnotations(
        read_only=True,
        destructive=False,
        idempotent=True,
        open_world=True,
    )
    parameters = probatio.Schema(
        {
            probatio.Required("query"): str,
            probatio.Optional("count"): int,
            probatio.Optional("lang"): str,
        }
    )

    async def async_call(
        self,
        hass: HomeAssistant,
        tool_input: _llm.ToolInput,
        llm_context: _llm.LLMContext,
    ) -> _llm.ToolResult:
        """Run the search against Firecrawl /v2/search."""
        query = str(tool_input.tool_args.get("query", "")).strip()
        count = tool_input.tool_args.get("count") or 3
        try:
            count = max(1, min(int(count), 5))
        except (TypeError, ValueError):
            count = 3
        lang = str(tool_input.tool_args.get("lang") or "gl").strip() or "gl"
        if len(lang) < 2:
            lang = "gl"

        if not query:
            return _llm.ToolResult(
                data={"error": "empty query"}, error=True
            )

        session = async_get_clientsession(hass)
        payload = {
            "query": query,
            "limit": count,
            "lang": lang,
        }
        try:
            resp = await session.post(SEARCH_URL, json=payload, timeout=TIMEOUT)
            resp.raise_for_status()
            body = await resp.json()
        except TimeoutError:
            return _llm.ToolResult(data={"error": "search timed out"}, error=True)
        except aiohttp.ClientError as err:
            _LOGGER.warning("Firecrawl search request failed: %s", err)
            return _llm.ToolResult(data={"error": f"search request failed: {err}"}, error=True)

        data = body.get("data") or {}
        raw = data.get("web") or []
        results = []
        for item in raw[:count]:
            title = item.get("title") or ""
            snippet = item.get("description") or item.get("content") or ""
            snippet = _TAG_RE.sub(" ", str(snippet))
            snippet = " ".join(snippet.split())[:300]
            results.append(
                {
                    "title": str(title)[:200],
                    "url": str(item.get("url") or ""),
                    "snippet": snippet,
                }
            )

        _LOGGER.info(
            "Firecrawl web_search %r lang=%s -> %s results",
            query,
            lang,
            len(results),
        )
        return _llm.ToolResult(
            data={"query": query, "results": results},
        )