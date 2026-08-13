# CoreNova EKS SSM Bastion product assets

This directory is the source of truth for the EKS SSM Bastion Marketplace
delivery experience. The current public Marketplace version remains a
standalone AMI. These assets prepare a later, additive version with three
delivery options:

1. **Identity Relay** — recommended for production. A private SSM relay carries
   encrypted traffic to the EKS API while kubectl authenticates as the operator.
   The EC2 role has no EKS permissions.
2. **Audited Workstation** — for recorded administrative shells. SSM runs a
   non-root shell and streams its content to retained CloudWatch Logs. Shell
   users share a scoped EC2 role.
3. **Standalone AMI** — compatibility and advanced manual deployment. The buyer
   must configure networking, IAM, SSM, and EKS authorization.

AWS Marketplace can open the CloudFormation console for the two guided delivery
options. A CoreNova website launch link is optional for documentation and
marketing; it is not required for the buyer to launch the product.

## Customer documentation

- [Choose a mode](docs/choose-a-mode.md)
- [Quickstart](docs/quickstart.md)
- [Security model](docs/security.md)
- [Upgrade and existing subscribers](docs/upgrade.md)
- [Troubleshooting](docs/troubleshooting.md)
- [Use cases](docs/use-cases.md)

## Release assets and controls

- Source templates: `cloudformation/identity-relay.yaml` and
  `cloudformation/audited-workstation.yaml`
- Compatibility template: `cloudformation/eks-admin-bastion.yaml` (not modified
  or silently substituted)
- Local Identity Relay client: `client/corenova_eks_connect.py`
- Buyer IAM starting points: `iam/identity-relay-operator-policy.json` and
  `iam/audited-workstation-operator-policy.json`
- Seller submission copy: `cloudformation/marketplace-submission.md`
- Release runbook: `docs/release-runbook.md`
- Real-deployment screenshot checklist: `screenshots/README.md`
- Release evidence template: `releases/evidence-template.md`

Build and validate the delivery assets without changing AWS:

```bash
make test-eks-delivery
make package-eks-delivery
```

The packaged `dist/eks-admin-bastion/{x86_64,arm64}` templates lock the AMI
architecture and select a compatible default instance type. Upload that exact
directory to a versioned public S3 prefix before rendering a Marketplace plan.

Rendering a plan does not submit it:

```bash
make render-eks-add-version \
  PRODUCT=eks-admin-bastion-al2023-x86_64 \
  AMI=ami-REPLACE_ME \
  ACCESS_ROLE_ARN=arn:aws:iam::SELLER:role/CoreNovaMarketplaceAmiIngestion \
  ASSET_BASE_URL=https://PUBLIC-ASSET-BUCKET.s3.amazonaws.com/eks-admin-bastion/vYYYYMMDD-COMMITSHA12
```

Use Catalog API `Intent=VALIDATE`, complete both non-production deployment
tests, and review the evidence record before any `APPLY` request.
