# Design

## Context

`lab-5/abox` is a vendored, lab-scoped fork of the `abox` GitOps bundle:

- KinD cluster `abox-lab5`, bootstrapped by `bootstrap/cluster.tf`.
- Flux Operator + FluxInstance + ResourceSetInputProvider in `bootstrap/flux.tf`
  reconcile the `releases-lab5` OCI artifact published from
  `lab-5/abox/releases/` by `.github/workflows/flux-push-lab5.yaml`
  on `lab5-v*` tags.
- `releases/crds/` reconciles first (`wait: true`), `releases/` second
  (`dependsOn: releases-crds`). This ordering is structural and **must not**
  be relaxed - kagent and agentgateway both rely on their CRDs existing before
  their HelmReleases install.
- The current bundle ships agentgateway, kagent, External Secrets, the lab-5
  DeepWiki MCP route, and (commented-out) the lab-5 `public-github-docs-agent`.
- The lab-3 bundle in `lab-3/abox/` ships the same agentgateway/kagent core
  plus a custom `time-mcp-server` + `time-agent` pair built and pushed by
  `.github/workflows/time-mcp-image-lab3.yaml` and
  `.github/workflows/time-agent-image-lab3.yaml`. Their image registries are
  scoped to `ghcr.io/<owner>/aire-course/lab-3/...` so they cannot collide
  with lab-5 images.
- Constraints inherited from `lab-5/abox/README.md`: gitless GitOps via OCI
  (no Git polling, no deploy keys), KinD on Apple Silicon needs multi-arch
  images, and the gateway is the single observable chokepoint for LLM and MCP
  traffic.
- Stakeholders: the lab-5 author/operator running `make run`, future labs
  that may layer telemetry on top of this work, and any reviewer following
  the OpenSpec workflow.

## Goals / Non-Goals

**Goals**

1. Deploy Arize Phoenix via Flux into a dedicated `observability` namespace
   with persistent storage so trace history survives controller restarts.
2. Deploy an OpenTelemetry Collector that fronts Phoenix and exposes a single
   in-cluster OTLP endpoint reachable from any namespace.
3. Replace the manual Agent Sandbox install with a Flux-managed deployment
   whose CRDs reconcile before the controller (no race with admission
   webhooks) and ship a `SandboxTemplate` the metrics walkthrough can use.
4. Port lab-3's `time-mcp-server` and `time-agent` into lab-5 with
   OpenInference + Phoenix tracing so a single MCP tool call shows up as one
   continuous trace from agent through gateway to server.
5. Reproduce the lab-3 CI image-build pattern for lab-5 so the new images are
   published independently of the `releases-lab5` OCI bundle.
6. Provide explicit, executable testing flows for each capability and a
   smoke test that asserts a unified trace lands in Phoenix.

**Non-Goals**

- We do not migrate kagent or agentgateway off their existing chart pins.
- We do not configure Phoenix evaluators, datasets, or any prompt playback
  features beyond what the default helm install enables - they are out of
  scope for the Experienced tasks.
- We do not implement the `Max` tasks (agentgateway → Phoenix telemetry,
  Sandbox SDK code-interpreter agent). Those remain future work.
- We do not migrate other agents (e.g. the commented-out
  `public-github-docs-agent`) onto the new tracing pipeline; their
  instrumentation can land in a follow-up change.
- We do not introduce Prometheus, Grafana, Tempo, or any non-Phoenix backend.
  Metrics from sandboxes that have no natural Phoenix home (e.g. SDK process
  metrics) are emitted to the collector's `logging` exporter for inspection
  during the lab; persisting them is out of scope.

## Decisions

### D1. Phoenix as an in-cluster Flux `HelmRelease`, not external SaaS

Phoenix is the explicit target named in the lab brief. Two install modes are
documented upstream:

- SaaS: Arize-hosted Phoenix at `app.phoenix.arize.com`. Free tier exists but
  requires an account, an API key, and outbound HTTPS for every trace.
- Self-host on Kubernetes with Helm.

We pick self-host. Rationale: the abox philosophy is reproducible local
infra with no external dependencies beyond GHCR pulls; the lab brief links
the self-host docs explicitly; and a self-hosted Phoenix lets us assert
"trace lands in Phoenix" in a test that runs offline.

The chart ships under `oci://registry-1.docker.io/arizephoenix/phoenix-helm`.
We wrap it as a Flux `OCIRepository` + `HelmRelease`, using the same idiom as
`releases/kagent.yaml`. We pin the chart version (initial value `0.1.13`) and
default Phoenix image - upgrades go through OpenSpec change proposals, not
silently via `latest`.

Storage: keep the chart's bundled Postgres with a `PersistentVolumeClaim`.
KinD's default storage class (`standard` / local-path) is sufficient for the
lab. The PVC retains data across `helm uninstall` per the upstream docs - we
note this in tests so a "reset Phoenix" step deletes the PVC explicitly.

Networking:
- ClusterIP `phoenix.observability.svc.cluster.local:6006` for OTLP/HTTP and
  the UI (the chart serves both on the same port).
- An `HTTPRoute` on the existing `agentgateway-external` Gateway exposes the
  UI at `/phoenix` so the operator hits `http://<gateway-ip>/phoenix` after
  `make run`. No TLS terminations or auth - this is local-only.

**Alternatives considered**

- Pin to the Helm chart's stable image tag without specifying `version`: too
  loose, breaks the project's "pin everything" habit observed in
  `releases/kagent.yaml` and `releases/agentgateway.yaml`.
- Run Phoenix in `kagent` namespace next to the existing workloads: collides
  with the chart's expectation that it owns its namespace, and makes a
  per-namespace NetworkPolicy in lab-6 harder. Dedicated `observability`
  namespace mirrors the OTel convention (`opentelemetry-system` is widely
  used; we shorten to `observability` because both Phoenix and the collector
  share it).

### D2. OpenTelemetry Collector fronting Phoenix

Phoenix accepts OTLP/HTTP directly, so a collector is not strictly required
for MCP tracing. We still include one because:

- The Sandbox metrics walkthrough emits **both** traces and metrics. Phoenix
  is a trace backend and silently drops metrics. The collector lets us route
  traces → Phoenix and metrics → `logging` (or future Prometheus) without
  every client knowing.
- The agentgateway → Phoenix integration in the `Max` track also expects an
  OTel endpoint. Having the collector in place future-proofs that work.
- Single endpoint (`http://otel-collector.observability.svc.cluster.local:4318`)
  is the only thing clients need to know. Pointing the same env var at a
  different backend later is a one-line change in
  `releases/otel-collector.yaml`, not a fleet-wide rollout.

We use the upstream `opentelemetry-collector` chart from
`oci://ghcr.io/open-telemetry/opentelemetry-helm-charts` with
`mode: deployment` (not DaemonSet - we don't need node-level collection for
the lab). The pipeline is intentionally minimal:

```yaml
receivers:
  otlp:
    protocols:
      grpc: { endpoint: 0.0.0.0:4317 }
      http: { endpoint: 0.0.0.0:4318 }
exporters:
  otlphttp/phoenix:
    endpoint: http://phoenix.observability.svc.cluster.local:6006
  debug: { verbosity: detailed }
service:
  pipelines:
    traces:
      receivers: [otlp]
      exporters: [otlphttp/phoenix]
    metrics:
      receivers: [otlp]
      exporters: [debug]
```

**Alternatives considered**

- Direct OTLP from clients to Phoenix: shorter pipeline but couples every
  client to Phoenix's URL and forces us to multiplex traces vs metrics in the
  client. Rejected.
- Collector as DaemonSet: unnecessary for a 3-node KinD lab; doubles the pod
  count.
- Tempo + Grafana as the trace backend, with Phoenix as a frontend pointing
  at Tempo: massive scope expansion. Phoenix self-hosted with its bundled
  Postgres covers the lab brief.

### D3. Agent Sandbox managed by Flux via the upstream `manifest.yaml`

The upstream project ships `manifest.yaml` (controller + RBAC) and
`extensions.yaml` (SandboxTemplate / SandboxClaim / SandboxWarmPool CRDs +
controllers) as plain Kubernetes YAML, not a Helm chart. Flux's
`Kustomization` happily reconciles raw YAML from an `OCIRepository`, but
upstream does not currently publish OCI artifacts - only GitHub release
assets and a tag in the `kubernetes-sigs/agent-sandbox` Git repo.

Two options:

1. Use a `GitRepository` source pointing at the upstream Git tag and a
   `Kustomization` selecting `config/default` (or wherever the rendered
   YAML lives) - couples us to the upstream repo layout.
2. Vendor `manifest.yaml` + `extensions.yaml` into the lab-5 release bundle
   at a fixed version and reconcile them through the existing `releases-lab5`
   OCI artifact path.

We pick **option 2**. Rationale:

- Keeps the cluster's only Git polling target at zero (abox philosophy).
- Pinning is explicit in the file's URL comment; updates land via a normal
  OpenSpec change.
- The lab readme references a specific tag pattern
  (`curl -s .../releases/latest | jq -r .tag_name`); we resolve that once at
  spec-authoring time, vendor the manifests, and record the version we
  vendored. Initial target: `v0.7.0` (latest at the time of writing) - the
  proposal authorising team is free to bump it.

CRDs ship in `releases/crds/agent-sandbox-crds.yaml`, the controller
deployments live in `releases/agent-sandbox.yaml`. The split matches how
kagent CRDs and kagent itself are separated today, so the `releases-crds`
kustomization (with `wait: true`) blocks until CRDs are healthy before the
controller HelmRelease applies.

The manual `kubectl apply -f .../manifest.yaml` the operator ran previously
left a `Deployment` and `ClusterRoleBinding` outside any Flux-managed
selector. Flux will not delete unmanaged resources by default
(`prune: true` only deletes resources it created), so we document a one-time
`kubectl delete -f .../manifest.yaml` step in the README before
`make run` for lab-5.

**Alternatives considered**

- Helmify upstream YAML: out-of-scope and brittle (their manifests evolve).
- Re-run the manual install on every `make run`: violates GitOps and means
  there's no audit trail.

### D4. Reuse lab-3 server/agent code, instrument additively

The lab brief says "you may reuse lab-3/abox/time-mcp-server and time-agent
and all associated configuration". We copy the directories wholesale into
`lab-5/time-mcp-server/` and `lab-5/time-agent/` rather than
symlink or sharing across labs:

- Symlinking breaks the lab-N isolation property (each lab is currently a
  self-contained snapshot).
- Sharing across labs means an instrumentation change in lab-5 silently
  reshapes lab-3's running container.
- Copy + edit keeps the lab-3 image at `ghcr.io/.../lab-3/...` stable for the
  lab-3 workflow.

The image change is small and additive:

1. Add deps: `arize-phoenix-otel`, `openinference-instrumentation-mcp`,
   `opentelemetry-instrumentation-httpx`,
   `opentelemetry-exporter-otlp` to `pyproject.toml`.
2. At MCP server startup, before `mcp.run(...)`:
   ```python
   from phoenix.otel import register
   tracer_provider = register(
       project_name=os.environ.get("PHOENIX_PROJECT_NAME", "time-mcp-server"),
       endpoint=os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT"),
       auto_instrument=True,
   )
   tracer = tracer_provider.get_tracer("time-mcp-server")
   ```
3. Wrap tools with `@tracer.tool(name="MCP.<tool>")` per the
   [Phoenix MCP tracing docs](https://arize.com/docs/phoenix/integrations/python/mcp-tracing).
4. The agent does the same `register(...)` plus
   `openinference-instrumentation-mcp` so its outbound MCP calls propagate
   the trace context. The Phoenix MCP integration explicitly handles
   client→server context propagation - that is the whole point of installing
   `openinference-instrumentation-mcp` on both sides.

Environment-driven config (no image rebuild for endpoint changes):

- `OTEL_EXPORTER_OTLP_ENDPOINT` -
  `http://otel-collector.observability.svc.cluster.local:4318`.
- `OTEL_EXPORTER_OTLP_PROTOCOL` - `http/protobuf` (matches collector OTLP/HTTP).
- `PHOENIX_PROJECT_NAME` - `time-mcp-server` or `time-agent` (so the Phoenix UI
  groups spans per service).
- `PHOENIX_COLLECTOR_ENDPOINT` - optional, used by `register()` when the user
  wants traces to skip the collector and go straight to Phoenix during local
  debug. Unset in the in-cluster manifests; documented for local dev.

If any of these env vars is unset, `register()` from `arize-phoenix-otel`
falls back to its defaults (`http://localhost:6006/v1/traces`), which makes
local debugging trivial: `phoenix serve` + `python -m app.main` "just works".

**Alternatives considered**

- A new MCP server from scratch in lab-5: rejected by the user's brief
  ("you may reuse...").
- Sidecar OTel agent per pod instead of a cluster collector: doubles the
  pod count and obscures the data path during debugging.
- Tracing via the agentgateway sidecar: that's the `Max` track, out of scope.

### D5. CI workflows mirror the lab-3 shape

`.github/workflows/time-mcp-image-lab3.yaml` is well-shaped: dual mode
(branch push → build only; tag push → build + publish), multi-arch
(amd64 + arm64), GHA cache, tag pattern `lab-3-time-mcp-<semver>`.

We replicate that exactly with `lab-5` substituted everywhere:

- Paths: `lab-5/time-mcp-server/**`,
  `lab-5/time-agent/**`.
- Tag patterns: `lab-5-time-mcp-*`, `lab-5-time-agent-*`.
- Image tags: `ghcr.io/<owner>/aire-course/lab-5/time-mcp-server`,
  `ghcr.io/<owner>/aire-course/lab-5/time-agent`.
- Workflow file names: `time-mcp-image-lab5.yaml`,
  `time-agent-image-lab5.yaml`.

The `flux-push-lab5.yaml` workflow already exists and publishes
`releases-lab5` from `./lab-5/abox/releases` on `lab5-v*` tags, so the
existing tag cadence (`make push`) is unchanged.

**Alternatives considered**

- Reusable workflow `_image-build.yaml` with lab as a matrix input: cleaner
  in steady state but breaks the principle "each lab is self-contained, you
  can read one workflow and understand the whole lifecycle". Future
  refactor, not this change.

### D6. SandboxTemplate purpose-built for the metrics walkthrough

The upstream docs assume a `SandboxTemplate` named `python-sandbox-template`
(or the simpler `simple-sandbox-template`) is already applied. We ship
`releases/sandbox-template.yaml` defining `python-sandbox-template`:

- Base image: `python:3.12-slim` plus a tiny init script that
  `pip install "k8s-agent-sandbox[tracing]" opentelemetry-distro` and runs
  `opentelemetry-bootstrap -a install`. This matches the prerequisites
  section of the metrics doc verbatim.
- Resource limits: 200m CPU / 256Mi RAM so a sandbox is cheap to keep
  around.
- No persistent storage initially - the walkthrough only echoes
  `Hello World`. The Sandbox API supports adding PVCs later.

**Alternatives considered**

- A purpose-built sandbox image hosted in GHCR: locks the lab to one image
  rev; not worth it for an `echo Hello World` demo.
- No template: the walkthrough cannot run without one. Rejected.

### D7. Observability namespace, RBAC, and gateway exposure

- Both Phoenix and the OTel collector run in `observability`. The
  `releases/phoenix.yaml` and `releases/otel-collector.yaml` both declare the
  namespace; the second declaration is a no-op once the first one has
  applied, and Flux's `kustomize` build merges them cleanly.
- Phoenix's UI is exposed through the existing
  `agentgateway-external` Gateway via an `HTTPRoute` matching `/phoenix`. A
  `ReferenceGrant` from the `agentgateway-system` HTTPRoute to the
  `observability` Service is added (modelled on the existing
  `ReferenceGrant` in `releases/kagent.yaml`).
- The OTel collector is **not** exposed through the gateway. Trace ingestion
  is in-cluster only; nothing outside the cluster should write traces.

### D8. Versioning and rollout

- The lab-5 OCI bundle is bumped by a single tag (`lab5-v0.2.0` say) after
  all six new manifests land. Flux's RSIP picks the new tag within 5
  minutes; `make push` from `lab-5/abox/` is unchanged.
- The two image workflows publish independently. Image pins in the
  manifests start at `0.1.0` for both `time-mcp-server` and `time-agent`,
  then move forward as instrumentation changes warrant.
- The Agent Sandbox vendored manifests carry a `# version: v0.7.0` header
  comment so the next OpenSpec change can grep for the pin.

## Risks / Trade-offs

- **Phoenix PVC retention on uninstall**: the chart explicitly does not
  delete the PVC on `helm uninstall`. If an operator reinstalls Phoenix in
  the same namespace, the new Postgres pod fails to attach to the existing
  PVC if its credentials changed. → Document `kubectl delete pvc -l app.kubernetes.io/instance=phoenix -n observability`
  as the "reset Phoenix data" step in the README.
- **Manual cleanup before first Flux reconcile of Agent Sandbox**: the
  hand-installed controller's ClusterRoleBinding has different selectors
  than the Flux-managed one, so leaving both around results in two
  controllers fighting over the same CRDs. → README documents
  `kubectl delete -f https://github.com/kubernetes-sigs/agent-sandbox/releases/download/<VERSION>/manifest.yaml`
  and `extensions.yaml` once. The OpenSpec change documents the same step.
- **OpenInference instrumentor coverage**: the Phoenix MCP integration does
  not generate spans by itself - it only stitches client/server traces
  together. Without `auto_instrument=True` on `register()` you get an empty
  trace. → Bootstrap code calls `register(auto_instrument=True)`, and the
  smoke test asserts at least two spans on each side (server tool call +
  outbound LLM call from the agent).
- **OTel collector single point of failure**: a crashed collector silently
  drops traces; clients don't retry indefinitely. → For the lab this is
  acceptable. We set `replicas: 1`, `resources.requests` modest, and accept
  the trade-off. In production this would warrant a deployment with
  `replicas: 2` and a PodDisruptionBudget; explicitly noted as out of scope.
- **Image multi-arch**: lab-3 already documents the gotcha
  (`docker/setup-qemu-action`, `platforms: linux/amd64,linux/arm64`). We
  inherit it verbatim.
- **Phoenix image size**: the chart pulls ~1GB of Postgres + Phoenix. KinD
  pulls it once per node, which slows first `make run` by a few minutes. →
  Note in README; not solvable without a registry mirror.
- **CI tag collision**: `lab-5-time-mcp-*` and `lab-5-time-agent-*` are new
  tag namespaces; no overlap with existing `lab-3-*` and `lab-4-*` tags. →
  Verified by inspecting `.github/workflows/*.yaml`.
- **Phoenix exposed at `/phoenix` overlaps with kagent UI at `/`**: the
  kagent HTTPRoute has a catch-all `/` route. Gateway API matches by
  longest-prefix, so `/phoenix` wins over `/`. Verified by reading
  `releases/kagent.yaml`. Should kagent's route ever become exclusive, the
  Phoenix exposure must be re-routed (e.g. dedicated hostname). Documented.
- **Phoenix in-cluster vs SaaS for production**: this lab uses self-host;
  any real workflow with retention/SLO requirements should swap to
  SaaS or a managed alternative. Out of scope here but flagged.

## Migration Plan

1. **Pre-reconcile cleanup (one-time, manual)**: operator runs:
   ```bash
   VERSION=$(curl -s https://api.github.com/repos/kubernetes-sigs/agent-sandbox/releases/latest | jq -r .tag_name)
   kubectl delete -f https://github.com/kubernetes-sigs/agent-sandbox/releases/download/${VERSION}/extensions.yaml --ignore-not-found
   kubectl delete -f https://github.com/kubernetes-sigs/agent-sandbox/releases/download/${VERSION}/manifest.yaml --ignore-not-found
   ```
   The README adds this snippet under "lab-5 first run".
2. **Author the lab-5 release artifacts** (manifests, code, workflows) in
   the order tasks.md prescribes.
3. **First image publish**: tag `lab-5-time-mcp-0.1.0` and
   `lab-5-time-agent-0.1.0`; CI publishes images to GHCR. Verify packages
   are public (`gh api -H "Accept: application/vnd.github+json"
   /user/packages/container/aire-course%2Flab-5%2Ftime-mcp-server`).
4. **First bundle publish**: tag `lab5-v<next>` to publish a new
   `releases-lab5` OCI artifact via `flux-push-lab5.yaml`.
5. **Bootstrap or reconcile the cluster**:
   - Fresh cluster: `cd lab-5/abox && make run`.
   - Existing cluster: `flux reconcile source oci releases -n flux-system`
     and `flux reconcile kustomization releases -n flux-system`.
6. **Validation**:
   - `kubectl -n observability get pods` shows Phoenix and the OTel
     collector both Ready.
   - `kubectl -n agent-sandbox-system get pods` shows the controller
     Ready; `kubectl get crd | grep agents.x-k8s.io` shows the four
     Sandbox CRDs.
   - `kubectl -n kagent get pods | grep -E 'time-mcp|time-agent'` shows
     both Ready.
   - `curl -s http://<gateway-ip>/phoenix` returns the Phoenix UI.
   - Smoke test (`tasks.md` §7): run the Python script from
     `lab-5/time-agent/tests/integration/test_phoenix_trace.py`
     against the running gateway; assert a span with `name=MCP.get_current_time`
     appears in Phoenix's API.
7. **Rollback**: if anything goes wrong, retag `lab5-v<previous>` to point
   `releases-lab5:latest` back at the prior bundle, then
   `flux reconcile source oci releases -n flux-system`. The prior bundle has
   no Phoenix / OTel / Sandbox manifests, so Flux's `prune: true` removes
   them cleanly. CRDs need `kubectl delete crd ...` manually because Flux
   prunes them but the operator may want their data preserved.

## Open Questions

- **Phoenix retention**: how many days of traces do we want to keep on the
  KinD PVC? Default is unlimited (Postgres until disk full). We propose
  documenting "wipe via `kubectl delete pvc ...`" but not configuring an
  automatic retention job in this change.
- **Auth on the `/phoenix` route**: the Phoenix UI ships with optional
  basic auth + admin user. For the lab we leave it open; should we wire
  the `aire-openai-token` ExternalSecret pattern to inject a Phoenix admin
  password? Deferred unless the reviewer asks.
- **Sandbox extensions vs core**: do we need
  `SandboxClaim`/`SandboxWarmPool` for the metrics walkthrough? The doc's
  example uses `python-sandbox-template`, which implies `extensions.yaml`
  is needed. We default to deploying both `manifest.yaml` and
  `extensions.yaml`. If only the core CRDs are required, future changes
  can drop the extensions kustomization.
