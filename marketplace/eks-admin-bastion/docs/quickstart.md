# AWS Marketplace quickstart

## Prerequisites

- Subscribe to the x86_64 or ARM64 product.
- Use a private subnet with NAT or VPC endpoints for Systems Manager. Add the
  endpoints required by the AWS APIs your administrators use.
- Know the existing EKS cluster name and cluster security group ID.
- If CloudFormation creates an EKS Access Entry, the cluster authentication mode
  must be `API` or `API_AND_CONFIG_MAP`.
- The stack deployer needs permission to create EC2, IAM, SSM, CloudWatch Logs,
  security-group ingress, and optional EKS Access Entry resources.

## Launch in AWS

1. Open the subscribed product in AWS Marketplace.
2. Choose **Continue to Launch**, then **Custom Launch**.
3. Select either **Identity Relay** or **Audited Workstation** and choose
   **Launch with CloudFormation Console**.
4. Select the VPC, private subnet, EKS cluster, and cluster security group.
5. Keep **View** and **Namespace** for the first launch. Change them only after a
   reviewed access request.
6. Acknowledge IAM resource creation, review the cost estimate, and create the
   stack.

No separate CoreNova website link is required. The website can link back to the
Marketplace listing and host extended documentation.

## Identity Relay connection

Install AWS CLI v2, kubectl, and the Session Manager plugin locally. Download
`corenova_eks_connect.py` from the versioned product documentation, then run the
`ConnectCommand` stack output:

```bash
python3 corenova_eks_connect.py \
  --stack-name corenova-eks-identity-relay \
  --region us-east-1
```

The default command is read-only:

```text
kubectl auth can-i get pods --namespace default
```

To run another explicit command, place its kubectl arguments after `--`:

```bash
python3 corenova_eks_connect.py \
  --stack-name corenova-eks-identity-relay \
  --region us-east-1 \
  -- get pods --namespace default
```

The local IAM identity needs `cloudformation:DescribeStacks`,
`eks:DescribeCluster`, and `ssm:StartSession` on the relay instance and the AWS
managed `AWS-StartPortForwardingSessionToRemoteHost` document. Kubernetes access
is controlled by the operator role's EKS Access Entry. Start from
`iam/identity-relay-operator-policy.json`, replace every placeholder, and review
it in the buyer's IAM process.

## Audited Workstation connection

Run the `StartSessionCommand` stack output. Do not omit its document name, or the
product Run As and log-streaming settings will not apply.

```bash
aws ssm start-session \
  --target i-REPLACE_ME \
  --document-name STACK_DOCUMENT_NAME \
  --region us-east-1
```

Then perform read-only checks:

```bash
corenova-eks-doctor --cluster CLUSTER_NAME --region us-east-1 --output json
aws eks update-kubeconfig --name CLUSTER_NAME --region us-east-1
kubectl auth can-i get pods --namespace default
kubectl get pods --namespace default
```

Start from `iam/audited-workstation-operator-policy.json` to limit the operator
to the one EC2 instance and its dedicated session document. Replace every
placeholder and review it before attachment.

## Costs

The buyer pays the live Marketplace software fee and AWS infrastructure costs,
including EC2, EBS, data transfer, NAT gateway or VPC endpoints, and CloudWatch
Logs for Audited Workstation. Deleting the audited stack retains its log group;
delete it separately only under the buyer's retention policy.
