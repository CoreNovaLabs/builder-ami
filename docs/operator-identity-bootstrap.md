# Operator identity bootstrap decision

## Decision

The dedicated private repository is `CoreNovaLabs/builder-ami`. GitHub OIDC is
configured to use immutable owner and repository IDs. Every AWS workflow role
trusts only this exact subject on `refs/heads/main`:

```text
repo:CoreNovaLabs@283825262/builder-ami@1301293394:ref:refs/heads/main
```

The repository is personal/private, so GitHub environments are not treated as
an approval boundary. Mutating workflows are manual-only and require both the
current 40-character commit SHA and a fixed confirmation phrase.

## AWS identities

The Terraform bootstrap creates four GitHub roles and one temporary EC2 role:

- `CoreNovaMarketplaceObserverRole`: cost, product, AMI inventory, and seller
  agreement counts; read-only.
- `CoreNovaAmiBuilderRole`: Amazon Linux 2023 candidate builds in one exact
  VPC/subnet with limited instance types and mandatory tags.
- `CoreNovaEksBastionSmokeRunnerRole`: one tagged no-ingress smoke instance in
  the reviewed subnet.
- `CoreNovaMarketplaceValidatorRole`: `AddDeliveryOptions` with explicit
  `VALIDATE` only.
- `CoreNovaEksBastionSmokeInstanceRole`: custom SSM managed-node core without
  Parameter Store read access.

There is no GitHub Publisher role. Any future Marketplace `APPLY`, pricing,
trial, offer, or release action remains a separate human approval path using a
non-root MFA-governed identity.

## Root boundary

The seller account currently exposes account-root CLI credentials. Terraform
blocks root by default and permits it only when
`allow_root_bootstrap=true` is deliberately supplied for the one-time creation
of these non-root roles. After GitHub OIDC has been tested, remove the root
access key. Do not reuse the existing `CoreNovaGitHubPackerBuild` role: its
`AmazonEC2FullAccess` attachment and trust for another repository are broader
than this pipeline.

IAM Identity Center remains the recommended next step for interactive human
administration; do not create a replacement long-lived IAM user key.
