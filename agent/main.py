import argparse
import json
import sys
from pathlib import Path

if __package__:
    from .pipeline import preview_summary, run_pipeline
else:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from agent.pipeline import preview_summary, run_pipeline

ROOT = Path(__file__).resolve().parent


def main(argv=None):
    parser = argparse.ArgumentParser(description="Rank exported jobs and prepare proposal drafts. No network requests or submissions.")
    parser.add_argument("--jobs", type=Path, default=ROOT / "jobs.json", help="JSON array of exported job objects")
    parser.add_argument("--config", type=Path, default=ROOT / "config.json")
    parser.add_argument("--profile", type=Path, default=ROOT / "profile.json", help="Verified profile facts; omitted default may be absent")
    parser.add_argument("--connects-balance", type=int, default=0)
    parser.add_argument("--output", type=Path, help="Write compact draft queue as UTF-8 JSON")
    args = parser.parse_args(argv)
    if args.connects_balance < 0:
        parser.error("--connects-balance must be non-negative")
    try:
        config = json.loads(args.config.read_text(encoding="utf-8"))
        profile = json.loads(args.profile.read_text(encoding="utf-8")) if args.profile.exists() else {}
        if not args.profile.exists() and args.profile != ROOT / "profile.json":
            raise ValueError("The selected profile file does not exist")
        raw_jobs = json.loads(args.jobs.read_text(encoding="utf-8"))
        if not isinstance(config, dict) or not isinstance(profile, dict):
            raise ValueError("Config and profile must be JSON objects")
        if not isinstance(raw_jobs, list) or any(not isinstance(job, dict) for job in raw_jobs):
            raise ValueError("Jobs must be a JSON array of objects")
    except (OSError, ValueError) as exc:
        parser.error(str(exc))

    ranked = run_pipeline(
        raw_jobs,
        config=config,
        profile=profile,
        connects_balance=args.connects_balance,
    )

    output = json.dumps([preview_summary(job) for job in ranked], ensure_ascii=False, indent=2) + "\n"
    if args.output:
        try:
            args.output.write_text(output, encoding="utf-8")
        except OSError as exc:
            parser.error(str(exc))
    else:
        print(output, end="")


if __name__ == "__main__":
    main()
