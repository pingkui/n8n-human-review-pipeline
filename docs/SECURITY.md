**English** | [简体中文](zh-CN/SECURITY.md)

# Security and privacy notes

A demo, not a hardened service. What is known, and what is and is not covered.

## The resume URL is a capability
Whoever has a draft's resume URL can approve, revise or reject it. Send it only over a private channel. In production put
authentication in front of the n8n webhook endpoints. This repository adds none.

## The reviewer page has no login
`deploy/inbox.py` listens on `127.0.0.1` only and has no authentication. Anyone who can reach it can submit requests (which cost
model calls) and approve drafts. Reach it through an SSH tunnel, or put authentication, rate limits and a spending cap in front of it.
Everything it prints is HTML-escaped, so model or requester text cannot run script in the page.

## Requester text goes into the prompt
`topic` and `facts` are free text from whoever calls the webhook and are inserted into the model's prompt, so they can try to
steer the model. What limits the damage: the model cannot publish, a person reviews every draft, and the checks flag banned
words and numbers that were not supplied. What is not covered: a draft can still be misleading without tripping a check, and the
number check only compares strings.

## Secrets and environment
- `LLM_API_KEY` reaches nodes through `$env`, which needs `N8N_BLOCK_ENV_ACCESS_IN_NODE=false`. That setting lets any workflow on the
  same n8n instance read the environment, so do not share the instance with workflows you do not trust, or use n8n credentials instead.
- `deploy/.env` holds the key; it is in `.gitignore` and should have mode 600. Never commit it.

## Personal and confidential data
Topics, facts and drafts go to your model provider and to whatever `NOTIFY_URL`, `PUBLISH_URL` and `AUDIT_URL` point at. Whether the
provider keeps or trains on that data depends on your contract with them, not on this repository. For confidential material,
use a provider and plan whose terms you have read. The audit record keeps the final text only for published posts.

## Publishing to a network
`PUBLISH_URL` is generic. If you connect it to a social network, follow that platform's terms and rate limits. Automating
engagement (likes, comments, messages) can get accounts restricted; this workflow does not do it.

## Not done
No authentication, no rate limiting, no retention policy for the audit log, no retries or alerting when a call fails.
