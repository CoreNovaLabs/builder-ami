terraform {
  required_version = ">= 1.6.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 5.0, < 7.0"
    }
  }
}

provider "aws" {
  region              = "us-east-1"
  allowed_account_ids = ["582920575154"]
}

data "aws_caller_identity" "current" {}

data "aws_iam_role" "marketplace_ingestion" {
  name = "CoreNovaMarketplaceAmiIngestion"
}

resource "terraform_data" "caller_guard" {
  input = {
    caller_arn           = data.aws_caller_identity.current.arn
    marketplace_role_arn = data.aws_iam_role.marketplace_ingestion.arn
  }

  lifecycle {
    precondition {
      condition     = data.aws_caller_identity.current.account_id == "582920575154"
      error_message = "Refusing to deploy outside the CoreNova seller account 582920575154."
    }

    precondition {
      condition     = data.aws_iam_role.marketplace_ingestion.arn == "arn:aws:iam::582920575154:role/CoreNovaMarketplaceAmiIngestion"
      error_message = "The verified CoreNovaMarketplaceAmiIngestion role is missing or has an unexpected ARN."
    }

    precondition {
      condition = (
        data.aws_caller_identity.current.arn != "arn:aws:iam::582920575154:root" ||
        var.allow_root_bootstrap
      )
      error_message = "Root credentials are blocked by default. Set allow_root_bootstrap=true only for the reviewed one-time bootstrap."
    }
  }
}

locals {
  policy_dir = "${path.module}/../../../marketplace/eks-admin-bastion/iam"

  operator_roles = {
    observer = {
      role_name   = "CoreNovaMarketplaceObserverRole"
      policy_name = "CoreNovaMarketplaceObserverPolicy"
      policy_file = "marketplace-observer-policy.json"
      description = "Reads CoreNova Marketplace health, agreement counts, infrastructure inventory, and AWS cost data."
    }
    builder = {
      role_name   = "CoreNovaAmiBuilderRole"
      policy_name = "CoreNovaAmiBuilderPolicy"
      policy_file = "ami-builder-policy.json"
      description = "Builds tagged CoreNova EKS Admin Bastion AMI candidates."
    }
    smoke = {
      role_name   = "CoreNovaEksBastionSmokeRunnerRole"
      policy_name = "CoreNovaEksBastionSmokeRunnerPolicy"
      policy_file = "ssm-smoke-runner-policy.json"
      description = "Runs the no-ingress SSM smoke test against candidate AMIs."
    }
    validator = {
      role_name   = "CoreNovaMarketplaceValidatorRole"
      policy_name = "CoreNovaMarketplaceValidatorPolicy"
      policy_file = "marketplace-validator-policy.json"
      description = "Validates AddDeliveryOptions for the two EKS AMI products."
    }
  }

  operator_policy_documents = {
    for key, config in local.operator_roles :
    key => jsonencode(jsondecode(file("${local.policy_dir}/${config.policy_file}")))
  }
}

data "aws_iam_policy_document" "github_oidc_trust" {
  for_each = local.operator_roles

  statement {
    sid     = "ExactImmutableRepositoryMainOnly"
    effect  = "Allow"
    actions = ["sts:AssumeRoleWithWebIdentity"]

    principals {
      type        = "Federated"
      identifiers = [var.github_oidc_provider_arn]
    }

    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:aud"
      values   = ["sts.amazonaws.com"]
    }

    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:sub"
      values   = [var.github_oidc_subject]
    }
  }
}

resource "aws_iam_policy" "operator" {
  for_each = local.operator_roles

  depends_on = [terraform_data.caller_guard]

  name        = each.value.policy_name
  description = each.value.description
  policy      = local.operator_policy_documents[each.key]

  lifecycle {
    precondition {
      condition     = length(local.operator_policy_documents[each.key]) <= 6144
      error_message = "${each.value.policy_file} exceeds the 6,144-character IAM managed-policy limit."
    }
  }

  tags = {
    ManagedBy = "terraform"
    Project   = "builder-ami"
    Product   = "eks-admin-bastion"
  }
}

resource "aws_iam_role" "operator" {
  for_each = local.operator_roles

  name                 = each.value.role_name
  description          = each.value.description
  assume_role_policy   = data.aws_iam_policy_document.github_oidc_trust[each.key].json
  max_session_duration = 3600
  permissions_boundary = aws_iam_policy.operator[each.key].arn

  tags = {
    ManagedBy     = "terraform"
    Project       = "builder-ami"
    Product       = "eks-admin-bastion"
    GitHubSubject = var.github_oidc_subject
  }
}

resource "aws_iam_role_policy_attachment" "operator" {
  for_each = local.operator_roles

  role       = aws_iam_role.operator[each.key].name
  policy_arn = aws_iam_policy.operator[each.key].arn
}

data "aws_iam_policy_document" "smoke_instance_trust" {
  statement {
    sid     = "Ec2Only"
    effect  = "Allow"
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["ec2.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "smoke_instance" {
  depends_on = [terraform_data.caller_guard]

  name                 = "CoreNovaEksBastionSmokeInstanceRole"
  description          = "Temporary EC2 role for EKS Admin Bastion SSM smoke tests."
  assume_role_policy   = data.aws_iam_policy_document.smoke_instance_trust.json
  permissions_boundary = aws_iam_policy.smoke_instance_core.arn

  tags = {
    ManagedBy = "terraform"
    Project   = "builder-ami"
    Product   = "eks-admin-bastion"
    Purpose   = "ssm-smoke-test"
  }
}

resource "aws_iam_policy" "smoke_instance_core" {
  depends_on = [terraform_data.caller_guard]

  name        = "CoreNovaEksBastionSmokeInstanceCorePolicy"
  description = "SSM managed-node core for temporary smoke instances without Parameter Store read access."
  policy      = jsonencode(jsondecode(file("${local.policy_dir}/ssm-smoke-instance-core-policy.json")))

  tags = {
    ManagedBy = "terraform"
    Project   = "builder-ami"
    Product   = "eks-admin-bastion"
    Purpose   = "ssm-smoke-test"
  }
}

resource "aws_iam_role_policy_attachment" "smoke_instance_ssm" {
  role       = aws_iam_role.smoke_instance.name
  policy_arn = aws_iam_policy.smoke_instance_core.arn
}

resource "aws_iam_instance_profile" "smoke_instance" {
  name = "CoreNovaEksBastionSmokeInstanceRole"
  role = aws_iam_role.smoke_instance.name

  tags = {
    ManagedBy = "terraform"
    Project   = "builder-ami"
    Product   = "eks-admin-bastion"
    Purpose   = "ssm-smoke-test"
  }
}
