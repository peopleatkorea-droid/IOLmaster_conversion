# Repository instructions

## Agent-requested Codex review

Owner directive (2026-10-15): the PR authoring agent decides from the complete final diff whether to request Codex review. Skip only changes that are clearly trivial; uncertainty always means review.

### Classify the final diff

- Inspect every changed file and hunk against the current PR base, including generated files, renames, assets, and all commits. Do not decide from the title, author summary, line count, file extension, or absence of previous findings. If any part cannot be inspected or its effect is unclear, request review.
- Skip only when the entire diff is demonstrably nonfunctional: ordinary documentation spelling/formatting, public descriptive copy, decorative static assets, or isolated cosmetic styling that preserves behavior, accessibility, focus/input, visibility, responsive layout, and performance.
- Request review for runtime behavior, authentication/authorization, billing, data identity/storage/deletion/import/export, concurrency/caching, calculation logic or units, scientific/clinical interpretation, AI prompts/model routing, dependencies/lockfiles, configuration/build/deployment/security, agent instructions, and validation criteria. Documentation, copy, or assets affecting commands, download/link destinations, legal/security/clinical claims, or safety notices are not automatically trivial. Mixed or ambiguous diffs require review.
- Reassess after the last push and after relevant base changes. Record the decision, current head SHA, affected paths, and a short reason in the PR body: `Codex review: skipped (clearly trivial)`, `requested`, or `already reviewed`. Do not claim a previous review covers new risky changes.

### Request once when ready

- Repository automatic Code Review is intentionally disabled for this author-directed workflow. Do not turn it back on as a shortcut. Keep the GitHub/Codex connection available for manual requests.
- Do not request reviews while the PR is a draft. For a review-required PR, finish the changes and local checks, mark it ready, then post one `@codex review` comment.
- First inspect existing requests, running/completed summaries, and reviewed commits. Reuse a review that covers the intended changes; do not duplicate a running request or request both automatically and manually.
- After additional changes, re-request only when a completed review no longer covers a meaningful or uncertain change. Batch fixes and request once; never request after every push, resolved conversation, or cosmetic follow-up, and do not run a review/fix/re-review loop.
- Read and assess available findings before merging. Review feedback remains advisory: do not add Codex as a required check or approval, bypass existing gates, or claim an unavailable review passed. Report a missing/failed review and its limitation explicitly.

### Keep execution policy

- Preserve the owner's manual-only GitHub Actions policy. Do not add automatic PR/push/schedule triggers or dispatch hosted workflows without an explicit hosted-run request. This review decision runs in the authoring agent, not a new Action.
- Keep existing local verification, security scans, dependency audits, branch protections, and independent security-review settings. This policy changes Code Review invocation, not those controls.
