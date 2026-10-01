import json
from pathlib import Path

from eligibility import apply_gate
from job_normalizer import normalize_jobs
from proposal import build_proposal, build_screening_drafts, qualification_check
from scorer import score_job


ROOT = Path(__file__).resolve().parent


def run_pipeline(raw_jobs, config=None, profile=None, connects_balance=0):
    """Build a safe, preview-only application queue from raw Upwork jobs."""
    if config is None:
        config = json.loads((ROOT / "config.json").read_text())
    if profile is None:
        profile = json.loads((ROOT / "profile.json").read_text())

    ranked = []
    for raw_job in raw_jobs:
        job = normalize_jobs([raw_job])[0]
        score = score_job(job, config)
        job = {**job, **score}
        gate = apply_gate(job, connects_balance)
        job["eligibility"] = gate
        job["proposal_preview"] = build_proposal(job, profile)
        job["qualification_gaps"] = qualification_check(job, profile)
        job["screening_drafts"] = build_screening_drafts(job, profile)
        ranked.append(job)

    ranked.sort(key=lambda item: item.get("score", 0), reverse=True)
    return ranked[: config.get("max_proposals_to_consider", 20)]
