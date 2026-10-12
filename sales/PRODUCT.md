# MexAy Job Draft Assistant and Channel Hub

An independent tool to rank authorized job exports and prepare editable proposal drafts using the buyer's verified profile facts.

## Deliverable editions

- **Offline draft assistant:** Python source, configurable ranking, qualification checks, proposal drafts, fictional sample, tests and setup guide. Works without a paid AI API. Proposal generation is template based.
- **Optional Channel Hub setup:** Flask/PostgreSQL workspace for job/proposal and order tracking. Provider synchronization needs the buyer's own approved API access. Bionluk and Payhip tracking is manual/CSV.

The offline package is the standalone deliverable. Hosted customer access, billing, external authorization and email delivery are separate acceptance tasks. The seller's existing account is not transferred to a buyer.

## Scope and acceptance

A buyer must be able to run the documented command, import a valid JSON export and save a draft queue. The queue must keep submission eligibility false. Missing Connects cost and insufficient balance are shown as review limits. Profile facts are supplied by the buyer; the tool does not verify their truth.

## Service package draft (USD; scope to be included in marketplace listing)

| Package | Price | Delivery | Included |
|---|---:|---|---|
| Starter | $29 | 3 days | Offline source package; one profile/configuration; setup guide; one revision |
| Standard | $79 | 5 days | Starter plus ranking configuration for one workflow and one sample export; two revisions |
| Hosted setup | $149 | 7 days | Standard plus one buyer-owned Channel Hub deployment and handover; valid provider credentials and paid hosting supplied separately |

Hosted setup must be offered only after its deployment/backup acceptance is verified. No guaranteed jobs or earnings; no automatic proposal submission; no Upwork affiliation. The buyer submits applications on Upwork. Live APIs, paid hosting and ongoing support are not included in the offline price.
