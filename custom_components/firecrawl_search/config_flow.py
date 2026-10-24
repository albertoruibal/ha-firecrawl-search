"""Config flow to set up the Firecrawl search tool from the UI."""
from __future__ import annotations

from typing import Any

import aiohttp
import probatio
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.const import CONF_API_KEY, CONF_URL
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .const import DEFAULT_HOSTED_URL, DEFAULT_SEARCH_URL, SEARCH_PATH


async def _probe(
    session: aiohttp.ClientSession, base_url: str, api_key: str | None = None
) -> str | None:
    """Try a real search; return None when OK, else a strings.json error key."""
    url = base_url.rstrip("/") + SEARCH_PATH
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    try:
        resp = await session.post(
            url,
            json={"query": "test", "limit": 1},
            headers=headers,
            timeout=aiohttp.ClientTimeout(total=15),
        )
        resp.raise_for_status()
        body = await resp.json()
    except TimeoutError:
        return "cannot_connect"
    except aiohttp.ClientResponseError as err:
        if err.status == 401 or err.status == 403:
            return "invalid_auth"
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


def _schema_url(default: str) -> probatio.Schema:
    return probatio.Schema(
        {
            probatio.Required(CONF_URL, default=default): TextSelector(
                TextSelectorConfig(type=TextSelectorType.URL)
            ),
            probatio.Optional(CONF_API_KEY): TextSelector(
                TextSelectorConfig(type=TextSelectorType.PASSWORD)
            ),
        }
    )


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
            api_key = (user_input.get(CONF_API_KEY) or "").strip()
            err = await _probe(async_get_clientsession(self.hass), base, api_key or None)
            if err is None:
                return self.async_create_entry(
                    title="Firecrawl Web Search",
                    data={CONF_URL: base, CONF_API_KEY: api_key},
                )
            errors[CONF_URL] = err

        return self.async_show_form(
            step_id="user",
            data_schema=_schema_url(DEFAULT_SEARCH_URL),
            errors=errors or None,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry) -> "FirecrawlSearchOptionsFlow":
        """Get the options flow for this handler."""
        return FirecrawlSearchOptionsFlow()


class FirecrawlSearchOptionsFlow(OptionsFlow):
    """Change the Firecrawl URL / API key without touching code."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            base = _normalize(user_input[CONF_URL])
            # Empty key field = keep the saved key; type spaces to clear it.
            api_key = (
                user_input.get(CONF_API_KEY) or ""
            ).strip() or (
                self.config_entry.options.get(CONF_API_KEY)
                or self.config_entry.data.get(CONF_API_KEY)
                or ""
            ).strip()
            err = await _probe(async_get_clientsession(self.hass), base, api_key or None)
            if err is None:
                return self.async_create_entry(
                    title="", data={CONF_URL: base, CONF_API_KEY: api_key}
                )
            errors[CONF_URL] = err

        current = (
            self.config_entry.options.get(CONF_URL)
            or self.config_entry.data.get(CONF_URL)
            or DEFAULT_SEARCH_URL
        )
        # Re-entering the saved key is not required when unchanged; leave the
        # field empty to keep it.
        return self.async_show_form(
            step_id="init",
            data_schema=_schema_url(current),
            errors=errors or None,
        )