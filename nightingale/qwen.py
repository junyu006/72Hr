"""Local Qwen2.5 inference for synthetic, redacted care-note summaries."""
from __future__ import annotations

import os
from functools import lru_cache
MODEL_ID = "Qwen/Qwen2.5-0.5B-Instruct"


class ModelUnavailable(RuntimeError):
    pass


@lru_cache(maxsize=1)
def _pipeline():
    try:
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer, pipeline
        device = -1
        tokenizer = AutoTokenizer.from_pretrained(MODEL_ID)
        model = AutoModelForCausalLM.from_pretrained(MODEL_ID, device_map="auto")
        print("tokenizer and model complete")
        return pipeline("text-generation", model=model, tokenizer=tokenizer, device=device)
    except Exception as exc:
        raise ModelUnavailable("Unable to load Qwen2.5-0.5B-Instruct. Check the local model cache and Transformers installation.") from exc


def _generate(prompt: str, tokens: int) -> str:
    print("starting to generate")
    result = _pipeline()([{"role": "user", "content": prompt}], max_new_tokens=tokens, do_sample=False)
    value = result[0]["generated_text"]
    return str(value[-1]["content"] if isinstance(value, list) else value).strip()


def generate_scribe(redacted_text: str, interaction_type: str) -> str:
    if interaction_type in {"doctor_patient_consult", "nurse_patient_consult", "ai_doctor_consult_summary", "ai_nurse_consult_summary"}:
        prompt = (
            "You are a clinical documentation assistant. Summarize only the following "
            "redacted synthetic consult in one short paragraph of no more than three "
            "sentences. Include only the main concern, essential facts, and immediate "
            "follow-up. Do not diagnose, prescribe, add a heading, invent a source ID, "
            "or replace clinical judgment. Use English and stay under 60 words."
            f"\nInteraction type: {interaction_type}\nRedacted source:\n{redacted_text[:6000]}"
        )
        return _generate(prompt, 80)
    return _generate("You are a clinical documentation assistant. Summarize only the following redacted synthetic interaction. Do not diagnose, prescribe, or replace clinical judgment. Use English and no more than five concise bullets: change/concern, key facts, items to confirm, and suggested follow-up. Word limit is 100 words" + f"\nInteraction type: {interaction_type}\nRedacted source:\n{redacted_text[:6000]}", 128)


def generate_glance(redacted_timeline: str) -> str:
    return _generate("You are a clinical documentation assistant. Use only the following redacted synthetic longitudinal record to create a clinician-readable glance view. Do not diagnose. Provide at most three items in this exact format: Priority | reason | source entry ID. Prioritize open actions, allergies/risks, and recent changes. Word limit is 100 words" + f"\nRecord:\n{redacted_timeline[:8000]}", 96)