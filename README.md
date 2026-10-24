# Firecrawl Web Search for Home Assistant

An [Assist](https://www.home-assistant.io/voice_control/) LLM tool that gives your
conversation agent (Ollama, OpenAI, Google, Anthropic, …) a `web_search` tool backed by a
**self-hosted [Firecrawl](https://github.com/firecrawl/firecrawl)** instance.

Ask things like *"Search the web for whether Celta plays today"* or *"google the price
of a train ticket from Ourense to Madrid"* — the agent calls the tool, gets the top
results (title, url, snippet) and answers from them, in the language of your pipeline.

## How it works

Uses the Home Assistant [LLM API](https://developers.home-assistant.io/core/internals/llm-api/)
tool-contribution mechanism: the integration ships an `llm.py` platform that registers a
web-search tool (`firecrawl_search__web_search`) on the built-in **Assist** API. Any
conversation agent configured with the
Assist API (e.g. the Ollama integration with *Control Home Assistant* enabled) picks the tool
up automatically — no changes to your pipelines or agents.

```
voice satellite → Assist pipeline → conversation agent (Ollama / OpenAI / …)
                                          ↓ tool call
                              POST {FIRECRAWL_URL}/v2/search   (self-hosted)
                                          ↓
                            top-3 results: title / url / snippet
```

Snippets only, by design (fast, voice-friendly). No scraping of individual pages.

## Requirements

- Home Assistant ≥ 2025.8 (LLM tools platform; tested on 2026.10.4)
- A reachable Firecrawl instance with its bundled search working
  (`POST /v2/search` returning `data.web[]`). The integration needs **no API key**
  if your instance does not enforce one (typical for a LAN/self-hosted stack).

## Installation

### HACS (custom repository)

1. HACS → ⋮ → *Custom repositories*
2. Add this repository, category **Integration**
3. Install *Firecrawl Web Search*, restart Home Assistant

### Manual

```bash
cp -r custom_components/firecrawl_search <config>/custom_components/
```
Restart Home Assistant.

## Configuration

No YAML needed — the Firecrawl URL is configured in the web UI:

- **First setup:** *Settings → Devices & Services → Add Integration → Firecrawl Web
  Search*. Enter your instance's URL — a base URL (`http://192.168.0.11:3002`) or the
  full search URL (`http://…:3002/v2/search`) both work. Before saving, the integration
  runs a real test search against it, so a wrong host/port/endpoint is caught at setup.
- **Change it later:** open the integration in *Settings → Devices & Services* and hit
  **Configure** — same probe, entry reloads automatically. No code edits, no restarts.
- **Without the UI (optional):** a bare `firecrawl_search:` key in `configuration.yaml`
  also works; the tool then uses the built-in default URL (`http://192.168.0.11:3002`,
  change `DEFAULT_SEARCH_URL` in `const.py` if you fork). A config entry, if present,
  overrides the YAML path.

Point it at your instance (host LAN IP works well from a separate HA machine;
a Tailscale/VPN IP makes it usable off-home). If your Firecrawl enforces an API key,
add an `Authorization: Bearer …` header to the `session.post(…)` call in
`__init__.py` — the shared HA aiohttp session keeps it out of any config storage.

## Using it

Make sure your conversation agent has the **Assist** LLM API enabled:

- *Settings → Voice assistants → edit your assistant → Conversation agent*
  (Ollama: the subentry must have *Control Home Assistant* checked — that is what
  enables the `assist` API)

Then just ask. The model decides when to search; the tool's description tells it to
search for current events, news, prices, weather, sport — anything that may have
changed recently — and never to claim it lacks real-time information.

Tool arguments: `query` (required), `count` (1–5, default 3), `lang` (language code;
the model picks it from your pipeline language, defaulting to `"gl"` when it doesn't).

## Troubleshooting

- *The assistant says it has no real-time access / doesn't search* — the most common
  cause is the tool never reaching the model: the integration must actually be **set
  up**. Either add it once through the UI flow (above), or keep the bare
  `firecrawl_search:` key in `configuration.yaml`. Then restart HA and look for the
  boot INFO line `firecrawl_search loaded: web_search tool registered`.
- *Tool never gets called despite being loaded* — check the agent actually has the
  `assist` API enabled, and that the model supports tool calling (Ollama cloud models
  do).
- *`search request failed`* in HA logs — Firecrawl unreachable from the HA host
  (test: `curl -X POST http://<host>:3002/v2/search -H 'Content-Type: application/json' -d '{"query":"test","limit":1}'`).
- Search activity is logged one INFO line per call
  (`Firecrawl web_search '<query>' lang=… -> N results`).
- Enable debug logging:
  ```yaml
  logger:
    logs:
      custom_components.firecrawl_search: debug
  ```

## License

MIT © Alberto Alonso Ruibal