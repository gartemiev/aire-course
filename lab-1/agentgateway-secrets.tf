locals {
  # One entry per provider whose API key we want pulled from GCP Secret Manager.
  # k8s_secret_name      — name of the Secret (and ExternalSecret) in agentgateway-system
  # gcp_secret_name      — name of the secret stored in GCP Secret Manager
  # k8s_secret_data_key  — secret key consumed by AgentgatewayBackend.spec.*.policies.auth.secretRef
  # k8s_secret_value_tpl — Go template (ESO) building the value for k8s_secret_data_key
  agentgateway_provider_secrets = {
    openai = {
      k8s_secret_name      = var.agentgateway_openai_secret_name
      gcp_secret_name      = var.agentgateway_openai_gcp_secret_name
      k8s_secret_data_key  = "Authorization"
      k8s_secret_value_tpl = "Bearer {{ .api_key }}"
    }
    gemini = {
      k8s_secret_name      = var.agentgateway_gemini_secret_name
      gcp_secret_name      = var.agentgateway_gemini_gcp_secret_name
      k8s_secret_data_key  = "Authorization"
      k8s_secret_value_tpl = "Bearer {{ .api_key }}"
    }
  }
}

# ExternalSecret per provider — each pulls the matching key from GCP Secret
# Manager via the cluster-wide ClusterSecretStore and surfaces it as a native
# Kubernetes Secret inside the agentgateway-system namespace, using the data
# shape that AgentgatewayBackend expects (Authorization: Bearer <key>).
resource "kubectl_manifest" "agentgateway_provider_token" {
  # Gate on phase 2: ClusterSecretStore must exist before the ExternalSecret is
  # created, otherwise ESO enters a backoff loop that persists even after the
  # store becomes available.
  for_each = var.external_secrets_key_provisioned ? local.agentgateway_provider_secrets : {}

  yaml_body = <<-YAML
    apiVersion: external-secrets.io/v1
    kind: ExternalSecret
    metadata:
      name: ${each.value.k8s_secret_name}
      namespace: ${kubernetes_namespace_v1.agentgateway.metadata[0].name}
    spec:
      refreshInterval: ${var.agentgateway_secret_refresh_interval}
      secretStoreRef:
        name: ${kubectl_manifest.cluster_secret_store[0].name}
        kind: ClusterSecretStore
      target:
        name: ${each.value.k8s_secret_name}
        creationPolicy: Owner
        template:
          data:
            ${each.value.k8s_secret_data_key}: "${each.value.k8s_secret_value_tpl}"
      data:
        - secretKey: api_key
          remoteRef:
            key: ${each.value.gcp_secret_name}
  YAML

  server_side_apply = true
  wait              = true
}
