## Task: draft the remediation

Turn the selected fix candidate into concrete file changes.

- Provide the full new content for each file you change — the caller
  computes the actual diff against the real base commit; you do not need to
  produce a diff yourself, and a diff you did produce would be discarded.
- `action` is `modify` for an existing file being edited, or `revert` for
  restoring a file to a prior known-good state. There is no `delete` and no
  way to express running a command — those are not present in your schema.
- Touch no more than 10 files. If the true fix needs more than that, it is
  not a remediation — set a lower-risk, narrower strategy instead and note
  in `risk_assessment` that broader changes are out of scope for automated
  drafting.
- Write `pr_body_markdown` for a human reviewer: what broke, why, what this
  changes, and how to verify it. Assume the reader has not seen the
  diagnosis.
