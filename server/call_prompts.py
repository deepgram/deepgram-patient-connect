"""Opening line and Bedrock system prompt for promotion calls."""

from __future__ import annotations

import json
from typing import Any


def opening_greeting(record: dict[str, Any]) -> str:
    first = (record.get("patient") or {}).get("first_name") or "there"
    return (
        f"Hello {first}, this is the Deepgram patient agent, calling from Deepgram Pharmacy. "
        f"How are you doing today?"
    )


def bedrock_system_prompt(record: dict[str, Any]) -> str:
    patient = record.get("patient") or {}
    clinical = record.get("clinical") or {}
    promotion = record.get("promotion") or {}
    call = record.get("call") or {}

    ctx = {
        "record_id": record.get("record_id"),
        "patient_first_name": patient.get("first_name"),
        "state": patient.get("state"),
        "primary_condition": clinical.get("primary_condition"),
        "drug": promotion.get("drug_name"),
        "manufacturer": promotion.get("manufacturer"),
        "benefit_summary": promotion.get("benefit_description"),
        "eligibility_criteria": promotion.get("eligibility_criteria"),
        "call_scenario": call.get("scenario_label"),
        "agent_notes": call.get("agent_notes"),
    }

    return f"""You are the Deepgram patient outreach agent calling from Deepgram Pharmacy about a savings program.

Patient and program context (JSON):
{json.dumps(ctx, indent=2)}

Rules:
- Continue naturally after your opening (described below in the session instructions). Do not repeat the full introduction unless they ask who you are.
- Be warm, brief, and respectful. Do not diagnose or give medical advice.
- Explain the program benefits clearly and answer questions about eligibility and next steps.
- If the patient declines, thank them and offer to send information by mail or end the call politely.
- Keep each reply under about 4 sentences unless they ask for detail.
"""


def bedrock_fallback_reply(record: dict[str, Any], user_text: str) -> str:
    """Used when BEDROCK_MODEL_ID is not configured."""
    drug = (record.get("promotion") or {}).get("drug_name", "this medication")
    return (
        f"I appreciate you sharing that. I wanted to reach out about a savings option that may apply to {drug}. "
        f"Would you like a quick overview of the benefit, or do you have questions about your coverage?"
    )
