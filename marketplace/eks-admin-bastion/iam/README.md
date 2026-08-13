# IAM separation for EKS Admin Bastion operations

These policies are deployed by the reviewed Terraform bootstrap. Account-root
must never be used to build AMIs or call `StartChangeSet`.

## Daily roles

GitHub assumes the four workflow roles through one immutable repository/main
subject. Do not use long-lived IAM user keys.

1. `CoreNovaMarketplaceObserverRole`
   - Uses `marketplace-observer-policy.json` for scheduled cost and health
     reports. It has no write action.
2. `CoreNovaAmiBuilderRole`
   - Create an IAM managed policy from `ami-builder-policy.json`, attach it to
     the role, and set the same policy as the role's permissions boundary.
   - Do not attach Marketplace or `iam:PassRole` permissions.
3. `CoreNovaEksBastionSmokeRunnerRole`
   - Create an IAM managed policy from `ssm-smoke-runner-policy.json`, attach it
     to the role, and set the same policy as the role's permissions boundary.
   - Create a dedicated EC2 role named
     `CoreNovaEksBastionSmokeInstanceRole`, attach
     `ssm-smoke-instance-core-policy.json`, use the same policy as its boundary,
     and expose it through an instance profile. The custom policy deliberately
     excludes Parameter Store reads.
4. `CoreNovaMarketplaceValidatorRole`
   - Create an IAM managed policy from `marketplace-validator-policy.json`.
   - Attach that policy to the role and also set the same policy as the role's
     permissions boundary.
   - Do not attach `AWSMarketplaceSellerProductsFullAccess`.

The validator policy can only validate an `AddDeliveryOptions` change for the
two existing EKS AMI products. It explicitly denies `APPLY`, including an API
call that omits `Intent` (the AWS default is `APPLY`). It can pass only the
existing `CoreNovaMarketplaceAmiIngestion` role, and only to
`assets.marketplace.amazonaws.com`.

## Delivery release roles

Run `scripts/bootstrap_eks_delivery_release_roles.sh` once from the seller root
caller after reviewing every policy. Root only creates the boundaries, roles,
and versioned public asset bucket; it never builds, tests, uploads assets, or
calls Marketplace Catalog.

- `CoreNovaMarketplaceAssetPublisherRole` can put/read only versioned EKS assets
  in the dedicated bucket and explicitly cannot delete objects or mutate bucket
  controls.
- `CoreNovaEksDeliveryE2ERole` can operate fixed-prefix test stacks, use the
  required SSM documents, read safety state, and remove retained test logs. It
  passes only `CoreNovaEksDeliveryE2ECloudFormationRole` to CloudFormation.
- `CoreNovaEksDeliveryE2ECloudFormationRole` is a service role for disposable
  EKS/VPC/bastion resources. Its attached policy is also its permissions
  boundary.
- `CoreNovaMarketplaceDeliveryPublisherRole` trusts only the immutable repo's
  `marketplace-production` environment. It can APPLY only
  `AddDeliveryOptions` for the two exact EKS products and pass only the existing
  Marketplace ingestion role.

The release script independently requires a two-product plan, three delivery
options per product, the same version title, the exact successful VALIDATE
evidence, matching commit SHA, and matching plan SHA-256.

## Manual metadata publisher

Do not create a GitHub OIDC Publisher. If a human Publisher is introduced after
the metadata plans have been reviewed, use
`marketplace-metadata-publisher-policy.json` both as its attached policy and
permissions boundary. Restrict trust to an MFA-governed non-root administrator.

This publisher can apply only `UpdateInformation` to the two EKS products. It
cannot release products or offers, change visibility, add AMIs, or change
pricing. The repository submit script independently enforces the expected role
name and refuses all Marketplace submissions made with account-root
credentials.

AWS currently documents `VALIDATE` for adding versions to single-AMI products.
Do not assume it provides a dry run for `UpdateInformation`; metadata publishing
therefore requires the narrowly scoped publisher role and a human diff review.

## Manual instance-type publisher

`CoreNovaMarketplaceInstancePublisherRole` is a separate, temporary publisher
for reviewed instance-type expansion plans. Its trust requires an MFA-authenticated
seller-root session. Its policy and permissions boundary allow only
`AddInstanceTypes`, `AddDimensions`, and `UpdatePricingTerms` against the two EKS
Admin products and their exact released public offers. The guarded submitter
also requires the live product delta, dimension additions, and complete hourly
rate card to match `products.candidates.yaml` before it calls `APPLY`.

Bootstrap it once with `scripts/bootstrap_marketplace_instance_publisher.sh`.
Use an assumed session named `CoreNovaMarketplaceInstancePublisherRole`, then
submit each generated plan with `scripts/submit_add_instance_types_changeset.py`.

## Suggested profile names

Configure role assumption from a non-root source profile:

```ini
[profile corenova-ami-builder]
role_arn = arn:aws:iam::582920575154:role/CoreNovaAmiBuilderRole
source_profile = REPLACE_WITH_NON_ROOT_SOURCE_PROFILE

[profile corenova-eks-smoke]
role_arn = arn:aws:iam::582920575154:role/CoreNovaEksBastionSmokeRunnerRole
source_profile = REPLACE_WITH_NON_ROOT_SOURCE_PROFILE

[profile corenova-marketplace-validator]
role_arn = arn:aws:iam::582920575154:role/CoreNovaMarketplaceValidatorRole
source_profile = REPLACE_WITH_NON_ROOT_SOURCE_PROFILE

[profile corenova-marketplace-publisher]
role_arn = arn:aws:iam::582920575154:role/CoreNovaMarketplacePublisherRole
source_profile = REPLACE_WITH_NON_ROOT_SOURCE_PROFILE
```

Pass the profile only after `aws sts get-caller-identity` shows the expected
`assumed-role/...` ARN. The submit script will perform the same check again.

The build and smoke-test entry points also enforce their exact role names before
the first mutating AWS call:

- `build_one.sh`, `build_candidate.sh`, and the SSH smoke test require
  `CoreNovaAmiBuilderRole`.
- `smoke_test_eks_admin_bastion_ssm.sh` requires
  `CoreNovaEksBastionSmokeRunnerRole`.
- `submit_changeset.py` requires `CoreNovaMarketplaceValidatorRole` for
  `VALIDATE` or `CoreNovaMarketplacePublisherRole` for the guarded metadata
  `APPLY` path.

All of these scripts reject account-root credentials.

## Buyer operator policy examples

The product also ships two customer-side starting points. They are not deployed
into the seller account:

- `identity-relay-operator-policy.json` permits stack/cluster discovery and the
  AWS-managed remote-host forwarding document for one relay instance.
- `audited-workstation-operator-policy.json` permits the one stack-created
  session document on one workstation instance.

Replace every uppercase placeholder before use. Both policies scope session
resume/termination and the SSM message data channel to the caller's own session
ARN. Buyers must still apply their permission boundaries, SCPs, EKS Access
Entries, and access-review process.

## Enforced tightening

The build role accepts only Amazon Linux source AMIs, `t3.medium` or
`t4g.medium`, one exact VPC/subnet, and atomically tagged temporary resources.
The smoke role accepts only seller-owned candidate images, `t3.small` or
`t4g.small`, the same reviewed network, and the exact instance profile. Cleanup
is tag-bound. Run Command is limited to `AWS-RunShellScript` on tagged smoke
instances. Both roles explicitly lack Marketplace publication permissions.
