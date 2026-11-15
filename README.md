# UniSender Agent Skills

Public, versioned agent skills distilled from verified UniSender work. Raw task evidence stays in the private OS user-state directory; only generalized instructions, deterministic helpers, tests, and release metadata are published.

## Install

```bash
npx skills add turanaturana7-alt/unisender-agent-skills@unisender-skill-factory -g -y
```

## Learning loop

1. Complete a UniSender task and verify an observable result.
2. Capture a sanitized learning record with `learning_loop.py capture`.
3. Pass the weighted evidence gate, or prepare an explicitly approved early proposal.
4. Create or update the narrowest skill and run behavioral Codex evals.
5. Open a candidate release PR. Required checks merge it, create the tag, and publish the GitHub Release.

```bash
python skills/unisender-skill-factory/scripts/learning_loop.py status
python skills/unisender-skill-factory/scripts/eval_runner.py run \
  --skill-dir skills/unisender-skill-factory \
  --cases skills/unisender-skill-factory/evals/cases.json
python skills/unisender-skill-factory/scripts/release.py \
  --skill unisender-skill-factory \
  --bump patch \
  --summary "Clarify the promotion evidence gate" \
  --publish
```

## Safety boundary

The repository is public. It must not contain campaign HTML, contact data, credentials, private URLs, account identifiers, protected copy, screenshots, or business metrics. The repository audit blocks common secret and personal-data patterns before release, and GitHub push protection is expected to remain enabled.

## Versioning

Each skill has its own `VERSION` and `CHANGELOG.md`. Tags use `<skill>-v<version>`, for example `unisender-skill-factory-v0.1.0`.

## License

MIT
