# Lab 4

## Beginners

### Research

1. Review the A2A specification:  
   https://a2a-protocol.org

### Development

2. Implement your own agent using any framework.  
   The agent must include an **Agent Card**, and you should be able to retrieve the Agent Card via a **Well-Known URI**.

### Infrastructure

3. Deploy **Inventory** on `abox` or in your own environment: https://github.com/den-vasyliev/agentregistry-inventory

   After deployment, retrieve the list of AI resources available in the cluster.

4. Deploy **MCPG** in your own AI infrastructure or use a similar tool: https://github.com/techwithhuz/mcp-security-governance

5. Deploy the **Qdrant** vector database on `abox` or in your own environment: https://github.com/qdrant/qdrant-helm

---

## Experienced

1. Complete all Beginner tasks.

2. **Development:** Implement A2A task communication between two agents.

---

## Max

1. Complete all Experienced tasks.

2. **Development:** Implement an A2A team that includes your own agent and selected `kagent` agents.

   Create one complex task that must be completed collaboratively by multiple agents.

---

The lab result may be submitted as an **asciinema** recording: https://www.asciinema.org/

Submit a link to the public recording, not the recording file itself.

---

The `abox/` directory here is a vendored, lightly customised copy of [den-vasyliev/abox](https://github.com/den-vasyliev/abox), independent from `lab-3/abox/`:

| Resource         | lab-3                                    | lab-4                                    |
| ---------------- | ---------------------------------------- | ---------------------------------------- |
| KinD cluster     | `abox-lab3`                              | `abox-lab4`                              |
| OCI artifact     | `…/releases-lab3:<tag>`                  | `…/releases-lab4:<tag>`                  |
| Git tag pattern  | `lab3-vX.Y.Z`                            | `lab4-vX.Y.Z`                            |
| CI workflow      | `.github/workflows/flux-push-lab3.yaml`  | `.github/workflows/flux-push-lab4.yaml`  |

### One-time fork setup

1. **Repoint the OCI registry** in [abox/bootstrap/variables.tf](abox/bootstrap/variables.tf):

   ```hcl
   variable "oci_registry" {
     default = "oci://ghcr.io/<your-gh-user>/aire-course"
   }
   ```

   (`releases_artifact` already defaults to `releases-lab4` so it doesn't collide with other labs' artifacts.)

2. **No edit needed** in [.github/workflows/flux-push-lab4.yaml](../.github/workflows/flux-push-lab4.yaml) — it already uses `${{ github.repository }}` to derive the OCI publish path, so it follows your fork automatically.

3. **Bootstrap order matters.** The cluster's `OCIRepository` polls for `releases-lab4:<tag>` artifacts in your GHCR. If no tag exists yet, reconciliation fails until one is published. Sequence:

   ```bash
   git add lab-4/abox/bootstrap/variables.tf
   git commit -m "lab-4/abox: point at my GHCR"
   git push
   cd lab-4/abox && make push     # publishes the first lab4-vX.Y.Z artifact
   ```

4. **Make the GHCR package public** (one-time). The first publish creates a private package; the cluster pulls anonymously. Go to `https://github.com/users/<your-gh-user>?tab=packages` → click `aire-course/releases-lab4` → Package settings → "Change visibility" → **Public**.

5. **Bring the cluster up:**

   ```bash
   cd lab-4/abox
   make run
   ```

   `make run` (defined by [abox/Makefile](abox/Makefile)) installs OpenTofu and k9s, runs `tofu apply` to bring up the KinD cluster (`abox-lab4`) + Flux + the ResourceSet that reconciles your `releases-lab4` artifact, and starts `cloud-provider-kind` so the gateway's LoadBalancer gets a real IP.

### Iterating on the lab

Edit anything under [abox/releases/](abox/releases/) → commit → git push → make push:

```bash
git add .
git commit
git push
cd lab-4/abox && make push
```

The workflow republishes `releases-lab4:<next-tag>`; Flux's `ResourceSetInputProvider` polls every 5 min, detects the new tag, and reconciles. To force immediate reconciliation:

```bash
kubectl --kubeconfig lab-4/abox/bootstrap/abox-lab4-config \
  annotate ocirepository releases -n flux-system reconcile.fluxcd.io/requestedAt="$(date +%s)" --overwrite
```

---

# Solutions

## 2. Public GitHub Documentation Agent (A2A + Well-Known URI)

### What the agent does

An ADK (Python) A2A agent scaffolded with [google-agents-cli](https://google.github.io/agents-cli/) using the `adk_a2a` template, living at [agent/](agent/). It answers natural-language questions about **public GitHub repositories** by delegating all retrieval to the public [DeepWiki MCP server](https://mcp.deepwiki.com/mcp) — no GitHub API, no scraping, no private-repo access.

Same image, two runtimes:

- **Locally:** `agents-cli playground` (ADK web UI on `:8080`) auto-discovers `app/agent.py` and runs an in-process Runner.
- **In Kubernetes (kagent BYO):** the container serves the [A2A protocol](https://a2a-protocol.org) via `uvicorn app.fast_api_app:app`; kagent creates a Deployment+Service from `spec.byo.deployment` and re-exposes it through the controller at `:8083/api/a2a/kagent/public-github-docs-agent/…`. The agent's own `/.well-known/agent-card.json` is additionally reachable through a direct HTTPRoute at `/a2a`, independently of kagent's re-exposure path.

Everything is env-var driven so the same image works in both runtimes: `OPENAI_API_BASE`, `DEEPWIKI_MCP_URL`, and optional routing headers (`OPENAI_EXTRA_HEADERS`, `MCP_EXTRA_HEADERS`).

Retrieve the Agent Card via the **Well-Known URI**:

```bash
# Port-forward the gateway first:
kubectl -n agentgateway-system port-forward svc/agentgateway-external 18180:80

# Fetch via Well-Known URI (spec-compliant path):
curl http://localhost:18180/a2a/.well-known/agent-card.json | jq .
```

```json
{
  "name": "public-github-docs-agent",
  "description": "Answers natural-language questions about public GitHub repositories. Uses DeepWiki MCP to retrieve and synthesise repository documentation.",
  "url": "http://localhost:18180/a2a",
  "version": "0.1.2",
  "protocolVersion": "0.2.5",
  "capabilities": {
    "streaming": true
  },
  "skills": [
    {
      "id": "answer_public_repo_questions",
      "name": "Answer public repo questions",
      "description": "Answers questions about public GitHub repositories using DeepWiki MCP.",
      "tags": ["github", "documentation", "deepwiki"],
      "inputModes": ["text/plain"],
      "outputModes": ["text/plain"]
    }
  ],
  "defaultInputModes": ["text/plain"],
  "defaultOutputModes": ["text/plain"],
  "supportsAuthenticatedExtendedCard": false
}
```

### Why the Agent Card is built manually

`AgentCardBuilder` from the A2A SDK auto-explodes **one skill per MCP tool**. DeepWiki exposes multiple tools (`read_wiki_contents`, `read_wiki_structure`, …), so auto-discovery would advertise all of them as separate agent skills — bloating the card and leaking implementation details about which underlying tools DeepWiki ships.

The agent's public surface is one logical skill — `answer_public_repo_questions` — regardless of how many tools DeepWiki adds underneath. [`app/fast_api_app.py`](agent/app/fast_api_app.py) calls `AgentCard(...)` directly with a fixed single skill, `streaming=True`, and `A2A_BASE_URL` as `url`. The skill list stays stable as DeepWiki evolves its tool roster.

As a side effect, the static skill definition also satisfies the kagent UI: it dials `message/stream` (SSE), which requires `capabilities.streaming === true` in the card. The auto-generated `to_a2a()` path would set streaming to `false` by default — the manual build makes this explicit and tested.

### Why `A2A_BASE_URL` is decoupled from the served path

kagent BYO's hardcoded readiness probe hits `/.well-known/agent-card.json` on the pod (no prefix). The agentgateway HTTPRoute therefore strips the `/a2a` prefix with a `URLRewrite → ReplacePrefixMatch: /` filter, so the pod always sees a path rooted at `/`. The card's `url` field is set to `http://<gateway>/a2a` (via `A2A_BASE_URL`) — that is what an external client uses to reach the agent through the gateway. The two are intentionally decoupled: the probe works, the card is spec-compliant (`{card.url}/.well-known/agent-card.json` resolves correctly), and no code path conflates the served path with the advertised URL.

### Testing locally

```bash
# Terminal 1 — port-forward gateway to :8090 (avoids :8080 collision with playground)
kubectl -n agentgateway-system port-forward svc/agentgateway-external 8090:80

# Terminal 2 — run the agent locally
cd lab-4/agent
export OPENAI_API_BASE=http://localhost:8090/v1
export DEEPWIKI_MCP_URL=http://localhost:8090/mcp
export OPENAI_API_KEY=placeholder-gateway-handles-auth
agents-cli install
agents-cli playground   # http://127.0.0.1:8080/dev-ui
```

Alternatively, hit DeepWiki and OpenAI directly with your own key (no cluster needed):

```bash
cd lab-4/agent
export DEEPWIKI_MCP_URL=https://mcp.deepwiki.com/mcp
export OPENAI_API_KEY=sk-…
unset OPENAI_API_BASE        # LiteLLM falls back to api.openai.com
agents-cli install && agents-cli playground
```

To exercise the same binary that kagent BYO runs:

```bash
uv run uvicorn app.fast_api_app:app --host 127.0.0.1 --port 8080
curl http://127.0.0.1:8080/.well-known/agent-card.json | jq .capabilities
# expect: { "streaming": true }
```

Tests:

```bash
uv run pytest tests/unit                            # always runs, no network
uv run pytest tests/integration/test_server_e2e.py  # boots A2A locally; requires DeepWiki reachable
uv run pytest tests/integration                     # full suite; requires OPENAI_API_KEY + DeepWiki
```

### Files

| Path | Purpose |
| --- | --- |
| [agent/app/agent.py](agent/app/agent.py) | `root_agent` definition. Env-switchable model (`MODEL_PROVIDER=openai`), DeepWiki `McpToolset`, optional `OPENAI_EXTRA_HEADERS` / `MCP_EXTRA_HEADERS` for header-based gateway routing. |
| [agent/app/fast_api_app.py](agent/app/fast_api_app.py) | A2A FastAPI entrypoint. Builds the `AgentCard` explicitly with `streaming=True` and one fixed skill. Mounts `/.well-known/agent-card.json`. |
| [agent/Dockerfile](agent/Dockerfile) | Multi-arch image. CMD runs `uvicorn app.fast_api_app:app`. |
| [agent/tests/](agent/tests/) | Unit tests (no network), A2A smoke test (e2e, DeepWiki required), full integration tests (LLM + DeepWiki). |
| [.github/workflows/a2a-agent-image-lab4.yaml](../.github/workflows/a2a-agent-image-lab4.yaml) | Multi-arch image build. Branch pushes build-only (sanity check); `lab-4-a2a-agent-*` tags publish to GHCR. |
| [abox/releases/a2a-agent.yaml](abox/releases/a2a-agent.yaml) | kagent `Agent` of `spec.type: BYO` + direct HTTPRoute at `/a2a` with the URLRewrite filter. |
| [abox/releases/agentgateway-mcp.yaml](abox/releases/agentgateway-mcp.yaml) | `AgentgatewayBackend` + HTTPRoute that forwards `/mcp` to `mcp.deepwiki.com:443` over TLS originated by the gateway. |

### Release cycle for the agent

The image and the cluster bundle version independently.

- **Change agent code or Dockerfile** → push to `main` runs the build-only CI (sanity check, no push) → cut an image tag when ready:
  ```bash
  git tag lab-4-a2a-agent-0.1.3
  git push origin lab-4-a2a-agent-0.1.3
  ```
  Publishes `ghcr.io/<owner>/aire-course/lab-4/a2a-agent:0.1.3`. First publish: make the GHCR package public.

- **Change the deployment** (image pin, env, resources, HTTPRoute, …) → edit [abox/releases/a2a-agent.yaml](abox/releases/a2a-agent.yaml) → commit, push, then from `abox/`:
  ```bash
  make push
  ```
  Force immediate reconcile with `flux reconcile source oci releases -n flux-system`.

### Gotchas worth knowing

- **Multi-arch is required.** KinD on Apple Silicon runs `linux/arm64`; GitHub runners are `linux/amd64`. A single-arch image fails `ImagePullBackOff` with `no match for platform in manifest`. The CI workflow uses `docker/setup-qemu-action` + `platforms: linux/amd64,linux/arm64`.
- **`AgentCardBuilder` auto-explodes MCP tools into skills.** DeepWiki exposes several tools; auto-discovery would advertise all of them and the card would change every time DeepWiki adds a tool. `fast_api_app.py` builds the card manually with exactly one fixed skill to keep the agent's public surface stable and independently versioned.
- **Port 8080 collides with `agents-cli playground`.** When testing with the cluster, forward agentgateway to `:8090` (or any free port), not `:8080`, to avoid LiteLLM accidentally POSTing `/v1/chat/completions` to the agent itself.
- **kagent BYO readiness probe hits `/.well-known/agent-card.json` on the pod.** The gateway HTTPRoute for `/a2a` must use `URLRewrite → ReplacePrefixMatch: /` so the pod receives a root-relative path. Without the rewrite, the pod returns 404 and the Deployment never becomes Ready.
- **`A2A_BASE_URL` controls `card.url` only, not where routes are served.** The card advertises `http://<gateway>/a2a`; the gateway strips `/a2a` before the request hits the pod. An external client following `{card.url}/.well-known/agent-card.json` correctly reaches the card through this rewrite.

---

## 3. Inventory — AI Resource Registry

### Deployment

Deployed via GitOps as a Flux `HelmRelease` from the OCI chart at `oci://ghcr.io/den-vasyliev/charts/agentregistry:0.5.16` using image tag `0.5.18` (chart and image version independently). Lives in the `agentregistry` namespace. Exposed through agentgateway at `/inventory` with a prefix-strip rewrite; separate HTTPRoute rules for `/v0`, `/admin`, `/_next`, and `/schemas` cover the embedded Next.js UI's absolute-path API calls.

### Accessing the Inventory API

```bash
kubectl -n agentgateway-system port-forward svc/agentgateway-external 18180:80
```

List AI agents discovered in the cluster:

```bash
curl http://localhost:18180/inventory/v0/agents | jq .
```

```json
[
  {
    "name": "public-github-docs-agent",
    "namespace": "kagent",
    "type": "A2A",
    "endpoint": "http://agentgateway-external.agentgateway-system.svc.cluster.local/a2a",
    "description": "Answers natural-language questions about public GitHub repositories using the DeepWiki MCP server.",
    "capabilities": {
      "streaming": true
    }
  }
]
```

List MCP servers registered in the cluster:

```bash
curl http://localhost:18180/inventory/v0/servers | jq .
```

(DeepWiki is an external MCP server reached through the gateway backend; there are no `MCPServer` CRs in `lab-4`'s cluster, so the inventory reports an empty list.)

List LLM models available through agentgateway:

```bash
curl http://localhost:18180/inventory/v0/models | jq .
```

```json
[
  {
    "name": "gpt-4.1-mini",
    "provider": "openai",
    "endpoint": "http://agentgateway-external.agentgateway-system.svc.cluster.local/v1"
  }
]
```

The Inventory UI is also available at **`http://localhost:18180/inventory/`**.

### Gotchas worth knowing

- **Image `0.5.4` has broken autodiscovery.** A failed `client.WithWatch` type assertion in the local-cluster client made all `/v0/*` endpoints return empty lists. Pin the image tag explicitly to `"0.5.18"` in HelmRelease values; the chart's own `appVersion: latest` is not trustworthy here.
- **`/_next`, `/v0`, and `/admin` routes must coexist with `/inventory`.** The Next.js UI injects absolute asset paths (`/_next/static/…`) and calls the JSON API at `/v0/*` without the `/inventory` prefix. The HTTPRoute ships four separate prefix rules so none of these 404.
- **`disableAuth: true` is the chart default.** Intentional for a single-tenant lab (the `/v0/*` API is open). Do not carry this to production.
- **`install.createNamespace: false`.** The `agentregistry` Namespace is declared above the `HelmRelease` in the same manifest; letting Helm also create it causes a race that can fail reconciliation.

---

## 4. MCPG — MCP Security Governance

### Deployment

Deployed via GitOps as a Flux `HelmRelease` from `oci://ghcr.io/techwithhuz/charts/mcp-governance:0.22.2`. Two components run in the `mcp-governance` namespace:

- **Controller** (`ghcr.io/techwithhuz/mcp-governance-controller:0.22.2`, port `:8090`) — discovers `MCPServer` CRs and scores them against the cluster governance policy across nine weighted categories (Agent Gateway integration, authentication, RBAC, CORS, TLS, prompt guard, rate limit, tool scope, hardened deployment).
- **Dashboard** (`ghcr.io/techwithhuz/mcp-governance-dashboard:0.22.2`, port `:3000`) — Next.js UI backed by the controller REST API. Service type forced to `ClusterIP` (chart default is `NodePort 30000`, which is incompatible with the gateway-centric routing in abox).

Access the dashboard:

```bash
kubectl -n mcp-governance port-forward svc/mcp-governance-dashboard 3000:3000
```

Open `http://localhost:3000` in a browser.

### CRD fix

Chart `v0.22.2` ships a malformed `mcpgovernancepolicies` CRD (`charts/mcp-governance/crds/mcpgovernancepolicies.yaml`). Under `spec.properties.spec` it has **two** `type/properties` blocks at the same indent level — YAML parsing silently keeps only the second (which contains the status fields), discarding every policy field (`requireRBAC`, `scoringWeights`, `requireJWTAuth`, etc.). The chart's sample `MCPGovernancePolicy` CR then fails admission with `field not declared in schema`.

Fix: [abox/releases/mcp-governance.yaml](abox/releases/mcp-governance.yaml) vendors a corrected CRD (all policy fields under `.spec`, all status fields under `.status`) and sets `install.crds: Skip` on the HelmRelease so Helm never applies the upstream broken one. Because `crds: Skip` suppresses *all* chart CRDs, the well-formed `GovernanceEvaluation` CRD is also vendored unchanged. Flux applies the vendored CRDs before the HelmRelease reconciles, so the controller and the sample policy install cleanly.

### Gotchas worth knowing

- **`install.crds: Skip` must be set on both `install` and `upgrade`.** Setting it only under `install` means the next `helm upgrade` reinstalls the broken upstream CRD, and the policy CR starts failing again.
- **Sample policy and evaluation are enabled (`samples.install: true`).** Safe because the corrected CRD is in place before the HelmRelease renders. `excludeNamespaces` is tuned to skip `flux-system`, `external-secrets`, and other system namespaces — those are cluster plumbing, not MCP infrastructure.
- **Dashboard `NodePort 30000` conflicts with abox conventions.** The chart's default service type is `NodePort`; overriding to `ClusterIP` and using `port-forward` keeps all external access routed through agentgateway or explicit kubectl forwards, which is consistent with how every other service in abox is accessed.

---

## 5. Qdrant — Vector Database

### Deployment

Deployed via GitOps as a Flux `HelmRelease` from `https://qdrant.github.io/qdrant-helm`, chart version `1.18.0`, image `docker.io/qdrant/qdrant:v1.18.0`. Single replica, 10 Gi PVC on the `standard` StorageClass (KinD's `rancher.io/local-path` backed class, pinned explicitly). API keys are sourced from GCP Secret Manager via External Secrets Operator — the `aire_qdrant_api_key` GCP secret contains both `api-key` and `read-only-api-key` fields that ESO projects into the `aire-qdrant-api-key` Kubernetes Secret. No HTTPRoute — Qdrant stays cluster-internal and is reached by agent workloads via the in-cluster DNS name `qdrant.qdrant.svc.cluster.local`.

```bash
kubectl -n qdrant port-forward svc/qdrant 6333:6333
```

Verify the instance:

```bash
curl http://localhost:6333/ | jq .
```

```json
{
  "title": "qdrant - vector search engine",
  "version": "1.18.0",
  "commit": "...",
  "features": {
    "sparse_vectors": true,
    "multivector": true,
    "payload_data_types": true
  }
}
```

List collections (empty on a fresh install):

```bash
curl -H "api-key: <your-api-key>" http://localhost:6333/collections | jq .
```

```json
{
  "result": {
    "collections": []
  },
  "status": "ok",
  "time": 0.000009
}
```

### Gotchas worth knowing

- **ExternalSecret races `qdrant` HelmRelease on first install.** The chart's Helm `lookup` reads the API key Secret at render time. If ESO hasn't materialized `aire-qdrant-api-key` yet, the key bakes in empty and Qdrant starts unauthenticated. Fix: wait until the ExternalSecret shows `SecretSynced`, then force reconcile once:
  ```bash
  flux reconcile helmrelease qdrant -n qdrant --force
  ```
- **`standard` StorageClass is pinned explicitly.** If the cluster's default StorageClass changes, a PVC without an explicit `storageClassName` would bind to a different class silently. Explicit pin prevents the surprise.
- **`metrics.serviceMonitor.enabled: false`.** The chart can render a `ServiceMonitor` CR for Prometheus scraping; with no `monitoring.coreos.com` CRD in the cluster this would fail. Disabled explicitly.
- **`resources` are set explicitly.** The chart leaves CPU/memory requests and limits unset by default, meaning the scheduler has no placement signal and Qdrant can starve other pods during ingest bursts on a shared KinD node. Floor (`100m` / `256Mi`) and ceiling (`1Gi` memory) are set in HelmRelease values.
