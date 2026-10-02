import json
from pathlib import Path

from .eligibility import apply_gate
from .job_normalizer import normalize_jobs
from .proposal import build_proposal, build_screening_drafts, qualification_check
from .scorer import score_job


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

        gate = apply_gate(job, connects_balance, config)
        job["eligibility"] = gate
        job["proposal_preview"] = build_proposal(job, profile)
        job["qualification_gaps"] = qualification_check(job, profile)
        job["screening_drafts"] = build_screening_drafts(job, profile)
        ranked.append(job)

    ranked.sort(
        key=lambda item: (
            bool(item.get("eligibility", {}).get("eligible_for_preview")),
            item.get("score", 0),
        ),
        reverse=True,
    )
    return ranked[: config.get("max_proposals_to_consider", 20)]


def preview_summary(job):
    """Return a compact, user-facing application preview."""
    eligibility = job.get("eligibility", {})
    return {
        "title": job.get("title"),
        "score": job.get("score", 0),
        "connects_cost": job.get("connects_cost"),
        "connects_balance": job.get("connects_balance"),
        "eligible_for_preview": eligibility.get("eligible_for_preview", False),
        "eligible_for_submission": False,
        "reasons": eligibility.get("reasons", []),
        "qualification_gaps": job.get("qualification_gaps", []),
        "proposal": job.get("proposal_preview", ""),
        "screening_drafts": job.get("screening_drafts", []),
        "url": job.get("url"),
    }
