**English** | [简体中文](zh-CN/EXTENDING.md)

# Extending it

Edit `build_workflow.py`, run `python3 build_workflow.py` to regenerate `workflow.json`, run `python3 test.py`, then import the
new JSON into n8n. Do not edit `workflow.json` by hand; the next regeneration would overwrite it.

## Add a client
In `build_workflow.py`, add an entry to `CLIENTS` in the `Load client profile` script:
```js
'law-firm': { voice: 'precise and sober', audience: 'in-house counsel',
              max_chars: 800, banned: ['guaranteed outcome', 'best lawyers'] },
```
`client` in a request must match the key. Add a test case in `test.py` for the new profile if its limits matter.

## Change the number of revision rounds
`MAX_ATTEMPTS` in the `Interpret decision` script (currently 3). With 3, a `revise` on the third draft ends the run as
`revision_limit_reached`.

## Change the reviewer channel
Point `NOTIFY_URL` at your channel. The body it receives has `request_id`, `client`, `topic`, `attempt`, `draft`, `checks`,
`checks_passed`, `resume_url` and a `reply_with` hint. Your channel only needs to let a person send back a POST to `resume_url` with
`decision`, optional `feedback` and `reviewer`. The reviewer page in `deploy/inbox.py` is one example.

## Change what "publish" means
Point `PUBLISH_URL` at a CMS or scheduler. It receives `request_id`, `client`, `content`, `attempt` and `reviewer`. If publishing must
be reliable, add retries and error handling around the `Publish` node (see the known gaps in `ARCHITECTURE.md`).

## Use a different model
Any OpenAI-compatible chat completions endpoint works: set `LLM_BASE_URL`, `LLM_API_KEY` and `LLM_MODEL`. A reasoning model adds seconds
per draft; the reviewer only waits for the first draft, so that is usually acceptable here.

## Add a check
See "Adding a check or a case" in `TESTING.md`.
