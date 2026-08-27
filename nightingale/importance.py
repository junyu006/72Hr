from __future__ import annotations

from datetime import datetime, timezone

from .domain import Entry


def importance(entry: Entry, learned_weights: dict[str, int]) -> tuple[float, str]:
    age_days = max(0, (datetime.now(timezone.utc) - entry.created_at).total_seconds() / 86400)
    score = max(0, 20 - age_days) + entry.risk_level * 20 + (25 if entry.open_action else 0)
    score += sum(max(0, learned_weights.get(tag, 0)) * 5 for tag in entry.tags)
    reasons = []
    if entry.risk_level: reasons.append(f"risk level {entry.risk_level}")
    if entry.open_action: reasons.append("open action")
    if entry.tags & learned_weights.keys(): reasons.append("clinician-confirmed topic")
    return score, "; ".join(reasons) or "recent clinical context"
