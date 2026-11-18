variable "project_id" {
  description = "ID do projeto GCP usado na demonstração."
  type        = string
}

variable "region" {
  description = "Região única para o bucket e os datasets."
  type        = string
  default     = "southamerica-east1"
}

variable "bucket_name" {
  description = "Nome globalmente único do bucket Landing/Raw."
  type        = string
}

variable "labels" {
  description = "Labels aplicados aos recursos versionados."
  type        = map(string)
  default = {
    env     = "demo"
    project = "lakehouse-financeiro"
  }
}
