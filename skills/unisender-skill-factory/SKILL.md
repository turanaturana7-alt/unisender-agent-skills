---
name: unisender-skill-factory
description: Capture reusable verified lessons after substantive UniSender work and promote them into sanitized, evaluated, semantically versioned public skills. Use at the end of a UniSender task with an observable outcome, or when reviewing learning candidates.
---

# UniSender Skill Factory

Convert evidence from completed UniSender work into small, auditable skills. A successful task is evidence, not automatic permission to generalize every detail.

## Capture a proven solution

Capture only when the final outcome is observable: a local artifact passed relevant QA, the UniSender interface showed the intended state, a user accepted the result, or an authorized delivery test arrived. Do not treat a plausible answer, preview alone, or an unfinished workaround as success.

Run `scripts/learning_loop.py capture` with a stable pattern key, problem, reusable solution, distinct task fingerprint, verification method, before/after state, evidence, and known limitation. The script stores records outside the public repository by default: the OS user-state directory, or `UNISENDER_SKILL_STATE_DIR` when configured.

Never include campaign HTML, contact data, credentials, account IDs, private URLs, client copy, screenshots, analytics exports, or merge-tag values. Abstract the method before capture.

## Decide whether to promote

Run `scripts/learning_loop.py status`. Promote a pattern only when:

- it passed the weighted evidence gate: normally two distinct tasks, score at least 5, and at least one technical verification;
- it is useful beyond one campaign and does not merely restate existing UniSender documentation;
- the evidence supports a clear decision rule, invariant, procedure, or deterministic helper;
- the public form passes the privacy and secret scan.

Use `scripts/learning_loop.py propose` to create a private proposal. Explicit user approval may create an early proposal from one technically verified case, but it cannot bypass privacy checks or behavioral evals. A proposal is not yet a public skill.

## Decision boundary

- One successful task can produce only `captured`, even when its evidence is strong. It cannot produce a proposal unless the user explicitly approves early promotion.
- `proposal prepared` means reusable skill artifacts may be drafted; it does not mean public release is allowed.
- Public release is allowed only when the evidence gate passed, the proposed skill exists, a fresh behavioral report matches its hash, the public audit and tests pass, and the release PR has merged.
- If any prerequisite is missing, `publish_allowed` is false.

## Create or update the skill

Use the installed `skill-creator` workflow. Prefer a narrow update to an existing skill when it owns the behavior; create a new skill only for a distinct reusable capability. Keep conditional detail in references and repeated deterministic logic in scripts.

Read [references/evidence-and-safety.md](references/evidence-and-safety.md) before publishing. Validate the skill structure, run its meaningful tests, and run `audit-public` across the repository.

Run the behavioral suite in `evals/cases.json` with `scripts/eval_runner.py run`. It must test explicit and implicit routing, adjacent negative requests, insufficient evidence, privacy blocking, and live-action boundaries. A candidate cannot be released unless the fresh report matches the current skill hash and every must-pass case succeeds.

## Version and publish

Use semantic versioning per skill:

- `patch`: compatible correction, clarification, or test improvement;
- `minor`: new compatible workflow, mode, script, or new skill;
- `major`: incompatible contract, invocation, output, or directory change.

Run `scripts/release.py --skill <name> --bump <patch|minor|major> --summary "..." --publish`. It verifies the current eval report, updates release metadata, creates a `codex/release/...` candidate branch and PR, and enables auto-merge after required checks. A merged release PR creates the skill-scoped tag; GitHub Actions creates the public GitHub Release. Pass `--approve-nonpatch` only when the user has approved a `minor` or `major` release.

Publishing is allowed only for generalized material that passes all gates. It never authorizes sending campaigns, changing live UniSender automation, importing contacts, or exposing private work.

## End state

After a release is observed, reinstall the published skill so the user-scoped copy does not drift from GitHub. Report one of: `captured`, `not reusable`, `waiting for more evidence`, `proposal prepared`, or `released <skill> v<version>`. State what verified the success and what remains untested.
