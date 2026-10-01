import re

def score_job(job, config):
    text = " ".join([
        str(job.get("title", "")),
        str(job.get("description", "")),
        " ".join(map(str, job.get("skills", [])))
    ]).lower()

    if any(k.lower() in text for k in config.get("exclude_keywords", [])):
        return {"score": 0, "reasons": [], "risks": ["excluded keyword"]}

    score = 0
    reasons = []
    risks = []

    hits = [k for k in config.get("keywords", []) if k.lower() in text]
    score += min(45, len(hits) * 7)
    if hits:
        reasons.append("Relevant keywords: " + ", ".join(hits[:6]))

    budget = job.get("hourly_rate_max") or job.get("fixed_budget")
    if budget is not None:
        try:
            value = float(budget)
            threshold = config["min_hourly_rate_usd"] if job.get("hourly_rate_max") else config["min_fixed_budget_usd"]
            if value >= threshold:
                score += 20
                reasons.append("Budget meets minimum")
            else:
                risks.append("Budget below minimum")
        except (TypeError, ValueError):
            risks.append("Budget unclear")

    if job.get("payment_verified") is True:
        score += 15
        reasons.append("Payment verified")
    elif config.get("prefer_verified_payment"):
        risks.append("Payment verification not confirmed")

    proposals = job.get("proposals_count")
    if proposals is not None:
        try:
            p = int(proposals)
            if p <= 10:
                score += 15
                reasons.append("Low proposal competition")
            elif p >= 50:
                risks.append("High proposal competition")
        except (TypeError, ValueError):
            pass

    hires = job.get("client_hires")
    if hires is not None:
        try:
            if int(hires) > 0:
                score += 5
                reasons.append("Client has prior hires")
        except (TypeError, ValueError):
            pass

    return {"score": min(100, score), "reasons": reasons, "risks": risks}
