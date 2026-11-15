# Evidence and public-safety gate

## Evidence hierarchy

Prefer the strongest available evidence:

1. An authorized test message arrived and behaved as intended in representative clients.
2. The UniSender interface showed the saved or completed state and the relevant read-back matched the canonical source.
3. A local artifact passed structural, link, token, accessibility, and rendering checks appropriate to the task.
4. The user explicitly accepted the outcome.

Preview alone is layout feedback. It does not prove delivery or Gmail/Outlook rendering.

## What becomes a learning candidate

Capture a reusable method only when it explains why the result worked. Good candidates include a stable editor workaround, a repeatable validation sequence, an email-client compatibility invariant, or a deterministic diagnostic script.

Do not capture routine execution, project status, campaign-specific copy, a one-off selector, an unexplained lucky result, or a workaround that has not been verified.

## Public-data boundary

Public skills may contain generic examples and links to public vendor documentation. They must not contain:

- subscriber names, email addresses, phone numbers, identifiers, or exports;
- API keys, cookies, bearer tokens, credentials, webhook secrets, or recovery data;
- private campaign URLs, account paths, screenshots, analytics, or business results;
- customer copy, protected templates, brand assets, or source HTML unless separately approved for public release;
- internal file paths that identify a person or organization.

Replace real values with clearly fake placeholders. Do not rely on redaction alone when the surrounding context still identifies the source.

## Promotion decision

Use these default evidence weights:

- authorized delivery test: 4;
- saved interface state plus read-back: 3;
- relevant artifact QA: 2;
- user acceptance without technical verification: 1.

Normal promotion requires two distinct task fingerprints, a total score of at least 5, and at least one technical verification. Two successes are necessary by default, not sufficient. Reject promotion if the pattern conflicts with vendor documentation, depends on undocumented account state, broadens permissions, or cannot be tested without affecting a live campaign.

An early user-approved proposal still requires one technically verified case and a score of at least 2. It remains a proposal until behavioral evals pass.

When a new observation changes only one edge case, update the narrowest existing instruction and release a patch. Do not accumulate universal rules from isolated examples.
