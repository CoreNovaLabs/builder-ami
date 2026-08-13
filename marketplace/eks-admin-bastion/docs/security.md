# Security model

## Controls common to both guided modes

- One EC2 instance in a buyer-selected private subnet.
- `AssociatePublicIpAddress=false` regardless of subnet defaults.
- Security group with zero inbound rules.
- TCP 443 cluster ingress sourced from the bastion security group, never a CIDR.
- Encrypted gp3 root volume.
- IMDSv2 required with response hop limit one.
- SSM Agent enabled; SSH is not part of the guided path.
- Architecture-locked release templates prevent x86/ARM instance mismatches.

## Identity Relay boundary

The relay role has `AmazonSSMManagedInstanceCore` and no `eks:*`, `ec2:*`, or
role-assumption permission. The operator's local AWS identity creates the EKS
token. Optional EKS Access Entry creation targets `OperatorRoleArn`, never the
instance role.

The relay uses the AWS-managed remote-host port-forwarding document. IAM can
restrict the target instance and session document, but that document accepts a
host parameter. The supplied client fixes the host to the endpoint returned by
`eks:DescribeCluster` and performs normal certificate verification; customers
that need policy-enforced destination allowlisting should additionally enforce
egress controls with a network firewall or use the Audited Workstation mode.

AWS Systems Manager does not support content logging for port-forwarded or SSH
sessions. Record EKS API audit logs when request-level visibility is required.

## Audited Workstation boundary

Standard stream sessions run as the locked, non-root `corenova-operator` account
and stream to a dedicated CloudWatch Logs group. The group has `DeletionPolicy`
and `UpdateReplacePolicy` set to `Retain`. CloudWatch service-managed encryption
is used; a customer-managed KMS key is not silently created or attached.

Kubernetes authorization belongs to a shared EC2 role. The first-launch default
is `AmazonEKSViewPolicy` scoped to the `default` namespace. All users with
`ssm:StartSession` on the instance inherit the role's access. Restrict session
permissions at IAM and use Identity Relay when individual EKS identity is more
important than a shell transcript.

## Required buyer reviews

- Confirm the subnet has no automatic public-IP requirement and has controlled
  outbound access.
- Confirm the cluster security group ID belongs to the intended cluster.
- Confirm the EKS Access Entry principal and namespace.
- Confirm only trusted roles can start, resume, or terminate sessions.
- Enable EKS control-plane audit logs if Kubernetes API audit evidence is needed.
- Review retained CloudWatch logs and their deletion lifecycle.

The product is a security control, not a compliance certification. Buyers remain
responsible for IAM, network, log retention, EKS audit policy, and operational
command approval in their AWS account.
