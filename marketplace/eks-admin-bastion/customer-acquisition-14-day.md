# EKS Admin Bastion: first-customer sprint

Goal: obtain three qualified walkthroughs, two real deployments, and the first
paid agreement. Do not measure success by the number of public listings.

## Offer

Lead with one outcome:

> Replace a public SSH EKS jump host with a private, SSM-first administration
> workstation in the customer's own AWS account.

The two architecture listings are variants of one product, not two separate
campaigns. Keep the live price at USD 0.04 per running instance-hour and request
a 14-day trial. For the first three design partners, include a 20-minute
architecture review and launch walkthrough at no professional-services charge.

## Days 1–3: make the product credible

- Deploy the revised bilingual landing page and verify both direct Marketplace
  links.
- Rebuild and smoke-test both AMIs; verify pinned tool downloads and the
  `corenova-eks-check` failure path.
- Validate the CloudFormation template and perform one x86_64 and one ARM64 test
  deployment in a non-production EKS environment.
- Submit the 14-day trial request to Seller Operations only after those checks.
- Update Marketplace metadata only after the landing page returns HTTP 200.

## Days 4–10: recruit design partners

Contact 20–30 narrowly qualified people, one-to-one. Prioritize small platform
teams, MSPs, and AWS consultancies that already operate EKS and mention bastions,
private clusters, SSM, or regulated access in public job posts or technical
content. Do not buy a generic mailing list.

Short outreach:

> We built a private EKS administration host that is reached through AWS Systems
> Manager, with kubectl/Helm/eksctl/k9s already versioned and checked. It is aimed
> at teams replacing public SSH jump hosts. If that is a live problem for you, I
> can review your current access path in 20 minutes and help launch a trial in
> your AWS account. No credentials or customer data leave the account.

Ask for a walkthrough, not an immediate purchase. During the call, capture:

1. How administrators reach private EKS endpoints today.
2. Who can enter the jump host and how individual actions are audited.
3. How often tools drift or are rebuilt.
4. Whether a shared instance role is acceptable; if not, do not force this
   product into the account.
5. What approval is needed to buy through AWS Marketplace.

## Days 11–14: convert evidence

- Personally help qualified prospects deploy; stop after the read-only
  `kubectl get nodes` check unless the customer authorizes more.
- Record time-to-first-session, deployment failures, objections, and the exact
  feature that triggered interest.
- Ask successful design partners for permission to publish an anonymized result,
  such as deployment time or removal of inbound SSH—not a vague testimonial.
- Follow up with one clear next step: continue as a paid Marketplace subscriber,
  remove the trial stack, or schedule a security review.

## Weekly scorecard and decision rule

- 20 qualified contacts
- 5 substantive replies
- 3 walkthroughs
- 2 successful deployments
- 1 paid agreement

If 20 qualified contacts produce fewer than three substantive replies, change
the message or target segment. If calls happen but deployments do not, fix the
onboarding. If deployments happen but nobody pays, interview on price and
ongoing value before building another Marketplace product.
