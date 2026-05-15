# Lab 3

## Beginner Level

### Research

Choose one of the following topics and describe which real technical or business use cases can be implemented with it:

1. MCP Sampling
2. MCP Elicitation
3. MCP Apps

### Development

1. Explore **kmcp**:  
   https://www.solo.io/blog/introducing-kmcp

   Develop and deploy your own MCP server inside **abox**.

2. Explore **google-agents-cli**:  
   https://google.github.io/agents-cli/

   Develop and deploy your own agent inside **abox** using your custom MCP server.

3. Explore how to use the following tools with your custom MCP server and agent running in your own infrastructure:

   - `npx @modelcontextprotocol/inspector@0.21.1`
   - `agents-cli playground`

## Experienced Level

1. Complete all Beginner Level tasks.

2. Development:  
   Implement your own MCP Apps use case.

## Max Level

1. Complete all Experienced Level tasks.

2. Development:  
   Implement your own MCP Sampling or MCP Elicitation use case.

## Solutions

The `abox/` directory here is a vendored, lightly customised copy of [den-vasyliev/abox](https://github.com/den-vasyliev/abox), independent from `lab-2/abox/`:

| Resource         | lab-2                              | lab-3                                    |
| ---------------- | ---------------------------------- | ---------------------------------------- |
| KinD cluster     | `abox`                             | `abox-lab3`                              |
| OCI artifact     | `…/releases:<tag>`                 | `…/releases-lab3:<tag>`                  |
| Git tag pattern  | `vX.Y.Z`                           | `lab3-vX.Y.Z`                            |
| CI workflow      | `.github/workflows/flux-push.yaml` | `.github/workflows/flux-push-lab3.yaml`  |

### One-time fork setup

1. **Repoint the OCI registry** in [abox/bootstrap/variables.tf](abox/bootstrap/variables.tf):

   ```hcl
   variable "oci_registry" {
     default = "oci://ghcr.io/<your-gh-user>/aire-course"
   }
   ```

   (`releases_artifact` already defaults to `releases-lab3` so it doesn't collide with lab-2's `releases` artifact.)

2. **No edit needed** in [.github/workflows/flux-push-lab3.yaml](../.github/workflows/flux-push-lab3.yaml) — it already uses `${{ github.repository }}` to derive the OCI publish path, so it follows your fork automatically.

3. **Bootstrap order matters.** The cluster's `OCIRepository` polls for `releases-lab3:<tag>` artifacts in your GHCR. If no tag exists yet, reconciliation fails until one is published. Sequence:

   ```bash
   # commit + push the fork-specific edits
   git add lab-3/abox/bootstrap/variables.tf
   git commit -m "lab-3/abox: point at my GHCR"
   git push
   cd lab-3/abox && make push     # publishes the first lab3-vX.Y.Z artifact
   ```

4. **Make the GHCR package public** (one-time). The first publish creates a private package; the cluster pulls anonymously. Go to `https://github.com/users/<your-gh-user>?tab=packages` → click `aire-course/releases-lab3` → Package settings → "Change visibility" → **Public**.

5. **Bring the cluster up:**

   ```bash
   cd lab-3/abox
   make run
   ```

   `make run` (defined by [abox/Makefile](abox/Makefile)) installs OpenTofu and k9s, runs `tofu apply` to bring up the KinD cluster (`abox-lab3`) + Flux + the ResourceSet that reconciles your `releases-lab3` artifact, and starts `cloud-provider-kind` so the gateway's LoadBalancer gets a real IP.

### Iterating on the lab

Edit anything under [abox/releases/](abox/releases/) → commit → git push → make push:

```bash
git add .
git commit
git push
cd lab-3/abox && make push
```

The workflow republishes `releases-lab3:<next-tag>`; Flux's `ResourceSetInputProvider` polls every 5 min, detects the new tag, and reconciles. To force immediate reconciliation:

```bash
kubectl --kubeconfig lab-3/abox/bootstrap/abox-lab3-config \
  annotate ocirepository releases -n flux-system reconcile.fluxcd.io/requestedAt="$(date +%s)" --overwrite
```

---

# Solutions

1. Solution for the research task is described in lab-3/research folder.

2. **Custom Time MCP server, deployed via GitOps.**

   ### What the server does

   A FastMCP 3 server scaffolded with [kmcp](https://github.com/kagent-dev/kmcp), living at [abox/time-mcp-server/](abox/time-mcp-server/). It exposes time-related tools to any MCP-compatible agent:

   - `get_current_time` — returns the current time in a given IANA timezone (defaults to UTC).
   - `convert_time` — converts a wall-clock time between two IANA timezones.
   - `echo` — diagnostic echo tool.

   Tools live under [abox/time-mcp-server/src/tools/](abox/time-mcp-server/src/tools/) and auto-register via FastMCP's `@mcp.tool()` decorator; the dynamic loader in [src/core/server.py](abox/time-mcp-server/src/core/server.py) picks them up at startup, so adding a tool is "drop a `.py` file, no wiring needed". Transport is **Streamable HTTP on `:3000/mcp`** — the same image can also run stdio (`start` script) for local MCP-inspector testing.

   ### Why not the kmcp quickstart flow

   The [kmcp quickstart](https://kagent.dev/docs/kmcp/quickstart#deploy-the-mcp-server) uses `kmcp deploy` which `kubectl apply`s an `MCPServer` CR straight at the cluster. That bypasses Flux. In abox, every cluster change must arrive through the `releases-lab3` OCI artifact, so we kept the same `MCPServer` CR (it's a kmcp-native, declarative resource) but ship it through GitOps and built the container image with our own CI.

   The kagent `time-agent` ([abox/releases/agent-time.yaml](abox/releases/agent-time.yaml)) reaches the server via the explicit `RemoteMCPServer time-mcp-via-gateway`, which points at the gateway URL — not the Service directly. Discovery is disabled on the `MCPServer` so kmcp does not auto-create a competing `RemoteMCPServer`.

   ### Files

   | Path | Purpose |
   | --- | --- |
   | [abox/time-mcp-server/](abox/time-mcp-server/) | Server source, `pyproject.toml`, `Dockerfile`, `kmcp.yaml`. |
   | [.github/workflows/time-mcp-image-lab3.yaml](../.github/workflows/time-mcp-image-lab3.yaml) | Multi-arch image build. Branch pushes build-only (sanity check); `lab-3-time-mcp-*` tags publish to GHCR. |
   | [abox/releases/time-mcp-server.yaml](abox/releases/time-mcp-server.yaml) | `MCPServer` CR (the declarative `kmcp deploy`) + `RemoteMCPServer` pointing at the gateway. |
   | [abox/releases/agentgateway-mcp.yaml](abox/releases/agentgateway-mcp.yaml) | `AgentgatewayBackend` + HTTPRoute that federates `/mcp` to the server. Untouched — its static target matches the Service the kmcp controller generates. |
   | [abox/releases/agent-time.yaml](abox/releases/agent-time.yaml) | kagent `Agent` declaring which tools to expose to the model. |

   ### Release cycle for the server

   The image and the cluster bundle version **independently**.

   - **Change the server code/Dockerfile** → push to `main` runs the build (no publish) → when ready, cut an image tag:
     ```bash
     git tag lab-3-time-mcp-0.1.1
     git push origin lab-3-time-mcp-0.1.1
     ```
     The workflow publishes `ghcr.io/<owner>/aire-course/lab-3/time-mcp-server:0.1.1`. First time: make the GHCR package public so KinD can pull it anonymously.

   - **Change the deployment** (image pin, env, replicas, gateway target, …) → edit [abox/releases/time-mcp-server.yaml](abox/releases/time-mcp-server.yaml) → commit, push, then from `abox/`:
     ```bash
     make push
     ```
     RSIP polls every 5 min; force immediate reconcile with `flux reconcile source oci releases -n flux-system`.

   ### Gotchas worth knowing

   - **Multi-arch is required.** KinD on Apple Silicon runs linux/arm64; GitHub runners are linux/amd64. A single-arch image will fail `ImagePullBackOff` with `no match for platform in manifest`. The workflow uses `docker/setup-qemu-action` + `platforms: linux/amd64,linux/arm64`.
   - **Don't wrap the entrypoint in `uv run`** inside the container. The image's venv is already baked at build time and `/app/.venv/bin` is on `PATH`, so `cmd: dev-http` runs the project's console script directly. `uv run` tries to populate `$HOME/.cache/uv`, which fails for the non-root `mcpuser`.
   - **`.python-version` must be committed.** The stock Python `.gitignore` excludes it; the Dockerfile copies it during `uv sync`. Without it, the CI build fails with `failed to compute cache key … "/.python-version": not found`.
   - **`discovery: disabled` on the MCPServer is intentional.** It stops the kmcp controller from auto-creating a `RemoteMCPServer` that would point at the Service. We want agents to traverse agentgateway so the gateway's MCP-aware features (session routing, observability) apply.


3. **Custom Time agent, deployed as kagent BYO via GitOps.**

   ### What the agent does

   An ADK (Python) agent scaffolded with [google-agents-cli](https://google.github.io/agents-cli/), living at [abox/time-agent/](abox/time-agent/). It answers time/timezone questions by calling the custom time MCP server through agentgateway. Same image, two runtimes:

   - **Locally:** `agents-cli playground` (ADK web UI on `:8080`) auto-discovers `app/agent.py` and runs an in-process Runner.
   - **In Kubernetes (kagent BYO):** the container serves the [A2A protocol](https://adk.dev/a2a/) via `uvicorn app.a2a_app:a2a_app`; kagent creates a Deployment+Service from `spec.byo.deployment` and re-exposes it through the controller at `:8083/api/a2a/kagent/time-agent/.well-known/agent.json`.

   Everything is env-var driven so the same image works in both: model provider, OpenAI base URL, MCP URL, optional routing headers.

   ### Why an explicit A2A agent card

   `to_a2a()` auto-generates an agent card from the ADK agent, but defaults `capabilities.streaming` to unset (treated as `false`). The kagent UI dials `message/stream` (SSE) — when the card says streaming isn't supported, the A2A SDK rejects the request with `Streaming is not supported by the agent` and the UI shows a red error box.

   [`app/a2a_app.py`](abox/time-agent/app/a2a_app.py) builds the card explicitly with `AgentCapabilities(streaming=True)` and lists the two MCP tools as `AgentSkill` entries (the auto-builder would have populated those, but providing our own card bypasses it). An e2e test asserts `card.capabilities.streaming === true` so a regression fails CI instead of production.

   ### Testing locally

   `agents-cli playground` binds to `:8080`, so port-forward agentgateway to a different port to avoid the collision:

   ```bash
   # Terminal 1
   kubectl -n agentgateway-system port-forward svc/agentgateway-external 8090:80

   # Terminal 2
   cd lab-3/abox/time-agent
   export OPENAI_API_BASE=http://localhost:8090/v1
   export TIME_MCP_URL=http://localhost:8090/mcp
   export OPENAI_API_KEY=placeholder-gateway-handles-auth
   agents-cli install
   agents-cli playground   # http://127.0.0.1:8080/dev-ui
   ```

   Alternatively, run the MCP server locally and use your own OpenAI key (no cluster needed):

   ```bash
   cd lab-3/abox/time-mcp-server && uv sync && uv run dev-http &
   cd ../time-agent
   export TIME_MCP_URL=http://localhost:3000/mcp
   export OPENAI_API_KEY=sk-…
   unset OPENAI_API_BASE        # LiteLLM falls back to api.openai.com
   agents-cli playground
   ```

   To exercise the same binary kagent BYO will run:

   ```bash
   uv run uvicorn app.a2a_app:a2a_app --host 127.0.0.1 --port 8080
   curl http://127.0.0.1:8080/.well-known/agent-card.json | jq .capabilities
   # expect: { "streaming": true, ... }
   ```

   Tests:

   ```bash
   uv run pytest tests/unit                            # always runs, no network
   uv run pytest tests/integration/test_server_e2e.py  # boots A2A locally, no LLM call
   uv run pytest tests/integration                     # requires TIME_MCP_URL reachable
   uv run adk eval tests/eval/evalsets/basic.evalset.json \
     --config_file_path tests/eval/eval_config.json
   ```

   ### Files

   | Path | Purpose |
   | --- | --- |
   | [abox/time-agent/app/agent.py](abox/time-agent/app/agent.py) | `root_agent` definition. Env-switchable model (`MODEL_PROVIDER=openai\|gemini`), MCP toolset filtered to `get_current_time` + `convert_time`, optional `OPENAI_EXTRA_HEADERS` / `MCP_EXTRA_HEADERS` for header-based gateway routing. |
   | [abox/time-agent/app/a2a_app.py](abox/time-agent/app/a2a_app.py) | A2A entrypoint for BYO. Builds the agent card explicitly with `streaming=true`. |
   | [abox/time-agent/Dockerfile](abox/time-agent/Dockerfile) | Builds the BYO image. CMD runs `uvicorn app.a2a_app:a2a_app`. |
   | [abox/time-agent/tests/](abox/time-agent/tests/) | Unit tests (no network), A2A smoke test, MCP-required integration tests, ADK evalset. |
   | [.github/workflows/time-agent-image-lab3.yaml](../.github/workflows/time-agent-image-lab3.yaml) | Multi-arch image build. Branch pushes build-only (sanity check); `lab-3-time-agent-*` tags publish to GHCR. |
   | [abox/releases/time-agent.yaml](abox/releases/time-agent.yaml) | kagent `Agent` of `spec.type: BYO`, pinned to a versioned image, with env wiring for model + MCP URLs. |

   ### Release cycle for the agent

   Same pattern as the MCP server — image and bundle version independently.

   - **Change the agent code/Dockerfile** → push to `main` runs the build (no publish) → cut an image tag when ready:
     ```bash
     git tag lab-3-time-agent-0.1.2
     git push origin lab-3-time-agent-0.1.2
     ```
     The workflow publishes `ghcr.io/<owner>/aire-course/lab-3/time-agent:0.1.2`. First publish: make the GHCR package public.

   - **Change the deployment** (image pin, env, resources, …) → edit [abox/releases/time-agent.yaml](abox/releases/time-agent.yaml) → commit, push, then from `abox/`:
     ```bash
     make push
     ```

   ### Gotchas worth knowing

   - **kagent UI uses A2A `message/stream`.** The auto-generated agent card from `to_a2a()` declares `streaming: false` by default. Without the explicit `AgentCard(capabilities=AgentCapabilities(streaming=True))` in [a2a_app.py](abox/time-agent/app/a2a_app.py), every chat hits a 500 with `Streaming is not supported by the agent`.
   - **Port 8080 collides with `agents-cli playground`.** The local dev UI binds to `:8080` — pick a different port (e.g. `:8090`) when port-forwarding the gateway, otherwise LiteLLM ends up POSTing `/v1/chat/completions` to the agent itself and gets a 404 instead of a model response.
   - **`OPENAI_API_BASE` unset ≠ empty string.** Earlier versions of [agent.py](abox/time-agent/app/agent.py) defaulted to `http://localhost:8080/v1`, which silently routed back to the agent's own port. The current code passes `api_base` only when the env var is non-empty so an unset value correctly falls through to LiteLLM's `api.openai.com` default.
   - **BYO does not consult `ModelConfig` or `RemoteMCPServer`.** Those CRDs only feed the Declarative runtime. For BYO, all model and MCP wiring lives in `spec.byo.deployment.env` — `kubectl describe agent time-agent` is the source of truth, not `kubectl get modelconfig`.
   - **Flux `Stalled: True` after a 10-min install timeout doesn't auto-retry.** If the kagent HelmRelease times out at first install (e.g. `kagent-controller` Deployment slow to become Ready), the entire `releases` kustomization stays in `HealthCheckFailed` and your new `time-agent.yaml` never reconciles. Kick it manually:
     ```bash
     flux reconcile helmrelease kagent -n kagent --force
     ```
   - **`pyproject.toml`'s `hatch.build.targets.wheel.packages` listed a non-existent `frontend` package** when the project was scaffolded. Pruned to `["app"]` — otherwise `uv build` (clean wheel build, not editable install) would fail.
