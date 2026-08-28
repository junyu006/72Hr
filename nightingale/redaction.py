"""PHI redaction at the boundary before text is supplied to an LLM.

Phileas performs the actual detection and replacement.  The policy combines
its built-in PII filters with local identifiers for Singapore NRIC/FIN values,
Singapore phone numbers, and honourific-prefixed names.
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping
from copy import deepcopy
from functools import lru_cache
import re
from uuid import uuid4

try:
    from phileas.policy.policy import Policy
    from phileas.services.filter_service import FilterService
except ImportError:  # Kept lazy so non-AI unit tests remain runnable without ML extras.
    Policy = None  # type: ignore[assignment,misc]
    FilterService = None  # type: ignore[assignment,misc]


class PHIRedactionUnavailable(RuntimeError):
    """Raised when text cannot safely be redacted for the LLM boundary."""


_ENTRY_ID_PATTERN = re.compile(r"entry_[0-9a-f]{8,32}")


def _redact_strategy() -> list[dict[str, str]]:
    return [{"strategy": "REDACT", "redactionFormat": "[REDACTED-%t]"}]


def phileas_policy_definition() -> dict:
    """Return the Nightingale policy without placing any patient data in it."""
    strategy = _redact_strategy()
    # Phileas 1.0 calls custom regex entries ``patterns``; 1.1 renamed that
    # section to ``identifiers`` and changed the strategy/classification keys.
    # Supplying both schemas is safe (each release ignores the unknown one) and
    # keeps the project compatible with the installed phileas-redact package.
    legacy_patterns = [
        {
            "label": "singapore-nric-fin",
            "pattern": r"(?i:\b[stfgm]\d{7}[a-z]\b)",
            "patternFilterStrategies": deepcopy(strategy),
        },
        {
            "label": "singapore-phone-number",
            "pattern": r"(?<!\w)(?:\+65[ -]?)?[689]\d{3}[ -]?\d{4}\b",
            "patternFilterStrategies": deepcopy(strategy),
        },
        {
            "label": "honorific-name",
            "pattern": r"\b(?:Mr|Ms|Mrs|Miss|Dr)\.?\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2}\b",
            "patternFilterStrategies": deepcopy(strategy),
        },
    ]
    return {
        "name": "nightingale-llm-phi-redaction",
        "identifiers": {
            "emailAddress": {"emailAddressFilterStrategies": deepcopy(strategy)},
            "phoneNumber": {"phoneNumberFilterStrategies": deepcopy(strategy)},
            "ssn": {"ssnFilterStrategies": deepcopy(strategy)},
            "passportNumber": {"passportNumberFilterStrategies": deepcopy(strategy)},
            "driversLicense": {"driversLicenseFilterStrategies": deepcopy(strategy)},
            "streetAddress": {"streetAddressFilterStrategies": deepcopy(strategy)},
            "date": {"dateFilterStrategies": deepcopy(strategy)},
            "age": {"ageFilterStrategies": deepcopy(strategy)},
            "patterns": legacy_patterns,
            # Phileas calls custom regex detectors ``identifiers`` (distinct
            # from the surrounding policy section) and expects this strategy
            # field name.  Using a generic ``patterns`` key is silently ignored.
            "identifiers": [
                {
                    "classification": "singapore-nric-fin",
                    "pattern": r"\b[stfgm]\d{7}[a-z]\b",
                    "caseSensitive": False,
                    "identifierFilterStrategies": deepcopy(strategy),
                },
                {
                    "classification": "singapore-phone-number",
                    "pattern": r"(?<!\w)(?:\+65[ -]?)?[689]\d{3}[ -]?\d{4}\b",
                    "identifierFilterStrategies": deepcopy(strategy),
                },
                {
                    "classification": "honorific-name",
                    "pattern": r"\b(?:Mr|Ms|Mrs|Miss|Dr)\.?\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2}\b",
                    "identifierFilterStrategies": deepcopy(strategy),
                },
            ],
        },
    }


@lru_cache(maxsize=1)
def _policy():
    if Policy is None:
        raise PHIRedactionUnavailable(
            "Phileas is not installed; refusing to send unredacted text to the AI model."
        )
    try:
        return Policy.from_dict(phileas_policy_definition())
    except Exception as exc:
        raise PHIRedactionUnavailable("Unable to initialise the PHI redaction policy.") from exc


def redact_for_llm(text: str) -> str:
    """Redact PHI using Phileas, or fail closed before any model invocation.

    A new service is created for each request so its in-memory context does not
    retain source tokens after the request completes.
    """
    if not isinstance(text, str):
        raise TypeError("text for PHI redaction must be a string")
    if FilterService is None:
        raise PHIRedactionUnavailable(
            "Phileas is not installed; refusing to send unredacted text to the AI model."
        )
    try:
        result = FilterService().filter(
            policy=_policy(),
            context="nightingale-llm-request",
            document_id=str(uuid4()),
            text=text,
        )
        return result.filtered_text
    except PHIRedactionUnavailable:
        raise
    except Exception as exc:
        raise PHIRedactionUnavailable("PHI redaction failed; the AI request was blocked.") from exc


def redact_glance_timeline(entries: Iterable[Mapping]) -> str:
    """Redact timeline text before adding trusted source-entry metadata.

    Entry IDs are validated application provenance, not clinical free text. They
    are appended only after Phileas runs, so policy changes cannot remove the
    citation Qwen needs to copy into its Glance output.
    """
    records: list[str] = []
    for entry in entries:
        entry_id = str(entry.get("id", ""))
        if _ENTRY_ID_PATTERN.fullmatch(entry_id) is None:
            raise PHIRedactionUnavailable(
                "Invalid entry provenance ID; the AI request was blocked."
            )
        clinical_text = f"{entry.get('created_at', '')}: {entry.get('content', '')}"
        records.append(
            f"Source Entry ID: {entry_id}\n{redact_for_llm(clinical_text)}"
        )
    return "\n\n".join(records)
