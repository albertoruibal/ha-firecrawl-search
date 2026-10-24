"""Assist LLM tools: web search and page reading via Firecrawl."""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

import aiohttp
import probatio
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_API_KEY, CONF_URL
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv, llm as _llm
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    CONF_CACHE_MAX_AGE_HOURS,
    CONF_DEFAULT_LANG,
    CONF_ENABLE_READ_PAGE,
    CONF_MAX_PAGE_CHARS,
    CONF_RESULTS,
    CONF_SCRAPE_TIMEOUT,
    CONF_SEARCH_TIMEOUT,
    CONF_SNIPPET_CHARS,
    CONF_WAIT_FOR,
    DEFAULT_CACHE_MAX_AGE_HOURS,
    DEFAULT_ENABLE_READ_PAGE,
    DEFAULT_LANG,
    DEFAULT_MAX_PAGE_CHARS,
    DEFAULT_RESULTS,
    DEFAULT_SCRAPE_TIMEOUT,
    DEFAULT_SEARCH_TIMEOUT,
    DEFAULT_SEARCH_URL,
    DEFAULT_SNIPPET_CHARS,
    DEFAULT_WAIT_FOR,
    MAX_CACHE_MAX_AGE_HOURS,
    MAX_PAGE_CHARS,
    MAX_RESULTS,
    MAX_SCRAPE_TIMEOUT,
    MAX_SEARCH_TIMEOUT,
    MAX_SNIPPET_CHARS,
    MAX_WAIT_FOR,
    MIN_CACHE_MAX_AGE_HOURS,
    MIN_PAGE_CHARS,
    MIN_RESULTS,
    MIN_SCRAPE_TIMEOUT,
    MIN_SEARCH_TIMEOUT,
    MIN_SNIPPET_CHARS,
    MIN_WAIT_FOR,
    MS_PER_HOUR,
    MS_PER_SECOND,
    SCRAPE_PATH,
    SEARCH_PATH,
)

_LOGGER = logging.getLogger(__name__)

DOMAIN = "firecrawl_search"
_TAG_RE = re.compile(r"<[^>]+>")

CONFIG_SCHEMA = cv.empty_config_schema(DOMAIN)


@dataclass(frozen=True)
class FirecrawlSettings:
    """Resolved settings for a Firecrawl installation."""

    url: str
    api_key: str
    results: int
    snippet_chars: int
    default_lang: str
    search_timeout: int
    enable_read_page: bool
    max_page_chars: int
    scrape_timeout: int
    cache_max_age_hours: int
    wait_for: int


def _as_int(value: Any, default: int, minimum: int, maximum: int) -> int:
    """Clamp a stored value to an integer range."""
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default
    return max(minimum, min(number, maximum))


def _as_bool(value: Any, default: bool) -> bool:
    """Coerce a stored boolean-like value."""
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "yes", "on")
    return bool(value)


def _normalize(base: str) -> str:
    """Turn a base URL or a full search URL into the base URL."""
    base = (base or "").strip().rstrip("/")
    if base.endswith(SEARCH_PATH):
        base = base[: -len(SEARCH_PATH)]
    return base


def _entry_value(entry: ConfigEntry, key: str, default: Any) -> Any:
    """Read a setting by key presence, so 0/False/empty are preserved."""
    if key in entry.options:
        return entry.options[key]
    if key in entry.data:
        return entry.data[key]
    return default


def _default_settings() -> FirecrawlSettings:
    """Return the built-in defaults."""
    return FirecrawlSettings(
        url=DEFAULT_SEARCH_URL,
        api_key="",
        results=DEFAULT_RESULTS,
        snippet_chars=DEFAULT_SNIPPET_CHARS,
        default_lang=DEFAULT_LANG,
        search_timeout=DEFAULT_SEARCH_TIMEOUT,
        enable_read_page=DEFAULT_ENABLE_READ_PAGE,
        max_page_chars=DEFAULT_MAX_PAGE_CHARS,
        scrape_timeout=DEFAULT_SCRAPE_TIMEOUT,
        cache_max_age_hours=DEFAULT_CACHE_MAX_AGE_HOURS,
        wait_for=DEFAULT_WAIT_FOR,
    )


def _entry_settings(hass: HomeAssistant) -> FirecrawlSettings:
    """Resolve settings live: config entry wins, then built-in defaults."""
    for entry in hass.config_entries.async_entries(DOMAIN):
        if entry.disabled_by is None and entry.state.recoverable:
            raw_url = _entry_value(entry, CONF_URL, DEFAULT_SEARCH_URL)
            url = _normalize(str(raw_url or DEFAULT_SEARCH_URL))
            if not url:
                url = DEFAULT_SEARCH_URL
            lang = str(
                _entry_value(entry, CONF_DEFAULT_LANG, DEFAULT_LANG) or DEFAULT_LANG
            ).strip().lower()
            if len(lang) < 2:
                lang = DEFAULT_LANG
            return FirecrawlSettings(
                url=url,
                api_key=str(_entry_value(entry, CONF_API_KEY, "") or "").strip(),
                results=_as_int(
                    _entry_value(entry, CONF_RESULTS, DEFAULT_RESULTS),
                    DEFAULT_RESULTS,
                    MIN_RESULTS,
                    MAX_RESULTS,
                ),
                snippet_chars=_as_int(
                    _entry_value(
                        entry, CONF_SNIPPET_CHARS, DEFAULT_SNIPPET_CHARS
                    ),
                    DEFAULT_SNIPPET_CHARS,
                    MIN_SNIPPET_CHARS,
                    MAX_SNIPPET_CHARS,
                ),
                default_lang=lang,
                search_timeout=_as_int(
                    _entry_value(
                        entry, CONF_SEARCH_TIMEOUT, DEFAULT_SEARCH_TIMEOUT
                    ),
                    DEFAULT_SEARCH_TIMEOUT,
                    MIN_SEARCH_TIMEOUT,
                    MAX_SEARCH_TIMEOUT,
                ),
                enable_read_page=_as_bool(
                    _entry_value(
                        entry, CONF_ENABLE_READ_PAGE, DEFAULT_ENABLE_READ_PAGE
                    ),
                    DEFAULT_ENABLE_READ_PAGE,
                ),
                max_page_chars=_as_int(
                    _entry_value(
                        entry, CONF_MAX_PAGE_CHARS, DEFAULT_MAX_PAGE_CHARS
                    ),
                    DEFAULT_MAX_PAGE_CHARS,
                    MIN_PAGE_CHARS,
                    MAX_PAGE_CHARS,
                ),
                scrape_timeout=_as_int(
                    _entry_value(
                        entry, CONF_SCRAPE_TIMEOUT, DEFAULT_SCRAPE_TIMEOUT
                    ),
                    DEFAULT_SCRAPE_TIMEOUT,
                    MIN_SCRAPE_TIMEOUT,
                    MAX_SCRAPE_TIMEOUT,
                ),
                cache_max_age_hours=_as_int(
                    _entry_value(
                        entry,
                        CONF_CACHE_MAX_AGE_HOURS,
                        DEFAULT_CACHE_MAX_AGE_HOURS,
                    ),
                    DEFAULT_CACHE_MAX_AGE_HOURS,
                    MIN_CACHE_MAX_AGE_HOURS,
                    MAX_CACHE_MAX_AGE_HOURS,
                ),
                wait_for=_as_int(
                    _entry_value(entry, CONF_WAIT_FOR, DEFAULT_WAIT_FOR),
                    DEFAULT_WAIT_FOR,
                    MIN_WAIT_FOR,
                    MAX_WAIT_FOR,
                ),
            )
    return _default_settings()


def get_search_url(hass: HomeAssistant) -> str:
    """Return the configured Firecrawl base URL (no trailing slash)."""
    return _entry_settings(hass).url


def get_api_key(hass: HomeAssistant) -> str:
    """Return the configured API key ("" = none, for self-hosted)."""
    return _entry_settings(hass).api_key


def get_read_page_enabled(hass: HomeAssistant) -> bool:
    """Return whether the full-page retrieval tool is enabled."""
    return _entry_settings(hass).enable_read_page


def _headers(api_key: str) -> dict[str, str]:
    """Build request headers for the configured Firecrawl instance."""
    return {"Authorization": f"Bearer {api_key}"} if api_key else {}


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """YAML load path: register the component so its llm.py platform loads."""
    _LOGGER.info(
        "firecrawl_search loaded: Assist LLM tools registered (backend %s)",
        get_search_url(hass),
    )
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up from the UI (Settings -> Devices & Services)."""
    settings = _entry_settings(hass)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    _LOGGER.info(
        "firecrawl_search configured: tools registered on the 'assist' LLM API "
        "(backend %s, api_key %s, read_page %s)",
        settings.url,
        "set" if settings.api_key else "not set",
        "enabled" if settings.enable_read_page else "disabled",
    )
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Nothing to clean up: settings are resolved per call."""
    return True


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the entry when its options change."""
    await hass.config_entries.async_reload(entry.entry_id)


class FirecrawlSearchTool(_llm.Tool):
    """Search the web with the configured Firecrawl stack."""

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
        settings = _entry_settings(hass)
        query = str(tool_input.tool_args.get("query", "")).strip()
        count = tool_input.tool_args.get("count")
        if count is None:
            count = settings.results
        try:
            count = max(MIN_RESULTS, min(int(count), MAX_RESULTS))
        except (TypeError, ValueError):
            count = settings.results
        lang = str(
            tool_input.tool_args.get("lang") or settings.default_lang
        ).strip().lower()
        if len(lang) < 2:
            lang = settings.default_lang

        if not query:
            return _llm.ToolResult(data={"error": "empty query"}, error=True)

        payload = {
            "query": query,
            "limit": count,
            "lang": lang,
        }
        try:
            resp = await session_post(
                hass,
                settings.url + SEARCH_PATH,
                payload,
                _headers(settings.api_key),
                settings.search_timeout,
            )
            body = await resp.json()
        except TimeoutError:
            return _llm.ToolResult(data={"error": "search timed out"}, error=True)
        except aiohttp.ClientError as err:
            _LOGGER.warning("Firecrawl search request failed: %s", err)
            return _llm.ToolResult(
                data={"error": f"search request failed: {err}"}, error=True
            )
        except ValueError:
            return _llm.ToolResult(
                data={"error": "invalid response from Firecrawl"}, error=True
            )

        if not isinstance(body, dict):
            return _llm.ToolResult(
                data={"error": "invalid response from Firecrawl"}, error=True
            )
        data = body.get("data") or {}
        if not isinstance(data, dict):
            return _llm.ToolResult(
                data={"error": "invalid response from Firecrawl"}, error=True
            )
        raw = data.get("web") or []
        if not isinstance(raw, list):
            return _llm.ToolResult(
                data={"error": "invalid response from Firecrawl"}, error=True
            )
        results = []
        for item in raw[:count]:
            if not isinstance(item, dict):
                continue
            title = item.get("title") or ""
            snippet = item.get("description") or item.get("content") or ""
            snippet = _TAG_RE.sub(" ", str(snippet))
            snippet = " ".join(snippet.split())[: settings.snippet_chars]
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


class FirecrawlReadPageTool(_llm.Tool):
    """Retrieve the full markdown of a web page with Firecrawl."""

    name = "firecrawl_search__read_page"
    title = "Read web page"
    integration = DOMAIN
    description = (
        "Retrieve the full text of a web page as markdown. Use this after "
        "web_search when snippets are not enough, passing the URL of a "
        "promising result. Prefer pages likely to contain the answer. Very "
        "long pages are truncated."
    )
    annotations = _llm.ToolAnnotations(
        read_only=True,
        destructive=False,
        idempotent=True,
        open_world=True,
    )
    parameters = probatio.Schema(
        {
            probatio.Required("url"): str,
        }
    )

    async def async_call(
        self,
        hass: HomeAssistant,
        tool_input: _llm.ToolInput,
        llm_context: _llm.LLMContext,
    ) -> _llm.ToolResult:
        """Run the scrape against Firecrawl /v2/scrape."""
        settings = _entry_settings(hass)
        if not settings.enable_read_page:
            return _llm.ToolResult(
                data={"error": "page retrieval is disabled"}, error=True
            )

        url = str(tool_input.tool_args.get("url", "")).strip()
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            return _llm.ToolResult(
                data={"error": "url must be an absolute http or https URL"},
                error=True,
            )

        payload = {
            "url": url,
            "formats": ["markdown"],
            "onlyMainContent": True,
            "removeBase64Images": True,
            "waitFor": settings.wait_for * MS_PER_SECOND,
            "maxAge": settings.cache_max_age_hours * MS_PER_HOUR,
            "timeout": settings.scrape_timeout * MS_PER_SECOND,
        }
        try:
            resp = await session_post(
                hass,
                settings.url + SCRAPE_PATH,
                payload,
                _headers(settings.api_key),
                settings.scrape_timeout + 5,
            )
            body = await resp.json()
        except TimeoutError:
            return _llm.ToolResult(
                data={"error": "page fetch timed out"}, error=True
            )
        except aiohttp.ClientError as err:
            _LOGGER.warning("Firecrawl read_page request failed for %s: %s", url, err)
            return _llm.ToolResult(
                data={"error": f"page fetch failed: {err}"}, error=True
            )
        except ValueError:
            return _llm.ToolResult(
                data={"error": "invalid response from Firecrawl"}, error=True
            )

        if not isinstance(body, dict) or body.get("success") is False:
            error = body.get("error") if isinstance(body, dict) else None
            return _llm.ToolResult(
                data={"error": str(error or "page fetch failed")}, error=True
            )

        data = body.get("data") or {}
        if not isinstance(data, dict):
            return _llm.ToolResult(
                data={"error": "invalid response from Firecrawl"}, error=True
            )
        markdown = data.get("markdown") or ""
        if not isinstance(markdown, str) or not markdown.strip():
            return _llm.ToolResult(
                data={"error": "page has no readable content"}, error=True
            )

        metadata = data.get("metadata") or {}
        if not isinstance(metadata, dict):
            metadata = {}
        content = markdown.strip()
        length = len(content)
        truncated = length > settings.max_page_chars
        if truncated:
            content = content[: settings.max_page_chars].rstrip()

        final_url = str(metadata.get("url") or metadata.get("sourceURL") or url)
        title = str(metadata.get("title") or "")[:200]
        _LOGGER.info(
            "Firecrawl read_page %s -> %s chars%s",
            final_url,
            len(content),
            " (truncated)" if truncated else "",
        )
        return _llm.ToolResult(
            data={
                "url": final_url,
                "title": title,
                "content": content,
                "truncated": truncated,
                "length": length,
            }
        )


async def session_post(
    hass: HomeAssistant,
    url: str,
    payload: dict[str, Any],
    headers: dict[str, str],
    timeout: int,
) -> aiohttp.ClientResponse:
    """POST JSON to Firecrawl and raise for non-success status codes."""
    session = async_get_clientsession(hass)
    resp = await session.post(
        url,
        json=payload,
        headers=headers,
        timeout=aiohttp.ClientTimeout(total=timeout),
    )
    resp.raise_for_status()
    return resp
