## Why

Lab 4 (Beginner) requires (a) a custom A2A agent whose Agent Card is discoverable via a Well-Known URI and (b) the agentregistry-inventory ("Inventory") catalog deployed on the cluster so the lab can enumerate the AI resources it sees. The abox baseline already gives us KinD + Flux + agentgateway + kagent; the only missing pieces are the agent itself and Inventory. We add both as Flux HelmReleases under `abox/releases/` so they reconcile through the same gitless-GitOps pipeline as everything else.

The custom agent is the **Public GitHub Documentation Agent**: a single-skill ADK A2A agent that answers natural-language questions about public GitHub repositories by delegating retrieval to the public DeepWiki MCP server (`https://mcp.deepwiki.com/mcp`). DeepWiki is used as the only external knowledge tool — no GitHub API calls, no scraping, no private repos.

Agent Card summary the agent will advertise:
- `name`: `public-github-docs-agent`
- One skill — `id: answer_public_repo_questions`, description "Answers questions about public GitHub repositories using DeepWiki MCP", `inputModes: ["text/plain"]`, `outputModes: ["text/plain"]`.

## What Changes

- Scaffold a new ADK A2A agent under `lab-4/agent/` using `agents-cli scaffold create --agent adk_a2a --prototype`. The template provides the A2A wiring (AgentCard schema, well-known URI handler, JSON-RPC tasks) — no hand-written A2A code.
- Wire the public DeepWiki MCP server (`https://mcp.deepwiki.com/mcp`, streamable HTTP transport) as the agent's sole tool source via ADK's MCP client. Constrain the agent to refuse questions that are not about public GitHub repositories.
- LLM provider is OpenAI through agentgateway `/v1`, NOT Gemini — mirrors lab-3 time-agent. The `--agent adk_a2a` scaffold defaults to Gemini; we override `app/agent.py` to dispatch on `MODEL_PROVIDER` and build `LiteLlm` when `MODEL_PROVIDER=openai`. The agentgateway already has the OpenAI route + `aire-openai-token` Secret; no new LLM credential is added.
- Publish the agent container image to GHCR via a new GitHub Actions workflow `.github/workflows/a2a-agent-image-lab4.yaml`, mirroring `time-agent-image-lab3.yaml`: multi-arch (linux/amd64 + linux/arm64), `paths: lab-4/agent/**` trigger, image at `ghcr.io/<repo>/lab-4/a2a-agent`, semver tag derived from a `lab-4-a2a-agent-<semver>` git tag. KinD nodes pull from GHCR — no `kind load`.
- Add `abox/releases/a2a-agent.yaml`: Namespace `a2a-agent` + HelmRelease (chart packaged from `lab-4/agent/deployment/helm/` or an inline kustomize/raw manifest helm chart) + HTTPRoute on `agentgateway-external` for path prefix `/a2a` and the Well-Known URI under that route + ReferenceGrant.
- Add `abox/releases/inventory.yaml`: Namespace `agentregistry` + HelmRelease pointing at the upstream `agentregistry-inventory` Helm chart with an explicit `ref.tag` + HTTPRoute on `agentgateway-external` for `/inventory` (rewriting to `/`) covering UI (`:8080`), API (`:8080/v0/*`), and optionally MCP (`:8083`) + ReferenceGrant.
- Update `abox/releases/kustomization.yaml` to include the two new files.
- `make push` from `abox/` to publish the new OCI artifact and let RSIP reconcile.
- Verification: `curl http://<gateway-ip>/a2a/.well-known/agent-card.json` returns the AgentCard and `curl http://<gateway-ip>/inventory/v0/agents` (and `/v0/servers`, `/v0/skills`) returns the AI resource list.

Non-goals (deferred to later changes): A2A task communication between two agents (Experienced), multi-agent team (Max), MCPG, Qdrant.

## Capabilities

### New Capabilities

- `a2a-agent`: the Public GitHub Documentation Agent — an ADK-scaffolded A2A agent advertising one skill (`answer_public_repo_questions`) backed by the public DeepWiki MCP server, with an Agent Card discoverable at a Well-Known URI, running in the KinD cluster and reachable through agentgateway.
- `inventory-deployment`: agentregistry-inventory deployed on the KinD cluster via Flux HelmRelease, with its public read-only API reachable through agentgateway so the lab can enumerate AI resources.

### Modified Capabilities

None — this change introduces two brand-new capabilities and does not alter existing abox specs.

## Impact

- New code/artifacts under `lab-4/agent/` (scaffolded project), `.github/workflows/a2a-agent-image-lab4.yaml`, and `lab-4/abox/releases/{a2a-agent,inventory}.yaml`.
- One edit to `lab-4/abox/releases/kustomization.yaml` to include the new release files.
- One new OCI artifact version published by the abox `flux-push` workflow on the next `v*` tag.
- Cluster footprint: two new namespaces (`a2a-agent`, `agentregistry`) plus two HTTPRoutes / ReferenceGrants. No changes to agentgateway, kagent, or Flux itself.
- External dependency added: agent container image published to GHCR at `ghcr.io/<repo>/lab-4/a2a-agent:<semver>` by the new CI workflow, the upstream `agentregistry-inventory` Helm chart (pinned by tag), and a runtime egress dependency on `https://mcp.deepwiki.com/mcp` from the agent Pod. KinD nodes already have outbound internet for the lab — no extra firewall config required.
