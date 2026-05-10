locals {
  # Per-provider placeholder secret descriptors. Adding a new provider here is
  # all it takes to materialize one more `kagent-<provider>` Secret in the
  # kagent namespace.
  #
  # secret_name      — name of the Kubernetes Secret (and the value referenced
  #                    by providers.<provider>.apiKeySecretRef in values.yaml)
  # secret_key       — key inside the Secret holding the placeholder token
  #                    (must match providers.<provider>.apiKeySecretKey)
  # placeholder_note — short string written into the Secret as the value, kept
  #                    visibly fake so anyone running `kubectl get secret -o
  #                    yaml` sees that the trust boundary lives elsewhere
  kagent_placeholder_secrets = {
    openai = {
      secret_name      = var.kagent_openai_secret_name
      secret_key       = var.kagent_openai_secret_key
      placeholder_note = "sk-placeholder-routed-via-agentgateway-openai"
    }
    gemini = {
      secret_name      = var.kagent_gemini_secret_name
      secret_key       = var.kagent_gemini_secret_key
      placeholder_note = "sk-placeholder-routed-via-agentgateway-gemini"
    }
  }
}

# Placeholder provider API keys for kagent.
#
# Why these are fake on purpose:
#   kagent's LLM traffic is routed through agentgateway (see
#   helm-values/kagent/values.yaml -> providers.<name>.config.baseUrl). The
#   agentgateway AgentgatewayBackends overwrite the Authorization header on
#   every request with the *real* keys from `aire-openai-token` /
#   `aire-gemini-token` in the agentgateway-system namespace, so whatever value
#   kagent's OpenAI SDK sends is dropped on the floor.
#
# Why the secrets have to exist at all:
#   The OpenAI SDK inside the kagent agent runtime refuses to dispatch a
#   request when the API key env var is empty. The ModelConfig CRD also
#   requires apiKeySecretKey when apiKeySecret is set. So we need a non-empty
#   value, but it can be anything — keeping it visibly fake makes it obvious
#   to anyone reading `kubectl get secret -o yaml` that the trust boundary
#   for the real keys has moved to agentgateway.
#
# What this replaces:
#   The previous version of this file pulled the OpenAI key from GCP Secret
#   Manager into the kagent namespace via an ExternalSecret. That sync was
#   wasted work — the value was overwritten by agentgateway before leaving
#   the cluster — and it created a redundant IAM dependency from the kagent
#   namespace to GCP Secret Manager.
resource "kubernetes_secret_v1" "kagent_provider_placeholder" {
  for_each = local.kagent_placeholder_secrets

  metadata {
    name      = each.value.secret_name
    namespace = kubernetes_namespace_v1.kagent.metadata[0].name
    labels = {
      "app.kubernetes.io/managed-by" = "terraform"
    }
    annotations = {
      "kagent.aire/purpose" = "Placeholder — real ${each.key} key lives in agentgateway-system"
    }
  }

  data = {
    (each.value.secret_key) = each.value.placeholder_note
  }

  type = "Opaque"
}
