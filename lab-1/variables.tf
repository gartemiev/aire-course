variable "kubeconfig_path" {
  type        = string
  description = "Path to kubeconfig (Minikube uses the default location)."
  default     = "~/.kube/config"
}

variable "kube_context" {
  type        = string
  description = "kubectl context name (for minikube: minikube)."
  default     = "minikube"
}

variable "agentgateway_chart_version" {
  type        = string
  description = "Chart version for both agentgateway OCI charts (published on cr.agentgateway.dev)."
  default     = "v1.1.0"
}

variable "gateway_api_version" {
  type        = string
  description = "Kubernetes Gateway API version to install (docs specify v1.5.0)."
  default     = "v1.5.0"
}

variable "agentgateway_values_file" {
  type        = string
  description = "Path to agentgateway Helm values YAML, relative to this module directory unless absolute."
  default     = "helm-values/agentgateway/values.yaml"
}

# ##### agentgateway secrets #####
variable "agentgateway_openai_gcp_secret_name" {
  type        = string
  description = "Name of the OpenAI API key secret in GCP Secret Manager."
  default     = "aire_openai_token"
}

variable "agentgateway_openai_secret_name" {
  type        = string
  description = "Name of the Kubernetes Secret (and ExternalSecret) for the OpenAI key in agentgateway-system."
  default     = "aire-openai-token"
}

variable "agentgateway_gemini_gcp_secret_name" {
  type        = string
  description = "Name of the Gemini API key secret in GCP Secret Manager."
  default     = "aire-gemini-token"
}

variable "agentgateway_gemini_secret_name" {
  type        = string
  description = "Name of the Kubernetes Secret (and ExternalSecret) for the Gemini key in agentgateway-system."
  default     = "aire-gemini-token"
}

variable "agentgateway_secret_refresh_interval" {
  type        = string
  description = "How often ESO re-syncs provider API key secrets from GCP Secret Manager (e.g. 1h, 15m)."
  default     = "1h"
}

# ##### agentgateway models #####
variable "agentgateway_openai_model" {
  type        = string
  description = "OpenAI model to expose via the openai AgentgatewayBackend."
  default     = "gpt-4.1-nano"
}

variable "agentgateway_gemini_model" {
  type        = string
  description = "Gemini model to expose via the gemini AgentgatewayBackend."
  default     = "gemini-2.5-flash"
}

# ##### GCP #####
variable "gcp_project" {
  type        = string
  description = "GCP project ID used for Secret Manager and service accounts."
  default     = "heorhii-artemiev-test-project"
}

# ##### External Secrets Operator #####
variable "external_secrets_chart_version" {
  type        = string
  description = "External Secrets Operator chart version (oci://ghcr.io/external-secrets/charts/external-secrets)."
  default     = "2.4.1"
}

variable "external_secrets_values_file" {
  type        = string
  description = "Path to External Secrets Operator Helm values YAML, relative to this module directory unless absolute."
  default     = "helm-values/external-secrets/values.yaml"
}

variable "external_secrets_sa_name" {
  type        = string
  description = "Name of the GCP service account created for External Secrets Operator to access Secret Manager."
  default     = "external-secrets"
}

variable "external_secrets_cluster_store_name" {
  type        = string
  description = "Name of the ClusterSecretStore resource that proxies GCP Secret Manager cluster-wide."
  default     = "gcp-secrets-manager"
}

# The SA key JSON must be generated outside Terraform and passed in at apply time.
# Because ephemeral = true, Terraform never writes this value to state.
#
# Generate with:
#   gcloud iam service-accounts keys create /tmp/key.json \
#     --iam-account=external-secrets@<project>.iam.gserviceaccount.com
#   export TF_VAR_external_secrets_gcp_sa_key_json=$(cat /tmp/key.json)
variable "external_secrets_gcp_sa_key_json" {
  type        = string
  sensitive   = true
  ephemeral   = true
  default     = null
  description = <<-EOT
    GCP service account JSON key for External Secrets Operator.
    Ephemeral — never written to state.

    Leave unset on the first apply (SA is created then).
    After the SA exists, generate the key and pass it on the second apply:

      gcloud iam service-accounts keys create /tmp/key.json \
        --iam-account=external-secrets@<project>.iam.gserviceaccount.com
      export TF_VAR_external_secrets_gcp_sa_key_json=$(cat /tmp/key.json)
      terraform apply
      rm /tmp/key.json
  EOT
}

# Set to true on the second apply (after the SA key has been generated with gcloud)
# to create the Kubernetes secret and ClusterSecretStore.
variable "external_secrets_key_provisioned" {
  type        = bool
  description = "Set to true once the GCP SA key has been generated and is being passed via external_secrets_gcp_sa_key_json."
  default     = true
}

# Increment this number when rotating the SA key to force Terraform to re-push data_wo.
variable "external_secrets_gcp_key_revision" {
  type        = number
  description = "Revision counter for the GCP SA key Kubernetes secret. Increment to trigger a key rotation."
  default     = 2
}
