variable "github_owner" {
  type        = string
  default     = "CoreNovaLabs"
  description = "GitHub organization or user that owns the workflow repository."

  validation {
    condition     = can(regex("^[A-Za-z0-9-]+$", var.github_owner))
    error_message = "github_owner must be a valid GitHub owner name."
  }
}

variable "allow_root_bootstrap" {
  type        = bool
  default     = false
  description = "Explicit one-time override for creating the non-root roles with root credentials. Keep false for normal planning and all later operations."
}

variable "github_repository" {
  type        = string
  default     = "builder-ami"
  description = "Private GitHub repository that contains the guarded workflows."

  validation {
    condition = (
      can(regex("^[A-Za-z0-9_.-]+$", var.github_repository)) &&
      var.github_repository == "builder-ami"
    )
    error_message = "github_repository must remain the reviewed builder-ami repository."
  }
}

variable "github_oidc_subject" {
  type        = string
  default     = "repo:CoreNovaLabs@283825262/builder-ami@1301293394:ref:refs/heads/main"
  description = "Immutable GitHub owner/repository IDs and exact main ref trusted by AWS."

  validation {
    condition     = var.github_oidc_subject == "repo:CoreNovaLabs@283825262/builder-ami@1301293394:ref:refs/heads/main"
    error_message = "github_oidc_subject must match the immutable IDs of CoreNovaLabs/builder-ami on refs/heads/main."
  }
}

variable "github_oidc_provider_arn" {
  type        = string
  default     = "arn:aws:iam::582920575154:oidc-provider/token.actions.githubusercontent.com"
  description = "Existing GitHub Actions OIDC provider in the CoreNova seller account."

  validation {
    condition     = var.github_oidc_provider_arn == "arn:aws:iam::582920575154:oidc-provider/token.actions.githubusercontent.com"
    error_message = "Use the verified GitHub Actions OIDC provider in seller account 582920575154."
  }
}
