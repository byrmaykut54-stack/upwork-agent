import json
from pathlib import Path
from scorer import score_job
from proposal import build_proposal, build_screening_drafts, qualification_check

ROOT = Path(__file__).resolve().parent

def main():
    jobs_path = ROOT / "jobs.json"
    if not jobs_path.exists():
        print("jobs.json bulunamadı. Live Upwork işleri connector üzerinden alınmalıdır.")
        return

    config = json.loads((ROOT / "config.json").read_text())
    profile = json.loads((ROOT / "profile.json").read_text())
    jobs = json.loads(jobs_path.read_text())

    ranked = []
    for job in jobs:
        result = score_job(job, config)
        ranked.append({**job, **result})

    ranked.sort(key=lambda x: x["score"], reverse=True)
    for job in ranked[:config["max_proposals_to_consider"]]:
        print(f"[{job['score']}/100] {job.get('title', 'Untitled')}")
        for reason in job["reasons"]:
            print(f"  + {reason}")
        for risk in job["risks"]:
            print(f"  ! {risk}")
        print("  Proposal draft:")
        print(build_proposal(job, profile))
        unmet = qualification_check(job, profile)
        if unmet:
            print("  Unmet preferred qualifications:")
            for item in unmet:
                print(f"  ! {item}")
        screening = build_screening_drafts(job)
        if screening:
            print("  Screening drafts require manual completion:")
            for item in screening:
                print(f"  ? {item['question']}")
                print(f"    {item['answer']}")

if __name__ == "__main__":
    main()
