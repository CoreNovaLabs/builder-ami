# GitHub OIDC bootstrap for EKS Admin Bastion operations

This module creates four least-privilege GitHub OIDC roles plus the dedicated
SSM smoke-test instance role/profile. It creates no IAM users, access keys,
Marketplace changes, or paid infrastructure.

All workflow roles trust only the immutable GitHub subject for
`CoreNovaLabs/builder-ami` on `refs/heads/main`. Each role uses its own managed
policy both as its identity policy and permissions boundary. The module verifies
the existing `CoreNovaMarketplaceAmiIngestion` role but never alters it.

Created identities:

- `CoreNovaMarketplaceObserverRole`
- `CoreNovaAmiBuilderRole`
- `CoreNovaEksBastionSmokeRunnerRole`
- `CoreNovaMarketplaceValidatorRole`
- `CoreNovaEksBastionSmokeInstanceRole`
- instance profile `CoreNovaEksBastionSmokeInstanceRole`

The smoke instance uses
`CoreNovaEksBastionSmokeInstanceCorePolicy`, a customer-managed copy of the SSM
managed-node core actions with all Parameter Store reads removed. GitHub never
receives a Publisher role and cannot call Marketplace `APPLY`.

## Validate and bootstrap

```bash
terraform init
terraform fmt -check
terraform validate
terraform plan
```

The provider is locked to seller account `582920575154`. Account-root is
rejected unless the reviewed one-time command explicitly supplies
`-var allow_root_bootstrap=true`. A reviewed plan should contain only IAM
policies, roles, attachments, the smoke instance profile, and the local
`terraform_data` guard; it must contain no delete or paid-resource action.

After apply, run the read-only GitHub workflow first. Verify that its AWS caller
is `CoreNovaMarketplaceObserverRole`, then test each manual role without
starting a paid build. Remove the root access key after an interactive non-root
administration path has also been established.
