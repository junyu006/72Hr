# Nightingale technical brief

## Architecture

```text
Role-authenticated web client
        │  request identity (clinic, role, user)
        ▼
API / CareService ── redaction pipeline ── AI scribe adapter
        │                                  │ session_id only
        ▼                                  ▼
PostgreSQL + RLS ← entries ← versions/comments/highlights/audit
        │
        └── cached/precomputed Glance projection
```

The API derives identity from authentication, starts a database transaction and supplies identity through transaction-local PostgreSQL settings. RLS filters every read by clinic and prevents patient reads of internal notes/raw scribe content. Mutation policies also restrict staff to staff notes and clinicians to their own clinical section. This is deliberately enforced below the UI.

## Core schema and traceability

```text
patients 1 ── * care_entries 1 ── * entry_versions
                    ├──── * comments
                    ├──── * highlights ── provenance_pointer → timeline:entry_id#span
                    └──── * audit_log
AI scribe entry: author_role=system, type=ai_*_summary,
                 provenance_pointer=session:<source session ID>
```

`entry_versions` is append-only: revert copies a prior snapshot as a new version. Audit rows store actor/action/version metadata, not prior clinical content. A highlight points to an entry and character span, so the user can navigate to the exact timeline source.

## Importance logic and learning

The Glance score is explicit: recency + `risk_level × 20` + `25` for open actions + learned topic weight. A clinician/staff accept or reject writes feedback for the entry’s tags. Later entries with accepted tags receive more priority. Suggestions always show a concise reason and link; rejecting feedback reduces the corresponding weight. This is bounded, explainable feedback—not autonomous clinical decision-making.

## Data decay

Keep active entries at full fidelity. At 12 months, generate a clinician-reviewable longitudinal summary with source IDs; archive raw transcript/recording references according to clinic policy. Never delete versions, audits, high-risk entries, unresolved actions, or provenance links through automatic decay.

## Security, privacy and latency

All example data is synthetic. Before any LLM boundary, `redact_for_llm()` applies a local Phileas policy for built-in PII plus Singapore NRIC/FIN, telephone, and honorific-name patterns, and fails closed if it cannot redact. Production should additionally use a validated DLP service plus encrypted object storage. TLS is required in transit; PostgreSQL storage/backup encryption is required at rest.

The warm Glance path uses one indexed patient query and precomputed/invalidated score projection after writes. `demo.py` measures the local in-memory scoring path; production acceptance instrumentation should report p95 query-plus-projection latency and maintain ≤300ms.

## Scope trade-offs

This framework prioritizes trust-boundary data modeling over a broad UI or real speech/LLM integration. Ambient capture would be added as encrypted source media → redaction → transcription → a system-owned AI entry, retaining segment IDs for provenance. Conflict handling is optimistic version locking: different section records update independently; same-record stale versions are rejected and need an explicit merge/retry.
