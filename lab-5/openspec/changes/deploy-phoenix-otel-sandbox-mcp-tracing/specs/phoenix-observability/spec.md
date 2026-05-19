# phoenix-observability

## ADDED Requirements

### Requirement: Phoenix is deployed via Flux into the `observability` namespace

The cluster SHALL run Arize Phoenix as a Flux-managed `HelmRelease` sourced
from `oci://registry-1.docker.io/arizephoenix/phoenix-helm` at a pinned chart
version, in a dedicated `observability` namespace, with persistent storage
backed by the cluster's default StorageClass.

#### Scenario: Phoenix HelmRelease reconciles successfully on fresh cluster

- **WHEN** the operator runs `make run` from `lab-5/abox/` against a clean
  KinD cluster
- **THEN** `flux get helmreleases -n observability` SHALL show `phoenix` with
  `Ready=True`
- **AND** `kubectl -n observability get pods -l app.kubernetes.io/name=phoenix`
  SHALL show one pod in `Running` state with all containers ready
- **AND** `kubectl -n observability get pvc` SHALL show a Bound PVC for the
  bundled Postgres

#### Scenario: Phoenix chart version is pinned, not floating

- **WHEN** any reviewer inspects `lab-5/abox/releases/phoenix.yaml`
- **THEN** the `HelmRelease.spec.chartRef.tag` (or equivalent
  `OCIRepository.spec.ref.tag`) SHALL be a concrete semver string (e.g.
  `0.1.13`), not `latest`, `main`, or unset

#### Scenario: Phoenix retains traces across pod restarts

- **GIVEN** at least one trace has been ingested by Phoenix
- **WHEN** the Phoenix pod is deleted and recreated by Kubernetes
- **THEN** the previously ingested trace SHALL still be visible in the UI
  after the new pod becomes Ready

### Requirement: Phoenix exposes an OTLP/HTTP ingestion endpoint in-cluster

Phoenix SHALL accept OTLP/HTTP trace data on its in-cluster Service so any
namespace can write traces without traversing the gateway.

#### Scenario: ClusterIP Service is reachable on the documented port

- **WHEN** any pod runs `curl -sS -o /dev/null -w "%{http_code}" -X POST
  http://phoenix-svc.observability.svc.cluster.local:6006/v1/traces -H "Content-Type:
  application/x-protobuf" --data-binary @/dev/null`
- **THEN** the response status SHALL be `200` or `400` (proto parse error),
  never a connection error such as `Connection refused`

### Requirement: Phoenix UI is reachable through the existing gateway

The Phoenix UI SHALL be exposed at the `/phoenix` path on the
`agentgateway-external` Gateway so the operator can open it from the cluster's
LoadBalancer IP without port-forwarding.

#### Scenario: HTTPRoute and ReferenceGrant resolve

- **WHEN** `kubectl get httproute phoenix -n observability -o
  jsonpath='{.status.parents[0].conditions[?(@.type=="ResolvedRefs")].status}'`
  is queried
- **THEN** the result SHALL be `True`
- **AND** `kubectl get referencegrant -n observability` SHALL list a grant
  permitting the HTTPRoute in `agentgateway-system` to reference the Phoenix
  Service

#### Scenario: UI loads from gateway IP

- **GIVEN** the gateway LoadBalancer IP from
  `kubectl -n agentgateway-system get svc agentgateway-external -o
  jsonpath='{.status.loadBalancer.ingress[0].ip}'`
- **WHEN** the operator opens `http://<IP>/phoenix/` in a browser
- **THEN** the Phoenix UI SHALL render
- **AND** the projects list SHALL be visible (empty on a brand-new cluster)

### Requirement: An OpenTelemetry Collector fronts Phoenix

The cluster SHALL run an OpenTelemetry Collector deployed via the upstream Helm chart in the same `observability` namespace; the collector MUST accept OTLP traces and metrics from any in-cluster client, forward traces to Phoenix, and route metrics to the `debug` exporter.

#### Scenario: OTel collector ports respond

- **WHEN** any pod runs
  `nc -vz otel-collector.observability.svc.cluster.local 4318` and
  `nc -vz otel-collector.observability.svc.cluster.local 4317`
- **THEN** both TCP connections SHALL succeed

#### Scenario: OTel collector forwards traces to Phoenix

- **GIVEN** the collector is Ready and Phoenix is Ready
- **WHEN** a test client posts an OTLP/HTTP payload containing a single span
  named `test-span` to
  `http://otel-collector.observability.svc.cluster.local:4318/v1/traces`
- **THEN** within 30 seconds the Phoenix API
  (`GET /v1/projects/<project>/spans`) SHALL return that span

#### Scenario: Collector configuration is pinned and reviewable

- **WHEN** `lab-5/abox/releases/otel-collector.yaml` is read
- **THEN** the Helm chart version SHALL be a concrete semver string
- **AND** the `config.exporters.otlphttp/phoenix.endpoint` value SHALL equal
  `http://phoenix-svc.observability.svc.cluster.local:6006`
- **AND** the `config.service.pipelines.traces.exporters` list SHALL include
  `otlphttp/phoenix`

### Requirement: Observability components are reconcile-ordered after CRDs

The Phoenix and OTel collector HelmReleases SHALL not start until the
`releases-crds` Kustomization is Ready, so dependent CRDs (Gateway API,
agentgateway) exist before any HTTPRoute or AgentgatewayBackend is applied.

#### Scenario: CRD-before-app ordering is preserved

- **WHEN** a reviewer reads `lab-5/abox/releases/kustomization.yaml` and
  `lab-5/abox/bootstrap/flux.tf`
- **THEN** the `releases` Kustomization SHALL still declare
  `dependsOn: [{ name: releases-crds }]`
- **AND** the Phoenix and OTel collector HelmReleases SHALL live under
  `releases/`, not `releases/crds/`
