from __future__ import annotations


class HaalandError(Exception):
    """Base class for domain errors."""


class IllegalTransition(HaalandError):
    def __init__(self, current: str, target: str) -> None:
        super().__init__(f"illegal transition: {current} -> {target}")
        self.current = current
        self.target = target


class RemediationRejected(HaalandError):
    """Raised when a drafted patch fails post-parse policy validation
    (path traversal, denylist, file-count ceiling). docs/09 layer 1."""


class BudgetExceeded(HaalandError):
    def __init__(self, spent_usd: float, limit_usd: float, scope: str) -> None:
        super().__init__(f"{scope} budget exceeded: ${spent_usd:.2f} / ${limit_usd:.2f}")
        self.spent_usd = spent_usd
        self.limit_usd = limit_usd
        self.scope = scope


class AIRefusalError(HaalandError):
    def __init__(self, stage: str) -> None:
        super().__init__(f"model refused stage={stage}")
        self.stage = stage


class RedactionUnavailable(HaalandError):
    """Raised when the PII vault cannot be written to. Fail closed: if we
    cannot redact, we do not call the model (docs/09)."""


class ChainVerificationError(HaalandError):
    def __init__(self, incident_id: str, first_divergence_seq: int) -> None:
        super().__init__(f"audit chain broken for {incident_id} at seq={first_divergence_seq}")
        self.incident_id = incident_id
        self.first_divergence_seq = first_divergence_seq
