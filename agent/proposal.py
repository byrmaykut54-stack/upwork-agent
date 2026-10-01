def build_proposal(job, profile):
    title = job.get("title", "your project")
    skills = ", ".join(job.get("skills", [])[:5])
    experience = profile.get("relevant_experience", [])
    proof = profile.get("proof", "")
    lines = ["Hi,", "", f"I can help with {title.lower()}.", ""]
    if experience:
        lines.append("My relevant background includes " + "; ".join(experience[:3]) + ".")
    if proof:
        lines.extend(["", proof])
    if skills:
        lines.extend(["", f"Relevant areas for this project include {skills}."])
    lines.extend(["", "I would first review the current workflow and requirements, then build or improve the solution with a focus on reliability and maintainability.", "", "Best regards"])
    return "\n".join(lines)


def qualification_check(job, profile):
    """Return unmet preferred qualifications without inventing evidence."""
    preferred = job.get("preferred_qualifications", {}) or {}
    unmet = []
    language = preferred.get("english_proficiency")
    if language and language.lower() == "fluent" and profile.get("language", "").lower() != "fluent":
        unmet.append("English proficiency: Fluent")
    if preferred.get("rising_talent") and not profile.get("rising_talent", False):
        unmet.append("Rising Talent")
    min_jss = preferred.get("min_job_success_score")
    if min_jss is not None:
        jss = profile.get("job_success_score")
        if jss is None or float(jss) < float(min_jss):
            unmet.append("Job Success Score: {}% minimum".format(min_jss))
    min_earnings = preferred.get("min_earnings_usd")
    if min_earnings is not None:
        earnings = profile.get("earnings_usd")
        if earnings is None or float(earnings) < float(min_earnings):
            unmet.append("Upwork earnings: ${}+ minimum".format(min_earnings))
    if preferred.get("has_portfolio") and not profile.get("has_portfolio", False):
        unmet.append("Portfolio")
    if preferred.get("contractor_type") and profile.get("contractor_type") != preferred.get("contractor_type"):
        unmet.append("Contractor type: " + str(preferred.get("contractor_type")))
    return unmet


def build_screening_drafts(job):
    """Create honest answer placeholders; never fabricate experience."""
    return [{"question": q, "answer": "[Taslak: Bu soruya gerçek deneyim ve kanıtlarımıza göre cevap verilmelidir.]"} for q in job.get("screening_questions", [])]
