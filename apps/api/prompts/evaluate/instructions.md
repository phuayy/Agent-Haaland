## Task: evaluate candidate fixes

Given the diagnosis, propose two to five candidate fixes for the root cause.
For each: a one-line summary, the approach, a risk rating (low/medium/high),
and why it would resolve the root cause specifically — not just make the
symptom go away.

Select one candidate as `selected_index` and justify the selection. Prefer
the smallest change that fully addresses the root cause. A fix that touches
more files or more logic than the diagnosis calls for is a worse choice even
if it is more "thorough" — smaller diffs are easier for a human to review
correctly, and review correctness is the actual safety property here.

If this is a retry after a failed check (static analysis or test failure),
you will be given the specific failure output. Treat it as authoritative:
your previous candidate was wrong or incomplete in the way the failure
describes, and the new candidate must address that specifically.
