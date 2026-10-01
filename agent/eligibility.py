def apply_gate(job, connects_balance):
    """Return a safe application decision without spending Connects."""
    reasons = []
    if not job.get("can_apply", False):
        reasons.append("Upwork currently marks this job as not applicable")
    cost = job.get("connects_cost")
    if cost is None:
        reasons.append("Connects cost is unknown")
    elif int(connects_balance or 0) < int(cost):
        reasons.append("Insufficient Connects")
    if job.get("score", 0) <= 0:
        reasons.append("Job score is zero")
    return {
        "eligible_for_preview": not reasons,
        "eligible_for_submission": False,
        "reasons": reasons,
        "requires_user_confirmation": True,
    }
