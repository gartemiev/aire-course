## ADDED Requirements

### Requirement: Inventory SHALL be deployed via Flux HelmRelease under abox/releases/

The agentregistry-inventory ("Inventory") application SHALL be deployed by adding `abox/releases/inventory.yaml` containing a `Namespace` resource (`agentregistry`) and a Flux `HelmRelease` referencing the upstream `agentregistry-inventory` Helm chart with an explicit `ref.tag`. The HelmRelease MUST follow abox conventions: `dependsOn` pointing at `gateway-api-crds` in `flux-system`, no `latest` tags anywhere in the file, and namespace defined in the same file.

#### Scenario: Inventory reconciles cleanly after make push

- **WHEN** `make push` is run from `lab-4/abox/` and at least 5 minutes pass
- **AND** `flux get helmreleases -n agentregistry` is run
- **THEN** the inventory HelmRelease MUST report `Ready: True`
- **AND** `kubectl get pods -n agentregistry` MUST show all pods in `Running` and `READY` matching `desired`

#### Scenario: HelmRelease pins an explicit chart version

- **WHEN** `abox/releases/inventory.yaml` is inspected
- **THEN** the chart source (`OCIRepository` or `GitRepository` / `HelmRepository`) MUST set `ref.tag` (or `ref.semver`) to a concrete value
- **AND** the inventory controller image tag MUST be set explicitly via HelmRelease values

### Requirement: Inventory HTTP API SHALL be reachable through agentgateway

The release SHALL include an `HTTPRoute` in `agentregistry` targeting the `agentgateway-external` Gateway in `agentgateway-system`, routing the Inventory HTTP service on port 8080 such that the public read-only API (`/v0/agents`, `/v0/servers`, `/v0/skills`) is reachable from outside the cluster on the gateway LoadBalancer IP. A matching `ReferenceGrant` in `agentregistry` MUST permit the cross-namespace gateway reference.

#### Scenario: AI resource list is retrievable through the gateway

- **WHEN** an operator runs `curl -fsS http://<gateway-ip>/inventory/v0/agents`
- **THEN** the HTTP response status MUST be 200
- **AND** the body MUST be a valid JSON array (possibly empty before any agents register)
- **AND** the same MUST hold for `curl -fsS http://<gateway-ip>/inventory/v0/servers` and `curl -fsS http://<gateway-ip>/inventory/v0/skills`

#### Scenario: The custom A2A agent appears in the inventory after both are deployed

- **WHEN** both this change's HelmReleases are `Ready: True` and Inventory's reconciliation loop has run at least once after the agent Pod became ready
- **AND** an operator runs `curl -fsS http://<gateway-ip>/inventory/v0/agents`
- **THEN** the response MUST contain at least one entry whose name or labels identify the scaffolded A2A agent

#### Scenario: HTTPRoute is accepted by the gateway

- **WHEN** `kubectl get httproute -n agentregistry inventory -o yaml` is inspected
- **THEN** `status.parents[0].conditions` MUST include `Accepted: True` and `ResolvedRefs: True`

### Requirement: Inventory MCP and metrics ports SHALL remain cluster-internal

The Inventory Pod exposes MCP on `:8083`, metrics on `:8081`, and health on `:8082`. Only the `:8080` HTTP service SHALL be routed through `agentgateway-external`. Ports `8081`, `8082`, and `8083` MUST NOT be exposed via any HTTPRoute introduced by this change.

#### Scenario: Only the HTTP API port is reachable externally

- **WHEN** the HTTPRoute(s) in `agentregistry` are inspected
- **THEN** every `backendRefs` entry MUST reference a Service port named or numbered `8080`
- **AND** no HTTPRoute backendRef in `agentregistry` MUST point at ports `8081`, `8082`, or `8083`

### Requirement: Inventory release SHALL coexist with kagent and agentgateway without conflicts

The Inventory deployment MUST NOT collide with existing abox releases on Namespace names, Service names, ClusterRole names, or webhook configurations.

#### Scenario: No release goes NotReady after inventory rolls out

- **WHEN** `flux get all -A` is run after the inventory HelmRelease reports `Ready: True`
- **THEN** every previously-Ready release (`agentgateway`, `kagent`, all entries in `releases/crds/`) MUST still report `Ready: True`
- **AND** no resource MUST be flagged with `Conflict` or `Stalled`
