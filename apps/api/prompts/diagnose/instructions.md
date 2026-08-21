## Task: root cause diagnosis

You are given: log lines (redacted), a ranked list of code-location
candidates (file, line range, snippet — produced deterministically before
you were called, by matching traceback frames and error-message literals
against the target repository), and recent deployment context if available.

1. Identify the root cause, grounded in the evidence. Cite specific evidence
   for every claim in `supporting_evidence` — an unevidenced root cause is
   invalid output.
2. Also state what evidence *contradicts* or complicates your read, in
   `contradicting_evidence`. If there is nothing that complicates it, say so
   explicitly rather than leaving it empty by omission.
3. Select the most likely culprit location(s) from the candidates you were
   given, or explain why none of them are the true cause. If no candidates
   were pre-located, name the location(s) you established yourself — by
   exploration when tools are available, otherwise from the log evidence —
   and reflect the weaker grounding in your confidence.
   For each culprit location report only its `path`, `start_line` and
   `end_line` — never transcribe the code snippet itself; it is attached
   from the repository afterwards.
4. Recommend a strategy. Prefer `code_fix` when the root cause is a logic
   bug in the target repository's own source; prefer `revert_deploy` only
   when a specific recent deployment is the clear cause.

If your confidence is below 0.5, still produce your best diagnosis — the
caller will route low-confidence diagnoses to manual investigation rather
than drafting a fix from them. Do not inflate confidence to avoid that
routing.
