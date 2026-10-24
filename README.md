# Firecrawl Web Search for Home Assistant

An [Assist](https://www.home-assistant.io/voice_control/) LLM tool that gives your
conversation agent (Ollama, OpenAI, Google, Anthropic, …) a `web_search` tool backed by a
**self-hosted [Firecrawl](https://github.com/firecrawl/firecrawl)** instance.

Ask things like *"Busca na web se xoga o Celta hoxe"* or *"google o prezo do billete de tren
Ourense Madrid"* — the agent calls the tool, gets the top results (title, url, snippet) and
answers from them, in the language of your pipeline.

## How it works

Uses the Home Assistant [LLM API](https://developers.home-assistant.io/core/internals/llm-api/)
tool-contribution mechanism: the integration ships an `llm.py` platform that registers a
`web_search` tool on the built-in **Assist** API. Any conversation agent configured with the
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

The Firecrawl URL is a constant in
`custom_components/firecrawl_search/__init__.py`:

```python
SEARCH_URL = "http://192.168.0.11:3002/v2/search"
```

Point it at your instance (host LAN IP works well from a separate HA machine;
a Tailscale/VPN IP makes it usable off-home). If your Firecrawl enforces an API key,
add an `Authorization: Bearer …` header to the `session.post(…)` call — the shared
HA aiohttp session keeps it out of any config storage.

No configuration entries, no UI: install, restart, done.

## Using it

Make sure your conversation agent has the **Assist** LLM API enabled:

- *Settings → Voice assistants → edit your assistant → Conversation agent*
  (Ollama: the subentry must have *Control Home Assistant* checked — that is what
  enables the `assist` API)

Then just ask. The model decides when to search; the tool prompt nudges it to use
search for current events, prices, weather, sport — anything outside the home.

Tool arguments: `query` (required), `count` (1–5, default 3), `lang` (language code,
default `"gl"` — edit the fallback in `async_call` in `__init__.py` to fit your family,
or just let the model pass `lang` explicitly).

## Troubleshooting

- *Tool never gets called* — check the agent actually has the `assist` API enabled, and
  that the model supports tool calling (Ollama cloud models do).
- *`search request failed`* in HA logs — Firecrawl unreachable from the HA host
  (test: `curl -X POST http://<host>:3002/v2/search -H 'Content-Type: application/json' -d '{"query":"test","limit":1}'`).
- Enable debug logging:
  ```yaml
  logger:
    logs:
      custom_components.firecrawl_search: debug
  ```

## License

MIT © Alberto Alonso Ruibal