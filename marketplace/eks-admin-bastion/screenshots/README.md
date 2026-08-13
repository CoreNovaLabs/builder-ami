# Real screenshot evidence checklist

Do not create mock AWS screenshots. Capture these only from the final
non-production subscribed-buyer test using synthetic names and no customer data.

Required screenshots for each architecture where the UI differs:

1. Marketplace delivery-option selector showing Standalone AMI, Identity Relay,
   and Audited Workstation.
2. Identity Relay CloudFormation parameter groups with View/Namespace defaults.
3. Identity Relay stack `CREATE_COMPLETE` and outputs, with account IDs redacted.
4. EC2 networking showing no public IPv4 and zero inbound rules.
5. Identity Relay client default read-only authorization result.
6. Two operator roles shown as distinct EKS identities or audit principals.
7. Audited Workstation parameter form with View/Namespace defaults.
8. Audited stack `CREATE_COMPLETE` and exact StartSession output.
9. SSM shell showing non-root `corenova-operator` and doctor PASS output.
10. CloudWatch log stream receiving the standard shell session.
11. Stack deletion with the audit log group retained.
12. Previous Marketplace version still visible/usable to an existing subscriber.

Before committing an image, remove account IDs, email addresses, role session
names, IP addresses, cluster endpoints, instance IDs, stack IDs, log content,
and browser/session metadata unless the evidence reviewer explicitly approves
the synthetic value. Record unredacted evidence only in the controlled release
system, not in this public repository.
