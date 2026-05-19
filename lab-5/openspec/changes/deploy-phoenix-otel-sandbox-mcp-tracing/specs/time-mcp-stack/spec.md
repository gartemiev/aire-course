# time-mcp-stack

## ADDED Requirements

### Requirement: Lab-5 ships an independent copy of the lab-3 `time-mcp-server`

`lab-5/time-mcp-server/` SHALL contain a copy of the lab-3
`time-mcp-server` source tree, independently versioned, so changes to lab-5's
instrumentation cannot regress the lab-3 image.

#### Scenario: Source tree exists in lab-5

- **WHEN** any reviewer runs
  `ls lab-5/time-mcp-server`
- **THEN** the output SHALL include at minimum `Dockerfile`, `pyproject.toml`,
  `src/`, `tests/`, and `kmcp.yaml`

#### Scenario: Image path is lab-5-scoped

- **WHEN** `lab-5/abox/releases/time-mcp-server.yaml` is read
- **THEN** the `MCPServer.spec.deployment.image` SHALL match the regex
  `^ghcr\.io/[^/]+/aire-course/lab-5/time-mcp-server:\d+\.\d+\.\d+$`
- **AND** the image SHALL NOT reference any `lab-3/` path

### Requirement: Lab-5 ships an independent copy of the lab-3 `time-agent`

`lab-5/time-agent/` SHALL contain a copy of the lab-3 `time-agent`
source tree, independently versioned, with its kagent `Agent` manifest
pinning a lab-5 image tag.

#### Scenario: Source tree exists in lab-5

- **WHEN** any reviewer runs
  `ls lab-5/time-agent`
- **THEN** the output SHALL include at minimum `Dockerfile`, `pyproject.toml`,
  `app/`, and `tests/`

#### Scenario: Image path is lab-5-scoped

- **WHEN** `lab-5/abox/releases/time-agent.yaml` is read
- **THEN** the `Agent.spec.byo.deployment.image` SHALL match the regex
  `^ghcr\.io/[^/]+/aire-course/lab-5/time-agent:\d+\.\d+\.\d+$`
- **AND** the image SHALL NOT reference any `lab-3/` path

### Requirement: Both services bootstrap OpenInference tracing on startup

The MCP server and the agent SHALL initialise an OpenInference-aware OTel
tracer via `phoenix.otel.register(...)` before any request-handling code
starts.

#### Scenario: register() is called on the MCP server

- **WHEN** a reviewer runs
  `rg "phoenix\.otel.*register" lab-5/time-mcp-server/src/`
- **THEN** the output SHALL contain at least one match
- **AND** that call SHALL pass `auto_instrument=True`

#### Scenario: register() is called on the agent

- **WHEN** a reviewer runs
  `rg "phoenix\.otel.*register" lab-5/time-agent/app/`
- **THEN** the output SHALL contain at least one match
- **AND** that call SHALL pass `auto_instrument=True`

#### Scenario: openinference-instrumentation-mcp is on both classpaths

- **WHEN** `lab-5/time-mcp-server/pyproject.toml` and
  `lab-5/time-agent/pyproject.toml` are read
- **THEN** both files SHALL list `openinference-instrumentation-mcp` in their
  primary dependency block
- **AND** both files SHALL list `arize-phoenix-otel` in their primary
  dependency block

### Requirement: Tracing endpoint and project name come from environment variables

The MCP server and the agent SHALL read the OTLP endpoint and Phoenix project
name from environment variables; no hardcoded endpoint SHALL ship in the
image.

#### Scenario: Endpoint is env-configurable

- **WHEN** the bootstrap code is read
- **THEN** the endpoint passed to `register()` (or set via
  `OTEL_EXPORTER_OTLP_ENDPOINT`) SHALL be read from the environment, defaulting
  to a localhost value only when the env var is unset
- **AND** no string matching `phoenix\.observability\.svc\.cluster\.local`
  or `otel-collector\.observability\.svc\.cluster\.local` SHALL appear in the
  Python source

#### Scenario: In-cluster manifests inject the endpoint

- **WHEN** `lab-5/abox/releases/time-mcp-server.yaml` and
  `lab-5/abox/releases/time-agent.yaml` are read
- **THEN** both SHALL set `OTEL_EXPORTER_OTLP_ENDPOINT` to
  `http://otel-collector.observability.svc.cluster.local:4318`
- **AND** both SHALL set `OTEL_EXPORTER_OTLP_PROTOCOL` to `http/protobuf`
- **AND** both SHALL set `PHOENIX_PROJECT_NAME` to a distinct, descriptive
  value (e.g. `time-mcp-server` and `time-agent` respectively)

### Requirement: Each MCP tool emits a named OpenInference span

Every tool exposed by the time MCP server (`get_current_time`, `convert_time`, `echo` if retained) SHALL be wrapped so that one invocation produces at least one OpenInference span tagged with the tool's name.

#### Scenario: Spans appear in Phoenix with the expected names

- **GIVEN** the cluster is Ready and an integration test calls
  `tools/call` for `get_current_time` via the gateway
- **WHEN** the test queries the Phoenix HTTP API for the
  `time-mcp-server` project
- **THEN** within 30 seconds at least one span with name matching
  `(?i)MCP\.get_current_time` SHALL appear

### Requirement: A unified trace links the agent and the MCP server

A single MCP tool invocation initiated by the time-agent SHALL appear in
Phoenix as one trace containing spans from both the agent process and the
MCP server process, with a parent-child relationship.

#### Scenario: Client and server spans share a trace ID

- **GIVEN** the time-agent answers a question that requires a tool call
- **WHEN** Phoenix is queried for the resulting trace
- **THEN** the trace SHALL contain at least one span attributed to the
  `time-agent` project AND at least one span attributed to the
  `time-mcp-server` project
- **AND** those spans SHALL share the same `trace_id`

### Requirement: `releases/kustomization.yaml` includes the time stack

`lab-5/abox/releases/kustomization.yaml` SHALL list the new
`time-mcp-server.yaml` and `time-agent.yaml` resources so Flux reconciles
them with the rest of the bundle.

#### Scenario: Kustomization references both files

- **WHEN** `lab-5/abox/releases/kustomization.yaml` is read
- **THEN** the `resources:` list SHALL contain both `time-mcp-server.yaml`
  and `time-agent.yaml`
- **AND** the agentgateway MCP route (`agentgateway-mcp.yaml`) SHALL be
  updated so its `AgentgatewayBackend.spec.mcp.targets[]` references
  `time-mcp.kagent.svc.cluster.local:3000`, replacing or augmenting the
  existing DeepWiki target

### Requirement: Local and integration tests cover the trace pipeline

The lab-5 `time-mcp-server` and `time-agent` test suites SHALL include
checks that fail when tracing instrumentation is removed or misconfigured.

#### Scenario: Unit test asserts register() is called

- **WHEN** the operator runs
  `uv run pytest tests/unit -q` in `lab-5/time-mcp-server/` and
  `lab-5/time-agent/`
- **THEN** both suites SHALL pass on a machine with no cluster access
- **AND** both suites SHALL include at least one test that monkeypatches
  `phoenix.otel.register` and asserts the server's / agent's startup hook
  invoked it

#### Scenario: Integration test asserts spans land in Phoenix

- **GIVEN** the cluster is Ready and the gateway IP is exported as
  `GATEWAY_IP`
- **WHEN** the operator runs
  `uv run pytest tests/integration/test_phoenix_trace.py -q`
  in `lab-5/time-agent/`
- **THEN** the test SHALL drive a single question end-to-end through the
  agent → gateway → MCP server path
- **AND** the test SHALL assert via Phoenix's HTTP API that the resulting
  trace contains spans from both projects sharing a `trace_id`
