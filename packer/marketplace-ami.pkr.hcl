packer {
  required_plugins {
    amazon = {
      source  = "github.com/hashicorp/amazon"
      version = "= 1.8.0"
    }
    ansible = {
      source  = "github.com/hashicorp/ansible"
      version = "= 1.1.5"
    }
  }
}

variable "region" {
  type    = string
  default = "us-east-1"
}

variable "product_key" {
  type = string
}

variable "product_title" {
  type = string
}

variable "source_ami_id" {
  type = string
}

variable "ssh_username" {
  type = string
}

variable "architecture" {
  type = string
}

variable "layout" {
  type = string
}

variable "filesystem" {
  type = string
}

variable "version_title" {
  type = string
}

variable "product_profile" {
  type    = string
  default = "hardened-linux"
}

variable "build_instance_type" {
  type = string
}

variable "root_device_name" {
  type = string
}

variable "root_volume_size" {
  type = number
}

variable "build_subnet_id" {
  type = string
}

locals {
  ami_name = "corenova-${var.product_key}-${var.version_title}-${formatdate("YYYYMMDD-hhmm", timestamp())}"
}

source "amazon-ebs" "marketplace" {
  region                                    = var.region
  source_ami                                = var.source_ami_id
  subnet_id                                 = var.build_subnet_id
  instance_type                             = var.build_instance_type
  ssh_username                              = var.ssh_username
  associate_public_ip_address               = true
  temporary_security_group_source_public_ip = true
  ami_name                                  = local.ami_name
  ami_description                           = "${var.product_title} ${var.version_title}"
  ena_support                               = true
  sriov_support                             = true
  force_deregister                          = false
  force_delete_snapshot                     = false
  imds_support                              = "v2.0"

  metadata_options {
    http_endpoint               = "enabled"
    http_tokens                 = "required"
    http_put_response_hop_limit = 1
    instance_metadata_tags      = "disabled"
  }

  launch_block_device_mappings {
    device_name           = var.root_device_name
    volume_type           = "gp3"
    volume_size           = var.root_volume_size
    delete_on_termination = true
    encrypted             = false
  }

  ami_block_device_mappings {
    device_name           = var.root_device_name
    volume_type           = "gp3"
    volume_size           = var.root_volume_size
    delete_on_termination = true
    encrypted             = false
  }

  tags = {
    Name         = local.ami_name
    ManagedBy    = "packer"
    Project      = "builder-ami"
    Seller       = "CoreNova Intelligence Limited"
    ProductKey   = var.product_key
    Profile      = var.product_profile
    Version      = var.version_title
    Architecture = var.architecture
    Layout       = var.layout
    Filesystem   = var.filesystem
    Marketplace  = "candidate"
    Purpose      = "ami-build"
  }

  snapshot_tags = {
    Name        = local.ami_name
    ManagedBy   = "packer"
    Project     = "builder-ami"
    ProductKey  = var.product_key
    Version     = var.version_title
    Marketplace = "candidate"
    Purpose     = "ami-build"
  }

  run_tags = {
    ManagedBy  = "packer"
    Project    = "builder-ami"
    Seller     = "CoreNova Intelligence Limited"
    ProductKey = var.product_key
    Purpose    = "ami-build"
  }

  run_volume_tags = {
    ManagedBy  = "packer"
    Project    = "builder-ami"
    ProductKey = var.product_key
    Purpose    = "ami-build-temporary"
  }
}

build {
  sources = ["source.amazon-ebs.marketplace"]

  provisioner "ansible" {
    playbook_file = "ansible/playbook.yml"
    extra_arguments = [
      "--extra-vars",
      "product_key=${var.product_key} product_profile=${var.product_profile} layout=${var.layout} filesystem=${var.filesystem}"
    ]
  }

  provisioner "shell" {
    inline = [
      "set -eux",
      "sudo cloud-init clean --logs || true",
      "sudo find /root /home -path '*/.ssh/authorized_keys' -type f -delete || true",
      "sudo rm -f /etc/ssh/ssh_host_*",
      "sudo truncate -s 0 /etc/machine-id || true",
      "sudo rm -f /var/lib/dbus/machine-id || true",
      "sudo find /var/log -type f -exec truncate -s 0 {} \\; || true",
      "history -c || true"
    ]
  }
}
