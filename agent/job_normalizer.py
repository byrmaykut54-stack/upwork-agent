def _as_int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _as_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _first(*values):
    for value in values:
        if value not in (None, "", []):
            return value
    return None


def normalize_job(raw):
    posting = raw.get("data", {}).get("marketplaceJobPosting", raw)
    client = posting.get("client", {}) or {}
    budget = posting.get("budget", {}) or {}
    hourly = posting.get("hourlyRate", {}) or {}
    skills = posting.get("skills", []) or []
    if isinstance(skills, list):
        skills = [s.get("name", s) if isinstance(s, dict) else s for s in skills]
    proposals = _first(posting.get("proposalsCount"), posting.get("proposals_count"), raw.get("proposals_count"))
    client_hires = _first(client.get("totalHires"), client.get("hires"), posting.get("clientHires"), raw.get("client_hires"))
    fixed_budget = _first(budget.get("amount"), posting.get("fixedBudget"), raw.get("fixed_budget"))
    hourly_max = _first(hourly.get("max"), posting.get("hourlyRateMax"), raw.get("hourly_rate_max"))
    return {
        "id": _first(posting.get("id"), raw.get("id")),
        "title": _first(posting.get("title"), raw.get("title"), "Untitled"),
        "description": _first(posting.get("description"), raw.get("description"), ""),
        "skills": skills,
        "hourly_rate_min": _as_float(_first(hourly.get("min"), posting.get("hourlyRateMin"), raw.get("hourly_rate_min"))),
        "hourly_rate_max": _as_float(hourly_max),
        "fixed_budget": _as_float(fixed_budget),
        "payment_verified": _first(client.get("paymentVerified"), posting.get("paymentVerified"), raw.get("payment_verified")),
        "proposals_count": _as_int(proposals),
        "client_hires": _as_int(client_hires),
        "client_rating": _as_float(_first(client.get("rating"), posting.get("clientRating"), raw.get("client_rating"))),
        "connects_cost": _as_int(_first(posting.get("connectsCost"), raw.get("connects_cost"))),
        "can_apply": _first(posting.get("canApply"), raw.get("can_apply")),
        "preferred_qualifications": posting.get("preferredQualifications", raw.get("preferred_qualifications", {})) or {},
        "screening_questions": posting.get("screeningQuestions", raw.get("screening_questions", [])) or [],
        "url": _first(posting.get("url"), posting.get("jobUrl"), raw.get("url")),
        "raw": raw,
    }


def normalize_jobs(raw_jobs):
    return [normalize_job(job) for job in raw_jobs]
