# time-agent

ADK agent that answers time and timezone questions using the [time-mcp-server](../time-mcp-server). Designed to run in two places with the same code:

- **Locally**, via `agents-cli playground` (or `adk web`), against port-forwarded gateways.
- **In Kubernetes via kagent BYO** — the container speaks the [A2A protocol](https://adk.dev/a2a/) and kagent registers it as an `Agent` of `spec.type: BYO`.

## Project structure

```
time-agent/
├── app/
│   ├── agent.py        # root_agent (model + MCP toolset)
│   ├── a2a_app.py      # A2A entrypoint for kagent BYO (`uvicorn app.a2a_app:a2a_app`)
│   └── __init__.py
├── tests/
│   ├── unit/           # No-network wiring tests
│   ├── integration/    # Real MCP + A2A smoke tests
│   └── eval/           # ADK evalset + rubric
├── Dockerfile          # Builds the BYO image
├── GEMINI.md           # AI-assisted development guide
└── pyproject.toml
```

## Configuration (env vars)

| Var | Default | Purpose |
|-----|---------|---------|
| `MODEL_PROVIDER` | `openai` | `openai` → `LiteLlm` via agentgateway `/v1`; `gemini` → Vertex AI direct |
| `OPENAI_API_BASE` | _(unset → api.openai.com)_ | Set to the agentgateway `/v1` URL to route via the gateway; leave unset to talk to OpenAI directly |
| `OPENAI_API_KEY` | _(none)_ | Real key when going direct; placeholder is fine when going via the gateway |
| `OPENAI_MODEL` | `openai/gpt-4.1-mini` | LiteLLM model string |
| `OPENAI_EXTRA_HEADERS` | _(unset)_ | Optional JSON dict of headers added to every LLM call. Use for agentgateway routing/tenancy headers. Example: `'{"X-Route-Tier":"premium"}'` |
| `TIME_MCP_URL` | `http://localhost:8080/mcp` | URL of the time-mcp-server (gateway or direct). When using port-forward, see Local Development for port-collision notes |
| `MCP_EXTRA_HEADERS` | _(unset)_ | Optional JSON dict of headers added to every MCP request. Same use-case as `OPENAI_EXTRA_HEADERS` |
| `PORT` | `8080` | A2A server port (BYO) |
| `GEMINI_MODEL` | `gemini-flash-latest` | Used only when `MODEL_PROVIDER=gemini` |

## Local development

### Option A — via the cluster gateway (closest to prod)

`agents-cli playground` binds to `:8080`, so forward the gateway to a
different port (e.g. `:8090`) to avoid the collision.

```bash
# Terminal 1
kubectl -n agentgateway-system port-forward svc/agentgateway-external 8090:80

# Terminal 2
cd time-agent
export OPENAI_API_BASE=http://localhost:8090/v1
export TIME_MCP_URL=http://localhost:8090/mcp
export OPENAI_API_KEY=placeholder-gateway-handles-auth
agents-cli install
agents-cli playground   # opens http://127.0.0.1:8080/dev-ui
```

### Option B — local MCP + direct OpenAI

```bash
# Terminal 1 — run the MCP server locally on :3000
cd time-mcp-server && uv sync && uv run dev-http

# Terminal 2
cd time-agent
export TIME_MCP_URL=http://localhost:3000/mcp
export OPENAI_API_KEY=sk-…       # your real key
# leave OPENAI_API_BASE unset → LiteLLM uses api.openai.com
agents-cli playground
```

### A2A entrypoint directly

To exercise the same binary kagent BYO will run:

```bash
uv run uvicorn app.a2a_app:a2a_app --host 127.0.0.1 --port 8080
curl http://127.0.0.1:8080/.well-known/agent-card.json | jq
```

### Tests

```bash
uv run pytest tests/unit              # always runs, no network
uv run pytest tests/integration       # auto-skips if MCP not reachable
uv run adk eval tests/eval/evalsets/basic.evalset.json --config_file_path tests/eval/eval_config.json
```

## Deployment as kagent BYO

The container exposes the A2A protocol on `:8080`. Build via the existing
`time-agent-image-lab3` workflow, then register it with a `kind: Agent`
manifest of `spec.type: BYO`. Example:

```yaml
apiVersion: kagent.dev/v1alpha2
kind: Agent
metadata:
  name: time-agent
  namespace: kagent
spec:
  type: BYO
  description: "Agent that answers time and timezone questions."
  byo:
    deployment:
      image: ghcr.io/gartemiev/aire-course/lab-3/time-agent:<tag>
      env:
        - name: MODEL_PROVIDER
          value: openai
        - name: OPENAI_API_BASE
          value: http://agentgateway-external.agentgateway-system.svc.cluster.local/v1
        - name: TIME_MCP_URL
          value: http://agentgateway-external.agentgateway-system.svc.cluster.local/mcp
        - name: PORT
          value: "8080"
```

kagent creates the Deployment + Service and re-exposes the agent through the
controller at `:8083/api/a2a/kagent/time-agent/.well-known/agent.json`.
