# Troubleshooting

Run the read-only diagnostics first:

```bash
corenova-eks-doctor --cluster CLUSTER_NAME --region AWS_REGION --output json
```

## Instance is not online in Systems Manager

- Confirm the instance profile contains `AmazonSSMManagedInstanceCore`.
- Confirm DNS and outbound HTTPS through NAT or the `ssm`, `ssmmessages`, and
  related VPC endpoints required in the Region.
- Confirm `amazon-ssm-agent` is active.
- Confirm the account/Region is not using a restrictive SSM activation policy.

## Identity Relay tunnel does not start

- Install AWS CLI v2, kubectl, and the Session Manager plugin locally.
- Confirm local port 18443 is unused or select `--local-port`.
- Confirm the operator may describe the stack and cluster and start the managed
  remote-host port-forwarding document on the relay instance.
- The AMI smoke test requires SSM Agent 3.1.1374.0 or newer for remote-host
  forwarding.

## TLS or connection timeout

- Do not enable insecure TLS. The client uses the real EKS hostname through
  kubeconfig `tls-server-name` and the cluster CA.
- Confirm the relay/workstation security group can reach the endpoint on 443.
- For a private endpoint, confirm the cluster security group allows 443 from the
  stack security group.
- Confirm the private subnet resolves the EKS endpoint hostname.

## kubectl says Unauthorized or Forbidden

- `Unauthorized` usually means the AWS role is not recognized by EKS. Confirm the
  exact principal ARN has an Access Entry and the cluster auth mode supports it.
- `Forbidden` usually means the identity is recognized but the policy or scope
  does not allow the operation. Check the namespace and start with
  `kubectl auth can-i`.
- In Identity Relay, check the local role/profile. In Audited Workstation, check
  the stack's `WorkstationRoleArn` output.

## Audited shell has no CloudWatch events

- Start the session with the exact `SessionDocumentName`/`StartSessionCommand`
  output. A default SSM shell does not inherit this product document.
- Confirm the instance role can describe log groups and create/describe/write a
  stream in the retained log group.
- Standard shell content is loggable; port-forward and SSH content is not.

Support requests should include Region, Marketplace version, AMI ID, stack ID,
instance ID, cluster version, access mode, doctor JSON, and redacted error text.
Never include AWS credentials, kubeconfigs, tokens, or Kubernetes secrets.
