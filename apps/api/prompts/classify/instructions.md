## Task: severity classification

Given the evidence bundle (log signatures, affected service, deploy
context), classify the incident.

| Level | Definition |
|---|---|
| P1 | Customer-facing outage or funds/data-integrity impact. |
| P2 | Significant degradation, no data loss. |
| P3 | Elevated errors within error budget, single non-critical service. |
| P4 | Informational, self-recovered, or a known flapping signal. |

When you are unsure, prefer a higher (more severe) rating — the cost of
waking a human unnecessarily is far lower than the cost of missing a real
outage. State your rationale in one to three sentences, grounded in the
specific evidence you were given.
