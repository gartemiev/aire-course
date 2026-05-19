# lab5-release-pipeline

## ADDED Requirements

### Requirement: A lab-5 `time-mcp-server` image workflow exists

A GitHub Actions workflow SHALL build and publish the lab-5 `time-mcp-server`
image to GHCR, mirroring the lab-3 workflow contract.

#### Scenario: Workflow file exists with the expected shape

- **WHEN** any reviewer inspects
  `.github/workflows/time-mcp-image-lab5.yaml`
- **THEN** the file SHALL exist
- **AND** its `on.push.paths` SHALL include `lab-5/time-mcp-server/**`
  and `.github/workflows/time-mcp-image-lab5.yaml`
- **AND** its `on.push.tags` SHALL include `lab-5-time-mcp-*`
- **AND** its `docker/metadata-action` step SHALL set `images:` to
  `ghcr.io/${{ github.repository }}/lab-5/time-mcp-server`
- **AND** its tag match pattern SHALL be `lab-5-time-mcp-(\d+\.\d+\.\d+)`
- **AND** `docker/build-push-action` SHALL be configured with
  `platforms: linux/amd64,linux/arm64`

#### Scenario: Branch pushes build only; tag pushes publish

- **WHEN** the workflow runs on `push` to `main` touching
  `lab-5/time-mcp-server/**`
- **THEN** the `docker/login-action` step SHALL be skipped (its `if:`
  predicate gates on the `lab-5-time-mcp-` tag prefix)
- **AND** `docker/build-push-action.push` SHALL evaluate to `false`

- **WHEN** the workflow runs on `push` of tag `lab-5-time-mcp-0.1.0`
- **THEN** `docker/login-action` SHALL run
- **AND** `docker/build-push-action.push` SHALL evaluate to `true`
- **AND** the resulting image
  `ghcr.io/<owner>/aire-course/lab-5/time-mcp-server:0.1.0` SHALL be pullable
  by KinD nodes

### Requirement: A lab-5 `time-agent` image workflow exists

A GitHub Actions workflow SHALL build and publish the lab-5 `time-agent`
image to GHCR, mirroring the lab-3 workflow contract.

#### Scenario: Workflow file exists with the expected shape

- **WHEN** any reviewer inspects
  `.github/workflows/time-agent-image-lab5.yaml`
- **THEN** the file SHALL exist
- **AND** its `on.push.paths` SHALL include `lab-5/time-agent/**` and
  `.github/workflows/time-agent-image-lab5.yaml`
- **AND** its `on.push.tags` SHALL include `lab-5-time-agent-*`
- **AND** its `docker/metadata-action` step SHALL set `images:` to
  `ghcr.io/${{ github.repository }}/lab-5/time-agent`
- **AND** its tag match pattern SHALL be `lab-5-time-agent-(\d+\.\d+\.\d+)`
- **AND** `docker/build-push-action.build-args` SHALL forward
  `COMMIT_SHA=${{ github.sha }}` and `AGENT_VERSION=${{ github.ref_name }}`
- **AND** `docker/build-push-action.platforms` SHALL be
  `linux/amd64,linux/arm64`

### Requirement: Workflows do not collide with other labs

The lab-5 workflows SHALL use distinct tag prefixes, paths, and image
registries so they cannot trigger from lab-3 or lab-4 changes and cannot
publish to lab-3 or lab-4 image namespaces.

#### Scenario: Tag prefixes and paths are unique to lab-5

- **WHEN** all `.github/workflows/*.yaml` files are inspected
- **THEN** only `time-mcp-image-lab5.yaml` and
  `time-agent-image-lab5.yaml` SHALL include `lab-5-time-*` tag patterns
- **AND** no other workflow SHALL include
  `lab-5/time-mcp-server/**` or `lab-5/time-agent/**` under its
  `paths` filter

#### Scenario: Image registries do not overlap with prior labs

- **WHEN** the metadata `images:` lines from
  `time-mcp-image-lab3.yaml`, `time-agent-image-lab3.yaml`,
  `time-mcp-image-lab5.yaml`, `time-agent-image-lab5.yaml` are diffed
- **THEN** the four `images:` values SHALL each differ by the lab segment
  (`lab-3/` vs `lab-5/`)
- **AND** no two workflows SHALL share an image path

### Requirement: The bundle OCI artifact workflow remains untouched

This change SHALL NOT modify `.github/workflows/flux-push-lab5.yaml`; the existing workflow that publishes `releases-lab5:<tag>` from `./lab-5/abox/releases` on `lab5-v*` tags MUST stay byte-for-byte identical.

#### Scenario: flux-push-lab5.yaml is unchanged by this change

- **WHEN** the change is applied
- **THEN** `.github/workflows/flux-push-lab5.yaml` SHALL match its
  pre-change contents byte-for-byte
