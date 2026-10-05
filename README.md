# MexAy Channel Hub

Live service: https://upwork-agent-pro.onrender.com

One authenticated workspace for Upwork jobs/proposal drafts and Upwork, Gumroad,
Fiverr orders. Existing accounts and job history are preserved by additive database migrations.

- Platform cards show real connection status, last sync and provider errors.
- Gumroad API connection validates `view_profile` and `view_sales`, encrypts the
  access token, and reads products and one bounded sales page per sync. Click sync
  again to continue older pages; after a full cycle the next sync refreshes newest sales.
- Upwork requires an approved developer application's OAuth access token with job
  search permission. Sync reads marketplace jobs; proposals remain drafts and must
  be submitted on Upwork. Token renewal is manual. No contract/message API is implemented.
- Fiverr is manual order tracking and normalized CSV import, with a direct platform link.
- Orders use platform + order ID for deduplication. API records cannot be edited
  manually. Manual records support status, due date and notes.
- Completed gross amounts are grouped by currency, without FX conversion or fee
  deductions. Test, refunded, partially refunded and disputed sales are excluded.
  Gumroad canonical sale price is USD cents, independent of buyer display currency.
- CSV export includes all records and escapes spreadsheet formulas. Imports accept
  1–500 rows atomically. Order view shows the latest 1,000 records with a total count.

## Configuration

Required: `DATABASE_URL`, stable `SESSION_SECRET`, `INTEGRATION_ENCRYPTION_KEY`
(Fernet key). HTTPS cookies are enabled by default. Keep the encryption key stable
or existing connections must be re-entered; never commit tokens or keys.

Optional Google login: `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`,
`GOOGLE_REDIRECT_URI`. Optional password reset: `RESEND_API_KEY`,
`RESEND_FROM_EMAIL`, `APP_BASE_URL`. Missing optional settings do not affect email
and password login. Browser sign-in on a provider does not connect its API to this app.

API keys are entered in Platformlar → API bağla; credentials are encrypted in
PostgreSQL and are never returned to the client. Synchronization is user-triggered,
not a scheduled background job. External platform permissions and valid keys are
needed to validate live provider integration.

## Validation

Use a dedicated disposable PostgreSQL database:

```sh
TEST_DATABASE_URL=postgresql://postgres:postgres@localhost:5432/mexay_test python -m unittest discover -s tests -v
python scripts/check_web.py
```

GitHub Actions provisions PostgreSQL 16. API tests cover CSRF, login, tenant
isolation, atomic imports, totals, encrypted credential storage, sync deduplication,
API record protection and provider failures. Provider responses are mocked;
external account connectivity is tested only after valid provider keys are supplied.

## CSV import columns

`platform,external_id,title,customer,amount,currency,status,due_date,notes`

Platform: `upwork`, `gumroad`, `fiverr`. Currency defaults to `USD`.
Status: `lead`, `in_progress`, `completed`, `cancelled`, `refunded`,
`partial_refund`, `disputed`. Due date: `YYYY-MM-DD` or empty.

---

# Upwork Agent Pro

SaaS MVP for finding, filtering, scoring and preparing Upwork applications.

## Deployment

The hosted SaaS runs on Render from the `main` branch.

## Safety

Final application submission remains human-confirmed. The product does not fabricate credentials or guarantee jobs or earnings.

## Commercial

See `sales/PRODUCT.md`, `sales/SETUP.md`, and `sales/FAQ.md`.
