# Lab 2: MCP / Agentic Infrastructure

## Beginners (Certificate Task)

1. Deploy **abox**: <https://github.com/den-vasyliev/abox>
2. Get access to the **Flux UI**, **Kagent UI**, and **agentgateway UI**.
3. Connect an LLM model, create a declarative **MCP tool server**, and create an agent in **Kagent**.

## Experienced

1. Complete the beginner tasks, but deploy the **MCP server** and **agent** using **GitOps**.

## Max Level

### Development

1. Complete the experienced tasks, but use a custom-built **MCP server**.
   - For example, you can build it using **KMCP**: <https://kagent.dev/docs/kmcp/quickstart>
2. Deploy it using **GitLessOps**.

## Research: Preparation for the MCP / A2A Session

1. Complete the course:  
   <https://anthropic.skilljar.com/model-context-protocol-advanced-topics>

---

## Solutions

The `abox/` directory here is a vendored, lightly customised copy of [den-vasyliev/abox](https://github.com/den-vasyliev/abox). To run it from your own fork of `aire-course`, two coordinates need to point at *your* GitHub account so the GitOps loop publishes and pulls from your own GHCR.

### One-time fork setup

1. **Repoint the OCI registry** in [abox/bootstrap/variables.tf](abox/bootstrap/variables.tf):

   ```hcl
   variable "oci_registry" {
     default = "oci://ghcr.io/<your-gh-user>/aire-course"
   }
   ```

2. **No edit needed** in [.github/workflows/flux-push.yaml](../.github/workflows/flux-push.yaml) — it already uses `${{ github.repository }}` to derive the OCI publish path, so it follows your fork automatically.

3. **Bootstrap order matters.** The cluster's `OCIRepository` polls for `releases:<tag>` artifacts in your GHCR. If no tag exists yet, reconciliation fails until one is published. Sequence:

   ```bash
   # commit + push the fork-specific edits
   git add lab-2/abox/bootstrap/variables.tf
   git commit -m "lab-2/abox: point at my GHCR"
   git push

   # tag — the workflow publishes the first OCI artifact
   git tag v0.1.0
   git push origin v0.1.0
   ```

4. **Make the GHCR package public** (one-time). The first publish creates a private package; the cluster pulls anonymously. Go to `https://github.com/users/<your-gh-user>?tab=packages` → click `aire-course/releases` → Package settings → "Change visibility" → **Public**.

5. **Bring the cluster up:**

   ```bash
   cd lab-2/abox
   make run
   ```

   `make run` (defined by [abox/Makefile](abox/Makefile)) installs OpenTofu and k9s, runs `tofu apply` to bring up the KinD cluster + Flux + the ResourceSet that reconciles your `releases/` artifact, and starts `cloud-provider-kind` so the gateway's LoadBalancer gets a real IP. The Flux UI is bundled with the Flux Operator — no extra install step needed.

### Iterating on the lab

Edit anything under [abox/releases/](abox/releases/) → commit → bump tag → push:

```bash
git tag v0.1.1   # bump patch
git push origin v0.1.1
```

The workflow republishes `releases:0.1.1`; Flux's `ResourceSetInputProvider` polls every 5 min, detects the new tag, and reconciles. To force immediate reconciliation:

```bash
kubectl annotate ocirepository releases -n flux-system \
  reconcile.fluxcd.io/requestedAt="$(date +%s)" --overwrite
```

---

## Step 2 — UI access (solutions)

### Flux UI — Flux Operator Status UI

abox installs the [controlplaneio-fluxcd Flux Operator](https://fluxcd.control-plane.io/) (see [abox/bootstrap/flux.tf](abox/bootstrap/flux.tf)), which ships a built-in Status UI on the `flux-operator` Service, port **9080**. No external dashboard install needed — just port-forward the existing Service:

```bash
kubectl --kubeconfig lab-2/abox/bootstrap/abox-config \
  port-forward -n flux-system svc/flux-operator 9080:9080
```

Open **http://localhost:9080** in your browser. The UI shows:

- **Cluster Info** — Kubernetes version, node count, Flux Operator + Distribution versions
- **Flux Components** — `helm-controller`, `kustomize-controller`, `notification-controller`, `source-controller` health & versions
- **Flux Reconcilers** — live counts of `FluxInstance`, `ResourceSet`, `Kustomization`, `HelmRelease` with running totals
- **Sources** — including `OCIRepository` (this lab's primary source type), plus `GitRepository`, `HelmRepository`, etc.

### Kagent UI - via the gateway

The lab's HTTPRoute ([abox/releases/kagent.yaml](abox/releases/kagent.yaml)) routes `/` on `agentgateway-external` to the `kagent-ui` Service. The architecturally correct way to access the Kagent UI is through the gateway's external IP - this exercises the agentgateway's declarative routing.

```bash
kubectl --kubeconfig lab-2/abox/bootstrap/abox-config \
  get svc -n agentgateway-system agentgateway-external
```

Open `http://<EXTERNAL-IP>/` (e.g. `http://172.19.0.5/`) in your browser.

If `EXTERNAL-IP` is `<pending>`, `cloud-provider-kind` isn't running. `make run` starts it; if it's been stopped, restart it manually:

```bash
nohup /tmp/cloud-provider-kind > /tmp/cloud-provider-kind.log 2>&1 &
disown
```

On macOS with Docker Desktop the Docker bridge subnet (`172.18.0.0/16` or `172.19.0.0/16`) isn't reachable from the host by default. If `http://<EXTERNAL-IP>/` won't load, fall back to port-forwarding the gateway Service:

```bash
kubectl port-forward -n agentgateway-system svc/agentgateway-external 8080:80
# then open http://localhost:8080
```

This still flows through the gateway data plane - only the last hop from your laptop changes.

### agentgateway UI - via Service

By default the agentgateway admin UI binds to `127.0.0.1:15000` inside the data-plane pod, so it can only be reached via `kubectl port-forward deployment/...`. This lab patches the data-plane config to bind on `0.0.0.0:15000` (via [abox/releases/agentgateway-ui.yaml](abox/releases/agentgateway-ui.yaml) - an `AgentgatewayParameters` resource attached to the Gateway through `infrastructure.parametersRef`) and exposes it as a ClusterIP Service `agentgateway-ui`.

```bash
kubectl --kubeconfig lab-2/abox/bootstrap/abox-config \
  port-forward -n agentgateway-system svc/agentgateway-ui 15000:15000
```

Open **http://localhost:15000/ui/** (trailing slash matters - the Next.js bundle assumes it).


# Research part

This was successfully accomplished: https://verify.skilljar.com/c/2wp2qpp4966d
