def build_proposal(job, profile):
    title = job.get("title", "your project")
    skills = ", ".join(job.get("skills", [])[:5])

    return f"""Hi,

I can help with {title.lower()}. My background includes {profile['relevant_experience'][0]}, {profile['relevant_experience'][1].lower()}, and {profile['relevant_experience'][2].lower()}.

I also built a 6-in-1 automated Excel toolkit covering budget tracking, invoice generation, income tracking, client tracking, rate calculation, and KPI reporting.

For this project, I would first review the current workflow, identify the repetitive steps, and then build a reliable solution around the requirements. {("Relevant areas include " + skills + ".") if skills else ""}

Best regards
"""
