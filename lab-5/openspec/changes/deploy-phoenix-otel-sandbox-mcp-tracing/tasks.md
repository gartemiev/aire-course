# Tasks

## 1. Pre-flight cleanup and discovery

- [x] 1.1 Run `curl -s https://api.github.com/repos/kubernetes-sigs/agent-sandbox/releases/latest | jq -r .tag_name` and record the exact Agent Sandbox release tag we will vendor (call it `${SANDBOX_VERSION}` in the rest of this checklist). _Recorded: `${SANDBOX_VERSION}=v0.4.6` (manifest sha256 db8424b2…; extensions sha256 b8f88c4b…)._
- [ ] 1.2 On any cluster that ran the manual install, run `kubectl delete -f https://github.com/kubernetes-sigs/agent-sandbox/releases/download/${SANDBOX_VERSION}/extensions.yaml --ignore-not-found` and `kubectl delete -f https://github.com/kubernetes-sigs/agent-sandbox/releases/download/${SANDBOX_VERSION}/manifest.yaml --ignore-not-found`. Confirm `kubectl get crd | grep agents.x-k8s.io` returns nothing afterwards.
- [x] 1.3 Confirm `lab-5/abox/releases/kustomization.yaml` and `lab-5/abox/releases/crds/kustomization.yaml` are at their current contents, so the diff in §6 is clean.
- [ ] 1.4 Confirm the GHCR packages we intend to create (`lab-5/time-mcp-server`, `lab-5/time-agent`, `lab-5/releases-lab5`) do not collide with anything pre-existing under `https://github.com/<owner>?tab=packages`.

## 2. Vendor Agent Sandbox manifests under Flux

- [x] 2.1 Download `https://github.com/kubernetes-sigs/agent-sandbox/releases/download/${SANDBOX_VERSION}/manifest.yaml` and place it at `lab-5/abox/releases/agent-sandbox.yaml`. Prepend a comment block recording the source URL, the `${SANDBOX_VERSION}` value, and the SHA-256 of the downloaded file.
- [x] 2.2 Download `extensions.yaml` from the same release, append its contents to the same file separated by `---`, and record its SHA-256 in the same header comment. _Dedup note: kept only the extensions-flavoured Deployment (strict superset); both Deployments would collide in `kustomize build`._
- [x] 2.3 Move any CRD definitions found in those two files into `lab-5/abox/releases/crds/agent-sandbox-crds.yaml`, leaving only Namespaces, RBAC, Services, and Deployments in `agent-sandbox.yaml`. Record the upstream release tag in a header comment in the CRDs file.
- [x] 2.4 Append `agent-sandbox-crds.yaml` to `lab-5/abox/releases/crds/kustomization.yaml` under `resources:` (after `kmcp-crds.yaml`).
- [x] 2.5 Append `agent-sandbox.yaml` to `lab-5/abox/releases/kustomization.yaml` under `resources:` (after `kagent.yaml`).
- [x] 2.6 Write `lab-5/abox/releases/sandbox-template.yaml` defining a `SandboxTemplate` named `python-sandbox-template` whose pod spec runs `python:3.12-slim`, has an init step that runs `pip install "k8s-agent-sandbox[tracing]" opentelemetry-distro && opentelemetry-bootstrap -a install`, and sets resource requests/limits per `design.md` §D6. Append the file to `releases/kustomization.yaml`.

## 3. Deploy Phoenix and the OpenTelemetry Collector via Flux

- [x] 3.1 Write `lab-5/abox/releases/phoenix.yaml`: declare the `observability` Namespace, an `OCIRepository` named `phoenix` pointing at `oci://registry-1.docker.io/arizephoenix/phoenix-helm` with `ref.tag` pinned to `0.1.13` (or the latest stable at implementation time - record the version chosen in the file's header comment), and a `HelmRelease` named `phoenix` in `observability` with PVC-backed Postgres enabled and the Phoenix Service exposed on the default port.
- [x] 3.2 Append a `ReferenceGrant` allowing HTTPRoutes from `agentgateway-system` to reach Services in `observability`, and an `HTTPRoute` named `phoenix` that matches `PathPrefix /phoenix` and forwards to the Phoenix Service on its UI port. Mirror the style of `lab-5/abox/releases/kagent.yaml`'s `ReferenceGrant` + `HTTPRoute` pair.
- [x] 3.3 Write `lab-5/abox/releases/otel-collector.yaml`: declare an `OCIRepository` for `oci://ghcr.io/open-telemetry/opentelemetry-helm-charts/opentelemetry-collector` pinned to a concrete chart version, and a `HelmRelease` deploying the collector with `mode: deployment`, OTLP gRPC on `:4317` and OTLP HTTP on `:4318`, and an `otlphttp/phoenix` exporter pointing at `http://phoenix.observability.svc.cluster.local:6006`. Wire `service.pipelines.traces` to `[otlphttp/phoenix]` and `service.pipelines.metrics` to `[debug]`.
- [x] 3.4 Append both files to `lab-5/abox/releases/kustomization.yaml`.

## 4. Port lab-3 `time-mcp-server` into lab-5

- [x] 4.1 `cp -R lab-3/abox/time-mcp-server lab-5/time-mcp-server`. Commit the verbatim copy before any edits so the diff in subsequent steps is review-friendly.
- [x] 4.2 In `lab-5/time-mcp-server/pyproject.toml`, add the dependencies `arize-phoenix-otel`, `openinference-instrumentation-mcp`, `opentelemetry-instrumentation-httpx`, `opentelemetry-exporter-otlp` to the primary dependency list.
- [x] 4.3 In `lab-5/time-mcp-server/src/core/server.py` (or the startup module identified by reading the source), call `phoenix.otel.register(project_name=os.environ.get("PHOENIX_PROJECT_NAME", "time-mcp-server"), endpoint=os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT"), auto_instrument=True)` before `mcp.run(...)` and expose the returned `tracer_provider` as a module-level `TRACER_PROVIDER`. Acquire a tracer via `tracer = tracer_provider.get_tracer("time-mcp-server")`.
- [x] 4.4 Decorate each `@mcp.tool()` (`get_current_time`, `convert_time`, `echo`) with `@tracer.tool(name="MCP.<tool_name>")`. Update tool unit tests to confirm decoration is applied (e.g. via `tool.__wrapped__` presence) or, where the FastMCP API exposes a tool registry, walk the registry and assert each entry's span name.
- [x] 4.5 Add `lab-5/time-mcp-server/tests/unit/test_tracing.py`: monkeypatch `phoenix.otel.register` and assert the server's startup hook calls it with `auto_instrument=True`.
- [x] 4.6 Write `lab-5/abox/releases/time-mcp-server.yaml` based on `lab-3/abox/releases/time-mcp-server.yaml` but with: `image: ghcr.io/<owner>/aire-course/lab-5/time-mcp-server:0.1.0`, three additional env vars (`OTEL_EXPORTER_OTLP_ENDPOINT`, `OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf`, `PHOENIX_PROJECT_NAME=time-mcp-server`), and the `RemoteMCPServer` URL unchanged. Add the file to `releases/kustomization.yaml`.

## 5. Port lab-3 `time-agent` into lab-5

- [x] 5.1 `cp -R lab-3/abox/time-agent lab-5/time-agent`. Commit the verbatim copy before any edits.
- [x] 5.2 In `lab-5/time-agent/pyproject.toml`, add `arize-phoenix-otel`, `openinference-instrumentation-mcp`, `openinference-instrumentation-openai`, `opentelemetry-instrumentation-httpx`, `opentelemetry-exporter-otlp` to the primary dependency list.
- [x] 5.3 In `lab-5/time-agent/app/a2a_app.py` (or `app/agent.py` if the bootstrap belongs there), call `phoenix.otel.register(...)` with the same env-driven config as in 4.3, before constructing the `Agent` / `AgentCardBuilder`.
- [x] 5.4 Add an integration test `lab-5/time-agent/tests/integration/test_phoenix_trace.py` that: (a) skips unless `GATEWAY_IP` and `PHOENIX_BASE_URL` are set, (b) drives the agent end-to-end with a question that forces a `get_current_time` tool call, (c) polls Phoenix's `/v1/projects/{project}/spans` API for both projects until both have a span sharing a `trace_id`, (d) fails after 60 s with a clear error.
- [x] 5.5 Add a unit test `lab-5/time-agent/tests/unit/test_tracing.py` mirroring 4.5.
- [x] 5.6 Write `lab-5/abox/releases/time-agent.yaml` based on `lab-3/abox/releases/time-agent.yaml` but with: `image: ghcr.io/<owner>/aire-course/lab-5/time-agent:0.1.0`, the same three OTel env vars (`PHOENIX_PROJECT_NAME=time-agent`), and the existing OpenAI/MCP wiring unchanged. Add the file to `releases/kustomization.yaml`.

## 6. Federate the time MCP target through agentgateway

- [x] 6.1 Edit `lab-5/abox/releases/agentgateway-mcp.yaml`: add a second `targets[]` entry named `time` pointing at `time-mcp.kagent.svc.cluster.local:3000` with `protocol: StreamableHTTP`, keeping the existing `deepwiki` target. Verify the `HTTPRoute` rule still matches `PathPrefix /mcp`.
- [x] 6.2 Re-read `lab-5/abox/releases/kustomization.yaml` end-to-end and confirm the `resources:` list now includes `phoenix.yaml`, `otel-collector.yaml`, `agent-sandbox.yaml`, `sandbox-template.yaml`, `time-mcp-server.yaml`, and `time-agent.yaml`.
- [x] 6.3 Re-read `lab-5/abox/releases/crds/kustomization.yaml` and confirm `agent-sandbox-crds.yaml` is appended.

## 7. CI workflows

- [x] 7.1 Create `.github/workflows/time-mcp-image-lab5.yaml` by copying `.github/workflows/time-mcp-image-lab3.yaml` and substituting every `lab-3` with `lab-5` (workflow name header, paths, tag prefixes, image registry, `if:` predicate). Do not change any other line.
- [x] 7.2 Create `.github/workflows/time-agent-image-lab5.yaml` by copying `.github/workflows/time-agent-image-lab3.yaml` and applying the same `lab-3` → `lab-5` substitution.
- [x] 7.3 Diff the new workflows against their lab-3 originals to verify only the `lab-3` → `lab-5` substitution occurred. Reject the change if any other line differs.
- [ ] 7.4 Tag and push `lab-5-time-mcp-0.1.0` and `lab-5-time-agent-0.1.0` to trigger first image publishes. Verify the images appear in GHCR, mark both packages public if they default to private (one-time per package).

## 8. Bundle publish and reconcile

- [ ] 8.1 Commit and push all manifest changes from §2-§6 to `main`.
- [ ] 8.2 `cd lab-5/abox && make push` (or tag `lab5-v<next>` directly) to publish a new `releases-lab5` OCI artifact via `.github/workflows/flux-push-lab5.yaml`.
- [ ] 8.3 Force-reconcile the cluster: `kubectl --kubeconfig lab-5/abox/bootstrap/abox-lab5-config annotate ocirepository releases -n flux-system reconcile.fluxcd.io/requestedAt="$(date +%s)" --overwrite`.
- [ ] 8.4 Wait for all Kustomizations to converge: `flux get kustomization -A` SHALL show `releases-crds` and `releases` both `Ready=True`.

## 9. End-to-end validation

- [ ] 9.1 `kubectl -n observability get pods` SHALL show Phoenix and the OTel collector both Ready.
- [ ] 9.2 `kubectl -n agent-sandbox-system get pods` SHALL show the Agent Sandbox controller Ready; `kubectl get crd | grep agents.x-k8s.io` SHALL list at least four CRDs.
- [ ] 9.3 `kubectl get sandboxtemplate python-sandbox-template -o yaml` SHALL exist; apply the `SandboxClaim` snippet from `agent-sandbox.sigs.k8s.io/docs/sandbox/metrics/` and confirm the resulting `Sandbox` becomes Ready.
- [ ] 9.4 `kubectl -n kagent get pods` SHALL show the new `time-mcp` and `time-agent` pods Ready.
- [ ] 9.5 `curl -s http://<gateway-ip>/phoenix/` SHALL return HTML containing the Phoenix UI title.
- [ ] 9.6 Run the Sandbox metrics walkthrough: in a venv, `pip install "k8s-agent-sandbox[tracing]" opentelemetry-distro`, `opentelemetry-bootstrap -a install`, then `OTEL_TRACES_EXPORTER=console OTEL_METRICS_EXPORTER=console opentelemetry-instrument python main.py`. Confirm `Span` and `resource_metrics` JSON are printed. Capture the output in a file linked from `lab-5/README.md` Solutions.
- [ ] 9.7 Run `uv run pytest tests/integration/test_phoenix_trace.py -q` from `lab-5/time-agent/` against the running cluster. Confirm a span from `time-agent` and a span from `time-mcp-server` share a `trace_id` in Phoenix.
- [ ] 9.8 Run `uv run pytest tests/unit -q` from both `lab-5/time-mcp-server/` and `lab-5/time-agent/` and confirm both suites pass with no cluster access.

## 10. Documentation and OpenSpec hygiene

- [x] 10.1 Update `lab-5/README.md` Solutions section: add entries for Experienced #1, #2, #3 linking to the new files, document the one-time `kubectl delete -f .../manifest.yaml` cleanup, the gateway `/phoenix` URL, and the validation commands in §9.
- [x] 10.2 Add a short `lab-5/abox/CODEBASE.md` (or extend the existing one) section describing the new namespaces (`observability`, `agent-sandbox-system`) and the `OTEL_EXPORTER_OTLP_ENDPOINT` env convention.
- [x] 10.3 Run `openspec validate deploy-phoenix-otel-sandbox-mcp-tracing` from `lab-5/`. Resolve any reported issues. Then `openspec show deploy-phoenix-otel-sandbox-mcp-tracing` and confirm proposal, design, all four specs, and tasks all render. _`openspec validate` → "valid"; `openspec show` rendered proposal, design, all four specs, and tasks._
- [ ] 10.4 Once §9 passes on a fresh `make run`, archive the change: `openspec archive deploy-phoenix-otel-sandbox-mcp-tracing` from `lab-5/`. The four delta specs SHALL be merged into `lab-5/openspec/specs/{phoenix-observability,agent-sandbox-platform,time-mcp-stack,lab5-release-pipeline}/spec.md`.
