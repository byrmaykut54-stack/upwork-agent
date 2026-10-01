def apply_gate(job, connects_balance, config=None):
    """Return a safe application decision without spending Connects."""
    config = config or {}
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

    min_hourly = float(config.get("min_hourly_rate_usd", 15))
    min_fixed = float(config.get("min_fixed_budget_usd", 100))

    if job.get("hourly_rate_max") is not None:
        try:
            if float(job["hourly_rate_max"]) < min_hourly:
                reasons.append("Hourly rate below configured minimum")
        except (TypeError, ValueError):
            reasons.append("Hourly rate unclear")
    elif job.get("fixed_budget") is not None:
        try:
            if float(job["fixed_budget"]) < min_fixed:
                reasons.append("Fixed budget below configured minimum")
        except (TypeError, ValueError):
            reasons.append("Fixed budget unclear")

    return {
        "eligible_for_preview": not reasons,
        "eligible_for_submission": False,
        "reasons": reasons,
        "requires_user_confirmation": True,
    }
