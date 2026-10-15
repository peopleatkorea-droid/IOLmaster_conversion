# Repository instructions

## Agent-requested Codex review

Owner directive (2026-10-15, updated): reduce Codex review requests by at least 70% against the recent near-every-PR baseline. The authoring agent still classifies the complete final diff, but ordinary changes are skipped by default and scarce review requests go to the highest risks. This supersedes the earlier "skip only clearly trivial; uncertainty always means review" rule.

### Shared review budget: at most one request per four PRs

- Keep repository automatic Code Review disabled, including review on new pushes. Use author-requested reviews only; never review draft PRs.
- Apply one shared budget across all repositories owned by `peopleatkorea-droid`, not a separate allowance for every repository or agent. The policy starts at `2026-10-15T02:23:00Z`. Before each request, use GitHub records for the trailing 30 days, truncated at that start time.
- Let `N` be distinct non-draft PRs created in that window against their repository's default branch that are currently open or merged. Exclude closed-unmerged PRs, duplicates and empty/dummy PRs. Let `R` be Codex review invocations requested in that window across the same owner's repositories, including invocations on older PRs. Count pending requests, retries, failed runs and re-reviews separately; include known human/automatic requests as well. A new agent-initiated request is allowed only when `R + 1 <= floor(N / 4)`. Never borrow future PRs or reset the allowance by switching repositories, agents or calendar months.
- Check current requests and running/completed summaries immediately before posting. Record the counted PR/request links and the budget timestamp in the PR body so another author can verify the allowance. If records are incomplete or another active author may have consumed the last slot, skip the request until the count is reliable. Do not infer zero usage from a missing summary.
- A slot is a ceiling, not a reason to request review. Never split work, open filler PRs, or request routine reviews to fill it. No automatic risk exception bypasses the budget. Only an explicit user request for a particular additional review can override it; count that invocation and report the exception.
- The historical comparison was 370 reviewed PRs out of 419 PRs. A 25% PR allowance would permit at most 104 requests at that volume (about 72% fewer). This is a volume-based target, not a measured future saving or a guarantee of the same reduction in cost; review size and explicit overrides can change the result.

### Allocate by risk from the final diff

- Inspect every changed file/hunk against the current PR base, including all commits, generated files, renames and assets. Do not classify by title, line count, extension or absence of previous findings. Reassess after the last push and relevant base changes.
- Give available slots first to concrete risks of unauthorized access/secret exposure, payment or billing errors, irreversible data loss/corruption or migrations, cross-user/project data isolation, or scientific/clinical calculation, units or interpretation errors. A change in these areas is a priority candidate, not an automatic budget exemption.
- Consider another change only when the complete diff shows a credible major failure with weak local verification: for example broad concurrency/state changes, an unverified dependency/deployment change, or AI routing/prompt changes with major safety/data consequences. Merely touching runtime code, dependencies, configuration, prompts, tests or agent instructions does not require Codex review.
- Skip ordinary UI/features, routine fixes/refactoring, performance tuning, test additions, documentation, copy and cosmetics when local verification adequately covers their risk. Uncertainty alone no longer triggers Codex: inspect context and run proportionate local checks, then prioritize any remaining concrete high risk within the budget.
- Skipping Codex never waives sufficient local verification or existing merge gates. Resolve or report remaining risks under the existing merge policy; do not merge an unsafe change merely to meet the reduction target. Do not describe an unreviewed change as reviewed or risk-free.

### Request once, when ready

- Finish the changes and local checks, then make the PR ready before an allowed `@codex review` request. Inspect existing requests and reviewed commits first; never duplicate a running request or request after every push.
- Batch follow-up fixes. Do not automatically re-request after findings, resolved conversations or cosmetic updates. A materially new high-risk diff may justify another request only after checking the shared budget again; it consumes another invocation. Assess available findings before merging and do not claim an old review covers new changes.
- Keep one decision record in the PR body: `Codex review: skipped (routine / budget / insufficient accounting)`, `requested`, or `already reviewed`; include risk/reason, final head SHA, relevant paths, local verification, `N`, `R`, `floor(N / 4)`, counting timestamp and evidence links when requesting. Record explicit user overrides separately.
- Feedback remains advisory. Do not add Codex as a required check/approval, bypass existing gates or claim a failed/unavailable review passed. Report unavailable review evidence accurately.

### Keep execution policy

- Keep PR review classification in the authoring agent, not a GitHub Action. Do not add automatic PR/push/schedule triggers or dispatch hosted workflows without an explicit hosted-run request.
- The existing `.github/workflows/publish-biometry-ood.yml` release trigger for `biometry-ood-v*` tags is outside this PR-review policy change. Preserve that documented release path; do not remove, broaden, or invoke it while applying these review rules. Normal PR review work remains manual with respect to Actions.
- Keep existing local verification, security scans, dependency audits, branch protections and independent security-review settings. This policy changes Code Review invocation only.
