# agent-sandbox-platform

## ADDED Requirements

### Requirement: Agent Sandbox CRDs are reconciled through `releases/crds/`

The cluster SHALL install the Agent Sandbox CRDs
(`agents.x-k8s.io_sandboxes.yaml` and the extension CRDs for
`SandboxTemplate`, `SandboxClaim`, `SandboxWarmPool`) via the
`releases-crds` Flux Kustomization, pinned to an explicit upstream release
version.

#### Scenario: All Sandbox CRDs are Established

- **WHEN** `kubectl get crd | grep -E 'sandboxes|sandboxtemplates|sandboxclaims|sandboxwarmpools'`
  is run after `make run`
- **THEN** the list SHALL contain at minimum:
  - `sandboxes.agents.x-k8s.io`
  - `sandboxtemplates.agents.x-k8s.io`
  - `sandboxclaims.agents.x-k8s.io`
  - `sandboxwarmpools.agents.x-k8s.io`
- **AND** each SHALL report
  `Established=True` in `kubectl get crd <name> -o jsonpath='{.status.conditions[?(@.type=="Established")].status}'`

#### Scenario: CRD version is pinned in the vendored manifest

- **WHEN** any reviewer reads
  `lab-5/abox/releases/crds/agent-sandbox-crds.yaml`
- **THEN** a top-of-file comment SHALL record the upstream release tag
  (e.g. `# Source: https://github.com/kubernetes-sigs/agent-sandbox/releases/tag/v0.7.0`)
- **AND** the file SHALL be vendored as-is from that release, not generated
  on the fly at reconcile time

### Requirement: Agent Sandbox controller is Flux-managed in its own namespace

The Agent Sandbox controller and its extensions SHALL be deployed by a Flux
`Kustomization` (vendored YAML from the upstream `manifest.yaml` and
`extensions.yaml`) into the `agent-sandbox-system` namespace.

#### Scenario: Controller becomes Ready

- **WHEN** `make run` completes
- **THEN** `kubectl -n agent-sandbox-system get deploy` SHALL list the Agent
  Sandbox controller deployment with `READY` equal to `desired`
- **AND** `kubectl -n agent-sandbox-system get pods` SHALL show all pods in
  `Running` state with no `CrashLoopBackOff`

#### Scenario: No manual `kubectl apply` is required after the first run

- **GIVEN** the cluster is Ready
- **WHEN** the operator runs the lab-5 quickstart from `lab-5/README.md`
- **THEN** the quickstart SHALL NOT instruct the operator to run
  `kubectl apply -f https://github.com/kubernetes-sigs/agent-sandbox/releases/...`
- **AND** the quickstart SHALL only document a one-time
  `kubectl delete -f .../manifest.yaml && kubectl delete -f .../extensions.yaml`
  cleanup of any pre-existing hand-installed controller

### Requirement: A baseline `SandboxTemplate` is available for the metrics walkthrough

The cluster SHALL ship a `SandboxTemplate` named `python-sandbox-template`
ready to back the upstream metrics walkthrough so the operator can run the
Python script in `https://agent-sandbox.sigs.k8s.io/docs/sandbox/metrics/`
without authoring their own template.

#### Scenario: Template applies and validates

- **WHEN** `kubectl get sandboxtemplate python-sandbox-template -o yaml` is
  run
- **THEN** the resource SHALL exist
- **AND** its `spec.podTemplate.spec.containers[0].image` SHALL be the
  upstream `python-runtime-sandbox` image (which bakes in the HTTP
  `/execute` agent the SDK talks to on port 8888) pinned to a concrete
  dated tag, with `imagePullPolicy: IfNotPresent`

#### Scenario: A SandboxClaim from the template becomes Ready

- **GIVEN** the controller and the template are reconciled
- **WHEN** the operator applies a `SandboxClaim` referencing
  `python-sandbox-template`
- **THEN** within 60 seconds the corresponding `Sandbox` resource SHALL
  reach `Ready=True`
- **AND** `kubectl exec -n default <sandbox-pod> -- echo ok` SHALL print
  `ok` and exit 0

### Requirement: Sandbox metrics walkthrough runs end-to-end

The lab-5 README SHALL document an executable form of the upstream metrics
walkthrough and the script SHALL produce both `resource_metrics` and `Span`
output when run from inside the cluster against the shipped
`python-sandbox-template`.

#### Scenario: opentelemetry-instrument prints spans

- **GIVEN** the Python virtualenv described in
  `https://agent-sandbox.sigs.k8s.io/docs/sandbox/metrics/`
  (`pip install "k8s-agent-sandbox[tracing]" opentelemetry-distro` and
  `opentelemetry-bootstrap -a install`)
- **WHEN** the operator runs
  `OTEL_TRACES_EXPORTER=console OTEL_METRICS_EXPORTER=console opentelemetry-instrument python main.py`
  where `main.py` is the script from the upstream docs pointing at the
  shipped `python-sandbox-template`
- **THEN** stdout SHALL contain at least one JSON `Span` object whose
  `attributes."http.url"` matches the sandbox tunnel URL
- **AND** stdout SHALL contain `resource_metrics` from
  `opentelemetry.instrumentation.requests`

#### Scenario: Walkthrough is repeatable from the lab README

- **WHEN** any reviewer reads `lab-5/README.md` Solutions for the
  Experienced track
- **THEN** the README SHALL link to the metrics walkthrough and document
  the exact commands required to reproduce it against this cluster
