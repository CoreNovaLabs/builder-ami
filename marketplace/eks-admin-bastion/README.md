# CoreNova EKS Admin Bastion deployment assets

The CloudFormation template in this directory deploys the AMI as a private,
SSM-first EKS administration host. It is a local release asset and is not yet a
published AWS Marketplace CloudFormation delivery option.

## Prerequisites

- Subscribe to the x86_64 or ARM64 listing and copy its AMI ID in `us-east-1`.
- Choose an architecture-compatible instance type (`t3.small` for x86_64 or
  `t4g.small` for ARM64 are the normal starting points).
- Use a private subnet with NAT or VPC endpoints for Systems Manager and the
  AWS APIs used by the administration tools.
- Install AWS CLI v2 and the Session Manager plugin on the operator workstation.
- For automatic EKS Access Entry creation, the existing cluster authentication
  mode must be `API` or `API_AND_CONFIG_MAP`.
- The deployer must be allowed to create IAM, EC2, and optional EKS Access Entry
  resources. CloudFormation requires acknowledgement of IAM capabilities.

## Deploy

```bash
aws cloudformation deploy \
  --stack-name corenova-eks-admin-bastion \
  --template-file cloudformation/eks-admin-bastion.yaml \
  --capabilities CAPABILITY_IAM \
  --parameter-overrides \
    AmiId=ami-REPLACE_ME \
    VpcId=vpc-REPLACE_ME \
    SubnetId=subnet-REPLACE_ME \
    ClusterName=cluster-REPLACE_ME \
    InstanceType=t3.small \
    CreateEksAccessEntry=Yes \
    EksAccessPolicyName=AmazonEKSViewPolicy
```

For an EKS cluster with a private API endpoint, set
`CreateClusterSecurityGroupIngress=Yes` and pass its
`ClusterSecurityGroupId`. The template then allows TCP 443 from the bastion
security group to that cluster security group.

If the cluster still uses the legacy `CONFIG_MAP` authentication mode, set
`CreateEksAccessEntry=No` and configure the instance role in `aws-auth` through
your existing cluster-administration process.

## Verify

Use the `StartSessionCommand` stack output, then run:

```bash
corenova-eks-check
aws sts get-caller-identity
aws eks update-kubeconfig --region us-east-1 --name cluster-REPLACE_ME
kubectl get nodes
```

Before publishing a rebuilt AMI, run the no-ingress smoke test from the
repository root. The instance profile must use the custom CoreNova SSM core
policy. A private subnet requires NAT or the required Systems Manager VPC
endpoints. The cost-capped GitHub workflow instead uses a short-lived public
IPv4 address in the reviewed public subnet while retaining zero inbound rules.

```bash
export CORENOVA_SMOKE_SUBNET_ID=subnet-REPLACE_ME
export CORENOVA_SMOKE_INSTANCE_PROFILE_NAME=profile-REPLACE_ME
# Set true only for the reviewed ephemeral public-subnet mode.
export CORENOVA_SMOKE_ALLOW_PUBLIC_IP=false

scripts/smoke_test_eks_admin_bastion_ssm.sh \
  eks-admin-bastion-al2023-x86_64 \
  ami-REPLACE_ME
```

The test creates an instance with a security group that has no inbound rules,
waits for Systems Manager registration, runs the product diagnostic, checks
IMDSv2 and common credential residue, and then terminates the instance. Private
mode rejects a public address; reviewed cost-capped mode requires one only for
outbound SSM access. Set `CORENOVA_SMOKE_EKS_CLUSTER_NAME` to also perform a read-only
`kubectl get nodes` check; the test instance role must already have the intended
EKS Access Entry.

## Security boundary

The template creates no inbound security-group rules and does not assign a
public IPv4 address. Anyone permitted to start a shell on the instance can use
the shared EC2 instance-role credentials and therefore inherits that role's EKS
permissions. Treat Session Manager access as a trusted-administrator boundary;
this deployment does not provide per-user EKS identity isolation.

The AWS Marketplace standalone-AMI delivery option is different: its schema
requires at least one security-group recommendation. For that path, CoreNova
recommends TCP 22 only from RFC1918 private ranges as an optional SSH fallback.
The CloudFormation template is the intended zero-ingress, SSM-first deployment
path and must be added to the Marketplace version as an `AMI with
CloudFormation` delivery option before that launch experience is advertised as
available in the listing.
