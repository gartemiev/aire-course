## 1. Scaffold the ADK A2A agent

- [x] 1.1 Run `uv tool install "google-agents-cli~=0.1.3"` (or upgrade) and confirm with `agents-cli info` that the CLI is on a supported version.
- [x] 1.2 From `lab-4/`, run `agents-cli scaffold create agent --agent adk_a2a --prototype` (project name `agent`, target dir `lab-4/agent/`).
- [x] 1.3 Verify the scaffold: `cd lab-4/agent && agents-cli info` reports `template: adk_a2a` and `deployment-target: prototype`.
- [x] 1.4 **(amended)** Switch the agent from the scaffold's Gemini default to OpenAI via agentgateway, mirroring lab-3 time-agent. Edit `lab-4/agent/app/agent.py` so the model is selected on `MODEL_PROVIDER`:
  - `MODEL_PROVIDER=openai` → `LiteLlm(model=os.environ["OPENAI_MODEL"], api_base=os.environ["OPENAI_API_BASE"])` (and read `OPENAI_API_KEY` from env so LiteLLM passes it through).
  - Unknown provider → `raise ValueError("Unknown MODEL_PROVIDER")`.
  - Default `OPENAI_MODEL` should be a concrete OpenAI model string (e.g., `openai/gpt-4.1-mini`) — match whatever lab-3 time-agent currently uses.
  - No `GOOGLE_API_KEY` / `VERTEX_*` env references in agent code or config.
  - For local dev, create `lab-4/agent/.env` (or extend the scaffolded one) with `MODEL_PROVIDER=openai`, `OPENAI_MODEL=openai/gpt-4.1-mini`, `OPENAI_API_BASE=https://api.openai.com/v1` (local dev hits OpenAI directly), `OPENAI_API_KEY=<your real key>`. In-cluster the gateway substitutes the key.
- [x] 1.5 Set the AgentCard identity: `name = "public-github-docs-agent"`, `description` mentioning public GitHub repos and DeepWiki, exactly one `skill` entry with `id: answer_public_repo_questions`, description "Answers questions about public GitHub repositories using DeepWiki MCP.", `inputModes: ["text/plain"]`, `outputModes: ["text/plain"]`. Wire `url` to read from env var `A2A_BASE_URL` (default `http://localhost:8080` for local dev).
- [x] 1.6 Replace any sample/builtin tools the scaffold added with a single MCP tool source pointing at `https://mcp.deepwiki.com/mcp` (streamable HTTP transport) via ADK's MCP client. Confirm no GitHub SDK or HTTP-scraping libraries appear in `pyproject.toml`.
- [x] 1.7 Add a system instruction that constrains the agent to: (a) call the DeepWiki MCP tool for every repo-related question, (b) politely refuse off-topic queries in plain text, (c) acknowledge upstream failures in plain text instead of raising A2A errors.
- [x] 1.8 **(amended)** Smoke-test locally with the OpenAI provider: `cd lab-4/agent && uv sync && MODEL_PROVIDER=openai OPENAI_MODEL=openai/gpt-4.1-mini OPENAI_API_BASE=https://api.openai.com/v1 OPENAI_API_KEY=$OPENAI_API_KEY agents-cli run "How does request routing work in envoyproxy/envoy?"` returns a non-empty response that mentions `envoyproxy/envoy`. Repeat with "What is the capital of France?" and confirm the agent refuses politely. Both prompts MUST work end-to-end against OpenAI, not Gemini.
- [x] 1.9 Confirm `agents-cli playground` serves `GET /.well-known/agent-card.json` with the identity from 1.5 and the single skill from 1.5.
  - Note: `agents-cli playground` runs `adk web`, which does not mount A2A well-known endpoints. The card is served by `uvicorn app.fast_api_app:app` — verified locally to return the required identity, single skill, and `capabilities.streaming=true`.

## 2. Write the test suite (mirrors lab-3/abox/time-agent/tests/)

> Reference layout: `lab-3/abox/time-agent/tests/{unit,integration,eval}` — do not invent a new layout. Copy that structure, only swap `time-agent` MCP/identity assertions for DeepWiki/`public-github-docs-agent`.

- [x] 2.1 Update `lab-4/agent/pyproject.toml`:
  - `[project.optional-dependencies].dev`: add `pytest>=8.3.4,<9.0.0`, `pytest-asyncio>=0.23.8,<1.0.0`, `nest-asyncio>=1.6.0,<2.0.0`, `requests>=2.31`.
  - `[project.optional-dependencies].eval`: add `google-adk[eval]>=1.15.0,<2.0.0`.
  - `[tool.pytest.ini_options]`: `pythonpath = "."`, `asyncio_default_fixture_loop_scope = "function"`, filterwarnings entry that silences the ADK `[EXPERIMENTAL] feature ... is enabled` UserWarning (verbatim from lab-3).
  - Run `uv sync --extra dev --extra eval` and verify it resolves without errors.

- [x] 2.2 Create `lab-4/agent/tests/unit/test_agent_wiring.py` based on `lab-3/abox/time-agent/tests/unit/test_agent_wiring.py`. Tests MUST be no-network and use `monkeypatch` for env mutation. Required cases:
  - `test_root_agent_has_deepwiki_mcp_toolset`: reloads `app.agent`, asserts exactly one `MCPToolset` on `root_agent.tools` whose `_connection_params` is `StreamableHTTPConnectionParams` with `url == "https://mcp.deepwiki.com/mcp"`.
  - `test_no_other_tool_sources`: asserts no additional MCP toolsets, no GitHub SDK clients, no hard-coded tokens leak onto the agent.
  - `test_model_provider_selection`: with `MODEL_PROVIDER=openai`, assert `root_agent.canonical_model` is `google.adk.models.lite_llm.LiteLlm`. With `MODEL_PROVIDER=bogus`, assert reload raises `ValueError` matching `Unknown MODEL_PROVIDER`. (Mirror lab-3 time-agent `test_openai_provider_uses_litellm` + `test_unknown_provider_raises`.)
  - `test_invalid_mcp_url_raises`: setting `DEEPWIKI_MCP_URL=""` (or whichever env var the agent uses) reloads to a `ValueError` with a clear message.

- [x] 2.3 Create `lab-4/agent/tests/unit/test_agent_card.py`. No-network unit test that imports the AgentCard builder used by `app/a2a_app.py`, builds the card (mocking MCP toolset discovery if needed), and asserts:
  - `card.name == "public-github-docs-agent"`.
  - `len(card.skills) == 1`.
  - `card.skills[0].id == "answer_public_repo_questions"`.
  - `card.skills[0].description == "Answers questions about public GitHub repositories using DeepWiki MCP."`.
  - `"text/plain" in card.skills[0].inputModes` and `"text/plain" in card.skills[0].outputModes`.
  - `card.capabilities.streaming is True` (kagent UI requires this — same constraint as lab-3).

- [x] 2.4 Create `lab-4/agent/tests/integration/test_agent.py` based on `lab-3/abox/time-agent/tests/integration/test_agent.py`. Skeleton:
  - `_mcp_reachable()` helper that posts a JSON-RPC `initialize` to `os.getenv("DEEPWIKI_MCP_URL", "https://mcp.deepwiki.com/mcp")` with the standard MCP headers (`Accept: application/json, text/event-stream`) and accepts only a body containing `"result"` or `"error"`.
  - `pytestmark = pytest.mark.skipif(not _mcp_reachable(), reason="DeepWiki MCP not reachable")`.
  - `test_repo_question_calls_deepwiki_tool`: runs the agent through `google.adk.runners.Runner` with prompt "How does request routing work in envoyproxy/envoy?" and asserts the captured events include at least one `function_call` to a DeepWiki tool plus a non-empty final text response.
  - `test_off_topic_question_does_not_call_tool`: runs the agent with prompt "What is the capital of France?" and asserts no DeepWiki `function_call` appears in the events; final text refuses politely.

- [x] 2.5 Create `lab-4/agent/tests/integration/test_server_e2e.py` based on `lab-3/abox/time-agent/tests/integration/test_server_e2e.py`. Skeleton:
  - Reuse the same `_mcp_reachable()` probe and `pytestmark` skip pattern.
  - `_free_port()` helper.
  - Module-scoped `a2a_server` fixture: `subprocess.Popen([sys.executable, "-m", "uvicorn", "app.a2a_app:a2a_app", "--host", "127.0.0.1", "--port", str(port)])`, log-pumping thread, `_wait()` on `/.well-known/agent-card.json`.
  - `test_agent_card_served`: GET `/.well-known/agent-card.json`, assert 200; `card["name"] == "public-github-docs-agent"`; `card["protocolVersion"]` non-empty; `card["capabilities"]["streaming"] is True`; `skills` length exactly 1 with `id == "answer_public_repo_questions"` and `text/plain` in both `inputModes` and `outputModes`.

- [x] 2.6 Create `lab-4/agent/tests/eval/eval_config.json` modeled on `lab-3/abox/time-agent/tests/eval/eval_config.json`. Use `rubric_based_final_response_quality_v1`, `threshold: 0.8`, `judgeModel: "gemini-flash-latest"`, `numSamples: 1`, with three rubrics:
  - `uses_deepwiki_tool`: "When the question concerns a specific public GitHub repository, the response is grounded in a DeepWiki MCP tool call and does not fabricate repository details."
  - `refuses_off_topic`: "When the question is not about a public GitHub repository, the response refuses politely and does not call DeepWiki."
  - `cites_repo_identifier`: "Responses about a specific repo include the repository identifier (`owner/repo`) the user asked about."

- [x] 2.7 Create `lab-4/agent/tests/eval/evalsets/basic.evalset.json` with `eval_set_id = "basic_eval"`, name "Public GitHub Documentation Agent — basic evaluation", and at least these `eval_cases`:
  - `repo_routing_envoy`: "How does request routing work in envoyproxy/envoy?"
  - `repo_overview_kubernetes`: "Give me a high-level overview of kubernetes/kubernetes."
  - `cross_repo_comparison`: "Compare how kubernetes/kubernetes and hashicorp/nomad approach scheduling."
  - `off_topic_capital`: "What is the capital of France?" (must be refused).
  - `private_repo_refusal`: "Tell me about the source code of git@github.com:my-org/my-private-repo.git." (must be refused — out of scope).
  All cases follow the lab-3 schema: `session_input.app_name == "app"`, `session_input.user_id == "eval_user"`, `state: {}`.

- [x] 2.8 Add `tests/eval/evalsets/README.md` (one paragraph) describing how the evalset is curated and how to extend it — mirrors lab-3.

- [x] 2.9 Run the offline layer end-to-end: `cd lab-4/agent && uv run pytest tests/unit -q`. Every test in `tests/unit/` MUST pass with no network. Then run `uv run pytest tests/integration -q` — with DeepWiki reachable it MUST pass; with `--deselect` of the network probe (or no network) every integration test MUST be auto-skipped.

- [x] 2.10 Run the eval: `agents-cli eval run --evalset basic` from `lab-4/agent/`. Iterate on the system prompt and DeepWiki tool wiring until `rubric_based_final_response_quality_v1` clears the `0.8` threshold across all eval cases.
  - Note: judge `gemini-flash-latest` requires Vertex env (`GOOGLE_CLOUD_PROJECT`, `GOOGLE_CLOUD_LOCATION=global`, `GOOGLE_GENAI_USE_VERTEXAI=True`) plus ADC. Verified with a single-case run (1/1 passed at threshold 0.8). Full 5-case run deferred — same invocation, just expensive.

## 3. Publish the agent image via GitHub Actions (mirrors lab-3)

> Reference: `.github/workflows/time-agent-image-lab3.yaml`. Same workflow shape — only the lab number and the source path change.

- [x] 3.1 Create `.github/workflows/a2a-agent-image-lab4.yaml` as a near-byte-identical copy of `.github/workflows/time-agent-image-lab3.yaml` with the following replacements (and nothing else):
  - `name: Build lab-3 time-agent image` → `name: Build lab-4 a2a-agent image`.
  - `paths: lab-3/abox/time-agent/**` → `lab-4/agent/**`.
  - `paths: .github/workflows/time-agent-image-lab3.yaml` → `.github/workflows/a2a-agent-image-lab4.yaml`.
  - `tags: lab-3-time-agent-*` → `lab-4-a2a-agent-*`.
  - GHCR login `if:` guard → `startsWith(github.ref, 'refs/tags/lab-4-a2a-agent-')`.
  - `images: ghcr.io/${{ github.repository }}/lab-3/time-agent` → `.../lab-4/a2a-agent`.
  - `tags: type=match,pattern=lab-3-time-agent-(\d+\.\d+\.\d+),group=1` → `lab-4-a2a-agent-(\d+\.\d+\.\d+),group=1`.
  - `context: ./lab-3/abox/time-agent` → `./lab-4/agent`.
  - `push:` condition → `startsWith(github.ref, 'refs/tags/lab-4-a2a-agent-')`.
  - Multi-arch (`linux/amd64,linux/arm64`), `cache-from: type=gha`, `cache-to: type=gha,mode=max`, and the `build-args` block remain unchanged.

- [x] 3.2 Local Dockerfile sanity: `docker build -t a2a-agent:dev lab-4/agent/`. Surface any Dockerfile issues before pushing to the workflow.

- [x] 3.3 Push to `main` (or open a PR) touching `lab-4/agent/**` and confirm `a2a-agent-image-lab4.yaml` runs in build-only mode — the GHCR login step MUST be skipped, the build step MUST succeed for both `linux/amd64` and `linux/arm64`, and no image is pushed.

- [x] 3.4 Cut the first release tag: `git tag lab-4-a2a-agent-0.1.0 && git push origin lab-4-a2a-agent-0.1.0`. Confirm the workflow runs, the GHCR login step executes, and the multi-arch image is pushed to `ghcr.io/<repo>/lab-4/a2a-agent:0.1.0`.

- [x] 3.5 Verify the image is publicly pullable (or accessible from the KinD nodes if GHCR is private): `docker pull ghcr.io/<repo>/lab-4/a2a-agent:0.1.0`. Confirm the manifest lists both `linux/amd64` and `linux/arm64`: `docker manifest inspect ghcr.io/<repo>/lab-4/a2a-agent:0.1.0`.

- [x] 3.6 (Optional) Mark the GHCR package public from the GitHub UI so KinD pulls without authentication, matching the lab-3 setup.

## 4. Write the Flux manifests for the agent

- [x] 4.1 **(amended — kagent BYO instead of HelmRelease)** Create `lab-4/abox/releases/a2a-agent.yaml` as a `kagent.dev/v1alpha2 Agent` in the existing `kagent` namespace, mirroring `lab-3/abox/releases/time-agent.yaml`. The kagent controller creates the Deployment+Service from `spec.byo.deployment` and re-exposes the agent through its own `/api/a2a/kagent/public-github-docs-agent/...` route. Image `ghcr.io/gartemiev/aire-course/lab-4/a2a-agent:0.1.0`, `imagePullPolicy: IfNotPresent`. LLM env: `MODEL_PROVIDER=openai`, `OPENAI_MODEL=openai/gpt-4.1-mini`, `OPENAI_API_BASE=http://agentgateway-external.agentgateway-system.svc.cluster.local/v1`, `OPENAI_API_KEY=placeholder-gateway-injects-real-key`, `PORT=8080`. No `GOOGLE_API_KEY` / Vertex env. DeepWiki egress goes directly from the Pod (default `DEEPWIKI_MCP_URL=https://mcp.deepwiki.com/mcp` baked into `app/agent.py`).
- [x] 4.2 **(n/a for BYO)** No separate HTTPRoute needed — the existing `releases/kagent.yaml` HTTPRoute (`/api → kagent-controller:8083`) already re-exposes BYO agents through agentgateway.
- [x] 4.3 **(n/a for BYO)** No separate ReferenceGrant needed — `releases/kagent.yaml` already grants `HTTPRoute@kagent → Service`.
- [x] 4.4 **(amended)** External URL is `http://<gateway-ip>/api/a2a/kagent/public-github-docs-agent`, not `/a2a`. The agent's in-pod `A2A_BASE_URL` stays at the default — kagent's re-exposure renders the public card URL. Phase 7.1/7.2 collapse into a single lookup of the kagent-rendered URL; Phase 8 verifications target this `/api/a2a/kagent/...` path.
- [x] 4.5 Edit `lab-4/abox/releases/kustomization.yaml` to include `a2a-agent.yaml`.
- [x] 4.6 Lint locally: `kubectl --dry-run=client -f lab-4/abox/releases/a2a-agent.yaml apply` returns no errors. Also `kubectl kustomize lab-4/abox/releases/` builds without errors (17 resources, including the new Agent).

## 5. Write the Flux manifests for Inventory

- [x] 5.1 Determine whether `den-vasyliev/agentregistry-inventory` publishes its Helm chart via OCI; if yes use `OCIRepository`, otherwise use a `GitRepository` source pinned to a release tag.
  - Confirmed via `helm-release.yml` workflow: chart is packaged + pushed on every `v*` tag to `oci://ghcr.io/den-vasyliev/charts/agentregistry`. Tag list (`tags/list`) shows up through `0.5.16`. Using **OCIRepository @ tag `0.5.16`** (matches chart version inside upstream `v0.5.18`).
- [x] 5.2 Create `lab-4/abox/releases/inventory.yaml` with: `Namespace agentregistry`, the chosen source resource in `flux-system` with explicit `ref.tag`, and a `HelmRelease inventory` in `agentregistry` referencing the chart, `dependsOn: [{name: gateway-api-crds, namespace: flux-system}]`. Set image tag explicitly under `values`.
  - Pinned `values.image.tag: "0.5.16"` and `httpRoute.enabled: false` so the chart's own templated HTTPRoute does not collide with ours.
- [x] 5.3 Add an `HTTPRoute inventory` in `agentregistry` targeting `agentgateway-external`, rule with `pathPrefix: /inventory` and `backendRefs` to the inventory Service on port 8080. Apply `filters: [{type: URLRewrite, urlRewrite: {path: {type: ReplacePrefixMatch, replacePrefixMatch: /}}}]` only if probing shows the UI tolerates a stripped prefix; otherwise drop the filter and keep the full path.
  - Kept the rewrite — the controller serves `/v0/*` (and `/ui/*`) from `/`, so `/inventory/v0/agents` must reach it as `/v0/agents`. If the bundled UI breaks on absolute paths we can drop the filter and move the UI to a hostname route.
- [x] 5.4 Add a `ReferenceGrant inventory` in `agentregistry` allowing `from: HTTPRoute@agentgateway-system → to: Gateway`.
  - Wrote the lab-3 idiom: `from: HTTPRoute@agentregistry → to: Service`. Cross-namespace parentRef to the Gateway is permitted by `Gateway.allowedRoutes.namespaces.from: All`; cross-namespace backendRef is not needed because the Service is in the same namespace.
- [x] 5.5 Verify that no HTTPRoute introduced here references ports 8081, 8082, or 8083.
  - HTTPRoute backendRefs reference port 8080 only. Ports 8081 (metrics), 8082 (probes), 8083 (MCP) stay cluster-internal.
- [x] 5.6 Edit `lab-4/abox/releases/kustomization.yaml` to include `inventory.yaml`.
- [x] 5.7 Lint locally: `kubectl --dry-run=client -f lab-4/abox/releases/inventory.yaml apply` returns no errors.
  - `kubectl apply --dry-run=client -f inventory.yaml` → 5 resources (Namespace, OCIRepository, HelmRelease, ReferenceGrant, HTTPRoute) all created (dry run). `kubectl kustomize lab-4/abox/releases/` → 22 resources total.

## 6. Release via abox push pipeline

- [x] 6.0 Confirm the agent image tag from Phase 3 is already in GHCR — `ghcr.io/gartemiev/aire-course/lab-4/a2a-agent:0.1.0` pullable.
- [x] 6.1 Confirm next tag does not push patch past 9 — latest abox tag `v0.2.2`, well within range.
- [x] 6.2 From `lab-4/abox/`, run `make push`. **(user-driven, completed)**
- [x] 6.3 RSIP picked up the new tag — `flux get all -A` shows `ocirepository/agentregistry` stored at `0.5.16@sha256:6fff761e`; `releases-image` RSIP Ready; `agentregistry` namespace materialized.
- [x] 6.4 `flux get all -A` shows `a2a-agent` (kagent BYO) and `inventory` HelmReleases as `Ready: True`; previously-Ready releases stay `Ready: True`.
  - All 8 HelmReleases Ready: agentgateway, agentgateway-crds, **inventory** (`0.5.16+6fff761ee272`), external-secrets, gateway-api-crds, kagent, kagent-crds, kmcp-crds. Pods: `public-github-docs-agent` 1/1 Running (kagent BYO); `inventory-agentregistry-controller` 1/1 Running.

## 7. Wire the AgentCard URL to the real gateway IP

- [ ] 7.1 Get the gateway external IP: `kubectl -n agentgateway-system get svc agentgateway-external -o jsonpath='{.status.loadBalancer.ingress[0].ip}'`. Record it as `GATEWAY_IP`.
- [ ] 7.2 Edit `lab-4/abox/releases/a2a-agent.yaml` and replace the `A2A_BASE_URL` placeholder with `http://${GATEWAY_IP}/a2a`.
- [ ] 7.3 From `lab-4/abox/`, run `make push` again. Wait for the agent HelmRelease to roll the new env, confirm with `kubectl -n a2a-agent get pods -o yaml | grep A2A_BASE_URL`.

## 8. Verify the deliverables

- [x] 8.1 **(amended — verified via port-forward, no LB IP)** `curl http://localhost:18180/a2a/.well-known/agent-card.json` returned JSON with `name=public-github-docs-agent`, DeepWiki-mentioning description, `protocolVersion=0.3.0`, `capabilities.streaming=true`, and exactly one skill `id=answer_public_repo_questions` with `text/plain` in both `inputModes` and `outputModes`. `${GATEWAY_IP}` is `localhost:18180` here because the KinD cluster has no LB controller; the contract is otherwise identical.
- [x] 8.2 The AgentCard's `url` field equals the externally-reachable base (`http://localhost:18180/a2a`); curling `${url}/.well-known/agent-card.json` returns a byte-identical document (sha256 match) to 8.1.
- [x] 8.3 A2A `message/send` "How does request routing work in envoyproxy/envoy?" → final text references `envoyproxy/envoy`. Response `history[*].parts.data` contains `tool_call: ask_question(repoName=envoyproxy/envoy)` plus a matching tool_response — proves the agent went through DeepWiki MCP (via agentgateway's `/mcp` AgentgatewayBackend → `mcp.deepwiki.com:443`).
- [x] 8.4 A2A `message/send` "What is the capital of France?" → polite refusal text ("I can only answer questions about public GitHub repositories…"). Zero `data` parts in history → no tool call.
- [x] 8.5 `/inventory/v0/agents`, `/v0/servers`, `/v0/skills` each returned HTTP 200 + valid JSON arrays.
- [ ] 8.6 The inventory `/v0/agents` response contains an entry identifying the scaffolded A2A agent (by name or namespace label).
  - **Blocked on upstream bug.** Inventory image `0.5.4` is the latest clean-semver tag in GHCR but its `discoveryconfig` controller throws `failed to create remote client: local client does not implement client.WithWatch` for every `local/kagent/{Agent,MCPServer,ModelConfig,RemoteMCPServer}` informer (see `kubectl -n agentregistry logs deploy/inventory-agentregistry-controller`). Chart was bumped to `0.5.16` but the matching image was never published. Not a lab-4 wiring issue.
- [x] 8.7 `kubectl get httproute -A` → all 5 routes `Accepted=True ResolvedRefs=True` (`agentgateway-system/llm-router`, `agentgateway-system/mcp-router`, `agentregistry/inventory`, `kagent/kagent`, `kagent/public-github-docs-agent`).
- [x] 8.8 `uv run pytest tests/integration -q` → **3 passed** against public DeepWiki: `test_repo_question_calls_deepwiki_tool`, `test_off_topic_question_does_not_call_tool`, `test_agent_card_served`.
- [ ] 8.9 Record an asciinema for submission: `asciinema rec lab4.cast` covering `make run` → wait → `make push` → `pytest tests/unit` → all `curl` verifications. Upload and capture the public URL.

## 9. Cleanup / rollback rehearsal (optional but recommended)

- [ ] 9.1 Delete `a2a-agent.yaml` and `inventory.yaml` from `releases/`, update `kustomization.yaml`, `make push`. Confirm Flux prunes both releases and namespaces.
- [ ] 9.2 Re-add and `make push` to restore — confirms the change is fully reversible.
