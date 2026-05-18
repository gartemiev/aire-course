## ADDED Requirements

### Requirement: Agent SHALL be scaffolded with ADK A2A template

The agent project under `lab-4/agent/` SHALL be created with `agents-cli scaffold create <name> --agent adk_a2a --prototype`. Hand-written A2A protocol code (AgentCard schema, well-known URI handler, JSON-RPC task endpoints) MUST NOT replace the template's wiring.

#### Scenario: Project layout shows the A2A template was used

- **WHEN** `agents-cli info` is run from `lab-4/agent/`
- **THEN** the output reports `template: adk_a2a` and `deployment-target: prototype`
- **AND** the project root contains `pyproject.toml`, an agent package directory, and a `Dockerfile`

#### Scenario: A2A wiring uses the SDK helper, not hand-written endpoints

- **WHEN** the agent's FastAPI app source is inspected
- **THEN** the A2A endpoints are mounted via the ADK `to_a2a()` helper (or the equivalent A2A SDK adapter the scaffold ships)
- **AND** no source file in the agent package defines a custom handler for `/.well-known/agent-card.json` or `/.well-known/agent.json`

### Requirement: Agent SHALL expose its Agent Card at a Well-Known URI

The deployed agent SHALL serve an A2A AgentCard JSON document at the Well-Known URI path defined by the A2A specification (`/.well-known/agent-card.json` for A2A 0.3.x and later; `/.well-known/agent.json` for older SDKs). The URI MUST be reachable through the `agentgateway-external` Gateway on port 80 under the agent's HTTPRoute prefix.

#### Scenario: Agent Card is retrievable via the gateway

- **WHEN** an operator runs `curl -fsS http://<gateway-ip>/a2a/.well-known/agent-card.json`
- **THEN** the HTTP response status MUST be 200
- **AND** the body MUST be valid JSON
- **AND** the JSON MUST contain at minimum the A2A-required fields `name`, `description`, `url`, `version`, and `capabilities`

#### Scenario: Agent Card declares the externally-reachable URL

- **WHEN** the AgentCard JSON is parsed
- **THEN** the `url` field MUST equal `http://<gateway-ip>/a2a` (the externally-reachable base URL, including the HTTPRoute prefix)
- **AND** appending `/.well-known/agent-card.json` to that `url` MUST resolve to the same document retrieved in the previous scenario

#### Scenario: Skills are advertised in the Agent Card

- **WHEN** the AgentCard JSON is parsed
- **THEN** the `skills` array (or its protocol-equivalent field) MUST contain at least one entry
- **AND** each entry MUST have a non-empty `id` and `description`

### Requirement: Agent SHALL advertise the answer_public_repo_questions skill

The deployed agent's AgentCard SHALL identify it as the Public GitHub Documentation Agent and advertise exactly one skill that answers questions about public GitHub repositories.

#### Scenario: Agent identity fields match the Public GitHub Documentation Agent

- **WHEN** the AgentCard JSON is fetched and parsed
- **THEN** the `name` field MUST equal `public-github-docs-agent`
- **AND** the `description` field MUST mention public GitHub repositories and DeepWiki

#### Scenario: Single skill advertises GitHub repo Q&A

- **WHEN** the AgentCard `skills` array is inspected
- **THEN** it MUST contain an entry with `id: answer_public_repo_questions`
- **AND** that entry's `description` MUST be "Answers questions about public GitHub repositories using DeepWiki MCP."
- **AND** the entry's `inputModes` MUST contain `text/plain`
- **AND** the entry's `outputModes` MUST contain `text/plain`

#### Scenario: No additional skills are leaked

- **WHEN** the AgentCard `skills` array is inspected
- **THEN** the array MUST contain exactly one entry — the agent MUST NOT advertise skills outside the documented scope

### Requirement: Agent SHALL route LLM calls through agentgateway as OpenAI

The agent SHALL use OpenAI as its model provider via the agentgateway `/v1` route, NOT Gemini or any direct LLM upstream. The ADK adapter MUST be `google.adk.models.lite_llm.LiteLlm`. The env contract MUST match lab-3 time-agent: `MODEL_PROVIDER=openai`, `OPENAI_API_BASE=http://agentgateway-external.agentgateway-system.svc.cluster.local/v1`, `OPENAI_MODEL` set to a concrete OpenAI model string, `OPENAI_API_KEY=placeholder-gateway-injects-real-key`. No new Kubernetes Secret SHALL be introduced for LLM credentials — the existing `aire-openai-token` (wired via `agentgateway-llm.yaml`) supplies the real key at the gateway hop.

#### Scenario: Agent code selects the LiteLlm model class on MODEL_PROVIDER=openai

- **WHEN** `app/agent.py` is inspected and reloaded with `MODEL_PROVIDER=openai` in the env
- **THEN** `root_agent.canonical_model` MUST be an instance of `google.adk.models.lite_llm.LiteLlm`
- **AND** the construction MUST read `OPENAI_MODEL`, `OPENAI_API_BASE`, and `OPENAI_API_KEY` from the env — no hard-coded model name, no hard-coded API base

#### Scenario: HelmRelease wires the env to agentgateway, not to a Google endpoint

- **WHEN** `abox/releases/a2a-agent.yaml` values are inspected
- **THEN** `OPENAI_API_BASE` MUST equal `http://agentgateway-external.agentgateway-system.svc.cluster.local/v1`
- **AND** `OPENAI_API_KEY` MUST be the literal placeholder string (the gateway injects the real key)
- **AND** the env block MUST NOT set `GOOGLE_API_KEY`, `GEMINI_API_KEY`, `VERTEX_PROJECT_ID`, or any Vertex / Google AI credential

#### Scenario: No second LLM upstream is added to agentgateway

- **WHEN** `abox/releases/agentgateway-llm.yaml` and `abox/releases/openai-credentials.yaml` are inspected after this change
- **THEN** no new route or Secret SHALL have been added for Gemini / Vertex
- **AND** the existing `aire-openai-token` Secret MUST remain the only LLM credential referenced by agentgateway

#### Scenario: Unknown MODEL_PROVIDER raises at startup

- **WHEN** `app/agent.py` is reloaded with `MODEL_PROVIDER=bogus`
- **THEN** the reload MUST raise `ValueError` with a message matching `Unknown MODEL_PROVIDER`

### Requirement: Agent SHALL use the public DeepWiki MCP server as its sole tool source

The agent SHALL be configured to call `https://mcp.deepwiki.com/mcp` (streamable HTTP MCP transport) as its only external tool source. No other MCP servers, no direct GitHub API calls, no web scraping. The agent SHALL refuse, in plain text, any request that is not about a public GitHub repository.

#### Scenario: DeepWiki endpoint is wired in agent configuration

- **WHEN** the agent source (or its deployed ConfigMap / env) is inspected
- **THEN** the MCP client configuration MUST reference exactly `https://mcp.deepwiki.com/mcp`
- **AND** no other MCP server URLs MUST be configured as tool sources
- **AND** no GitHub API client (e.g., `PyGithub`, `octokit`) MUST be imported or invoked from the agent code

#### Scenario: Repo-specific question triggers a DeepWiki MCP call

- **WHEN** an A2A `tasks/send` request is posted to the agent with input "How does request routing work in envoyproxy/envoy?"
- **AND** the agent's logs are inspected for the duration of the task
- **THEN** the logs MUST show at least one outbound MCP call to `mcp.deepwiki.com`
- **AND** the task's final text response MUST be non-empty and reference the repo identifier `envoyproxy/envoy`

#### Scenario: Off-topic question is refused in plain text

- **WHEN** an A2A `tasks/send` request is posted to the agent with input "What is the capital of France?"
- **THEN** the task's final text response MUST politely state that the agent only answers questions about public GitHub repositories
- **AND** no outbound call to `mcp.deepwiki.com` MUST be made for that task

#### Scenario: Upstream DeepWiki failure surfaces as a text response, not an A2A error

- **WHEN** `mcp.deepwiki.com` returns a non-2xx response or times out during a task
- **THEN** the A2A task MUST still complete (no protocol-level error)
- **AND** the final text response MUST inform the caller that DeepWiki was unreachable

### Requirement: Agent SHALL ship a test suite mirroring lab-3/time-agent/tests/

The agent project SHALL include a `tests/` tree with three subdirectories — `unit/`, `integration/`, `eval/` — following the same conventions as `lab-3/abox/time-agent/tests/`. Tests SHALL be runnable via `uv run pytest` from `lab-4/agent/` after `uv sync` and SHALL NOT depend on any cluster state to pass the unit layer.

The split is:
- `tests/unit/` — no network, no LLM calls. Asserts agent construction (DeepWiki MCP toolset wiring, model provider selection, AgentCard identity / single-skill shape).
- `tests/integration/` — runs the real agent against the live DeepWiki MCP and the configured LLM. Auto-skipped when DeepWiki is unreachable so CI without internet still passes.
- `tests/integration/test_server_e2e.py` — spawns the A2A server in a subprocess, fetches `/.well-known/agent-card.json`, asserts shape.
- `tests/eval/` — ADK `evalset` (`*.evalset.json`) plus `eval_config.json` with rubric-based LLM-as-judge criteria. Run via `agents-cli eval run`.

The agent's `pyproject.toml` SHALL declare `pytest`, `pytest-asyncio`, `nest-asyncio` in `[project.optional-dependencies].dev` and `google-adk[eval]` in `[project.optional-dependencies].eval`, matching lab-3.

#### Scenario: Unit tests run offline and pass

- **WHEN** an operator runs `uv sync --extra dev && uv run pytest tests/unit -q` from `lab-4/agent/` with no network access to `mcp.deepwiki.com`
- **THEN** every test in `tests/unit/` MUST be collected and pass
- **AND** no test in `tests/unit/` MUST attempt an outbound network call

#### Scenario: Unit tests assert the DeepWiki MCP wiring

- **WHEN** `tests/unit/test_agent_wiring.py` is inspected
- **THEN** it MUST include a test that constructs `root_agent` via `importlib.reload(app.agent)` under a `monkeypatch`-set env and asserts the agent has exactly one `MCPToolset` whose connection URL equals `https://mcp.deepwiki.com/mcp`
- **AND** it MUST include a test that asserts no other MCP toolsets, no `PyGithub`/`octokit`-style tools, and no hard-coded GitHub PAT are present on the agent

#### Scenario: Unit tests assert the AgentCard identity and single skill

- **WHEN** `tests/unit/test_agent_card.py` (or equivalent file under `tests/unit/`) is run
- **THEN** it MUST assert that the AgentCard built by the ADK helper has `name == "public-github-docs-agent"`
- **AND** asserts the `skills` list has exactly one entry with `id == "answer_public_repo_questions"`, `inputModes` containing `text/plain`, and `outputModes` containing `text/plain`

#### Scenario: Integration tests auto-skip when DeepWiki is unreachable

- **WHEN** `tests/integration/test_agent.py` is collected and `mcp.deepwiki.com` is not reachable (timeout or non-2xx on a JSON-RPC `initialize`)
- **THEN** `pytestmark = pytest.mark.skipif(...)` MUST mark every test in the file as skipped with a reason mentioning DeepWiki
- **AND** `uv run pytest tests/integration -q` MUST exit 0 (no failures, only skips)

#### Scenario: Integration tests exercise the live DeepWiki MCP

- **WHEN** DeepWiki MCP is reachable and `uv run pytest tests/integration/test_agent.py -q` is run
- **THEN** at least one test MUST send a repo-specific prompt (e.g., "How does request routing work in envoyproxy/envoy?") to `root_agent` through `google.adk.runners.Runner`
- **AND** MUST assert that the captured events include a `function_call` invoking a DeepWiki tool and a non-empty final text response

#### Scenario: A2A server e2e test boots a subprocess and asserts the Agent Card

- **WHEN** `tests/integration/test_server_e2e.py` is run with DeepWiki reachable
- **THEN** it MUST spawn the scaffolded A2A entry point (e.g., `uvicorn app.a2a_app:a2a_app`) on a free local port, wait for readiness, and fetch `http://127.0.0.1:<port>/.well-known/agent-card.json`
- **AND** assert HTTP 200, `card["name"] == "public-github-docs-agent"`, `card["protocolVersion"]` non-empty, and exactly one entry in `card["skills"]` with `id == "answer_public_repo_questions"`

#### Scenario: Eval suite ships a rubric-based config and at least three eval cases

- **WHEN** `tests/eval/eval_config.json` and `tests/eval/evalsets/basic.evalset.json` are inspected
- **THEN** `eval_config.json` MUST define `rubric_based_final_response_quality_v1` with `threshold >= 0.7`, `judgeModel` set to a current Gemini model, and at least three rubrics covering: (a) the response calls a DeepWiki tool when the question is repo-specific, (b) the response refuses off-topic questions politely, (c) the response cites the repo identifier it was asked about
- **AND** `basic.evalset.json` MUST contain at least three `eval_cases` — one repo-specific Q&A, one cross-repo or comparison question, one off-topic refusal — each with `session_input.app_name == "app"`

#### Scenario: Eval suite is invokable through agents-cli

- **WHEN** an operator runs `agents-cli eval run` from `lab-4/agent/` with the LLM credentials configured
- **THEN** the command MUST discover `tests/eval/evalsets/basic.evalset.json`, execute every eval case, and produce a result document
- **AND** the overall `rubric_based_final_response_quality_v1` score MUST meet the threshold declared in `eval_config.json`

### Requirement: Agent SHALL be deployed via Flux HelmRelease under abox/releases/

The agent SHALL be deployed by adding `abox/releases/a2a-agent.yaml` containing a `Namespace` resource (`a2a-agent`) and a Flux `HelmRelease` in that namespace, following abox conventions: explicit `ref.tag` on the chart source, `dependsOn` pointing at `gateway-api-crds` in `flux-system`, and image pull policy `IfNotPresent`.

#### Scenario: Release reconciles cleanly after make push

- **WHEN** `make push` is run from `lab-4/abox/` and at least 5 minutes pass
- **AND** `flux get helmreleases -n a2a-agent` is run
- **THEN** the `a2a-agent` HelmRelease MUST report `Ready: True`
- **AND** `kubectl get deploy -n a2a-agent` MUST show at least one Deployment with `READY` matching `desired` replicas

#### Scenario: HelmRelease uses an explicit tag, not latest

- **WHEN** `abox/releases/a2a-agent.yaml` is inspected
- **THEN** the chart source MUST set `ref.tag` to a concrete semver value
- **AND** no `ref.tag: latest` MUST appear anywhere in the file

### Requirement: Agent HTTPRoute SHALL route through agentgateway with a ReferenceGrant

The release SHALL include an `HTTPRoute` in the `a2a-agent` namespace targeting the `agentgateway-external` Gateway in `agentgateway-system` with path prefix `/a2a` (no rewrite), and a matching `ReferenceGrant` in `a2a-agent` permitting `HTTPRoute` → `Gateway` references from `agentgateway-system`.

#### Scenario: HTTPRoute is accepted by the gateway

- **WHEN** `kubectl get httproute -n a2a-agent a2a-agent -o yaml` is inspected
- **THEN** `status.parents[0].conditions` MUST include `Accepted: True` and `ResolvedRefs: True`

#### Scenario: ReferenceGrant authorises the cross-namespace reference

- **WHEN** `kubectl get referencegrant -n a2a-agent -o yaml` is inspected
- **THEN** at least one `ReferenceGrant` MUST permit `from: kind=HTTPRoute, namespace=agentgateway-system` to `to: kind=Gateway`
- **AND** no `Accepted: False` condition with reason `RefNotPermitted` MUST appear on the HTTPRoute status

### Requirement: Agent image SHALL be published to GHCR by a dedicated GitHub Actions workflow

The agent container image SHALL be published to GHCR at `ghcr.io/<repo>/lab-4/a2a-agent:<semver>` by a workflow file at `.github/workflows/a2a-agent-image-lab4.yaml`. The workflow SHALL mirror `.github/workflows/time-agent-image-lab3.yaml` — only the lab number and source path differ. The HelmRelease MUST reference this GHCR image with `imagePullPolicy: IfNotPresent`.

#### Scenario: Workflow file exists with the lab-4 triggers and paths

- **WHEN** `.github/workflows/a2a-agent-image-lab4.yaml` is inspected
- **THEN** its `name` MUST be `Build lab-4 a2a-agent image`
- **AND** `on.push.paths` MUST include `lab-4/agent/**` and `.github/workflows/a2a-agent-image-lab4.yaml`
- **AND** `on.push.tags` MUST include `lab-4-a2a-agent-*`
- **AND** `on` MUST also include `workflow_dispatch`

#### Scenario: Workflow publishes the image to a lab-scoped GHCR path

- **WHEN** the `docker/metadata-action` step is inspected
- **THEN** `images` MUST equal `ghcr.io/${{ github.repository }}/lab-4/a2a-agent`
- **AND** the `tags` rule MUST extract semver via `type=match,pattern=lab-4-a2a-agent-(\d+\.\d+\.\d+),group=1`

#### Scenario: Workflow builds multi-arch and only publishes on a release tag

- **WHEN** the `docker/build-push-action` step is inspected
- **THEN** `context` MUST equal `./lab-4/agent`
- **AND** `platforms` MUST include both `linux/amd64` and `linux/arm64`
- **AND** the `push` flag MUST be conditional on `startsWith(github.ref, 'refs/tags/lab-4-a2a-agent-')` so branch pushes and `workflow_dispatch` only build (no GHCR push)
- **AND** the GHCR login step MUST also be guarded by the same condition

#### Scenario: HelmRelease pulls from GHCR, not from a local image

- **WHEN** `abox/releases/a2a-agent.yaml` is inspected
- **THEN** `values.image.repository` MUST equal `ghcr.io/<repo>/lab-4/a2a-agent` (with the actual `<repo>` filled in)
- **AND** `values.image.tag` MUST match a semver published by a `lab-4-a2a-agent-<semver>` tag (no `latest`, no SHA-only references)
- **AND** `values.image.pullPolicy` MUST be `IfNotPresent`

#### Scenario: Pod starts by pulling from GHCR without auth errors

- **WHEN** after the abox reconciliation completes, `kubectl describe pod -n a2a-agent` is run
- **THEN** no event with reason `Failed` and message containing `ImagePullBackOff`, `ErrImagePull`, or `401 Unauthorized` MUST be present
- **AND** the container image reference MUST match `ghcr.io/<repo>/lab-4/a2a-agent:<tag>` where `<tag>` equals the value in the HelmRelease
