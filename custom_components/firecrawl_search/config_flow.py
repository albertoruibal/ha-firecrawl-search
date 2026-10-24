"""Config flow to set up the Firecrawl search tool from the UI."""
from __future__ import annotations

from typing import Any

import aiohttp
import probatio
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.const import CONF_URL
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .const import DEFAULT_SEARCH_URL, SEARCH_PATH


async def _probe(session: aiohttp.ClientSession, base_url: str) -> str | None:
    """Try a real search; return None when OK, else a strings.json error key."""
    url = base_url.rstrip("/") + SEARCH_PATH
    try:
        resp = await session.post(
            url,
            json={"query": "test", "limit": 1},
            timeout=aiohttp.ClientTimeout(total=12),
        )
        resp.raise_for_status()
        body = await resp.json()
    except TimeoutError:
        return "cannot_connect"
    except aiohttp.ClientResponseError as err:
        if err.status == 404:
            return "bad_search_path"
        return "cannot_connect"
    except (aiohttp.ClientError, OSError):
        return "cannot_connect"
    except ValueError:
        return "invalid_response"

    data = body.get("data") if isinstance(body, dict) else None
    web = data.get("web") if isinstance(data, dict) else None
    if not isinstance(web, list):
        return "invalid_response"
    return None


def _normalize(base: str) -> str:
    """Accept a base URL or a full search URL, return the base."""
    base = base.strip().rstrip("/")
    if base.endswith(SEARCH_PATH):
        base = base[: -len(SEARCH_PATH)]
    return base


class FirecrawlSearchConfigFlow(ConfigFlow, domain="firecrawl_search"):
    """Handle the UI setup flow."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Show the URL form, validate it, and create the entry."""
        errors: dict[str, str] = {}
        if user_input is not None:
            base = _normalize(user_input[CONF_URL])
            err = await _probe(async_get_clientsession(self.hass), base)
            if err is None:
                return self.async_create_entry(
                    title="Firecrawl Web Search",
                    data={CONF_URL: base},
                )
            errors[CONF_URL] = err

        return self.async_show_form(
            step_id="user",
            data_schema=probatio.Schema(
                {
                    probatio.Required(CONF_URL): TextSelector(
                        TextSelectorConfig(type=TextSelectorType.URL)
                    )
                }
            ),
            errors=errors or None,
        )

    @callback
    def async_get_options_flow(self, config_entry):
        """Get the options flow for this handler."""
        return FirecrawlSearchOptionsFlow()


class FirecrawlSearchOptionsFlow(OptionsFlow):
    """Change the Firecrawl URL without touching code."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            base = _normalize(user_input[CONF_URL])
            err = await _probe(async_get_clientsession(self.hass), base)
            if err is None:
                return self.async_create_entry(title="", data={CONF_URL: base})
            errors[CONF_URL] = err

        current = (
            self.config_entry.options.get(CONF_URL)
            or self.config_entry.data.get(CONF_URL)
            or DEFAULT_SEARCH_URL
        )
        return self.async_show_form(
            step_id="init",
            data_schema=probatio.Schema(
                {
                    probatio.Required(CONF_URL, default=current): TextSelector(
                        TextSelectorConfig(type=TextSelectorType.URL)
                    )
                }
            ),
            errors=errors or None,
        )