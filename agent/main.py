import json
from pathlib import Path
from scorer import score_job

ROOT = Path(__file__).resolve().parent

def main():
    jobs_path = ROOT / "jobs.json"
    if not jobs_path.exists():
        print("jobs.json bulunamadı. Live Upwork işleri connector üzerinden alınmalıdır.")
        return

    config = json.loads((ROOT / "config.json").read_text())
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

if __name__ == "__main__":
    main()
