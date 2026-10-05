import json
from pathlib import Path

if __package__:
    from .pipeline import preview_summary, run_pipeline
else:
    from pipeline import preview_summary, run_pipeline

ROOT = Path(__file__).resolve().parent


def main():
    jobs_path = ROOT / "jobs.json"
    if not jobs_path.exists():
        print("jobs.json bulunamadı. Live Upwork işleri connector üzerinden alınmalıdır.")
        return

    config = json.loads((ROOT / "config.json").read_text())
    profile_path = ROOT / "profile.json"
    profile = json.loads(profile_path.read_text()) if profile_path.exists() else {}
    raw_jobs = json.loads(jobs_path.read_text())

    connects_balance = 0
    ranked = run_pipeline(
        raw_jobs,
        config=config,
        profile=profile,
        connects_balance=connects_balance,
    )

    for job in ranked:
        print(json.dumps(preview_summary(job), ensure_ascii=False, indent=2))
        print("-" * 60)


if __name__ == "__main__":
    main()
