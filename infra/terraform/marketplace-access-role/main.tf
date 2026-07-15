terraform {
  required_version = ">= 1.6.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 5.0"
    }
  }
}

provider "aws" {
  region = "us-east-1"
}

variable "role_name" {
  type    = string
  default = "AwsMarketplaceAmiIngestion"
}

data "aws_iam_policy_document" "assume_role" {
  statement {
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["assets.marketplace.amazonaws.com"]
    }
  }
}

data "aws_iam_policy_document" "ami_access" {
  statement {
    sid = "MarketplaceAmiReadAccess"
    actions = [
      "ec2:DescribeImages",
      "ec2:DescribeSnapshots",
      "ec2:ModifyImageAttribute",
      "ec2:ModifySnapshotAttribute",
    ]
    resources = ["*"]
  }
}

resource "aws_iam_role" "marketplace_ami_ingestion" {
  name               = var.role_name
  assume_role_policy = data.aws_iam_policy_document.assume_role.json
}

resource "aws_iam_role_policy" "marketplace_ami_ingestion" {
  name   = "${var.role_name}-policy"
  role   = aws_iam_role.marketplace_ami_ingestion.id
  policy = data.aws_iam_policy_document.ami_access.json
}

output "role_arn" {
  value = aws_iam_role.marketplace_ami_ingestion.arn
}
