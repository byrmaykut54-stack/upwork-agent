def render_job_report(job):
    lines = [
        "[{}/100] {}".format(job.get("score", 0), job.get("title", "Untitled")),
        "Connects: {} | Can apply: {}".format(job.get("connects_cost", "unknown"), job.get("can_apply", "unknown")),
    ]
    if job.get("hourly_rate_max") is not None:
        lines.append("Rate: ${}–${}/hr".format(job.get("hourly_rate_min", "?"), job["hourly_rate_max"]))
    elif job.get("fixed_budget") is not None:
        lines.append("Budget: ${}".format(job["fixed_budget"]))
    for reason in job.get("reasons", []):
        lines.append("+ " + reason)
    for risk in job.get("risks", []):
        lines.append("! " + risk)
    return "\n".join(lines)
