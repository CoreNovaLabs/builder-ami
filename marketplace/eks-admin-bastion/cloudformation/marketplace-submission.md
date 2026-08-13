# Marketplace CloudFormation delivery submission

AWS Marketplace Catalog API supports `DeploymentTemplateDeliveryOptionDetails`
for AMI products. A version may contain one standalone AMI option and up to
three AMI-with-CloudFormation options. Every option for the version must be
included in the original `AddDeliveryOptions` request; an option cannot be added
to an existing version later.

This release uses three options:

1. Standalone AMI — compatibility/manual path.
2. Identity Relay — per-operator EKS identity, no EKS permission on EC2.
3. Audited Workstation — logged Run As shell, shared scoped EC2 role.

## Versioned assets

Run `make package-eks-delivery`. Upload the exact generated files to an immutable
public HTTPS S3 prefix:

```text
eks-admin-bastion/vYYYYMMDD-COMMITSHA12/
├── x86_64/
│   ├── identity-relay.yaml
│   ├── audited-workstation.yaml
│   ├── identity-relay-architecture.png
│   └── audited-workstation-architecture.png
├── arm64/
│   └── ...
└── manifest.json
```

The CFT `AmiId` parameter uses `AWS::EC2::Image::Id`. Catalog API
`TemplateSources[0].ParameterName` must equal `AmiId`. Each architecture's
rendered template allows only its matching architecture and selects a matching
default instance type.

## Rendering and validation

The renderer preserves the standalone AMI delivery option and adds both CFT
options only with the explicit `--include-eks-cloudformation` flag and HTTPS
asset base URL.

```bash
make render-eks-add-version \
  PRODUCT=eks-admin-bastion-al2023-x86_64 \
  AMI=ami-REPLACE_ME \
  ACCESS_ROLE_ARN=arn:aws:iam::SELLER:role/CoreNovaMarketplaceAmiIngestion \
  ASSET_BASE_URL=https://PUBLIC-BUCKET.s3.amazonaws.com/eks-admin-bastion/vYYYYMMDD-COMMITSHA12
```

Then:

1. Review the JSON and manifest hashes.
2. Confirm all four URLs for that architecture return the intended immutable
   asset without authentication or redirect.
3. Submit only `Intent=VALIDATE` and wait for validation to succeed.
4. Complete the release runbook and independent evidence review.
5. Submit `Intent=APPLY` only after explicit release authorization.

## Buyer launch experience

After subscription, the buyer can choose Custom Launch and **Launch with
CloudFormation Console** directly in AWS Marketplace. They configure their VPC,
private subnet, cluster, security group, access principal/scope, and audit
settings before CloudFormation creates resources. A website quick-launch link is
not required and must not be advertised as the primary launch path.

## Compatibility requirements

- Publish as a new version; never replace an existing version's AMI.
- Do not restrict the old version during initial rollout.
- Do not silently migrate or terminate buyer instances.
- Keep standalone AMI instructions available and clearly label its shared-role
  and optional SSH responsibilities.
- Support the prior version for the Marketplace-required period if it is later
  restricted.
