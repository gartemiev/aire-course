# Kubernetes-native equivalent of the standalone config.yaml.
# Routes are header-matched on x-provider:
#   x-provider: gemini  -> AgentgatewayBackend/gemini
#   x-provider: openai  -> AgentgatewayBackend/openai
#   (no header)         -> AgentgatewayBackend/openai (default fallback)
# All resources are gated on phase 2 (external_secrets_key_provisioned = true)
# because the AgentgatewayBackends reference the per-provider auth secrets.

locals {
  # One AgentgatewayBackend per LLM provider. Adding a new provider = adding a
  # map entry here plus a matching local.agentgateway_provider_secrets entry.
  # provider_key — name of the provider stanza inside spec.ai.groups[].providers[]
  #                (must match an agentgateway-supported provider, e.g. openai/gemini)
  agentgateway_providers = {
    openai = {
      provider_key = "openai"
      model        = var.agentgateway_openai_model
      secret_name  = var.agentgateway_openai_secret_name
    }
    gemini = {
      provider_key = "gemini"
      model        = var.agentgateway_gemini_model
      secret_name  = var.agentgateway_gemini_secret_name
    }
  }
}

# Gateway — provisions the agentgateway data plane proxy pod.
resource "kubectl_manifest" "agentgateway_gateway" {
  count = var.external_secrets_key_provisioned ? 1 : 0

  yaml_body = <<-YAML
    apiVersion: gateway.networking.k8s.io/v1
    kind: Gateway
    metadata:
      name: agentgateway-external
      namespace: ${kubernetes_namespace_v1.agentgateway.metadata[0].name}
    spec:
      gatewayClassName: agentgateway
      listeners:
      - name: http
        port: 80
        protocol: HTTP
        allowedRoutes:
          namespaces:
            from: All
  YAML

  server_side_apply = true
  wait              = true

  depends_on = [helm_release.agentgateway]
}

# AgentgatewayBackend — one per provider, API key pulled from the matching
# Kubernetes secret created by ESO from GCP Secret Manager.
resource "kubectl_manifest" "agentgateway_backend" {
  for_each = var.external_secrets_key_provisioned ? local.agentgateway_providers : {}

  yaml_body = <<-YAML
    apiVersion: agentgateway.dev/v1alpha1
    kind: AgentgatewayBackend
    metadata:
      name: ${each.key}
      namespace: ${kubernetes_namespace_v1.agentgateway.metadata[0].name}
    spec:
      ai:
        groups:
        - providers:
          - name: ${each.key}
            ${each.value.provider_key}:
              model: ${each.value.model}
            policies:
              auth:
                secretRef:
                  name: ${each.value.secret_name}
  YAML

  server_side_apply = true
  wait              = true

  depends_on = [
    helm_release.agentgateway,
    kubectl_manifest.agentgateway_provider_token,
  ]
}

# HTTPRoute — header-matched per provider, with openai as the default catch-all.
resource "kubectl_manifest" "agentgateway_route" {
  count = var.external_secrets_key_provisioned ? 1 : 0

  yaml_body = <<-YAML
    apiVersion: gateway.networking.k8s.io/v1
    kind: HTTPRoute
    metadata:
      name: llm-router
      namespace: ${kubernetes_namespace_v1.agentgateway.metadata[0].name}
    spec:
      parentRefs:
      - name: ${kubectl_manifest.agentgateway_gateway[0].name}
        namespace: ${kubernetes_namespace_v1.agentgateway.metadata[0].name}
        sectionName: http
      rules:
      - name: gemini
        matches:
        - path:
            type: PathPrefix
            value: /
          headers:
          - name: x-provider
            value: gemini
        backendRefs:
        - group: agentgateway.dev
          kind: AgentgatewayBackend
          name: ${kubectl_manifest.agentgateway_backend["gemini"].name}
          namespace: ${kubernetes_namespace_v1.agentgateway.metadata[0].name}
      - name: openai
        matches:
        - path:
            type: PathPrefix
            value: /
          headers:
          - name: x-provider
            value: openai
        backendRefs:
        - group: agentgateway.dev
          kind: AgentgatewayBackend
          name: ${kubectl_manifest.agentgateway_backend["openai"].name}
          namespace: ${kubernetes_namespace_v1.agentgateway.metadata[0].name}
      - name: openai-default
        backendRefs:
        - group: agentgateway.dev
          kind: AgentgatewayBackend
          name: ${kubectl_manifest.agentgateway_backend["openai"].name}
          namespace: ${kubernetes_namespace_v1.agentgateway.metadata[0].name}
  YAML

  server_side_apply = true
  wait              = true
}

# AgentgatewayPolicy — single CORS policy attached to the multi-rule HTTPRoute.
# The standalone config attaches identical CORS to every route, so one policy
# targeting the whole HTTPRoute is equivalent and shorter.
resource "kubectl_manifest" "agentgateway_policy_cors" {
  count = var.external_secrets_key_provisioned ? 1 : 0

  yaml_body = <<-YAML
    apiVersion: agentgateway.dev/v1alpha1
    kind: AgentgatewayPolicy
    metadata:
      name: llm-router-cors
      namespace: ${kubernetes_namespace_v1.agentgateway.metadata[0].name}
    spec:
      targetRefs:
      - group: gateway.networking.k8s.io
        kind: HTTPRoute
        name: ${kubectl_manifest.agentgateway_route[0].name}
      traffic:
        cors:
          allowOrigins: ["*"]
          allowHeaders: ["*"]
          allowMethods: ["GET", "POST", "OPTIONS"]
  YAML

  server_side_apply = true
  wait              = true
}
