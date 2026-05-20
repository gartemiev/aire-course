# Lab 5

## Beginner

1. **Agent Sandbox:** Review the examples:  
   https://agent-sandbox.sigs.k8s.io/docs/use-cases/examples/

2. Implement any example, or the recommended one:  
   **Network Policies**  
   https://agent-sandbox.sigs.k8s.io/docs/use-cases/examples/network-policies/

3. Review **Tracing and Evaluating** and complete the **Colab LangChain Application** tutorial:  
   https://colab.research.google.com/github/Arize-ai/phoenix/blob/main/tutorials/tracing/langchain_tracing_tutorial.ipynb

---

## Experienced

1. Deploy **Arize Phoenix** in `abox`:  
   https://arize.com/docs/phoenix/self-hosting/deployment-options/kubernetes-helm

2. Implement telemetry collection in **Agent Sandbox**:  
   https://agent-sandbox.sigs.k8s.io/docs/sandbox/metrics/

3. Instrument tracing for your own **MCP server** and send traces to **Phoenix**:  
   https://arize.com/docs/phoenix/integrations/python/mcp-tracing

---

## Max

1. Configure telemetry collection from **agentgateway** to **Phoenix**:  
   https://agentgateway.dev/docs/kubernetes/latest/tutorials/telemetry/

2. Review how to manage **Agent Sandbox** using the SDK:  
   https://agent-sandbox.sigs.k8s.io/docs/use-cases/examples/code-interpreter-agent-on-adk/

---

## Additional Tasks

These tasks can be completed when `abox` is already deployed. They are implemented using several Kubernetes manifests.

1. **API Key case on agentgateway**  
   https://agentgateway.dev/docs/kubernetes/latest/security/apikey/

2. **Guardrails case on agentgateway**  
   https://agentgateway.dev/docs/kubernetes/latest/llm/guardrails/webhook/guardrails/


# Solutions

## Beginners

### #1-2 **Agent Sandbox:** Review the examples, implement **Network Policies** example

In terms of https://github.com/kubernetes-sigs/agent-sandbox - I didn't include it into abox Flux flow since my assumption
was that these steps are mostly focused on familiarizing with it functionality and possbile use cases.

I've deployed suggested example without any issues. Key ides which I got is: 

Agent Sandbox is not an agent by itself. It is a Kubernetes-native sandbox/runtime layer where an agent can perform risky, stateful, or interactive actions.

For your context with Kagent / A2A / MCP, I would think about it like this:

```
Kagent Agent / BYO Agent
   |
   | decides what to do
   | calls MCP tools / public MCP server / internal tools
   |
   +--> Agent Sandbox
          |
          +--> execute code
          +--> run shell commands
          +--> work with files
          +--> browser/computer use
          +--> temporary workspace
```

In other words, the agent remains the “brain” and the orchestration layer, while the Sandbox is the “hands” or working environment where the agent can safely do things.

When the agent can live inside the Sandbox: 

This makes sense when We need a long-lived personal or project-specific agent environment, for example: one sandbox per user / project / repo.

Inside it, We may have:
* agent process
* workspace files
* git repo
* installed tools
* local cache
* memory/state
* browser session


## Experienced

### #1 Arize Phoenix

Phoenix ships as a Flux `HelmRelease` against
`oci://registry-1.docker.io/arizephoenix/phoenix-helm` (pin `0.1.13`) into
the `observability` namespace, fronted by an OpenTelemetry Collector.

- Manifests: [`lab-5/abox/releases/phoenix.yaml`](abox/releases/phoenix.yaml),
  [`lab-5/abox/releases/otel-collector.yaml`](abox/releases/otel-collector.yaml).
- UI URL: `http://<gateway-ip>/phoenix/` via the HTTPRoute on
  `agentgateway-external` (no auth — cluster-local).
- Local access (kind / no external LB): port-forward the gateway and
  open the UI through it:
  ```bash
  kubectl -n agentgateway-system port-forward svc/agentgateway-external 8081:80
  # → http://127.0.0.1:8081/phoenix/
  ```
  The same forward also serves the Phoenix REST API at
  `http://127.0.0.1:8081/phoenix/v1/...` (used by the filter examples
  in #3).
- Reset data: `kubectl delete pvc -l app.kubernetes.io/instance=phoenix -n observability`.

### #2 Agent Sandbox metrics walkthrough

The controller and CRDs are reconciled by Flux from vendored upstream
manifests at tag `v0.4.6`:

- Controller manifests: [`lab-5/abox/releases/agent-sandbox.yaml`](abox/releases/agent-sandbox.yaml).
- CRDs: [`lab-5/abox/releases/crds/agent-sandbox-crds.yaml`](abox/releases/crds/agent-sandbox-crds.yaml).
- Baseline template:
  [`lab-5/abox/releases/sandbox-template.yaml`](abox/releases/sandbox-template.yaml)
  (`python-sandbox-template` in `default`).
- Sandbox Router: the `k8s-agent-sandbox` SDK tunnels HTTP traffic into
  individual sandboxes via a separate `sandbox-router-svc`. Upstream
  ships only source under `clients/python/agentic-sandbox-client/sandbox-router/`,
  so we vendor it to [`lab-5/sandbox-router/`](sandbox-router/), build via
  [`time-mcp-image-lab5.yaml`-style CI](../.github/workflows/sandbox-router-image-lab5.yaml),
  and deploy via [`lab-5/abox/releases/sandbox-router.yaml`](abox/releases/sandbox-router.yaml).

Run the metrics walkthrough from a venv:

```bash
python -m venv .venv && source .venv/bin/activate
pip install "k8s-agent-sandbox[tracing]" opentelemetry-distro
opentelemetry-bootstrap -a install
OTEL_TRACES_EXPORTER=console OTEL_METRICS_EXPORTER=console \
  opentelemetry-instrument python main.py
```

Both `Span` and `resource_metrics` JSON should appear on stdout. Capture
the output and link it from this README when running the walkthrough.

### #3 MCP tracing → Phoenix

Both `time-mcp-server` and `time-agent` call
`phoenix.otel.register(project_name=..., auto_instrument=True)` at import
time, so `openinference-instrumentation-mcp` propagates trace context
across the MCP call. Each MCP tool is also wrapped with
`@tracer.tool(name="MCP.<tool>")` to emit an OpenInference tool span
around the tool body (with `input.value` / `output.value` / `tool.*`
attributes).

- Server bootstrap: [`time-mcp-server/src/core/server.py`](time-mcp-server/src/core/server.py)
  (`project_name="time-mcp-server"`); per-tool spans in
  [`src/tools/get_current_time.py`](time-mcp-server/src/tools/get_current_time.py)
  and [`src/tools/convert_time.py`](time-mcp-server/src/tools/convert_time.py).
- Agent bootstrap: same pattern in
  [`time-agent/app/agent.py`](time-agent/app/agent.py)
  (`project_name="time-agent"`).
- OTLP wiring: `OTEL_EXPORTER_OTLP_ENDPOINT` →
  `http://otel-collector.observability.svc.cluster.local:4318/v1/traces`
  on both deployments
  ([`time-mcp-server.yaml`](abox/releases/time-mcp-server.yaml),
  [`time-agent.yaml`](abox/releases/time-agent.yaml)). The full
  `/v1/traces` suffix is required — `register(endpoint=...)` passes the
  value straight to the OTLP exporter without auto-append.
- Gateway path: the agent reaches the server through the existing `/mcp`
  HTTPRoute on `agentgateway-external`, served by the single `time`
  target in [`agentgateway-mcp.yaml`](abox/releases/agentgateway-mcp.yaml)
  (→ `time-mcp.kagent.svc.cluster.local:3000`).

**How the trace appears in Phoenix.** Because the context propagates
client→server, one tool call is a single distributed trace. Phoenix
buckets each trace by the *root span's* project, so the trace lives in
`time-agent` and the server-side spans appear as nested children:

```
invoke_agent root_agent          (agent)
└─ execute_tool convert_time     (ADK, agent-side)
   └─ tools/call convert_time    (auto-instrumented; rpc.service=time-mcp-server)
      └─ MCP.convert_time        (@tracer.tool; tool.name, input.value, output.value)
```

The `time-mcp-server` project is registered at server startup but stays
empty under normal agent-driven traffic — server spans are never root,
so nothing anchors a trace there. To see only the MCP server's emission,
filter inside `time-agent`:

- UI (Spans tab): `'MCP.' in name`, or
  `attributes['rpc.service'] == 'time-mcp-server'`.
- REST:
  ```bash
  curl -s "http://127.0.0.1:8081/phoenix/v1/projects/time-agent/spans?limit=500" | jq '.data[] | select(.name | startswith("MCP."))'
  ```

### Validation (run after `make run`)

```bash
# Phoenix + OTel collector
kubectl -n observability get pods
curl -s http://127.0.0.1:8081/phoenix/ | head

# Agent Sandbox
kubectl -n agent-sandbox-system get pods
kubectl get crd | grep agents.x-k8s.io
kubectl get sandboxtemplate python-sandbox-template -o yaml

# Time stack
kubectl -n kagent get pods | grep -E 'time-mcp|time-agent'

# Unified trace test
GATEWAY_IP=<svc-ip> PHOENIX_BASE_URL=http://<svc-ip>/phoenix \
  uv run --directory lab-5/time-agent pytest tests/integration/test_phoenix_trace.py -q

# Unit suites (no cluster access)
uv run --directory lab-5/time-mcp-server pytest tests/unit -q
uv run --directory lab-5/time-agent      pytest tests/unit -q
```
