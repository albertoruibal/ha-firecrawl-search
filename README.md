# Firecrawl Web Search for Home Assistant

An [Assist](https://www.home-assistant.io/voice_control/) LLM tool that gives your
conversation agent (Ollama, OpenAI, Google, Anthropic, …) a `web_search` tool backed by a
**self-hosted [Firecrawl](https://github.com/firecrawl/firecrawl)** instance.

Ask things like *"Search the web for whether Celta plays today"* or *"google the price
of a train ticket from Ourense to Madrid"* — the agent calls the tool, gets the top
results (title, url, snippet) and answers from them, in the language of your pipeline.
When snippets are not enough, the agent can call `read_page` to retrieve the full
markdown of a result URL.

## How it works

Uses the Home Assistant [LLM API](https://developers.home-assistant.io/core/internals/llm-api/)
tool-contribution mechanism: the integration ships an `llm.py` platform that registers
two web tools (`firecrawl_search__web_search` and `firecrawl_search__read_page`) on the
built-in **Assist** API. Any conversation agent configured with the Assist API (e.g. the
Ollama integration with *Control Home Assistant* enabled) picks them up automatically —
no changes to your pipelines or agents, and no per-model function definitions to write.

```
voice satellite → Assist pipeline → conversation agent (Ollama / OpenAI / …)
                                          ↓ tool call
                              POST {FIRECRAWL_URL}/v2/search   (snippets)
                                          ↓
                              POST {FIRECRAWL_URL}/v2/scrape   (full page)
```

Search returns title, url and a configurable snippet. Page retrieval returns clean
markdown, limited to a configurable number of characters. Base64 images are always
removed and only the main page content is returned.

## Requirements

- Home Assistant ≥ 2026.8 (LLM tools platform; tested on 2026.10.4)
- A reachable Firecrawl instance with its bundled search and scrape endpoints working
  (`POST /v2/search` returning `data.web[]`; `POST /v2/scrape` for full-page reads).
  The integration needs **no API key** if your instance does not enforce one (typical
  for a LAN/self-hosted stack).

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

No YAML needed — everything is configured in the web UI:

- **First setup:** *Settings → Devices & Services → Add Integration → Firecrawl Web
  Search*. Enter your instance's URL — a base URL (`http://192.168.0.1:3002`) or the
  full search URL (`http://…:3002/v2/search`) both work. Before saving, the integration
  runs a real test search against it, so a wrong host/port/endpoint is caught at setup.
- **Change settings later:** open the integration in *Settings → Devices & Services* and
  hit **Configure** — same probe, entry reloads automatically. No code edits, no restarts.
- **Without the UI (optional):** a bare `firecrawl_search:` key in `configuration.yaml`
  also works; the tools then use the built-in defaults below. A config entry, if present,
  overrides the YAML path.

The setup and options dialogs group the settings into **Connection**, **Search defaults**
and **Page retrieval** sections.

### Defaults

| Setting | Default | Notes |
|---|---|---|
| Firecrawl URL | `http://192.168.0.1:3002` | Base URL or full `/v2/search` URL |
| API key | empty | Optional for self-hosted; required by the hosted API |
| Number of results | 3 | 1–10; used when the model does not request a count |
| Snippet length | 300 characters | 100–2,000 |
| Default language | `en` | Used when the model does not provide `lang` |
| Search timeout | 15 seconds | 5–120 |
| Enable full-page retrieval | on | Registers the `read_page` tool |
| Max page characters | 20,000 | 1,000–50,000; longer pages are truncated |
| Page fetch timeout | 60 seconds | 1–300; Firecrawl request timeout |
| Cache max age | 0 hours | 0–168; `0` always fetches a fresh page |
| Page load wait | 0 seconds | 0–60; extra wait before extraction |

In the options dialog an empty API key field **keeps** the saved key. Tick *Clear saved
API key* to remove it. The key is stored in HA's config storage and only ever sent to
the Firecrawl host you configured.

### Using the hosted Firecrawl API (api.firecrawl.dev) instead

Don't run your own Firecrawl? Point the tools at the official hosted API:

1. Get an API key at [firecrawl.dev](https://www.firecrawl.dev/) (free tier available).
2. Set up the integration as above, with **URL** `https://api.firecrawl.dev` and your
   key in the **API key** field (sent as `Authorization: Bearer …`).
3. The same probe validates your key at setup — a wrong key is rejected with a clear
   error instead of failing later at runtime.

## Using it

Make sure your conversation agent has the **Assist** LLM API enabled:

- *Settings → Voice assistants → edit your assistant → Conversation agent*
  (Ollama: the subentry must have *Control Home Assistant* checked — that is what
  enables the `assist` API)

Then just ask. The model decides when to search; the tool descriptions tell it to search
for current events, news, prices, weather, sport — anything that may have changed
recently — and to read a result page when snippets are insufficient. They also tell it
never to claim it lacks real-time information.

Tool arguments:

- `web_search`: `query` (required), `count` (1–10, defaults to the configured value),
  `lang` (language code; defaults to the configured language).
- `read_page`: `url` (required, absolute `http`/`https`).

`read_page` can be slower than search and may consume additional Firecrawl credits.
Results longer than the configured character limit are returned truncated with a
`truncated` flag. Cache max age `0` always fetches the live page; increase it to reuse
Firecrawl's cache for faster, cheaper reads.

## Troubleshooting

- *The assistant says it has no real-time access / doesn't search* — the most common
  cause is the tool never reaching the model: the integration must actually be **set
  up**. Either add it once through the UI flow (above), or keep the bare
  `firecrawl_search:` key in `configuration.yaml`. Then restart HA and look for the
  boot INFO line `firecrawl_search loaded: Assist LLM tools registered`.
- *Tool never gets called despite being loaded* — check the agent actually has the
  `assist` API enabled, and that the model supports tool calling (Ollama cloud models
  do).
- *`search request failed`* in HA logs — Firecrawl unreachable from the HA host
  (test: `curl -X POST http://<host>:3002/v2/search -H 'Content-Type: application/json' -d '{"query":"test","limit":1}'`).
- *`page fetch failed`* in HA logs — Firecrawl's scrape endpoint is unreachable or
  disabled (test: `curl -X POST http://<host>:3002/v2/scrape -H 'Content-Type: application/json' -d '{"url":"https://example.com","formats":["markdown"]}'`).
- Search and page reads are logged one INFO line per call
  (`Firecrawl web_search … -> N results`, `Firecrawl read_page … -> N chars`).
- Enable debug logging:
  ```yaml
  logger:
    logs:
      custom_components.firecrawl_search: debug
  ```

## License

MIT © Alberto Alonso Ruibal
