**English** | [简体中文](zh-CN/TESTING.md)

# Testing

## What `python3 test.py` does
It starts `mock_server.py` and a real n8n container, imports and publishes `workflow.json`, waits until the webhook is registered,
drives the workflow over HTTP the way a requester and a reviewer would, and cleans up. Result: **12/12 checks pass**.

The mock server stands in for four outside things and records everything it receives (`GET /state`):
| mock endpoint | stands in for |
|---|---|
| `POST /v1/chat/completions` | the model; returns a deterministic draft (a revision draft quotes the feedback); a topic containing "overclaim" adds an unsupported number and one containing "banned" adds a banned word |
| `POST /notify` | the reviewer channel |
| `POST /publish` | the CMS |
| `POST /audit` | the audit log |

## The 12 checks
| # | check | proves |
|---|---|---|
| 1 | invalid input returns 400 | bad requests are refused up front |
| 2 | invalid input makes no model call | and cost nothing |
| 3 | a valid request is accepted (202) with a request id | the asynchronous contract |
| 4 | the reviewer is notified with the draft, the checks and a resume link | the human gets what they need |
| 5 | nothing is published before approval | the gate holds while waiting |
| 6 | revise triggers a second draft that reflects the feedback | the revision loop |
| 7 | approval publishes exactly the approved draft | no text drift between review and publish |
| 8 | the audit record says published after 2 attempts, with the reviewer | traceability |
| 9 | an unsupported number and a banned word are both flagged | the deterministic checks work |
| 10 | a rejected draft is never published | rejection is final |
| 11 | the revision limit stops the loop with nothing published | the loop is bounded |
| 12 | an unrecognised decision is not treated as approval | safe default |

## One live run (not part of the repo test)
One request was also run through a real model (Kimi `kimi-k2.6`) and the local deployment: the draft passed all four checks, a
revision was requested and honoured, and the approval was published and audited. It needs an API key, so it is not in `test.py`.

## What is not tested
- The quality of real model output; the mock is deterministic.
- A real reviewer channel (Slack, email) or a real CMS.
- Concurrency: many reviews open at once, or two replies to the same resume link.
- Failure of the model, notification or publish calls (see the known gaps in `ARCHITECTURE.md`).
- Behaviour after n8n restarts while executions are waiting.

## Adding a check or a case
- A new draft check: add an entry to the `checks` list in the `Check draft` code inside `build_workflow.py`, rerun
  `python3 build_workflow.py`, and add a trigger to `mock_server.py` (a keyword in the topic that makes the fake draft violate it) plus a
  case in `test.py`.
- A new client profile: see `EXTENDING.md`.
- Always regenerate `workflow.json` from `build_workflow.py` rather than editing the JSON by hand.
