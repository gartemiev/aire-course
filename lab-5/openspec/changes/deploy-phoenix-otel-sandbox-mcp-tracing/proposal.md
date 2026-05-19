# Proposal: deploy-phoenix-otel-sandbox-mcp-tracing

## Why

The lab-5 Experienced track requires three things that the current `lab-5/abox`
GitOps bundle cannot deliver today:

1. There is **no in-cluster observability backend**. `lab-5/abox/releases/`
   ships agentgateway + kagent only, so `Experienced #1`
   ([Arize Phoenix on Kubernetes](https://arize.com/docs/phoenix/self-hosting/deployment-options/kubernetes-helm))
   cannot be exercised.
2. The **Agent Sandbox controller is installed manually**
   (`kubectl apply -f https://github.com/kubernetes-sigs/agent-sandbox/releases/download/<VERSION>/manifest.yaml`).
   That out-of-band install violates the project's "every cluster change arrives
   through the `releases-lab5` OCI artifact" rule from
   `lab-5/abox/README.md`, so `Experienced #2`
   ([Sandbox metrics](https://agent-sandbox.sigs.k8s.io/docs/sandbox/metrics/))
   has no reproducible substrate.
3. There is **no custom MCP server in lab-5** to instrument. The only MCP route
   in `lab-5/abox/releases/agentgateway-mcp.yaml` is the public DeepWiki target,
   which we don't own and therefore cannot instrument with OpenInference.
   `Experienced #3`
   ([MCP tracing → Phoenix](https://arize.com/docs/phoenix/integrations/python/mcp-tracing))
   needs a server whose code we control.

We will close all three gaps in a single coordinated change, reusing the proven
lab-3 `time-mcp-server` and `time-agent` rather than scaffolding a new pair
from scratch.

## What Changes

- **Add Phoenix as an in-cluster trace backend** (`releases/phoenix.yaml`) using
  the official `arizephoenix/phoenix-helm` OCI chart, wrapped as a Flux
  `HelmRelease`. Expose its OTLP/HTTP ingestion endpoint inside the cluster and
  its UI on `/phoenix` through the existing `agentgateway-external` Gateway.
- **Add an OpenTelemetry Collector** (`releases/otel-collector.yaml`) deployed
  via the upstream Helm chart. The collector accepts OTLP/gRPC on `:4317` and
  OTLP/HTTP on `:4318` from any in-cluster client (sandboxes, MCP server,
  agent) and exports traces to Phoenix. A single ingestion endpoint
  (`http://otel-collector.observability.svc.cluster.local:4318`) means clients
  do not need to know whether the backend is Phoenix, Jaeger, or anything
  else - **BREAKING** for any future code that bypasses the collector.
- **Add Agent Sandbox via Flux** (`releases/agent-sandbox.yaml`,
  `releases/crds/agent-sandbox-crds.yaml`). Replace the manual
  `kubectl apply -f .../manifest.yaml` with a Flux `OCIRepository` +
  `Kustomization` reconciling the upstream `manifest.yaml` and
  `extensions.yaml`. The CRDs file becomes part of the `releases/crds/`
  kustomization so the regular CRDs-before-apps ordering holds.
- **Port lab-3 `time-mcp-server`** into `lab-5/time-mcp-server/` and
  **instrument it with OpenInference + Phoenix**. The image gains an
  `openinference-instrumentation-mcp` dependency and a `phoenix.otel.register`
  bootstrap so every tool call emits OpenInference spans. The container reads
  `OTEL_EXPORTER_OTLP_ENDPOINT` and `PHOENIX_COLLECTOR_ENDPOINT` from env so the
  collector address is injected by the manifest, not baked into the image.
- **Port lab-3 `time-agent`** into `lab-5/time-agent/` and instrument it
  symmetrically. Client-side `openinference-instrumentation-mcp` joins each
  agent→MCP call into the same trace as the server-side span, satisfying the
  "unique capability to trace client-to-server interactions under a single
  trace" property called out in the Phoenix MCP tracing docs.
- **Add a `SandboxTemplate`** (`releases/sandbox-template.yaml`) suitable for
  the Sandbox metrics walkthrough. The template runs a minimal Python image
  pre-loaded with `k8s-agent-sandbox[tracing]` and `opentelemetry-distro` so
  the `opentelemetry-instrument` CLI works out of the box.
- **Add CI for lab-5 images**: `.github/workflows/time-mcp-image-lab5.yaml` and
  `.github/workflows/time-agent-image-lab5.yaml`, identical in shape to the
  lab-3 workflows but scoped to `lab-5/abox/...` paths and the
  `lab-5-time-mcp-*` / `lab-5-time-agent-*` tag patterns. Images publish to
  `ghcr.io/<owner>/aire-course/lab-5/time-mcp-server` and
  `ghcr.io/<owner>/aire-course/lab-5/time-agent`.
- **Update `releases/kustomization.yaml`** to include the new manifests and
  `releases/crds/kustomization.yaml` to include the Agent Sandbox CRDs.
- **Update `lab-5/README.md` Solutions section** to document the Experienced
  track answers and the manual-uninstall step operators run once before the
  Flux-managed Agent Sandbox takes over.

## Capabilities

### New Capabilities

- `phoenix-observability`: In-cluster Arize Phoenix deployment that ingests
  OTLP traces, persists them in its bundled Postgres, and serves a UI. Includes
  the OpenTelemetry Collector that fronts Phoenix.
- `agent-sandbox-platform`: Flux-managed Agent Sandbox controller, its CRDs,
  and a baseline `SandboxTemplate` ready for the metrics walkthrough.
- `time-mcp-stack`: Lab-5 copies of the `time-mcp-server` MCP server and the
  `time-agent` kagent BYO agent, instrumented end-to-end with OpenInference so
  every client→server tool call lands as a single trace in Phoenix.
- `lab5-release-pipeline`: GitHub Actions workflows that publish lab-5 image
  artifacts (`time-mcp-server`, `time-agent`) to GHCR under the `lab-5/`
  scope, mirroring lab-3's release cadence.

### Modified Capabilities

_None._ `openspec/specs/` is currently empty (this is the first OpenSpec change
in lab-5), so every capability above is new. The change touches the existing
`lab-5/abox/releases/kustomization.yaml`, `lab-5/abox/releases/crds/kustomization.yaml`,
and the lab `README.md`, but those are not OpenSpec capabilities.

## Impact

- **Files added** under `lab-5/abox/releases/`: `phoenix.yaml`,
  `otel-collector.yaml`, `agent-sandbox.yaml`, `sandbox-template.yaml`,
  `time-mcp-server.yaml`, `time-agent.yaml`.
- **Files added** under `lab-5/abox/releases/crds/`: `agent-sandbox-crds.yaml`.
- **Files added** under `lab-5/abox/`: `time-mcp-server/`, `time-agent/`
  (copied from lab-3 and edited for OpenInference instrumentation).
- **Files added** under `.github/workflows/`: `time-mcp-image-lab5.yaml`,
  `time-agent-image-lab5.yaml`.
- **Files modified**: `lab-5/abox/releases/kustomization.yaml`,
  `lab-5/abox/releases/crds/kustomization.yaml`, `lab-5/README.md`.
- **New namespaces** in the cluster: `observability` (Phoenix + OTel Collector)
  and `agent-sandbox-system` (Agent Sandbox controller). `kagent` continues to
  host the MCP server and the agent.
- **Cluster reconcile ordering**: the new CRDs (`agent-sandbox-crds`) join
  `releases/crds/kustomization.yaml`, which Flux already reconciles before
  `releases/` (`dependsOn: releases-crds`, `wait: true` - preserved). Phoenix
  and the OTel Collector ship plain Helm charts so they fit in the same
  `releases/` kustomization without further ordering.
- **External dependencies**: Phoenix Helm chart
  (`oci://registry-1.docker.io/arizephoenix/phoenix-helm`), OpenTelemetry
  Collector Helm chart (`oci://ghcr.io/open-telemetry/opentelemetry-helm-charts/opentelemetry-collector`),
  Agent Sandbox release manifests
  (`https://github.com/kubernetes-sigs/agent-sandbox/releases/download/<VERSION>/manifest.yaml`
  and `.../extensions.yaml`), PyPI packages
  `openinference-instrumentation-mcp`, `arize-phoenix-otel`,
  `opentelemetry-instrumentation-httpx`, `opentelemetry-exporter-otlp`.
- **Manual one-time step before first Flux reconcile**: operator runs
  `kubectl delete -f https://github.com/kubernetes-sigs/agent-sandbox/releases/download/<VERSION>/manifest.yaml`
  (and `extensions.yaml`) to remove the prior hand-installed controller. The
  README documents this explicitly so reconciliation doesn't fight an orphaned
  Deployment + ClusterRoleBinding.
- **Testing surface**: each capability ships acceptance checks (`kubectl get`
  + `curl` + `pytest` flows) defined in its spec; a Phoenix smoke test asserts
  a unified MCP trace shows up end-to-end, and a Sandbox metrics smoke test
  asserts the `opentelemetry-instrument python main.py` flow from the upstream
  docs prints `Span` objects locally.
