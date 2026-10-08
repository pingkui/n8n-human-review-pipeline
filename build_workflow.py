#!/usr/bin/env python3
"""Generates workflow.json (the n8n workflow). Kept as a script so the node code stays readable."""
import json

LOAD = r"""
// Per-client profiles. Fictional examples: voice, audience, limits and banned words differ per client.
const CLIENTS = {
  'board-advisor': { voice: 'formal, concise, measured; no hype', audience: 'board-level marketing advisors',
                     max_chars: 900, banned: ['game-changer', 'revolutionary', 'guaranteed', 'synergy'] },
  'startup-coach': { voice: 'friendly, practical, direct', audience: 'early-stage founders',
                     max_chars: 700, banned: ['guaranteed', '10x', 'hack'] },
  'retail-brand':  { voice: 'playful and short', audience: 'online shoppers',
                     max_chars: 400, banned: ['cheap', 'guarantee'] },
};
const body = $input.first().json.body || {};
const errors = [];
if (!body.client || !CLIENTS[body.client]) errors.push('client must be one of: ' + Object.keys(CLIENTS).join(', '));
if (!body.topic || String(body.topic).trim().length < 5) errors.push('topic is required (min 5 characters)');
if (errors.length) return [{ json: { ok: false, errors } }];
const facts = Array.isArray(body.facts) ? body.facts.map(String) : [];
return [{ json: { ok: true, request_id: $execution.id, client: body.client, topic: String(body.topic).trim(),
                  facts, profile: CLIENTS[body.client], attempt: 1, feedback: '', previous_draft: '' } }];
""".strip()

PROMPT = r"""
const c = $input.first().json;
const p = c.profile;
const system = `You write short LinkedIn posts for the client described below. Voice: ${p.voice}. Audience: ${p.audience}. ` +
  `Hard limits: at most ${p.max_chars} characters; never use these words: ${p.banned.join(', ')}. ` +
  `Use only the facts provided. Do not invent statistics, names or customer claims. If no facts are provided, use no numbers.`;
let user = `Topic: ${c.topic}\nFacts you may use: ${c.facts.length ? c.facts.join(' | ') : '(none)'}`;
if (c.feedback) {
  user += `\n\nREVISION FEEDBACK from the human reviewer:\n${c.feedback}\n\nPrevious draft:\n${c.previous_draft}\n\nRewrite the post to address the feedback.`;
}
return [{ json: { ...c, llm_request: { model: $env.LLM_MODEL,
  messages: [{ role: 'system', content: system }, { role: 'user', content: user }] } } }];
""".strip()

CHECK = r"""
// Deterministic checks on the model output. The model is never trusted to police itself.
const ctx = $('Build prompt').first().json;
const res = $input.first().json;
const draft = String(res.choices?.[0]?.message?.content ?? '').trim();
const p = ctx.profile;
const lower = draft.toLowerCase();
const checks = [];
checks.push({ name: 'not_empty', ok: draft.length > 0 });
checks.push({ name: 'length_within_limit', ok: draft.length <= p.max_chars, detail: `${draft.length}/${p.max_chars}` });
const hits = p.banned.filter(w => lower.includes(w.toLowerCase()));
checks.push({ name: 'no_banned_words', ok: hits.length === 0, detail: hits.join(', ') });
const factText = ctx.facts.join(' ').toLowerCase();
const nums = draft.match(/\d[\d.,]*%?/g) || [];
const unsupported = nums.filter(n => !factText.includes(n.toLowerCase()));
checks.push({ name: 'numbers_supported_by_facts', ok: unsupported.length === 0, detail: unsupported.join(', ') });
const { llm_request, ...rest } = ctx;
return [{ json: { ctx: rest, draft, checks, passed: checks.every(c => c.ok) } }];
""".strip()

INTERPRET = r"""
const prev = $('Check draft').first().json;
const body = $input.first().json.body || {};
const MAX_ATTEMPTS = 3;
const decision = ['approve', 'revise', 'reject'].includes(body.decision) ? body.decision : 'expired';
const feedback = String(body.feedback || '');
const ctx = prev.ctx;
return [{ json: {
  decision, ctx, draft: prev.draft, checks_passed: prev.passed, feedback,
  reviewer: String(body.reviewer || 'unknown'),
  can_revise: ctx.attempt < MAX_ATTEMPTS,
  next: decision === 'revise'
    ? { ...ctx, attempt: ctx.attempt + 1, feedback: feedback || 'No specific feedback; tighten and improve.', previous_draft: prev.draft }
    : null,
} }];
""".strip()

REVISE = "return [{ json: $input.first().json.next }];"

AUDIT = r"""
const d = $('Interpret decision').first().json;
let outcome = 'published';
if (d.decision === 'reject') outcome = 'rejected';
else if (d.decision === 'expired') outcome = 'expired_no_decision';
else if (d.decision === 'revise') outcome = 'revision_limit_reached';
return [{ json: {
  request_id: d.ctx.request_id, client: d.ctx.client, topic: d.ctx.topic, attempts: d.ctx.attempt,
  outcome, reviewer: d.reviewer, approved_with_failed_checks: d.decision === 'approve' && !d.checks_passed,
  final_text: outcome === 'published' ? d.draft : null,
} }];
""".strip()

def node(name, type_, ver, pos, params):
    return {"parameters": params, "id": name.lower().replace(" ", "-"), "name": name,
            "type": type_, "typeVersion": ver, "position": pos}

JSON_HEADERS = {"parameters": [{"name": "Content-Type", "value": "application/json"}]}

nodes = [
  node("Content request", "n8n-nodes-base.webhook", 2, [0, 300],
       {"httpMethod": "POST", "path": "content-request", "responseMode": "responseNode", "options": {}}),
  node("Load client profile", "n8n-nodes-base.code", 2, [220, 300], {"jsCode": LOAD}),
  node("Input valid?", "n8n-nodes-base.if", 2.2, [440, 300], {
       "conditions": {"options": {"caseSensitive": True, "typeValidation": "strict", "version": 2},
                      "conditions": [{"id": "c1", "leftValue": "={{ $json.ok }}", "rightValue": True,
                                      "operator": {"type": "boolean", "operation": "true", "singleValue": True}}],
                      "combinator": "and"}, "options": {}}),
  node("Respond 400", "n8n-nodes-base.respondToWebhook", 1.4, [660, 480], {
       "respondWith": "json", "responseBody": "={{ JSON.stringify({ status: 'rejected_input', errors: $json.errors }) }}",
       "options": {"responseCode": 400}}),
  node("Respond accepted", "n8n-nodes-base.respondToWebhook", 1.4, [660, 200], {
       "respondWith": "json",
       "responseBody": "={{ JSON.stringify({ status: 'accepted', request_id: $json.request_id, note: 'A draft will be sent to the reviewer, who approves, revises or rejects it.' }) }}",
       "options": {"responseCode": 202}}),
  node("Build prompt", "n8n-nodes-base.code", 2, [880, 200], {"jsCode": PROMPT}),
  node("Draft with LLM", "n8n-nodes-base.httpRequest", 4.2, [1100, 200], {
       "method": "POST", "url": "={{ $env.LLM_BASE_URL + '/chat/completions' }}",
       "sendHeaders": True, "headerParameters": {"parameters": [
           {"name": "Authorization", "value": "={{ 'Bearer ' + $env.LLM_API_KEY }}"},
           {"name": "Content-Type", "value": "application/json"}]},
       "sendBody": True, "contentType": "raw", "rawContentType": "application/json",
       "body": "={{ JSON.stringify($json.llm_request) }}", "options": {"timeout": 120000}}),
  node("Check draft", "n8n-nodes-base.code", 2, [1320, 200], {"jsCode": CHECK}),
  node("Notify reviewer", "n8n-nodes-base.httpRequest", 4.2, [1540, 200], {
       "method": "POST", "url": "={{ $env.NOTIFY_URL }}", "sendBody": True,
       "contentType": "raw", "rawContentType": "application/json",
       "body": "={{ JSON.stringify({ request_id: $json.ctx.request_id, client: $json.ctx.client, topic: $json.ctx.topic, attempt: $json.ctx.attempt, draft: $json.draft, checks: $json.checks, checks_passed: $json.passed, resume_url: $execution.resumeUrl, reply_with: { decision: 'approve | revise | reject', feedback: 'required for revise', reviewer: 'your name' } }) }}",
       "options": {}}),
  node("Await human review", "n8n-nodes-base.wait", 1.1, [1760, 200], {
       "resume": "webhook", "httpMethod": "POST", "options": {},
       "limitWaitTime": True, "limitType": "afterTimeInterval", "resumeAmount": 24, "resumeUnit": "hours"}),
  node("Interpret decision", "n8n-nodes-base.code", 2, [1980, 200], {"jsCode": INTERPRET}),
  node("Approved?", "n8n-nodes-base.if", 2.2, [2200, 200], {
       "conditions": {"options": {"caseSensitive": True, "typeValidation": "strict", "version": 2},
                      "conditions": [{"id": "c1", "leftValue": "={{ $json.decision }}", "rightValue": "approve",
                                      "operator": {"type": "string", "operation": "equals"}}], "combinator": "and"}, "options": {}}),
  node("Publish", "n8n-nodes-base.httpRequest", 4.2, [2420, 100], {
       "method": "POST", "url": "={{ $env.PUBLISH_URL }}", "sendBody": True,
       "contentType": "raw", "rawContentType": "application/json",
       "body": "={{ JSON.stringify({ request_id: $json.ctx.request_id, client: $json.ctx.client, content: $json.draft, attempt: $json.ctx.attempt, reviewer: $json.reviewer }) }}",
       "options": {}}),
  node("Revise?", "n8n-nodes-base.if", 2.2, [2420, 320], {
       "conditions": {"options": {"caseSensitive": True, "typeValidation": "strict", "version": 2},
                      "conditions": [
                        {"id": "c1", "leftValue": "={{ $json.decision }}", "rightValue": "revise", "operator": {"type": "string", "operation": "equals"}},
                        {"id": "c2", "leftValue": "={{ $json.can_revise }}", "rightValue": True, "operator": {"type": "boolean", "operation": "true", "singleValue": True}}],
                      "combinator": "and"}, "options": {}}),
  node("Prepare revision", "n8n-nodes-base.code", 2, [2640, 240], {"jsCode": REVISE}),
  node("Audit record", "n8n-nodes-base.code", 2, [2860, 380], {"jsCode": AUDIT}),
  node("Log audit", "n8n-nodes-base.httpRequest", 4.2, [3080, 380], {
       "method": "POST", "url": "={{ $env.AUDIT_URL }}", "sendBody": True,
       "contentType": "raw", "rawContentType": "application/json",
       "body": "={{ JSON.stringify($json) }}", "options": {}}),
]

def link(a, b, out=0):
    return (a, out, b)

edges = [
  ("Content request", 0, "Load client profile"), ("Load client profile", 0, "Input valid?"),
  ("Input valid?", 0, "Respond accepted"), ("Input valid?", 1, "Respond 400"),
  ("Respond accepted", 0, "Build prompt"), ("Build prompt", 0, "Draft with LLM"),
  ("Draft with LLM", 0, "Check draft"), ("Check draft", 0, "Notify reviewer"),
  ("Notify reviewer", 0, "Await human review"), ("Await human review", 0, "Interpret decision"),
  ("Interpret decision", 0, "Approved?"), ("Approved?", 0, "Publish"), ("Approved?", 1, "Revise?"),
  ("Publish", 0, "Audit record"), ("Revise?", 0, "Prepare revision"), ("Revise?", 1, "Audit record"),
  ("Prepare revision", 0, "Build prompt"), ("Audit record", 0, "Log audit"),
]
connections = {}
for a, out, b in edges:
    connections.setdefault(a, {"main": []})
    lst = connections[a]["main"]
    while len(lst) <= out:
        lst.append([])
    lst[out].append({"node": b, "type": "main", "index": 0})

# Webhook-type nodes need a stable webhookId, otherwise n8n prefixes the path with workflow id and node name.
WEBHOOK_IDS = {"Content request": "7f0f3a52-4f1d-4c5e-9a53-2f6a1c0d9b11",
               "Await human review": "b3c1d7e8-61a2-4e40-8c7f-5d2e9a4b0c22"}
for n in nodes:
    if n["name"] in WEBHOOK_IDS:
        n["webhookId"] = WEBHOOK_IDS[n["name"]]

wf = {"id": "contentReview01", "name": "Content pipeline with human review", "active": False,
      "nodes": nodes, "connections": connections, "settings": {"executionOrder": "v1"}}
json.dump(wf, open("workflow.json", "w"), indent=2)
print("workflow.json written:", len(nodes), "nodes")
