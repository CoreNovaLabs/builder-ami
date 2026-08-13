# Customer use cases

## Private-endpoint production operations

A platform engineer needs temporary access to an EKS cluster with no public API
endpoint. Identity Relay creates the network path without an inbound bastion
port. The engineer keeps their own IAM role and namespace-scoped EKS Access
Entry. Offboarding the role removes cluster access without rotating a shared
host credential.

Evidence: CloudTrail caller identity, EKS Access Entry, EKS control-plane audit
logs when enabled, zero-ingress security group, and the release test record.

## Recorded maintenance window

A regulated operator must execute a reviewed runbook from a controlled shell.
Audited Workstation provides a non-root SSM shell, timeout controls, CloudWatch
streaming, and retained logs. The buyer restricts `StartSession` to an on-call
role and keeps the default View/namespace policy until an approved change window.

Evidence: SSM session history, retained CloudWatch stream, IAM authorization,
EKS audit logs, and change ticket. The shared EC2 identity must be disclosed in
the review.

## External vendor access

A vendor assumes a time-limited customer IAM role. Identity Relay lets the
customer scope that role with an EKS Access Entry rather than granting the
vendor access to a shared privileged EC2 identity. The stack may leave Access
Entry creation disabled when the customer's identity platform owns it.

Evidence: role session, EKS Access Entry scope, EKS audit logs, and stack outputs.

## Incident response with rollback

The team deploys an Audited Workstation in parallel with the existing bastion,
uses View access to diagnose, and elevates only after explicit acknowledgement.
After the incident, it deletes the EC2 stack but retains the CloudWatch log group
under the incident retention policy. The previous bastion remains available
during the rollback window.
