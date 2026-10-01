import json
from pathlib import Path
from scorer import score_job
from proposal import build_proposal, build_screening_drafts, qualification_check
from job_normalizer import normalize_jobs
from report import render_job_report

ROOT = Path(__file__).resolve().parent


def main():
    jobs_path = ROOT / "jobs.json"
    if not jobs_path.exists():
        print("jobs.json bulunamadı. Live Upwork işleri connector üzerinden alınmalıdır.")
        return

    config = json.loads((ROOT / "config.json").read_text())
    profile = json.loads((ROOT / "profile.json").read_text())
    raw_jobs = json.loads(jobs_path.read_text())

    jobs = normalize_jobs(raw_jobs)
    ranked = []

    for job in jobs:
        result = score_job(job, config)
        ranked.append({**job, **result})

    ranked.sort(key=lambda x: x["score"], reverse=True)

    for job in ranked[:config["max_proposals_to_consider"]]:
        print(render_job_report(job))
        print("Proposal draft:")
        print(build_proposal(job, profile))

        unmet = qualification_check(job, profile)
        if unmet:
            print("Unmet preferred qualifications:")
            for item in unmet:
                print("! " + item)

        screening = build_screening_drafts(job, profile)
        if screening:
            print("Screening drafts require manual completion:")
            for item in screening:
                print("? " + item["question"])
                print("  " + item["answer"])

        print("-" * 60)


if __name__ == "__main__":
    main()
