# CoreNova AMI Builder

This repository builds replacement AMI versions for the 11 existing AWS
Marketplace AMI products listed in `products.yaml`. Two focused EKS Admin
Bastion candidates are maintained separately in `products.candidates.yaml`.

The workflow is intentionally guarded:

1. Match product title and EntityId against the local allowlist.
2. Build a new AMI in `us-east-1` with Packer and Ansible.
3. Validate AMI ownership, architecture, virtualization, product codes, and unencrypted snapshots.
4. Generate a Marketplace `AddDeliveryOptions` change set.
5. Submit an `AddDeliveryOptions` request with `--intent VALIDATE` from the
   dedicated Marketplace Validator role.
6. Release or restrict delivery options only through a separate reviewed
   production workflow after validation succeeds.

The guarded `APPLY` path in `submit_changeset.py` is intentionally limited to
reviewed `UpdateInformation` metadata plans for the two existing EKS products.
It cannot release products or offers, change visibility, pricing, or delivery
options.

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

Before a Marketplace version request, run the no-ingress Systems Manager smoke
test documented in
`marketplace/eks-admin-bastion/README.md`. IAM separation and bootstrap options
are documented under `marketplace/eks-admin-bastion/iam/` and
`infra/terraform/eks-admin-bastion-operator-roles/`. The current account audit
and repository decision are recorded in `docs/operator-identity-bootstrap.md`.

The private GitHub repository contains three guarded workflows:

- source validation and secret scanning on every push;
- scheduled read-only cost and Marketplace health reports;
- a manual, single-architecture candidate pipeline that requires an exact main
  commit SHA and explicit confirmation, then stops at Marketplace `VALIDATE`.

No GitHub workflow has metadata Publisher permissions or an `APPLY` path.
