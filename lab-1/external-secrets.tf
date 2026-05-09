locals {
  external_secrets_values_yaml = file(
    startswith(var.external_secrets_values_file, "/") ? var.external_secrets_values_file : "${path.module}/${var.external_secrets_values_file}"
  )
}

# ##### GCP: Service Account #####
resource "google_service_account" "external_secrets" {
  account_id   = var.external_secrets_sa_name
  display_name = "External Secrets Operator — GCP Secret Manager access"
  description  = "Used by the External Secrets Operator ClusterSecretStore to read secrets from GCP Secret Manager."
  project      = var.gcp_project
}

# Least-privilege: read-only access to Secret Manager secret versions.
resource "google_project_iam_member" "external_secrets_secret_accessor" {
  project = var.gcp_project
  role    = "roles/secretmanager.secretAccessor"
  member  = "serviceAccount:${google_service_account.external_secrets.email}"
}


# ##### Kubernetes: namespace + secret #####
resource "kubernetes_namespace_v1" "external_secrets" {
  metadata {
    name = "external-secrets"
    labels = {
      "app.kubernetes.io/managed-by" = "terraform"
    }
  }
}

# Store the GCP SA JSON key as a Kubernetes secret in the ESO namespace.
# The ClusterSecretStore references this secret to authenticate against GCP.
resource "kubernetes_secret_v1" "external_secrets_gcp_key" {
  # Only created on phase 2 when external_secrets_key_provisioned = true.
  count = var.external_secrets_key_provisioned ? 1 : 0

  metadata {
    name      = "gcp-sa-key"
    namespace = kubernetes_namespace_v1.external_secrets.metadata[0].name
    labels = {
      "app.kubernetes.io/managed-by" = "terraform"
    }
  }

  # data_wo is write-only: the key JSON is pushed to the cluster but never stored in state.
  # var.external_secrets_gcp_sa_key_json is ephemeral so it is also never stored in state.
  data_wo = {
    "key.json" = var.external_secrets_gcp_sa_key_json
  }

  # Increment var.external_secrets_gcp_key_revision to force Terraform to re-push
  # the secret when rotating the SA key.
  data_wo_revision = var.external_secrets_gcp_key_revision

  type = "Opaque"
}

# ##### Helm: External Secrets Operator #####
resource "helm_release" "external_secrets" {
  name             = "external-secrets"
  chart            = "oci://ghcr.io/external-secrets/charts/external-secrets"
  version          = var.external_secrets_chart_version
  namespace        = kubernetes_namespace_v1.external_secrets.metadata[0].name
  create_namespace = false

  values = [local.external_secrets_values_yaml]

  wait = true
}

# ##### ClusterSecretStore: cluster-wide GCP Secret Manager proxy ######
# A single ClusterSecretStore lets any namespace create ExternalSecret resources
# that pull from GCP Secret Manager without needing per-namespace SecretStores.

resource "kubectl_manifest" "cluster_secret_store" {
  # Only created on phase 2 when external_secrets_key_provisioned = true.
  count     = var.external_secrets_key_provisioned ? 1 : 0
  yaml_body = <<-YAML
    apiVersion: external-secrets.io/v1
    kind: ClusterSecretStore
    metadata:
      name: ${var.external_secrets_cluster_store_name}
    spec:
      provider:
        gcpsm:
          projectID: ${var.gcp_project}
          auth:
            secretRef:
              secretAccessKeySecretRef:
                name: ${kubernetes_secret_v1.external_secrets_gcp_key[0].metadata[0].name}
                namespace: ${kubernetes_namespace_v1.external_secrets.metadata[0].name}
                key: key.json
  YAML

  server_side_apply = true
  wait              = true

  depends_on = [helm_release.external_secrets]
}
