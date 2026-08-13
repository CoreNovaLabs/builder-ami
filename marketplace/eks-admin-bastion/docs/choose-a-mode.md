# Choose an access mode

Start with Identity Relay unless a recorded interactive shell is a contractual
or regulatory requirement.

| Decision | Identity Relay | Audited Workstation | Standalone AMI |
|---|---|---|---|
| EKS identity | Each operator's AWS role | Shared EC2 role | Buyer-defined; commonly shared EC2 role |
| Interactive shell on EC2 | No | Yes, non-root Run As | Buyer-defined |
| Shell command logging | Not applicable | Streams to retained CloudWatch Logs | Buyer must configure |
| Port-forward content logging | Not supported by Session Manager | Not used for the audited shell | Depends on buyer design |
| Default Kubernetes access | Optional operator Access Entry; View + namespace | View + `default` namespace | None created |
| Customer configuration | VPC, private subnet, cluster, cluster security group; optionally operator role | VPC, private subnet, cluster, cluster security group | All networking, IAM, SSM, and EKS access |
| Best fit | Production access, vendor access, individual accountability | Regulated runbooks, incident rooms, recorded shell work | Custom platform automation or legacy compatibility |

## Identity Relay

The operator runs `corenova_eks_connect.py` locally. The program reads the stack
outputs and EKS endpoint, opens an SSM remote-host tunnel, creates a temporary
0600 kubeconfig, and runs kubectl. TLS still validates the real EKS endpoint
hostname. The EC2 role includes only `AmazonSSMManagedInstanceCore` and cannot
authenticate to EKS.

CloudTrail and EKS authorization preserve the operator role. Session Manager
does not record port-forward traffic, so this mode provides identity attribution
rather than a transcript of Kubernetes requests or responses.

## Audited Workstation

The buyer starts the exact session command in the stack output. A dedicated SSM
document runs the shell as `corenova-operator`, applies idle and maximum duration
limits, and streams the standard shell session to CloudWatch Logs. The log group
is retained when the stack is deleted.

Everyone allowed to start a session on this instance can use the same EC2 role.
Edit, Admin, and ClusterAdmin selections require an explicit CloudFormation
acknowledgement. Limit `ssm:StartSession` to trusted administrators and one
tagged instance.

## Does the customer configure anything?

Yes. AWS cannot safely infer the buyer's private subnet, EKS cluster, security
group, operator IAM role, or desired Kubernetes scope. The CloudFormation form
collects those choices before launch; the buyer does not need to manually create
the EC2 instance, instance profile, zero-ingress security group, encrypted
volume, session document, or optional EKS Access Entry.
