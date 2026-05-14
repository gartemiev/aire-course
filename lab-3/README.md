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