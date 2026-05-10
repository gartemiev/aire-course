# Dedicated Gateway for the kagent UI, isolated in the kagent namespace.
#
# Why a separate Gateway (not a second listener on agentgateway-external):
#   - Different concerns: agentgateway-external carries LLM data-plane traffic,
#     this Gateway carries kagent's control/UI traffic. Splitting them keeps
#     blast radius small — restarting/upgrading the LLM gateway proxy does not
#     affect UI access, and a misconfigured kagent route can't accidentally
#     hijack /v1/chat/completions on the LLM gateway.
#   - No cross-namespace plumbing: HTTPRoute, Service, and Gateway all live in
#     the kagent namespace, so no ReferenceGrant is required.
#   - No listener-level conflict surface: each Gateway has its own port space
#     and its own auto-created proxy Service.
#
# Why the Gateway name is `kagent-ui-gateway` and not `kagent-ui`:
#   The agentgateway controller materializes each Gateway as a Deployment +
#   Service whose names match the Gateway. The kagent Helm chart already
#   creates a Service named `kagent-ui` (the Next.js UI itself), so reusing
#   that name here would collide. The `-gateway` suffix avoids the clash.

resource "kubectl_manifest" "kagent_ui_gateway" {
  count = var.external_secrets_key_provisioned ? 1 : 0

  yaml_body = <<-YAML
    apiVersion: gateway.networking.k8s.io/v1
    kind: Gateway
    metadata:
      name: kagent-ui-gateway
      namespace: ${kubernetes_namespace_v1.kagent.metadata[0].name}
    spec:
      gatewayClassName: agentgateway
      listeners:
      - name: http
        port: 80
        protocol: HTTP
        allowedRoutes:
          namespaces:
            from: Same
  YAML

  server_side_apply = true
  wait              = true

  depends_on = [
    helm_release.agentgateway,
    helm_release.kagent,
  ]
}

resource "kubectl_manifest" "kagent_ui_route" {
  count = var.external_secrets_key_provisioned ? 1 : 0

  yaml_body = <<-YAML
    apiVersion: gateway.networking.k8s.io/v1
    kind: HTTPRoute
    metadata:
      name: kagent-ui
      namespace: ${kubernetes_namespace_v1.kagent.metadata[0].name}
    spec:
      parentRefs:
      - name: ${kubectl_manifest.kagent_ui_gateway[0].name}
        sectionName: http
      rules:
      - backendRefs:
        - group: ""
          kind: Service
          name: kagent-ui
          port: 8080
  YAML

  server_side_apply = true
  wait              = true
}
