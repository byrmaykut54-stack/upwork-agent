def build_proposal(job, profile):
    title = job.get("title", "your project")
    skills = ", ".join(job.get("skills", [])[:5])
    experience = profile.get("relevant_experience", [])
    proof = profile.get("proof", "")

    lines = [
        "Hi,",
        "",
        f"I can help with {title.lower()}.",
        "",
    ]
    if experience:
        lines.append("My relevant background includes " + "; ".join(experience[:3]) + ".")
    if proof:
        lines.extend(["", proof])
    if skills:
        lines.extend(["", f"Relevant areas for this project include {skills}."])
    lines.extend([
        "",
        "I would first review the current workflow and requirements, then build or improve the solution with a focus on reliability and maintainability.",
        "",
        "Best regards",
    ])
    return "\\n".join(lines)


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
    if min_jss and profile.get("job_success_score") is not None and profile["job_success_score"] < min_jss:
        unmet.append(f"Job Success Score: {min_jss}% minimum")
    if preferred.get("has_portfolio") and not profile.get("has_portfolio", False):
        unmet.append("Portfolio")
    return unmet


def build_screening_drafts(job):
    """Create honest answer placeholders; never fabricate experience."""
    return [
        {
            "question": q,
            "answer": "[Taslak: Bu soruya gerçek deneyim ve kanıtlarımıza göre cevap verilmelidir.]",
        }
        for q in job.get("screening_questions", [])
    ]
