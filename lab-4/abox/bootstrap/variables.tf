variable "cluster_name" {
  description = "Cluster Name"
  type        = string
  default     = "abox-lab4"
}

variable "oci_registry" {
  description = "OCI registry base URL"
  type        = string
  default     = "oci://ghcr.io/gartemiev/aire-course"
}

variable "releases_artifact" {
  description = "OCI artifact name under oci_registry that holds this lab's releases bundle"
  type        = string
  default     = "releases-lab3"
}

variable "releases_version" {
  description = "Default tag for releases OCI artifact bootstrap"
  type        = string
  default     = "0.1.0"
}
