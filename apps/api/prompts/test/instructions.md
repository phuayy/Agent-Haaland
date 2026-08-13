## Task: regression test generation

Given the failure scenario (trigger, observed symptom, root cause, the
applied fix) and an existing test file for style reference, write one
regression test that:

- Fails against the pre-fix code (it reproduces the original bug).
- Passes against the post-fix code.
- Follows the existing test file's naming, fixture, and assertion style.

The caller will run your test against both commits and discard it silently
if it does not fail-then-pass as specified — a test that passes on broken
code is worse than no test, so favour a precise, narrow assertion over a
broad one.
