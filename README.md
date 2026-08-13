# CoreNova AMI Builder

This repository builds replacement AMI versions for the 11 existing AWS
Marketplace AMI products listed in `products.yaml`. Two focused EKS Admin
Bastion candidates are maintained separately in `products.candidates.yaml`.

The workflow is intentionally guarded:

1. Match product title and EntityId against the local allowlist.
2. Build a new AMI in `us-east-1` with Packer and Ansible.
3. Validate AMI ownership, architecture, virtualization, product codes, and unencrypted snapshots.
4. Publish commit-bound CloudFormation, diagrams, documentation, client, and
   buyer IAM examples to one immutable public S3 prefix.
5. Run both guided modes against a disposable, no-node, private-endpoint EKS
   cluster for each architecture; require cleanup to succeed.
6. Compose x86_64 and ARM64 into one atomic `AddDeliveryOptions` plan and submit
   it with `Intent=VALIDATE` from the validation-only role.
7. Apply the exact validated plan only through the `marketplace-production`
   environment and its delivery-only publisher role.

The general `submit_changeset.py` APPLY path remains limited to reviewed
`UpdateInformation` metadata. EKS delivery release uses a separate script and
role that require two guarded products, three options per architecture, the
successful VALIDATE evidence, and the exact plan SHA-256. It cannot change
pricing, visibility, product release state, or old versions.

## Current focus

The 30-day commercial focus is the x86_64 and ARM64 EKS Admin Bastion pair in
`products.candidates.yaml`. Other historical products remain in the source
allowlist but are outside the guarded GitHub build role's permissions.

## Common Commands

Install Python dependencies:

```bash
python3 -m pip install --require-hashes -r requirements.lock
ansible-galaxy collection install -r ansible/requirements.yml
```

List only the allowlisted Marketplace products:

```bash
python3 scripts/list_allowed_products.py
```

Resolve the latest source AMI for one product:

```bash
python3 scripts/resolve_source_ami.py centos-stream-9-x86_64-ext4
```

Build one AMI:

```bash
scripts/build_one.sh centos-stream-9-x86_64-ext4
```

Validate a built AMI:

```bash
python3 scripts/validate_ami.py centos-stream-9-x86_64-ext4 ami-xxxxxxxxxxxxxxxxx
```

Render a Marketplace Add Version change set:

```bash
python3 scripts/render_marketplace_changeset.py centos-stream-9-x86_64-ext4 ami-xxxxxxxxxxxxxxxxx --access-role-arn arn:aws:iam::582920575154:role/CoreNovaMarketplaceAmiIngestion
```

Submit a validation-only Marketplace change set:

```bash
python3 scripts/submit_changeset.py plans/centos-stream-9-x86_64-ext4-add-version.json --intent VALIDATE
```

## Safety Rules

- `products.yaml` is the default allowlist; EKS work must explicitly select
  `products.candidates.yaml`.
- Scripts fail closed if AWS returns a product not matching both title and EntityId.
- Build, smoke, and Marketplace submission entry points reject AWS account-root
  credentials and require their exact assumed role.
- `VALIDATE` accepts only `AddDeliveryOptions`; guarded `APPLY` accepts only
  `UpdateInformation` and requires `--confirm-apply`.
- Old versions are not restricted by the add-version command.
- AMIs with existing Marketplace product codes are rejected.
- Encrypted snapshots are rejected because AWS Marketplace AMI ingestion requires unencrypted snapshots.

## EKS Admin Bastion workflow

Use the candidate allowlist and non-root roles:

```bash
export CORENOVA_PRODUCTS_FILE=products.candidates.yaml
export AWS_PROFILE=corenova-ami-builder

scripts/build_candidate.sh eks-admin-bastion-al2023-x86_64
scripts/build_candidate.sh eks-admin-bastion-al2023-arm64
```

To prepare a reviewed instance-type expansion for an existing EKS product,
render a plan from the live Marketplace product and offer. The renderer verifies
architecture, `us-east-1` availability, existing compatibility/dimension/price
consistency, and preserves every existing hourly rate:

```bash
export CORENOVA_PRODUCTS_FILE=products.candidates.yaml
python3 scripts/render_add_instance_types_changeset.py eks-admin-bastion-al2023-x86_64
python3 scripts/render_add_instance_types_changeset.py eks-admin-bastion-al2023-arm64
```

The generated `AddInstanceTypes`, `AddDimensions`, and `UpdatePricingTerms`
plans are review artifacts only. Apply them through a separate non-root,
MFA-governed Marketplace publisher path; the guarded repository submitter does
not publish pricing or instance-type changes.

Before a Marketplace version request, run the no-ingress Systems Manager smoke
test documented in
`marketplace/eks-admin-bastion/README.md`. IAM separation and bootstrap options
are documented under `marketplace/eks-admin-bastion/iam/` and
`infra/terraform/eks-admin-bastion-operator-roles/`. The current account audit
and repository decision are recorded in `docs/operator-identity-bootstrap.md`.

The next EKS version is additive: standalone AMI compatibility plus Identity
Relay and Audited Workstation CloudFormation delivery options. Validate and
package those assets before the AMI candidate workflow:

```bash
make test-eks-delivery
make package-eks-delivery
```

The guarded asset workflow publishes the exact package to
`eks-admin-bastion/vYYYYMMDD-COMMITSHA12`. Candidate workflows build and smoke
one architecture without touching Marketplace. E2E workflows then test the
candidate AMIs, and the dual-architecture validator consumes only those run
artifacts. Existing subscriber instances and old versions are not changed.

The private GitHub repository contains these guarded workflows:

- source validation and secret scanning on every push;
- scheduled read-only cost and Marketplace health reports;
- a manual, single-architecture candidate build and SSM smoke pipeline;
- immutable versioned asset publication;
- disposable EKS delivery integration testing;
- atomic dual-architecture Marketplace VALIDATE;
- hash-bound production release behind the `marketplace-production` environment.

No build, smoke, E2E, asset, or validator role can call Marketplace APPLY. The
production delivery publisher cannot change metadata, pricing, visibility, or
restrict the previous version.
