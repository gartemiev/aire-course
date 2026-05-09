locals {
  agentgateway_values_yaml = file(
    startswith(var.agentgateway_values_file, "/") ? var.agentgateway_values_file : "${path.module}/${var.agentgateway_values_file}"
  )
}

# Step 1 (docs): Fetch and split the multi-document Gateway API CRD manifest.
data "http" "gateway_api_crds" {
  url = "https://github.com/kubernetes-sigs/gateway-api/releases/download/${var.gateway_api_version}/standard-install.yaml"
}

data "kubectl_file_documents" "gateway_api_crds" {
  content = data.http.gateway_api_crds.response_body
}

# Apply each CRD document individually with server-side apply, matching the docs.
resource "kubectl_manifest" "gateway_api_crds" {
  for_each          = data.kubectl_file_documents.gateway_api_crds.manifests
  yaml_body         = each.value
  server_side_apply = true
  wait              = true
}

# Namespace created explicitly so it can be referenced by both the Helm
# releases and the ExternalSecret without coupling them together.
resource "kubernetes_namespace_v1" "agentgateway" {
  metadata {
    name = "agentgateway-system"
    labels = {
      "app.kubernetes.io/managed-by" = "terraform"
    }
  }
}

# Step 2 (docs): Install agentgateway CRDs.
resource "helm_release" "agentgateway_crds" {
  name             = "agentgateway-crds"
  chart            = "oci://cr.agentgateway.dev/charts/agentgateway-crds"
  version          = var.agentgateway_chart_version
  namespace        = kubernetes_namespace_v1.agentgateway.metadata[0].name
  create_namespace = false

  wait = true

  depends_on = [
    kubectl_manifest.gateway_api_crds,
  ]
}

# Step 3 (docs): Install agentgateway control plane.
resource "helm_release" "agentgateway" {
  name             = "agentgateway"
  chart            = "oci://cr.agentgateway.dev/charts/agentgateway"
  version          = var.agentgateway_chart_version
  namespace        = kubernetes_namespace_v1.agentgateway.metadata[0].name
  create_namespace = false

  values = [local.agentgateway_values_yaml]

  wait = true

  depends_on = [helm_release.agentgateway_crds]
}
