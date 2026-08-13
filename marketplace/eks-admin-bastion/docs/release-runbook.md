# Production release runbook

No Marketplace `APPLY` or public documentation announcement is allowed until
all blocking gates pass.

## 1. Source and offline gates

```bash
make validate-config
make test-eks-delivery
make package-eks-delivery
python scripts/validate_iam_boundaries.py
```

Also compile Python, run `bash -n` on shell scripts, inspect both architecture
PNGs, and verify the packaged manifest hashes. The source-validation workflow
runs the EKS delivery validator and unit tests on every pull request.

## 2. Guarded workflow order

Every workflow dispatch must target `main`, use the exact 40-character commit
SHA, and use the required confirmation phrase.

1. Run **Publish immutable EKS delivery assets** once for the fixed
   `vYYYYMMDD` title.
2. Run **Guarded EKS AMI candidate** once for x86_64 and once for ARM64. Record
   both run IDs and attempts.
3. Run **EKS delivery integration test** once for each successful candidate run.
   Each E2E run downloads the candidate manifest rather than accepting an AMI
   ID typed by hand.
4. Run **Validate dual-architecture EKS release** with both candidate runs,
   both E2E runs, and the asset run. It creates one atomic two-product plan.
5. Run **Release dual-architecture EKS version** only with the successful
   validation run. The protected environment role applies the exact plan hash.

## 3. Build and AMI smoke gates

For both x86_64 and ARM64:

1. Build from the pinned pipeline.
2. Run `validate_ami.py` and the no-ingress SSM smoke test.
3. Require no public IP in the production-like private test subnet.
4. Require zero ingress, IMDSv2, no credential residue, a non-root
   `corenova-operator`, and SSM Agent 3.1.1374.0 or newer.
5. Run `corenova-eks-doctor` against a disposable EKS namespace with View access.

## 4. CloudFormation integration gates

In the isolated disposable E2E environment, test both modes for each architecture:

- create, update with the same parameters, and delete the stack;
- verify no public IPv4 and zero instance-security-group ingress;
- verify only SG-to-SG TCP 443 is added to the intended cluster SG;
- verify the root volume is encrypted and IMDSv2 is required;
- Identity Relay: verify the EC2 role receives AccessDenied for
  `eks:DescribeCluster`, while two distinct operator roles retain distinct EKS
  identities and namespace scopes;
- Identity Relay: verify the client rejects a busy local port, invalid endpoint,
  and invalid CA; verify cleanup after Ctrl-C and kubectl failure;
- Audited Workstation: verify Run As UID is non-zero, View/default authorization,
  log streaming during the session, timeout settings, and retained log group
  after stack deletion;
- verify Edit/Admin cannot deploy without the explicit shared-role acknowledgement;
- verify rollback by returning to the old standalone AMI instance.

Use disposable resources. Do not point test stacks at a production EKS cluster.
The test uses a no-node EKS cluster with a private API endpoint, one NAT gateway,
zero-ingress bastions, and synthetic identities. Its exit trap deletes all
stacks and retained log groups; cleanup failure fails the workflow.

## 5. Marketplace gates

1. Upload architecture-locked assets to an immutable, versioned public S3 path.
2. Render one plan per product architecture.
3. Confirm exactly three delivery options and identical AMI source details.
4. Use Catalog API `Intent=VALIDATE`; wait for asynchronous success.
5. Capture real AWS console screenshots listed in `screenshots/README.md`.
6. Complete `releases/evidence-template.md` with AMI IDs, stack IDs, test output,
   asset hashes, reviewer, rollback owner, and support readiness.
7. Confirm the `marketplace-production` environment and explicit `APPLY`
   authorization before dispatching the release workflow.

## 6. Staged rollout and rollback

- Release as a new version without restricting the previous version.
- Validate the subscribed buyer experience from a separate buyer account.
- Announce an optional upgrade; never claim existing instances auto-update.
- Monitor support and launch failures during the observation window.
- Roll back the launch recommendation to the previous version if a blocking
  defect appears. Existing buyer instances remain untouched.
