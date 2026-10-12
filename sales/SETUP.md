# Buyer setup — job ranking and proposal drafts

## Offline edition (no provider account or paid API required)

1. Install Python 3.12 or newer and extract the source package.
2. Copy `agent/profile.example.json` to `agent/profile.json`. Replace every example with facts you can verify; remove fields for which you have no evidence.
3. Save an authorized job export as a UTF-8 JSON array. A fictional sample is provided in `agent/jobs.example.json`. Do not include credentials or private customer data.
4. Adjust `agent/config.json`: minimum hourly/fixed budget, preferred keywords and queue size.
5. Run from the extracted project directory:

```sh
python -m agent.main --jobs agent/jobs.example.json --connects-balance 10 --output draft-queue.json
```

`python agent/main.py` is also supported. The offline edition uses Python's standard library; installing the web server dependencies is unnecessary.

6. Review the output, qualification gaps and current Connects information on Upwork. Exports can be stale and missing values are not a verification of eligibility.
7. Edit your proposal and submit it yourself on Upwork. This package contains no submission or Connects spending operation.

## Optional hosted Channel Hub

Install `requirements.txt`; configure PostgreSQL `DATABASE_URL`, stable `SESSION_SECRET`, `INTEGRATION_ENCRYPTION_KEY` and `APP_BASE_URL`; run `gunicorn app:app`. See the main README for provider configuration and tests. Hosting, domain, database and provider charges are separate from a setup service.

Upwork job synchronization requires the buyer's approved developer application and valid authorized access token. Bionluk/Payhip records are manual or CSV imports. There is no message API or background automatic synchronization. Optional email recovery and Google login need separate provider configuration and live acceptance.

## Privacy and handover

Keep keys in deployment secrets. Keep profile, job exports and generated queues outside source control. The source ZIP excludes credentials, private profiles, job data and generated queues. Back up the buyer's database separately; never run test database suites against production.
