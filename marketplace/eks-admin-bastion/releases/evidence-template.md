# EKS SSM Bastion release evidence

- Version title:
- Candidate commit:
- Reviewer:
- Review date UTC:
- x86 AMI ID / source AMI ID:
- ARM AMI ID / source AMI ID:
- Asset S3 prefix:
- Manifest SHA-256:
- Catalog VALIDATE change-set IDs and final status:
- Non-production buyer account alias:
- Test EKS cluster / namespace (synthetic only):

## Automated gates

- [ ] Source validation workflow passed at candidate commit.
- [ ] EKS delivery unit tests and invariant validator passed.
- [ ] IAM boundary validator passed.
- [ ] x86 AMI validation and SSM smoke test passed.
- [ ] ARM AMI validation and SSM smoke test passed.
- [ ] Source and packaged templates passed AWS CloudFormation validation.
- [ ] Three delivery options share identical AMI source details per product.
- [ ] Architecture-specific parameters and defaults are locked correctly.

## Identity Relay integration

- [ ] No public IPv4; zero ingress.
- [ ] EC2 role denied EKS access.
- [ ] SSM remote-host tunnel and TLS verification passed.
- [ ] Separate operator identities and scopes verified.
- [ ] Client failure and cleanup cases passed.
- [ ] Port-forward content logging limitation appears in docs/listing.

## Audited Workstation integration

- [ ] No public IPv4; zero ingress.
- [ ] Run As user exists and is not root.
- [ ] View/default namespace is the effective default.
- [ ] Privileged acknowledgement gate passed negative/positive tests.
- [ ] Standard shell streamed to CloudWatch Logs.
- [ ] Idle/max timeout behavior verified.
- [ ] Log group retained after stack deletion.

## Compatibility and operations

- [ ] Existing subscriber instance was not changed.
- [ ] Previous version remains available during rollout.
- [ ] Parallel migration and rollback were tested.
- [ ] Support and troubleshooting documentation is published.
- [ ] Real screenshot checklist completed and redaction reviewed.
- [ ] Rollback owner and observation window recorded.
- [ ] Explicit Marketplace APPLY authorization attached.

## Exceptions

List every skipped or failed item, owner, compensating control, and expiry. A
blocking security, AMI smoke, CloudFormation integration, or Catalog VALIDATE
failure cannot be waived for production release.
