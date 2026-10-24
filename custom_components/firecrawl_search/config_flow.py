"""Config flow to set up the Firecrawl search tool from the UI."""
from __future__ import annotations

from typing import Any

import aiohttp
import probatio
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import CONF_API_KEY, CONF_URL
from homeassistant.core import callback
from homeassistant.data_entry_flow import section
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    BooleanSelector,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .const import (
    CONF_CACHE_MAX_AGE_HOURS,
    CONF_CLEAR_API_KEY,
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
    SEARCH_PATH,
)

SECTION_CONNECTION = "connection"
SECTION_SEARCH = "search"
SECTION_PAGE = "page"
_SECTIONS = (SECTION_CONNECTION, SECTION_SEARCH, SECTION_PAGE)


async def _probe(
    session: aiohttp.ClientSession,
    base_url: str,
    api_key: str | None = None,
    timeout: int = DEFAULT_SEARCH_TIMEOUT,
) -> str | None:
    """Try a real search; return None when OK, else a strings.json error key."""
    url = base_url.rstrip("/") + SEARCH_PATH
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    try:
        resp = await session.post(
            url,
            json={"query": "test", "limit": 1},
            headers=headers,
            timeout=aiohttp.ClientTimeout(total=timeout),
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


def _as_int(value: Any, default: int, minimum: int, maximum: int) -> int:
    """Clamp a user/stored value to an integer range."""
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


def _clean_values(values: dict[str, Any]) -> dict[str, Any]:
    """Normalize submitted values and clamp them to the supported ranges."""
    lang = str(values.get(CONF_DEFAULT_LANG) or DEFAULT_LANG).strip().lower()
    if len(lang) < 2:
        lang = DEFAULT_LANG
    return {
        CONF_URL: _normalize(str(values.get(CONF_URL) or DEFAULT_SEARCH_URL)),
        CONF_API_KEY: str(values.get(CONF_API_KEY) or "").strip(),
        CONF_RESULTS: _as_int(
            values.get(CONF_RESULTS), DEFAULT_RESULTS, MIN_RESULTS, MAX_RESULTS
        ),
        CONF_SNIPPET_CHARS: _as_int(
            values.get(CONF_SNIPPET_CHARS),
            DEFAULT_SNIPPET_CHARS,
            MIN_SNIPPET_CHARS,
            MAX_SNIPPET_CHARS,
        ),
        CONF_DEFAULT_LANG: lang,
        CONF_SEARCH_TIMEOUT: _as_int(
            values.get(CONF_SEARCH_TIMEOUT),
            DEFAULT_SEARCH_TIMEOUT,
            MIN_SEARCH_TIMEOUT,
            MAX_SEARCH_TIMEOUT,
        ),
        CONF_ENABLE_READ_PAGE: _as_bool(
            values.get(CONF_ENABLE_READ_PAGE), DEFAULT_ENABLE_READ_PAGE
        ),
        CONF_MAX_PAGE_CHARS: _as_int(
            values.get(CONF_MAX_PAGE_CHARS),
            DEFAULT_MAX_PAGE_CHARS,
            MIN_PAGE_CHARS,
            MAX_PAGE_CHARS,
        ),
        CONF_SCRAPE_TIMEOUT: _as_int(
            values.get(CONF_SCRAPE_TIMEOUT),
            DEFAULT_SCRAPE_TIMEOUT,
            MIN_SCRAPE_TIMEOUT,
            MAX_SCRAPE_TIMEOUT,
        ),
        CONF_CACHE_MAX_AGE_HOURS: _as_int(
            values.get(CONF_CACHE_MAX_AGE_HOURS),
            DEFAULT_CACHE_MAX_AGE_HOURS,
            MIN_CACHE_MAX_AGE_HOURS,
            MAX_CACHE_MAX_AGE_HOURS,
        ),
        CONF_WAIT_FOR: _as_int(
            values.get(CONF_WAIT_FOR),
            DEFAULT_WAIT_FOR,
            MIN_WAIT_FOR,
            MAX_WAIT_FOR,
        ),
    }


def _default_values() -> dict[str, Any]:
    """Return the defaults used by a fresh installation."""
    return _clean_values({CONF_URL: DEFAULT_SEARCH_URL})


def _entry_values(entry: ConfigEntry) -> dict[str, Any]:
    """Read current values, preferring options over the original data."""
    values: dict[str, Any] = {}
    for key in (
        CONF_URL,
        CONF_API_KEY,
        CONF_RESULTS,
        CONF_SNIPPET_CHARS,
        CONF_DEFAULT_LANG,
        CONF_SEARCH_TIMEOUT,
        CONF_ENABLE_READ_PAGE,
        CONF_MAX_PAGE_CHARS,
        CONF_SCRAPE_TIMEOUT,
        CONF_CACHE_MAX_AGE_HOURS,
        CONF_WAIT_FOR,
    ):
        if key in entry.options:
            values[key] = entry.options[key]
        elif key in entry.data:
            values[key] = entry.data[key]
    return _clean_values(values)


def _flatten(user_input: dict[str, Any]) -> dict[str, Any]:
    """Flatten the section dictionaries produced by the form."""
    values: dict[str, Any] = {}
    for key in _SECTIONS:
        nested = user_input.get(key)
        if isinstance(nested, dict):
            values.update(nested)
    for key, value in user_input.items():
        if key not in _SECTIONS:
            values[key] = value
    return values


def _number(
    minimum: int,
    maximum: int,
    step: int = 1,
    unit: str | None = None,
) -> NumberSelector:
    """Build a boxed number selector."""
    config: NumberSelectorConfig = {
        "min": minimum,
        "max": maximum,
        "step": step,
        "mode": NumberSelectorMode.BOX,
    }
    if unit:
        config["unit_of_measurement"] = unit
    return NumberSelector(config)


def _schema(values: dict[str, Any], *, include_clear: bool) -> probatio.Schema:
    """Build the setup/options form."""
    connection: dict[Any, Any] = {
        probatio.Required(CONF_URL, default=values[CONF_URL]): TextSelector(
            TextSelectorConfig(type=TextSelectorType.URL)
        ),
        probatio.Optional(CONF_API_KEY): TextSelector(
            TextSelectorConfig(type=TextSelectorType.PASSWORD)
        ),
    }
    if include_clear:
        connection[probatio.Optional(CONF_CLEAR_API_KEY, default=False)] = (
            BooleanSelector()
        )

    search: dict[Any, Any] = {
        probatio.Required(CONF_RESULTS, default=values[CONF_RESULTS]): _number(
            MIN_RESULTS, MAX_RESULTS
        ),
        probatio.Required(
            CONF_SNIPPET_CHARS, default=values[CONF_SNIPPET_CHARS]
        ): _number(
            MIN_SNIPPET_CHARS,
            MAX_SNIPPET_CHARS,
            unit="characters",
        ),
        probatio.Required(
            CONF_DEFAULT_LANG, default=values[CONF_DEFAULT_LANG]
        ): TextSelector(TextSelectorConfig()),
        probatio.Required(
            CONF_SEARCH_TIMEOUT, default=values[CONF_SEARCH_TIMEOUT]
        ): _number(
            MIN_SEARCH_TIMEOUT,
            MAX_SEARCH_TIMEOUT,
            unit="s",
        ),
    }

    page: dict[Any, Any] = {
        probatio.Required(
            CONF_ENABLE_READ_PAGE, default=values[CONF_ENABLE_READ_PAGE]
        ): BooleanSelector(),
        probatio.Required(
            CONF_MAX_PAGE_CHARS, default=values[CONF_MAX_PAGE_CHARS]
        ): _number(
            MIN_PAGE_CHARS,
            MAX_PAGE_CHARS,
            step=1000,
            unit="characters",
        ),
        probatio.Required(
            CONF_SCRAPE_TIMEOUT, default=values[CONF_SCRAPE_TIMEOUT]
        ): _number(
            MIN_SCRAPE_TIMEOUT,
            MAX_SCRAPE_TIMEOUT,
            unit="s",
        ),
        probatio.Required(
            CONF_CACHE_MAX_AGE_HOURS, default=values[CONF_CACHE_MAX_AGE_HOURS]
        ): _number(
            MIN_CACHE_MAX_AGE_HOURS,
            MAX_CACHE_MAX_AGE_HOURS,
            unit="h",
        ),
        probatio.Required(
            CONF_WAIT_FOR, default=values[CONF_WAIT_FOR]
        ): _number(
            MIN_WAIT_FOR,
            MAX_WAIT_FOR,
            unit="s",
        ),
    }

    return probatio.Schema(
        {
            probatio.Required(SECTION_CONNECTION): section(
                probatio.Schema(connection), {"collapsed": False}
            ),
            probatio.Required(SECTION_SEARCH): section(
                probatio.Schema(search), {"collapsed": True}
            ),
            probatio.Required(SECTION_PAGE): section(
                probatio.Schema(page), {"collapsed": True}
            ),
        }
    )


class FirecrawlSearchConfigFlow(ConfigFlow, domain="firecrawl_search"):
    """Handle the UI setup flow."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Show the settings form, validate it, and create the entry."""
        errors: dict[str, str] = {}
        values = _default_values()
        if user_input is not None:
            values = _clean_values(_flatten(user_input))
            err = await _probe(
                async_get_clientsession(self.hass),
                values[CONF_URL],
                values[CONF_API_KEY] or None,
                values[CONF_SEARCH_TIMEOUT],
            )
            if err is None:
                return self.async_create_entry(
                    title="Firecrawl Web Search",
                    data=values,
                )
            errors[CONF_URL] = err

        return self.async_show_form(
            step_id="user",
            data_schema=_schema(values, include_clear=False),
            errors=errors or None,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry) -> "FirecrawlSearchOptionsFlow":
        """Get the options flow for this handler."""
        return FirecrawlSearchOptionsFlow()


class FirecrawlSearchOptionsFlow(OptionsFlow):
    """Change the Firecrawl connection and defaults without touching code."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        current = _entry_values(self.config_entry)
        if user_input is not None:
            submitted = _flatten(user_input)
            clear_key = _as_bool(submitted.pop(CONF_CLEAR_API_KEY, False), False)
            values = _clean_values(submitted)
            entered_key = values[CONF_API_KEY]
            if entered_key:
                api_key = entered_key
            elif clear_key:
                api_key = ""
            else:
                api_key = current[CONF_API_KEY]
            values[CONF_API_KEY] = api_key

            err = await _probe(
                async_get_clientsession(self.hass),
                values[CONF_URL],
                api_key or None,
                values[CONF_SEARCH_TIMEOUT],
            )
            if err is None:
                return self.async_create_entry(title="", data=values)
            errors[CONF_URL] = err
            current = values

        return self.async_show_form(
            step_id="init",
            data_schema=_schema(current, include_clear=True),
            errors=errors or None,
        )
