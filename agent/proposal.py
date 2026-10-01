def build_proposal(job, profile):
    title = job.get("title", "your project")
    skills = ", ".join(job.get("skills", [])[:5])
    experience = profile.get("relevant_experience", [])
    proof = profile.get("proof", "")
    lines = ["Hi,", "", "I can help with " + title.lower() + ".", ""]
    if experience:
        lines.append("My relevant background includes " + "; ".join(experience[:3]) + ".")
    if proof:
        lines.extend(["", proof])
    if skills:
        lines.extend(["", "Relevant areas for this project include " + skills + "."])
    lines.extend(["", "I would first review the current workflow and requirements, then build or improve the solution with a focus on reliability and maintainability.", "", "Best regards"])
    return "\n".join(lines)

def qualification_check(job, profile):
    """Return unmet preferred qualifications without inventing evidence."""
    preferred = job.get("preferred_qualifications", {}) or {}
    unmet = []
    language = str(preferred.get("english_proficiency", ""))
    profile_language = str(profile.get("language", ""))
    if language.lower() == "fluent" and "fluent" not in profile_language.lower():
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

def build_screening_drafts(job, profile):
    """Draft only answers supported by verified profile facts; never fabricate."""
    drafts = []
    experience_text = "; ".join(profile.get("relevant_experience", [])[:4])
    proof = profile.get("proof", "")
    for question in job.get("screening_questions", []) or []:
        q = str(question).strip()
        lower = q.lower()
        answer = "[Manual answer required: no verified evidence is available for this question.]"
        if any(term in lower for term in ("recent experience", "similar project", "similar projects", "experience")):
            if experience_text or proof:
                answer = ("My relevant experience includes " + experience_text + ". " + proof).strip()
        elif "certification" in lower or "certifications" in lower:
            answer = "I do not have a verified certification to list for this project."
        elif "portfolio" in lower:
            answer = "I do not currently have a verified Upwork portfolio item to reference."
        drafts.append({"question": q, "answer": answer})
    return drafts