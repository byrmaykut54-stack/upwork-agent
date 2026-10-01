import re


def _as_int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        if isinstance(value, str):
            match = re.search(r"\d+", value)
            return int(match.group()) if match else None
        return None


def _as_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        if isinstance(value, str):
            match = re.search(r"\d+(?:\.\d+)?", value.replace(",", ""))
            return float(match.group()) if match else None
        return None


def _first(*values):
    for value in values:
        if value not in (None, "", []):
            return value
    return None


def _verification(client, posting, raw):
    value = _first(client.get("paymentVerified"), client.get("verification_status"), posting.get("paymentVerified"), raw.get("payment_verified"))
    if isinstance(value, str):
        return value.strip().upper() in {"VERIFIED", "TRUE", "YES"}
    return value is True


def normalize_job(raw):
    posting = raw.get("data", {}).get("marketplaceJobPosting", raw)
    client = posting.get("client", {}) or {}
    contract = posting.get("contractTerms", {}) or {}
    hourly_contract = contract.get("hourlyContractTerms", {}) or {}
    budget = posting.get("budget", {}) or {}
    hourly = posting.get("hourlyRate", {}) or {}
    skills = posting.get("skills", raw.get("skills", [])) or []
    if isinstance(skills, list):
        skills = [s.get("name", s) if isinstance(s, dict) else s for s in skills]

    proposals = _first(posting.get("proposalsCount"), posting.get("proposals_count"), raw.get("proposal_count"), raw.get("proposals_count"), raw.get("proposals_tier"))
    client_hires = _first(client.get("totalHires"), client.get("total_hires"), client.get("hires"), posting.get("clientHires"), raw.get("client_hires"))
    fixed_budget = _first(budget.get("amount"), contract.get("fixedBudget"), posting.get("fixedBudget"), raw.get("fixed_budget"), raw.get("budget"))
    hourly_min = _first(hourly.get("min"), hourly_contract.get("hourlyBudgetMin"), posting.get("hourlyRateMin"), raw.get("hourly_rate_min"))
    hourly_max = _first(hourly.get("max"), hourly_contract.get("hourlyBudgetMax"), posting.get("hourlyRateMax"), raw.get("hourly_rate_max"))
    preferred = _first(posting.get("preferredQualifications"), raw.get("preferred_qualifications"), {}) or {}
    if not isinstance(preferred, dict):
        preferred = {}

    return {
        "id": _first(posting.get("id"), raw.get("id")),
        "title": _first(posting.get("title"), raw.get("title"), "Untitled"),
        "description": _first(posting.get("description"), posting.get("content", {}).get("description") if isinstance(posting.get("content"), dict) else None, raw.get("description"), raw.get("description_snippet"), ""),
        "skills": skills,
        "hourly_rate_min": _as_float(hourly_min),
        "hourly_rate_max": _as_float(hourly_max),
        "fixed_budget": _as_float(fixed_budget),
        "payment_verified": _verification(client, posting, raw),
        "proposals_count": _as_int(proposals),
        "client_hires": _as_int(client_hires),
        "client_rating": _as_float(_first(client.get("rating"), posting.get("clientRating"), raw.get("client_rating"))),
        "connects_cost": _as_int(_first(raw.get("connects_cost"), posting.get("connectsCost"))),
        "connects_balance": _as_int(raw.get("connects_balance")),
        "can_apply": _first(raw.get("can_apply"), posting.get("canApply")),
        "preferred_qualifications": preferred,
        "screening_questions": raw.get("screening_questions", posting.get("screeningQuestions", [])) or [],
        "url": _first(posting.get("url"), posting.get("jobUrl"), raw.get("url")),
        "raw": raw,
    }


def normalize_jobs(raw_jobs):
    return [normalize_job(job) for job in raw_jobs]
