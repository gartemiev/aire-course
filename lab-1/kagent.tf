locals {
  kagent_values_yaml = file(
    startswith(var.kagent_values_file, "/") ? var.kagent_values_file : "${path.module}/${var.kagent_values_file}"
  )
}

# Namespace created explicitly so it can be referenced by both the Helm
# releases and the ExternalSecret without coupling them together.
resource "kubernetes_namespace_v1" "kagent" {
  metadata {
    name = "kagent"
    labels = {
      "app.kubernetes.io/managed-by" = "terraform"
    }
  }
}

# Step 1 (docs): Install kagent CRDs.
# Reference: https://kagent.dev/docs/kagent/introduction/installation
resource "helm_release" "kagent_crds" {
  name             = "kagent-crds"
  chart            = "oci://ghcr.io/kagent-dev/kagent/helm/kagent-crds"
  version          = var.kagent_chart_version
  namespace        = kubernetes_namespace_v1.kagent.metadata[0].name
  create_namespace = false

  wait = true
}

# Step 2 (docs): Install kagent control plane (controller, UI, bundled
# Postgres, agent CRs, MCP tools). Values are read from helm-values/kagent.
resource "helm_release" "kagent" {
  name             = "kagent"
  chart            = "oci://ghcr.io/kagent-dev/kagent/helm/kagent"
  version          = var.kagent_chart_version
  namespace        = kubernetes_namespace_v1.kagent.metadata[0].name
  create_namespace = false

  values = [local.kagent_values_yaml]

  # Bumped from the provider default to give the bundled Postgres + every
  # built-in agent enough time to pull images and pass health checks on a
  # cold minikube.
  timeout = 900
  wait    = true

  depends_on = [helm_release.kagent_crds]
}

resource "kubectl_manifest" "kagent_gemini_model_config" {
  yaml_body = <<-YAML
    apiVersion: kagent.dev/v1alpha2
    kind: ModelConfig
    metadata:
      name: kagent-gemini-model-config
      namespace: ${kubernetes_namespace_v1.kagent.metadata[0].name}
    spec:
      provider: OpenAI # BaseURL exists for OpenAI, SAPAICore, and partially other providers - but Gemini was deliberately left as an empty struct.
      model: gemini-2.5-flash
      apiKeySecret: ${kubernetes_secret_v1.kagent_provider_placeholder["gemini"].metadata[0].name}
      apiKeySecretKey: ${var.kagent_gemini_secret_key}
      defaultHeaders:
        x-provider: gemini
      openAI: # BaseURL exists for OpenAI, SAPAICore, and partially other providers - but Gemini was deliberately left as an empty struct.
        baseUrl: http://agentgateway-external.agentgateway-system.svc.cluster.local/v1
  YAML
  depends_on = [
    helm_release.kagent,
  ]
}
