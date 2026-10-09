**English** | [简体中文](zh-CN/RUNNING.md)

# Running

Tested with n8n 2.42.5 in Docker.

## 1. Run the test (needs only Docker and Python 3)
```bash
python3 test.py
```
It starts the mock server on port 8089 and an n8n container on port 5678, imports and publishes the workflow, runs 12 checks, and
removes the container and volume. The mock server stands in for the model, the reviewer channel, the CMS and the audit log, so
no key is needed. See `TESTING.md`.

## 2. Use the workflow in your own n8n
1. In n8n choose Workflows, then Import from file, and select `workflow.json`.
2. Set these environment variables **on the n8n process**:

| variable | meaning |
|---|---|
| `LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL` | any OpenAI-compatible chat completions API |
| `NOTIFY_URL` | where the draft and the resume link are sent (a Slack or Teams webhook, an email gateway, a ticket system) |
| `PUBLISH_URL` | where an approved post is sent (a CMS, a scheduler) |
| `AUDIT_URL` | where the audit record is sent (a log store, a sheet) |
| `N8N_BLOCK_ENV_ACCESS_IN_NODE=false` | n8n 2.x blocks `$env` inside nodes by default and this workflow reads its endpoints from it; alternatively move them into n8n credentials |
| `WEBHOOK_URL` | the base URL that reviewers' links will use; it must be reachable by whoever answers the review |

3. Publish the workflow. In n8n 2.x a published workflow registers its webhooks a few seconds after start; requests sent
   earlier get a 404.
4. Send a request and answer it:
```bash
curl -X POST $N8N/webhook/content-request -H 'Content-Type: application/json' \
  -d '{"client":"startup-coach","topic":"Launch week lessons","facts":["We shipped in 6 weeks"]}'
# the reviewer receives a draft and a resume_url, then answers with:
curl -X POST "$RESUME_URL" -H 'Content-Type: application/json' \
  -d '{"decision":"revise","feedback":"shorter, one concrete example","reviewer":"Sam"}'
```
Request fields: `client` (one of the profile names), `topic` (at least 5 characters), `facts` (optional list of strings the post may use).

## 3. Deploy it locally with a reviewer page
`deploy/` has a compose file with n8n plus a small web page (`inbox.py`) that receives the three outgoing calls and lets a
person submit requests and approve, revise or reject drafts.
```bash
cp deploy/.env.example deploy/.env      # fill in LLM_BASE_URL, LLM_API_KEY, LLM_MODEL
deploy/deploy.sh                        # imports and publishes the workflow, starts both services
```
- Reviewer page: **http://127.0.0.1:8089**. n8n editor: http://127.0.0.1:5678 (the first visit asks you to create an owner account).
- Both ports are bound to `127.0.0.1`. The page has **no login**; reach it through an SSH tunnel (`ssh -L 8089:127.0.0.1:8089 user@server`)
  or put authentication in front of it.
- On the page: pick a client, write a topic and optional facts, press send. A "Drafting" card appears, then the draft with its
  four checks; press Approve, Revise (feedback required) or Reject. The page refreshes itself when something changes and does
  not reload while you are typing. Approved posts show under Published, and the audit log is at the bottom.
- The deployment calls your model provider for every draft and every revision, so it costs money.
- Stop it: `cd deploy && docker compose down` (data stays in the volumes; `down -v` deletes it).

## Troubleshooting
| symptom | cause |
|---|---|
| 404 "webhook is not registered" right after start | n8n registers published workflows a few seconds after it becomes healthy; retry |
| the workflow fails at `Draft with LLM` with an env error | `N8N_BLOCK_ENV_ACCESS_IN_NODE` is not `false`, or `LLM_*` is not set on the n8n process |
| a request returns 202 but nothing reaches the reviewer | `NOTIFY_URL` is wrong or unreachable from n8n; check the execution in the editor |
| the resume link does not work from another machine | `WEBHOOK_URL` points at an address the reviewer cannot reach |
| n8n logs "Failed to start Python task runner" | harmless here: the workflow uses only JavaScript Code nodes |
