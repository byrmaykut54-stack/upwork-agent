# Quick start

Offline draft assistant (Python 3.12+, standard library only):

```sh
python -m agent.main --jobs agent/jobs.example.json --connects-balance 10 --output draft-queue.json
```

The sample is fictional. Replace it with your authorized export and configure verified profile facts. See `sales/SETUP.md` for full steps. Applications must be submitted manually on Upwork.

Optional web workspace: configure a disposable or buyer-owned PostgreSQL database and deployment secrets as described in README, install `requirements.txt`, and run `gunicorn app:app`. External provider access, billing and production acceptance are separate tasks.
