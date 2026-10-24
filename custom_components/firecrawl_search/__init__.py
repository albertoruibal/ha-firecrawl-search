"""Assist LLM tool: web search via a self-hosted Firecrawl instance."""
from __future__ import annotations

import logging
import re

import probatio
import aiohttp
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_API_KEY, CONF_URL
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv, llm as _llm
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import DEFAULT_SEARCH_URL, SEARCH_PATH

_LOGGER = logging.getLogger(__name__)

DOMAIN = "firecrawl_search"
TIMEOUT = aiohttp.ClientTimeout(total=15)
_TAG_RE = re.compile(r"<[^>]+>")

CONFIG_SCHEMA = cv.empty_config_schema(DOMAIN)


def _entry_settings(hass: HomeAssistant) -> tuple[str, str]:
    """Resolve (base_url, api_key) live: config entry wins, then YAML default.

    Read per call, so entry reloads can never leave a stale value behind.
    """
    for entry in hass.config_entries.async_entries(DOMAIN):
        if entry.disabled_by is None and entry.state.recoverable:
            url = entry.options.get(CONF_URL) or entry.data.get(CONF_URL)
            if url and _normalize(url):
                url = _normalize(url)
            else:
                url = DEFAULT_SEARCH_URL
            key = (
                entry.options.get(CONF_API_KEY)
                or entry.data.get(CONF_API_KEY)
                or ""
            ).strip()
            return url, key
    return DEFAULT_SEARCH_URL, ""


def get_search_url(hass: HomeAssistant) -> str:
    """Return the configured Firecrawl base URL (no trailing slash)."""
    return _entry_settings(hass)[0]


def get_api_key(hass: HomeAssistant) -> str:
    """Return the configured API key ("" = none, for self-hosted)."""
    return _entry_settings(hass)[1]


def _normalize(base: str) -> str:
    """Turn a base URL or a full search URL into the base URL."""
    base = (base or "").strip().rstrip("/")
    if base.endswith(SEARCH_PATH):
        base = base[: -len(SEARCH_PATH)]
    return base


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """YAML load path: register the component so its llm.py platform loads."""
    _LOGGER.info(
        "firecrawl_search loaded: web_search tool registered on the 'assist' "
        "LLM API (backend %s)",
        get_search_url(hass),
    )
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up from the UI (Settings -> Devices & Services)."""
    url, key = _entry_settings(hass)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    _LOGGER.info(
        "firecrawl_search configured: web_search tool registered on the "
        "'assist' LLM API (backend %s, api_key %s)",
        url,
        "set" if key else "not set",
    )
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Nothing to clean up: settings are resolved per call."""
    return True


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the entry when its options change."""
    await hass.config_entries.async_reload(entry.entry_id)


class FirecrawlSearchTool(_llm.Tool):
    """Search the web with the configured self-hosted Firecrawl stack."""

    name = "firecrawl_search__web_search"
    title = "Web search"
    integration = DOMAIN
    description = (
        "Search the web for CURRENT information. Use this for any question "
        "about news, recent events, current events, prices, weather, sports "
        "results, releases, schedules, or anything that may have changed "
        "recently. Never say that you lack real-time information or that your "
        "knowledge is outdated: this tool gives you live results. Always call "
        "it before answering questions about the present, the future, or any "
        "topic you are not fully certain about."
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

        base, _api_key = get_search_url(hass), get_api_key(hass)
        session = async_get_clientsession(hass)
        payload = {
            "query": query,
            "limit": count,
            "lang": lang,
        }
        headers = {}
        if api_key := _api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        try:
            resp = await session.post(
                base + SEARCH_PATH, json=payload, headers=headers, timeout=TIMEOUT
            )
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