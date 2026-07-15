output "operator_role_arns" {
  description = "Guarded GitHub OIDC operator role ARNs. No secrets are required."
  value = {
    for key, role in aws_iam_role.operator : key => role.arn
  }
}

output "smoke_instance_profile_name" {
  description = "Value for CORENOVA_SMOKE_INSTANCE_PROFILE_NAME."
  value       = aws_iam_instance_profile.smoke_instance.name
}

output "github_subject" {
  description = "Exact immutable GitHub OIDC subject trusted by the operator roles."
  value       = var.github_oidc_subject
}
