# Marketplace CloudFormation delivery submission

This is the preferred buyer launch path for the EKS Admin Bastion because the
template creates no public IPv4 address and no inbound security-group rules.
It is not published yet.

AWS Marketplace does not currently support single-AMI with CloudFormation
delivery through the Catalog API. Add this option manually in the Marketplace
Management Portal when submitting the next AMI version. All delivery options
for that version must be included in the same request; they cannot be added to
an existing version later.

## Assets

- Template: `eks-admin-bastion.yaml`
- Architecture diagram: `architecture.png`
- Editable diagram source: `architecture.svg`

The template's `AmiId` parameter uses `AWS::EC2::Image::Id`, allowing AWS
Marketplace to replace it with the subscribed product AMI during deployment.

## Delivery-option copy

**Title**

Private SSM EKS Admin Bastion

**Short description**

Deploy one EKS administration host in a private subnet with no public IP and no
inbound security-group rules.

**Long description**

This CloudFormation template deploys the subscribed CoreNova EKS Admin Bastion
AMI as one EC2 instance in a buyer-selected private subnet. It creates a
zero-ingress security group, an encrypted gp3 root volume, an EC2 instance role
with AmazonSSMManagedInstanceCore, and an instance profile. IMDSv2 is required
with a response hop limit of one. Operators connect through AWS Systems Manager
Session Manager.

The template can optionally create an EKS Access Entry for the shared instance
role. The default is the cluster-wide AmazonEKSViewPolicy; buyers can select an
edit or administrator policy only after reviewing the shared-role security
boundary. For a private EKS API endpoint, the template can optionally add TCP
443 from the bastion security group to an existing cluster security group.

The private subnet must provide NAT egress or VPC endpoints for Systems Manager
and every AWS API used by the administration tools. All users who can open a
shell on the instance can use its shared EC2 role credentials. Grant Session
Manager access only to trusted administrators.

**Usage instructions**

1. Select the VPC and a private subnet that can reach Systems Manager and the
   required AWS APIs.
2. Enter the existing EKS cluster name and an architecture-compatible instance
   type (`t3.small` for x86_64 or `t4g.small` for ARM64 is a normal start).
3. Keep `AmazonEKSViewPolicy` unless a reviewed operational need requires more
   access. The EKS cluster authentication mode must be `API` or
   `API_AND_CONFIG_MAP` when the template creates an Access Entry.
4. Acknowledge IAM resource creation and launch the stack.
5. Use the `StartSessionCommand` stack output, then run
   `corenova-eks-check`, `aws sts get-caller-identity`, and a read-only EKS
   command such as `kubectl get nodes`.

The stack creates an IAM role, inline EKS discovery policy, instance profile,
security group, EC2 instance, encrypted EBS volume, optional EKS Access Entry,
and optional cluster security-group ingress. It does not create an SSH key or
inbound rule.

**Costs and quotas**

Buyers pay the live AWS Marketplace software fee plus AWS infrastructure costs,
including EC2, EBS, data transfer, NAT gateway, and VPC endpoints when used.
Before launch, verify the regional EC2 On-Demand vCPU quota for the chosen
instance family and the relevant Systems Manager and EKS quotas. Request quota
increases through AWS Service Quotas if needed.

## Submission checklist

1. Rebuild both architectures with the pinned pipeline.
2. Run the no-ingress SSM smoke test and credential-residue checks.
3. Test the template with each new subscribed AMI in `us-east-1`; test every
   additional Region before enabling it.
4. Confirm the architecture diagram matches the submitted template.
5. In the new-version request, select `AMI with CloudFormation` and upload the
   template and diagram. Retain standalone AMI only as a clearly labeled private
   SSH fallback.
6. Review the generated Marketplace metadata and live offer terms.
7. Submit from a delegated seller role, never from account-root credentials.
