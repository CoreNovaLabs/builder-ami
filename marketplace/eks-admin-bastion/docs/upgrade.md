# Upgrade and existing subscribers

## What changes for current subscribers?

Nothing is changed in-place. Publishing this work creates a new Marketplace AMI
version. Existing subscriptions remain valid, existing EC2 instances keep
running, and old AMI delivery options remain available to entitled buyers under
AWS Marketplace version rules. AWS notifies subscribers that a new version is
available; it does not replace their instances or CloudFormation stacks.

## Recommended migration

Treat the new mode as a parallel deployment:

1. Keep the current bastion running.
2. Launch the new Identity Relay or Audited Workstation stack in a non-production
   namespace with View access.
3. Validate SSM registration, TLS, EKS identity, namespace authorization, and—if
   selected—CloudWatch log streaming.
4. Grant production scope through the buyer's normal access review.
5. Observe both paths during a defined rollback window.
6. Remove the old instance only after the buyer confirms success and retains any
   required logs.

There is no in-place package updater because replacing an administration host is
safer and more reproducible than mutating it. Kubeconfigs and credentials are
not copied automatically.

## Rollback

Rollback means stop using the new stack and resume the previous instance or
version. Do not delete the Audited Workstation log group as part of rollback;
the template intentionally retains it. Remove EKS Access Entries and cluster
security-group rules through CloudFormation stack deletion or reviewed platform
automation after confirming they are not shared.

## Seller support policy

Do not restrict the previous public version at the same time as publishing the
new version. After adoption and a support review, a version may be restricted
for new launches while remaining available to current subscribers. Continue
support for at least the AWS Marketplace-required period after restriction.
