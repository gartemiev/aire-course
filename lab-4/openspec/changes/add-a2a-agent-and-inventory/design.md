## Context

The abox stack (lab-4/abox/) gives us a working AI-aware data plane: a KinD cluster reconciled by Flux from an OCI artifact, agentgateway v2.2.1 fronting cluster traffic on port 80, and kagent 0.9.3 already running. The lab needs two add-ons reachable through that same gateway: a hand-written A2A agent and the agentregistry-inventory catalog. Both fit naturally as additional HelmReleases under `abox/releases/`, which means once `make push` publishes a new OCI tag the RSIP reconciles them automatically — no manual `kubectl apply` and no drift from the convention abox sets.

Constraints that drive the design:

- **A2A wire format is not stable across versions.** The ADK `--agent adk_a2a` template wraps a regular ADK agent with `to_a2a()` which mounts the Agent Card at `/.well-known/agent-card.json` (post-0.3.x A2A) and the JSON-RPC `tasks/*` endpoints. We do not re-implement this.
- **agentgateway listens on `:80` only.** Everything must be reachable via HTTP path prefix on the single Gateway `agentgateway-external` in `agentgateway-system`.
- **Path rewriting matters.** The A2A spec requires the Agent Card to live at the URL `/.well-known/agent-card.json` relative to the **declared service URL**. If we route `/a2a/*` to the pod, the AgentCard's `url` field must be `http://<gateway-ip>/a2a` so that `<declared-url>/.well-known/agent-card.json` resolves to `http://<gateway-ip>/a2a/.well-known/agent-card.json`. We keep the path prefix and do **not** rewrite it on the gateway.
- **abox conventions** (CODEBASE.md): explicit `ref.tag`, no `latest`, Namespace in the same file as the HelmRelease, ReferenceGrant for cross-namespace HTTPRoute, RSIP tag patch ≤ 9, app `dependsOn` its CRD release.

## Goals / Non-Goals

**Goals:**

- One `git tag v*` + `make push` from abox/ deploys both the agent and Inventory.
- `curl http://<gateway-ip>/a2a/.well-known/agent-card.json` returns a valid A2A AgentCard.
- `curl http://<gateway-ip>/inventory/v0/agents|servers|skills` returns the live cluster catalog.
- Zero new persistent state outside the cluster — the lab can be torn down and rebuilt by `make run`.

**Non-Goals:**

- Production-grade auth (Bearer tokens, mTLS). The Inventory public API is read-only; we use it as-is.
- A2A client implementation or task exchange between agents — that is the Experienced/Max scope.
- Pushing the agent image to a remote registry. We rely on `kind load docker-image` for the lab.
- Replacing kagent or adding MCPG/Qdrant.

## Decisions

### D1. Agent framework: Google ADK via `agents-cli scaffold create --agent adk_a2a`

The lab allows any framework, but the ADK template already ships A2A wiring (`AgentCard`, well-known route, JSON-RPC tasks) and is what the user has tooling for. We scaffold with `--prototype` (no GCP deployment target) and write our own Kubernetes manifests under `abox/releases/`, because the built-in GKE target generates Terraform for GKE Autopilot — useless on KinD.

Alternative considered: Python + raw FastAPI with hand-coded A2A — rejected because the A2A surface drifts between SDK versions (cf. agents-cli-scaffold SKILL note: "NEVER write A2A code from scratch").

### D1a. Agent identity and skill surface: Public GitHub Documentation Agent

The agent is single-purpose: answer questions about public GitHub repositories using DeepWiki. Concretely the AgentCard advertises:

- `name`: `public-github-docs-agent`
- `description`: "Answers natural-language questions about public GitHub repositories. Uses DeepWiki to retrieve and synthesise repository documentation."
- `skills[0]`: `id: answer_public_repo_questions`, `name: "Answer public repo questions"`, `description: "Answers questions about public GitHub repositories using DeepWiki MCP."`, `inputModes: ["text/plain"]`, `outputModes: ["text/plain"]`
- `capabilities`: streaming on/off as the ADK template defaults; no extensions claimed.

The agent's system instruction MUST constrain it to: (a) call the DeepWiki MCP tool for every repo-specific question, (b) refuse off-topic queries (private repos, non-GitHub sources, anything not about repository docs) with a short text response, (c) never fabricate citations — if DeepWiki returns no relevant content, say so.

### D1c. LLM provider: OpenAI via agentgateway `/v1`, NOT Gemini

The agent SHALL call its LLM through agentgateway's existing OpenAI route, mirroring lab-3 time-agent. Rationale: agentgateway in abox is already configured with an OpenAI upstream and a Secret-backed key injector (`aire-openai-token` → `agentgateway-llm.yaml` + `openai-credentials.yaml`). Routing through it gets us key injection, request tracing, and rate-limit centralisation for free. Adding a second LLM upstream (Gemini / Vertex) would require either a new agentgateway route + a Google credential Secret, or direct egress from the agent Pod with a hard-coded `GOOGLE_API_KEY` — both diverge from the abox pattern and break the "one gateway controls all AI traffic" invariant.

Concretely the agent runs with the same env block lab-3 uses:

```
MODEL_PROVIDER=openai
OPENAI_MODEL=openai/gpt-4.1-mini            # or whatever the lab settles on
OPENAI_API_BASE=http://agentgateway-external.agentgateway-system.svc.cluster.local/v1
OPENAI_API_KEY=placeholder-gateway-injects-real-key
```

The ADK adapter is **LiteLlm**, not the native Gemini model class. The `--agent adk_a2a` scaffold defaults to Gemini; we override at `app/agent.py` level to dispatch on `MODEL_PROVIDER` and construct `LiteLlm(model=os.environ["OPENAI_MODEL"], api_base=os.environ["OPENAI_API_BASE"])` when `MODEL_PROVIDER=openai`. The Gemini branch stays in the code path but is not exercised in this lab.

Implications:
- `tests/unit/test_agent_wiring.py::test_model_provider_selection` MUST assert the `openai` branch builds a `LiteLlm` model and the unknown-provider branch raises.
- `tests/eval/eval_config.json` keeps `judgeModel: "gemini-flash-latest"` because the **judge** runs in Gemini (cheap, fast, separate concern from the agent's LLM). If the lab cluster cannot reach Vertex from CI, the judge can be swapped to `judgeModel: "openai/gpt-4o-mini"` — that is an eval infrastructure choice, not an agent property.
- No `GOOGLE_API_KEY` Secret needs to be provisioned in the cluster. The HelmRelease wires `OPENAI_API_KEY` to the literal placeholder (not a real Secret) — the gateway substitutes the real key.

Alternative considered (Gemini direct from Pod): rejected because it diverges from the lab-3 wiring template and creates a second class of LLM upstream in abox.

### D1b. Tool integration: public DeepWiki MCP server

The agent uses the public DeepWiki MCP endpoint at `https://mcp.deepwiki.com/mcp` (streamable HTTP transport) as its sole tool source. It is mounted via ADK's MCP client integration (`MCPToolset` / `mcp_client` per the version pinned by `--agent adk_a2a`). No API key — the endpoint is anonymous public access. Egress from the agent Pod to `mcp.deepwiki.com:443` is required.

Failure modes we accept and surface to the caller:
- DeepWiki rate-limit or 5xx → the agent returns a text-mode response explaining the upstream failure, not an A2A error.
- DeepWiki latency → A2A request timeout (default 60s from the scaffold) bubbles up to the caller; no retry logic added in this change.

Out of scope for this change: caching DeepWiki responses, fallback to another retrieval source, switching to a private DeepWiki instance.

### D2. Agent Card URL must match the gateway prefix

We deploy the agent under HTTPRoute prefix `/a2a` and pass that base URL into the agent at startup (env var `A2A_BASE_URL=http://<gateway-ip>/a2a`). The `to_a2a()` helper renders the AgentCard with that base, so its `url` field and the discovery path `<base>/.well-known/agent-card.json` line up with what the gateway actually serves. We do not strip `/a2a` on the gateway side — that would force us to write the AgentCard manually.

The gateway IP is not known at chart-render time. We resolve this two ways:

- For the lab, a one-shot pre-flight step reads `kubectl get svc -n agentgateway-system` after the first reconcile, then we update the HelmRelease values with the IP and `make push` again. This is acceptable because the lab is run interactively.
- Long-term (out of scope): switch the agent to read the gateway IP from a downward-API lookup or use a hostname (`agentgateway.local`) resolved via `/etc/hosts`.

### D3. Inventory deployment uses upstream Helm chart, pinned tag

The repo ships `charts/agentregistry`. We declare an `OCIRepository` (or `HelmRepository` if the upstream publishes Helm artifacts via OCI) in `flux-system` pointing at it with an explicit `ref.tag`, and reference it from a `HelmRelease` in the new `agentregistry` namespace. If the upstream does not publish OCI artifacts, we fall back to a GitRepository source — confirmed at task time.

Inventory exposes UI/API on `:8080`, MCP on `:8083`, metrics `:8081`, health `:8082`. We route only `:8080` through the gateway under `/inventory` (no path strip). MCP and metrics stay cluster-internal; the lab only needs `/v0/{agents,servers,skills}`.

If Inventory's UI hardcodes absolute paths (`/static/...`) it will break under a prefix. We mitigate by trying `URLRewrite: ReplacePrefixMatch /` first; if the UI still breaks, we expose Inventory on a dedicated subdomain via HTTPRoute hostname (`inventory.localtest.me` resolves to `127.0.0.1` automatically) and drop the prefix.

### D4. No new CRDs

Neither addition introduces CRDs. `dependsOn` lines from abox conventions are still required, but they point at existing CRD releases (`gateway-api-crds`) so the HTTPRoute types are available. The agent's HelmRelease and Inventory's HelmRelease both depend on `gateway-api-crds` in `flux-system`.

### D5. Cross-namespace routing

Both HTTPRoutes live in their app namespace (`a2a-agent`, `agentregistry`) and reference the Gateway in `agentgateway-system`. Each app namespace ships a `ReferenceGrant` granting `HTTPRoute → Gateway` permission across the namespace boundary — mirrors the pattern in `releases/kagent.yaml`.

### D6. Image distribution: GHCR via GitHub Actions, mirroring lab-3

The agent image is published to GHCR by a new workflow `.github/workflows/a2a-agent-image-lab4.yaml`, an exact mirror of `time-agent-image-lab3.yaml` with only the lab number and source path swapped:

- `paths`: `lab-4/agent/**` and `.github/workflows/a2a-agent-image-lab4.yaml`
- Image: `ghcr.io/<repo>/lab-4/a2a-agent`
- Release-tag trigger and `docker/metadata-action` pattern: `lab-4-a2a-agent-<semver>` → image tag `<semver>` (e.g., `lab-4-a2a-agent-0.1.0` → image tag `0.1.0`)
- Platforms: `linux/amd64,linux/arm64` (required for KinD on Apple Silicon; single-arch builds fail to pull with "no match for platform in manifest")
- Push only on tag; branch pushes and `workflow_dispatch` build-and-discard for Dockerfile sanity
- `cache-from`/`cache-to`: `type=gha,mode=max`
- `build-args`: `COMMIT_SHA=${{ github.sha }}`, `AGENT_VERSION=${{ github.ref_name }}`

The HelmRelease references `ghcr.io/<repo>/lab-4/a2a-agent:<semver>` with `imagePullPolicy: IfNotPresent`. No `kind load` step — KinD nodes pull from GHCR on first reconcile. This matches the lab-3 deployment shape one-to-one, which is the precedent the repo already enforces.

The lab-scoped image path (`/lab-4/a2a-agent`, not `/a2a-agent`) is deliberate: future labs publish under `lab-N/` without colliding.

Alternative considered (`kind load docker-image`): rejected. It works for a single developer machine but diverges from the lab-3 pattern, hides the image from anyone re-running `make run` from a fresh checkout, and prevents `flux get all` from showing a meaningful image source.

## Risks / Trade-offs

- **Inventory UI under a path prefix may break** → Mitigation: subdomain fallback (`inventory.localtest.me`) without prefix strip; the lab only strictly needs the JSON API, so even a broken UI does not block the deliverable.
- **AgentCard URL hardcoded to gateway IP** → Mitigation: pre-flight `kubectl get svc` then bump HelmRelease values + `make push`; acceptable for a local lab, documented as a known wart.
- **Patch version overflow on `make push`** → Mitigation: abox CODEBASE.md already warns; we explicitly bump minor when patch would hit 10 (RSIP lexicographic sort).
- **Image must be published before the first `make push` of abox** → Mitigation: order the tasks so the `lab-4-a2a-agent-<semver>` tag (which triggers the image workflow) is pushed before the abox `v*` tag (which triggers reconciliation). HelmRelease pinning by digest is out of scope; we trust the immutable semver tag.
- **agentregistry-inventory chart may not pin a stable image tag** → Mitigation: override `image.tag` in HelmRelease values, never trust upstream defaults.
- **No auth on the gateway** → Acceptable for the lab; agentgateway listener allows all namespaces by design (abox decision).
- **DeepWiki MCP is third-party and may change shape or disappear** → Acceptable for a lab; if `mcp.deepwiki.com` returns non-2xx or unexpected schema the agent returns a plain-text apology, the AgentCard stays valid, and the rest of the lab (Agent Card retrieval, Inventory listing) is unaffected.
- **Egress from KinD to `mcp.deepwiki.com:443` may be blocked behind corporate proxies** → Mitigation: document in the agent's README that the lab assumes unrestricted outbound HTTPS; if behind a proxy, set `HTTPS_PROXY` on the HelmRelease pod env.

## Migration Plan

This is additive — nothing in abox today changes behaviour. The rollout is:

1. Scaffold `lab-4/agent/`, build image, `kind load` it.
2. Add `abox/releases/a2a-agent.yaml` and `abox/releases/inventory.yaml`.
3. Add both to `abox/releases/kustomization.yaml`.
4. `cd abox && make push` (tags + CI publishes OCI artifact).
5. Wait ≤ 5 min for RSIP to pick up the new tag; `flux get all -A` should show both reconciled.
6. Verify with `curl` against the gateway IP.

Rollback: delete the two release files, bump the abox tag, `make push`. Flux prunes the HelmReleases on next reconcile.

## Open Questions

- Does the upstream `agentregistry-inventory` publish an OCI Helm chart, or do we need a `GitRepository` source? — resolved when writing `inventory.yaml`.
- Which exact A2A SDK version does `agents-cli scaffold --agent adk_a2a` pin? — drives the Well-Known URI path (`agent.json` vs `agent-card.json`). The spec file uses `agent-card.json` as the default (post-0.3.x); we adjust if the scaffold pins an older SDK.
- (Resolved by D1c) The agent does NOT need `GOOGLE_API_KEY`. It uses OpenAI via agentgateway `/v1` with a placeholder key the gateway rewrites. No new Secret added by this change — `aire-openai-token` already exists.
- DeepWiki MCP transport: confirm at scaffold time whether the ADK MCP client supports the streamable-HTTP transport that `mcp.deepwiki.com/mcp` exposes, or whether we need a stdio→HTTP bridge. If a bridge is needed it ships as a sidecar in the agent Pod; the AgentCard surface is unaffected either way.
