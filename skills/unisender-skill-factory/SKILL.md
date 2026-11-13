---
name: unisender-skill-factory
description: Capture verified UniSender task successes, identify reusable patterns, and turn them into sanitized, tested, semantically versioned public agent skills. Use after a UniSender workflow has an observable successful outcome or when reviewing accumulated UniSender learning candidates. Do not use for raw session logging or unverified ideas.
---

# UniSender Skill Factory

Convert evidence from completed UniSender work into small, auditable skills. A successful task is evidence, not automatic permission to generalize every detail.

## Capture a proven solution

Capture only when the final outcome is observable: a local artifact passed relevant QA, the UniSender interface showed the intended state, a user accepted the result, or an authorized delivery test arrived. Do not treat a plausible answer, preview alone, or an unfinished workaround as success.

Run `scripts/learning_loop.py capture` with a stable pattern key, a one-sentence problem, the reusable solution, distinct task fingerprint, verification method, and concise evidence. The script stores records in the gitignored `.skill-learning/` directory by default.

Never include campaign HTML, contact data, credentials, account IDs, private URLs, client copy, screenshots, analytics exports, or merge-tag values. Abstract the method before capture.

## Decide whether to promote

Run `scripts/learning_loop.py status`. Promote a pattern only when:

- it succeeded in at least two distinct tasks, or the user explicitly approves early promotion;
- it is useful beyond one campaign and does not merely restate existing UniSender documentation;
- the evidence supports a clear decision rule, invariant, procedure, or deterministic helper;
- the public form passes the privacy and secret scan.

Use `scripts/learning_loop.py propose` to create a private proposal. A proposal is not yet a public skill.

## Create or update the skill

Use the installed `skill-creator` workflow. Prefer a narrow update to an existing skill when it owns the behavior; create a new skill only for a distinct reusable capability. Keep conditional detail in references and repeated deterministic logic in scripts.

Read [references/evidence-and-safety.md](references/evidence-and-safety.md) before publishing. Validate the skill structure, run its meaningful tests, and run `audit-public` across the repository.

## Version and publish

Use semantic versioning per skill:

- `patch`: compatible correction, clarification, or test improvement;
- `minor`: new compatible workflow, mode, script, or new skill;
- `major`: incompatible contract, invocation, output, or directory change.

Run `scripts/release.py --skill <name> --bump <patch|minor|major> --summary "..." --publish`. It updates the skill version and changelog, validates the repository, commits the release, creates a skill-scoped tag, and pushes it. GitHub Actions creates the public GitHub Release from the tag.

Publishing is allowed only for generalized material that passes all gates. It never authorizes sending campaigns, changing live UniSender automation, importing contacts, or exposing private work.

## End state

Report one of: `captured`, `not reusable`, `waiting for more evidence`, `proposal prepared`, or `released <skill> v<version>`. State what verified the success and what remains untested.
