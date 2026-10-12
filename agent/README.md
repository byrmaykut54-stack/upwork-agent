# Offline job draft assistant

Ranks exported jobs, compares configured eligibility rules and prepares template-based proposal drafts using supplied profile facts. No network calls, submission or Connects spending.

```sh
python -m agent.main --jobs agent/jobs.example.json --connects-balance 10 --output draft-queue.json
```

Both module and direct script entry points work. JSON input must be an array of job objects. Configuration/profile are JSON objects. The default missing profile yields neutral drafts; an explicitly selected missing profile is an error. See `sales/SETUP.md` for setup and privacy requirements.
