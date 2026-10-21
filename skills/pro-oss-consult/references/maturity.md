# Five maturity stages

Separately from the scores, state "which stage it is at now, and what comes first to reach the next one".
**Fill the gaps in the current stage first, then move on to the next stage's prerequisites.** Skipping stages
to build governance first is an anti-pattern.

Basis: Mattermost, Kubernetes, Rust, React, Django, Grafana, Supabase, Terraform, VS Code, ripgrep, bat (as of research on 2026-09-30).

## Stage table

The **M column** under "What to have" lists **item numbers from `rubric.md`**. Use an item for the stage verdict only when it is M for that repo type
(the rubric tables are the source of truth for M/S by type). The S column is recommended, so it is not used for the verdict; use it for prerequisites and improvements.

| Stage | What to have: M (rubric items) | What to have: S | Before moving to the next stage (prerequisites) |
|---|---|---|---|
| **0 Personal** | For a public repo, **E1 license chosen** and **E5 no secrets**. (Not applicable to private personal repos) | One-line build and test, basic CI (D6) | **Choose the license first.** Changing it after outside contributions pile up leads to forks, as with Terraform → OpenTofu |
| **1 Ready to publish** | **A1 · A2 · A5** README (value proposition, audience language, install, usage), **A6** About description and topics, **E2** a recognized LICENSE file, **F1** releases (only `app` · `cli` · `tool` · `ai` · `template`) | F2 CHANGELOG or release notes, E6 SECURITY.md (with a reporting channel) | Document the release procedure. Move questions out of issues (Discussions) (C7). Turn on a dependency bot (F3) |
| **2 Ready for contributions** | **C1** a practical CONTRIBUTING, **C2** yml issue forms (M only for `app` · `product`), **D6** tests and CI, **C10** agent guidance (only `ai` · `template`), **C9** AI contribution policy (only `ai`) | C3 · C4 · C5, D1 ARCHITECTURE.md, D2 extension guide | A second maintainer (removes single-person dependency, F5), **C8 CODE_OF_CONDUCT**, measure time to first response |
| **3 Community** | No matching rubric items. See "Stages 3 and 4" below | Forum or chat, public roadmap, lightweight RFC process, triage bot, stated security support scope, documentation site | Role ladder and decision rules, LTS and deprecation policy, who owns the trademark and infrastructure |
| **4 Governance** | No matching rubric items | GOVERNANCE.md, OWNERS-based permissions, formal RFCs (KEP · DEP), foundation or sponsorship, limits on any single company's share | |

## Verdict rules

- Stage N counts only when **every item in stage N's "M column"** is met. If even one is missing, it is N-1. "Partial" is not met.
- **The license spans two stages without contradiction.** E1 (has a license been chosen) is M at **stage 0**, and E2 (a file form GitHub recognizes) is
  M at stage 1. **A public repo with no license does not even pass stage 0.** It is public with no permission to use it, so
  write "did not pass stage 0" instead of a stage, and make it the top defect.
- **Stages 3 and 4 have no M items in the rubric.** These stages only matter once real outside contributors exist, so the agent records
  whether the evidence (roadmap, RFCs, GOVERNANCE and so on) is "present/absent", with reasons. Do not assign stage 3 or higher without evidence.
- Most of the user's repos are at stage 0–1. A realistic goal for a representative repo is stage 2. Suggest stage 3 and above only after
  real outside contributors appear.
- Do not assign a stage to `study` repos.
- **Recommend CODE_OF_CONDUCT only after stage 2 is complete (as the 2→3 prerequisite).** Do not create it first in a repo with no contributors.

## Anti-patterns (point them out when you see them; other documents refer to this list)

- Building GOVERNANCE or RFCs when there are no contributors
- Growing labels to dozens with no bot
- Filling empty templates to raise the health score
- Labeling `good first issue` and then leaving it unattended
- Bulk-closing stale issues without announcing the rule
- Changing the license after outside contributions pile up
- Using the issue tracker as a customer support desk
- Having no policy on AI-generated PRs
