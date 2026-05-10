# Lab 1: Deploying Basic Agentic Infrastructure

## Beginner

1. Install `agentgateway` locally: https://agentgateway.dev/docs/standalone/latest/deployment/binary/

2. Choose an LLM provider: https://agentgateway.dev/docs/standalone/latest/llm/providers/

3. Configure `config.yaml`: https://agentgateway.dev/docs/standalone/latest/tutorials/llm-gateway/

4. Start the gateway and access the UI: http://localhost:15000/ui/

5. Verify access to the LLM and explore the fundamental capabilities of **Backends** and **Policy**.

## Experienced

1. Complete the Beginner tasks, but deploy `agentgateway` as a Helm deployment in a Kubernetes cluster.

2. Configure Kubernetes `Secrets` and `ConfigMaps` for API keys and configuration.

3. Deploy `kagent`: https://kagent.dev/docs/kagent/getting-started/quickstart

4. Configure model routing through `agentgateway`.

5. Verify that any built-in agent is working correctly.

## Max

1. Complete the Experienced tasks, but use Gateway API: https://agentgateway.dev/docs/kubernetes/main/about/gateway-api/

### Research 1: Review the S&T ADR Project — DevOps Bot/Agent

Review and evaluate the ADR for the **S&T: DevOps Bot/Agent** project.

1. Prepare your questions about the project.
2. Suggest possible improvements.
3. Propose potential solutions.

##########################################################################

## Usage

### Prerequisites

| Tool | Purpose | Install |
|------|---------|---------|
| `minikube` | Local Kubernetes cluster | https://minikube.sigs.k8s.io/docs/start/ |
| `kubectl` | Kubernetes CLI | https://kubernetes.io/docs/tasks/tools/ |
| `helm` | Helm CLI (chart pulls) | https://helm.sh/docs/intro/install/ |
| `terraform14` / `terraform` ≥ 1.10 | Infrastructure provisioning | https://developer.hashicorp.com/terraform/install |
| `gcloud` | GCP CLI (SA key generation) | https://cloud.google.com/sdk/docs/install |

GCP access requirements:
- A GCP project (`heorhii-artemiev-test-project`) with Secret Manager API enabled
- A GCS bucket (`tf-state-aire`) for Terraform remote state
- Permissions to create service accounts and IAM bindings in the project
- The OpenAI API key must be created manually in GCP Secret Manager before provisioning:

```bash
# Create the secret (one-time, not managed by Terraform)
echo -n "YOUR_OPENAI_KEY" | gcloud secrets create aire_openai_token \
  --data-file=- \
  --project=heorhii-artemiev-test-project
  
echo -n "YOUR_GEMINI_KEY" | gcloud secrets create aire-gemini-token \
  --data-file=- \
  --project=heorhii-artemiev-test-project  

# To update an existing secrets versions:
echo -n "YOUR_NEW_KEY" | gcloud secrets versions add aire_openai_token \
  --data-file=- \
  --project=heorhii-artemiev-test-project
 
echo -n "YOUR_NEW_KEY" | gcloud secrets versions add aire-gemini-token \
  --data-file=- \
  --project=heorhii-artemiev-test-project 
```

##########################################################################

### Provision — Phase 1 (cluster + operator)

```bash
# Start the local cluster
minikube start

# Authenticate to GCP
gcloud auth application-default login

# Initialise Terraform (pulls providers, connects to GCS backend)
terraform init

# Deploy: Gateway API CRDs, agentgateway, External Secrets Operator, GCP SA + IAM
terraform apply
```

Phase 1 creates everything except the Kubernetes secret holding the GCP SA key.

##########################################################################

### Provision — Phase 2 (secrets + routing)

```bash
# Generate a service account key for the newly created SA
gcloud iam service-accounts keys create /tmp/key.json \
  --iam-account=external-secrets@heorhii-artemiev-test-project.iam.gserviceaccount.com

# Pass the key as an ephemeral variable (never written to state)
export TF_VAR_external_secrets_gcp_sa_key_json=$(cat /tmp/key.json)

# Flip the phase 2 gate in variables.tf:
# change default = false → default = true for external_secrets_key_provisioned

# Deploy: k8s SA key secret, ClusterSecretStore, ExternalSecret, Gateway, HTTPRoute, Backend, Policy
terraform apply

# Remove the local key file
rm /tmp/key.json
```

Phase 2 completes the setup. The `aire-openai-token` and `aire-gemini-token` secret is synced from GCP Secret Manager
into `agentgateway-system` and the OpenAI with Gemini routes become active.

##########################################################################

### Verify

```bash
# Port-forward the gateway
kubectl port-forward -n agentgateway-system svc/agentgateway-external 8080:80

# Test the OpenAI route
curl -s http://127.0.0.1:8080/v1/chat/completions \
  -H "Content-Type: application/json" -H "x-provider: openai" 
  -d '{"model": "gpt-4.1-nano", "messages": [{"role": "user", "content": "Can you give me the definition of K8S?"}]}' \
  | python3 -c "import json,sys; print(json.load(sys.stdin)['choices'][0]['message']['content'])"

# Test the Gemini route
curl -s http://127.0.0.1:8080/v1/chat/completions \ 
  -H "Content-Type: application/json" -H "x-provider: gemini" 
  -d '{"model": "gemini-2.5-flash", "messages": [{"role": "user", "content": "What is the capital of Romania?"}]}' \
  | python3 -c "import json,sys; print(json.load(sys.stdin)['choices'][0]['message']['content'])"

# Access the agentgateway admin UI
kubectl port-forward -n agentgateway-system deploy/agentgateway-external 15000:15000
# Open: http://localhost:15000/ui/
```

##########################################################################

### Verify — kagent through agentgateway

The default kagent `ModelConfig` is pointed at the agentgateway service, so
every built-in agent (k8s-agent, helm-agent, istio-agent, etc.) routes its
LLM calls through `agentgateway-external` (LLM data plane, port 80,
agentgateway-system namespace).

The kagent UI is exposed via a *separate* Gateway, `kagent-ui-gateway`, in
the kagent namespace. Splitting LLM and UI traffic onto two Gateways means
no listener conflicts, no cross-namespace ReferenceGrants, and an LLM-side
restart cannot affect UI access.

```bash
# 1. Confirm the default ModelConfig is wired to agentgateway
kubectl get modelconfig -n kagent default-model-config -o jsonpath='{.spec.openAI.baseUrl}{"\n"}'
# Expected: http://agentgateway-external.agentgateway-system.svc.cluster.local/v1

# 2. Reach the kagent UI through its dedicated Gateway proxy
kubectl port-forward -n kagent svc/kagent-ui-gateway 8081:80
# Open: http://127.0.0.1:8081/

# 3. Confirm the call traversed agentgateway (every built-in agent invocation
#    shows up here as an OpenAI request even though kagent never talked to
#    api.openai.com directly).
kubectl logs -n agentgateway-system deploy/agentgateway-external -f
```

##########################################################################

### Key rotation

Increment `external_secrets_gcp_key_revision` in `variables.tf` (default value), then re-run Phase 2:

```bash
gcloud iam service-accounts keys create /tmp/key.json \
  --iam-account=external-secrets@heorhii-artemiev-test-project.iam.gserviceaccount.com

export TF_VAR_external_secrets_gcp_sa_key_json=$(cat /tmp/key.json)
terraform apply
rm /tmp/key.json
```

##########################################################################

### Destroy

```bash
terraform destroy
```

> After destroy, the GCP service account is deleted. A fresh Phase 2 key generation is
> required on the next provision — never reuse a key file from a previous run.
