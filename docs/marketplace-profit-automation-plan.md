# AWS Marketplace profit automation plan

Plan date: 2026-07-15 (Asia/Shanghai)

## Objective and guardrails

- Primary offer for the first 30 days: CoreNova SSM EKS Admin Bastion AMI,
  x86_64 and Graviton ARM64.
- Profit means AWS Marketplace seller net revenue, after Marketplace listing
  fees and refunds, exceeds the entire AWS account bill for the calendar month.
- The entire AWS account must stay below USD 30 per month before profitability.
- No paid ads, seller-side always-on EC2, NAT gateway, database, or SaaS control
  plane before the first paid agreement.
- Automatic work may read systems, research, test locally, and produce drafts.
  External publishing, pricing, Marketplace mutations, paid resources, deletes,
  private offers, and outbound email always require explicit approval.

## Verified baseline

- July 1–15 AWS unblended cost: USD 3.49; July forecast: approximately USD 6.94.
- June AWS cost: USD 16.03.
- Current recurring cost is mostly 20 EBS snapshots (410 GiB). There are no
  running EC2 instances, EBS volumes, Elastic IPs, or NAT gateways in us-east-1.
- Both EKS products are public, active, limited to us-east-1, priced at USD
  0.04 per running instance-hour, and have zero historical agreements and zero
  reviews.
- At the standard public AMI listing fee of 20 percent, seller net revenue is
  approximately USD 0.032 per instance-hour before refunds and regional fees.
  At the current July cost forecast, break-even is about 217 paid instance-hours
  per month. A 40-hour-per-month customer contributes only about USD 1.28 net.
- The website landing pages and direct Marketplace links are already live in
  English and Chinese. The website intentionally has no visitor tracking today.

## Demand evidence board

| Evidence | Buyer and pain | Commercial implication | Confidence |
|---|---|---|---|
| [Private EKS endpoint access](https://docs.aws.amazon.com/eks/latest/userguide/cluster-endpoint.html) | Private-only API traffic must originate in the VPC or a connected network; AWS explicitly lists an EC2 bastion and CloudShell VPC as access options. | The network-access problem is real, but the AMI competes with free native options. | High |
| [EKS cluster access best practices](https://docs.aws.amazon.com/eks/latest/best-practices/cluster-access-management.html) | Platform teams must combine IAM identity, EKS Access Entries, access policies, and Kubernetes RBAC without locking themselves out. | Sell preflight, repeatability, and runbooks—not merely installed tools. | High |
| [Access entry migration behavior](https://docs.aws.amazon.com/eks/latest/userguide/access-entries.html) | Existing `aws-auth` mappings are not all migrated automatically. | A migration/preflight checklist is a concrete demo and lead magnet. | High |
| [Private cluster dependency matrix](https://docs.aws.amazon.com/eks/latest/userguide/private-clusters.html) | No-egress clusters require a non-trivial set of EKS, STS, ECR, S3, EC2, Logs, and optional SSM endpoints. | Include an honest network readiness check; do not claim the AMI configures buyer networking. | High |
| [kubectl compatibility requirement](https://docs.aws.amazon.com/eks/latest/userguide/install-kubectl.html) | `kubectl` must remain within one minor version of the EKS control plane. | The version selector is a defensible EKS-specific benefit. | High |
| [Terraform EKS access regression report](https://github.com/terraform-aws-modules/terraform-aws-eks/issues/3082) | Real platform users reported `Unauthorized` after module changes and resolved it with access entries. | Use permission diagnosis in demos and content. | Medium |
| [AWS CLI kubeconfig issue](https://github.com/aws/aws-cli/issues/4843) | Local kubeconfig state produced opaque failures and substantial community engagement. | A clean, persistent operations workstation reduces local-state drift. | Medium |
| [AWS CLI SSO token issue](https://github.com/aws/aws-cli/issues/5971) | SSO login can succeed while a later assume-role chain used by `kubectl` fails. | Add caller identity, profile, token, and kubeconfig checks to the preflight. | Medium |
| [CloudShell pricing](https://aws.amazon.com/cloudshell/pricing/) and [limits](https://docs.aws.amazon.com/cloudshell/latest/userguide/limits.html) | CloudShell has no additional service fee, but VPC environments have no persistent storage, idle sessions are removed, and long sessions end. | The wedge is persistent, versioned, team-standard operations—not “kubectl without installation.” | High |
| [Session Manager capabilities](https://docs.aws.amazon.com/systems-manager/latest/userguide/session-manager.html) | SSM avoids inbound ports and SSH key management and can centralize access. | SSM is a free AWS primitive; CoreNova sells the maintained EKS workstation on top of it. | High |
| [Guacamole Bastion Marketplace listing](https://aws.amazon.com/marketplace/pp/prodview-hl2sry7k37mgq) | A broader browser/SSO/MFA bastion charges about USD 0.08 per hour and has visible reviews. | Buyers pay for access workflow and audit capability, but CoreNova must not claim feature parity. | Medium |
| [StrongDM Marketplace listing](https://aws.amazon.com/marketplace/pp/prodview-57vja26o4xz66) | Enterprise buyers pay annual contracts for centralized infrastructure access and audit. | There is budget for the problem; CoreNova targets smaller teams below the enterprise platform threshold. | Medium |

## Competitor and substitute map

| Substitute | Public price signal | CoreNova response |
|---|---:|---|
| AWS CloudShell VPC | No extra CloudShell fee | Persistent disk, stable versions, team baseline, longer-running operations |
| DIY AL2023 + SSM | AWS infrastructure only | Supported image, pinned/checksummed tools, EKS preflight, examples, update cadence |
| [Solve DevOps Bastion](https://aws.amazon.com/marketplace/pp/prodview-r3g6qfickx33o) | About USD 0.014/hour | Do not compete on lowest price; demonstrate EKS-specific time saved |
| [Prezelfy AL2023 Bastion](https://aws.amazon.com/marketplace/pp/prodview-x6dxg4oafucjm) | About USD 0.022/hour | EKS-specific tooling, access entry guidance, x86 and ARM options |
| [netCUBED Guacamole](https://aws.amazon.com/marketplace/pp/prodview-hl2sry7k37mgq) | About USD 0.08/hour on recommended instance | Simpler buyer-account deployment without browser gateway or centralized SaaS claims |
| StrongDM / Teleport / Boundary | Annual enterprise contracts | Narrow self-service workstation; never claim PAM, JIT, session recording, or zero-trust equivalence |

## Opportunity score

Using the solo-founder weighted framework, the current offer scores 76/100:

| Dimension | Score (1–5) | Reason |
|---|---:|---|
| Pain urgency | 4 | Private endpoint reachability and access lockout can block operations. |
| Willingness to pay | 3 | Paid adjacent products exist, but free CloudShell and DIY EC2 cap pricing. |
| Marketplace fit | 4 | The software runs in the buyer account and procurement is AWS-native. |
| Solo-founder buildability | 5 | The AMIs and deployment assets already exist. |
| Support burden | 4 | Self-service is feasible if networking/IAM boundaries are explicit. |
| Competitive gap | 3 | The EKS-specific middle tier exists but is narrow. |
| Distribution reach | 3 | Platform teams and MSPs are identifiable, but Marketplace discovery alone is weak. |
| Risk containment | 4 | Buyer-controlled account, no seller control plane, and minimal data custody. |

Decision: validate aggressively for 30 days; do not expand the product family or
build a SaaS control plane yet.

## Thirty-day operating plan

### Foundation: days 1–4

1. Create a dedicated private `CoreNovaLabs/builder-ami` repository.
2. Create least-privilege GitHub OIDC roles for scheduled read-only checks,
   build, smoke test, and Catalog `VALIDATE`. Do not create an automated
   Marketplace publisher role.
3. Establish a non-root human administration path, verify it, and then remove
   the active root access key.
4. Finish tightening the Builder temporary-resource policy and replace the
   smoke instance's broad AWS-managed SSM boundary with a reviewed minimum
   custom policy.
5. Rebuild one architecture at a time, run the zero-ingress SSM smoke test,
   and submit Catalog `VALIDATE`. The cost-capped seller smoke path uses an
   ephemeral public IPv4 address for outbound SSM connectivity instead of a
   persistent NAT gateway or paid VPC endpoints. A build may run only while the
   monthly forecast is below USD 20 and its estimated incremental cost is below
   USD 5.
6. Configure free AWS Budget alerts at USD 20, USD 24, and USD 27. The hard
   target remains USD 30; billing data is delayed, so the guard acts early.

### Offer and proof: days 5–10

1. Publish the validated AMI versions only after explicit approval.
2. Request a 14-day software-fee free trial for both architectures. Buyers still
   pay their AWS infrastructure costs.
3. Keep USD 0.04/hour during the first test so messaging and trial are the only
   variables. Do not lower the price and introduce the trial simultaneously.
4. Add a concise CloudShell comparison, a 10-minute EKS access preflight demo,
   a sample diagnostic output, and exact buyer-responsibility boundaries to the
   landing page.
5. Publish a small open-source `corenova-eks-check` diagnostic or sample output
   without credentials, customer data, or unsupported compliance claims.

### Demand validation: days 8–21

1. Build a list of 20 qualified targets: small AWS MSPs, EKS consultants,
   fractional CTOs, and 2–20 person platform teams operating private EKS.
2. Research and draft no more than five personalized messages per batch. The
   user approves every outbound batch; do not buy lists or scrape gated data.
3. Offer a 20-minute walkthrough and a 14-day trial, not a generic product pitch.
   Lead with private endpoint reachability, access-entry preflight, stable tool
   versions, and persistent operation compared with CloudShell.
4. For a qualified buyer willing to commit, prefer a negotiated private offer:
   standard public AMI transactions have a 20 percent listing fee, while
   private offers below USD 1 million currently have a 3 percent fee.

### Decision: days 22–30

- Continue if there is at least one paid agreement, or at least two real trial
  deployments plus explicit price acceptance.
- If there are qualified conversations but price resistance, test USD
  0.029/hour for new subscribers after a separate approval.
- If there are no qualified replies after 20 well-targeted contacts, stop AMI
  feature work and test a fixed-scope private EKS access-readiness service.
- If prospects consistently choose CloudShell, narrow the product to persistent
  multi-cluster operations and preflight, or stop the offer rather than adding
  generic features.

## Automation set to create after plan approval

### 1. AWS cost guard

- Frequency: daily at 08:15 Asia/Shanghai. One cached current-month cost query
  and one forecast query, approximately USD 0.60/month in Cost Explorer API
  calls.
- Output: current spend, forecast, change since last run, cost by material
  service, and charge-bearing resource inventory.
- Rules: USD 20 warning; USD 24 freeze recommendation; USD 27 emergency cleanup
  plan; USD 30 incident. It never changes or deletes resources.

### 2. Marketplace health and agreement monitor

- Frequency: daily at 09:00 Asia/Shanghai.
- Checks: two product and offer entities, public listing HTTP status, pending or
  failed change sets, AMI availability, and proposer-side purchase agreements.
- It reports only changes and never calls `StartChangeSet`.

### 3. Demand and conversion experiment

- Frequency: Tuesday and Thursday at 10:00 Asia/Shanghai.
- Produces one evidence-backed ICP hypothesis, objection, comparison, content
  draft, target list increment, and seven-day success criterion.
- It may modify only local drafts. It does not publish the site, post to social
  networks, or contact prospects.

### 4. AMI freshness and security review

- Frequency: Tuesday at 14:00 Asia/Shanghai.
- Compares upstream AL2023/tool versions, Marketplace requirements, local
  Packer/Ansible pins, and current image age. It proposes a rebuild but cannot
  start one or create AWS resources.

### 5. Marketplace profit review

- Frequency: Friday at 17:30 Asia/Shanghai.
- Reuses cached task state rather than issuing duplicate Cost Explorer queries.
- Reports seller net revenue, total AWS cost, profit, agreements, trial state,
  qualified contacts, replies, walkthroughs, deployments, and the next three
  actions.

The existing `AWS Marketplace Public Rollout` automation remains paused and is
not reused for ongoing operations.

## KPI and stop-loss table

| Metric | Day 14 target | Day 30 target |
|---|---:|---:|
| Qualified target accounts | 10 | 20 |
| Approved personalized outreach | 5 | 20 |
| Meaningful replies | 2 | 5 |
| Walkthroughs | 1 | 3 |
| Real trial deployments | 1 | 2 |
| Paid agreements | 0–1 | at least 1 |
| AWS monthly forecast | below USD 20 | below USD 20, hard limit USD 30 |

No more than two paid AMI rebuild cycles are allowed in a calendar month before
revenue. Old AMIs or snapshots are deleted only after dependency mapping and
explicit approval.

## Remaining integration constraint

The configured QQ Mail Agent reads `zhengyihui@agent.qq.com`; it does not have
access to `support@corenovacloud.com` or `hlikex@qq.com`. It can prepare a
message to `hlikex@qq.com`, but every send requires two-stage confirmation.
Automated lead inbox triage must wait until the support mailbox is connected or
forwards into an authorized inbox. Until then, Codex task notifications are the
primary alert channel.
