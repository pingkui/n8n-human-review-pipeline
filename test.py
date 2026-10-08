#!/usr/bin/env python3
"""End-to-end test: starts the mock server and a real n8n container, imports and publishes the
workflow, then drives it over HTTP like a client and a human reviewer would.
Needs Docker and the image n8nio/n8n. Standard library only."""
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
IMAGE = "n8nio/n8n:latest"
VOLUME = "n8n-content-review-data"
NAME = "n8n-content-review"
MOCK = "http://localhost:8089"
N8N = "http://localhost:5678"
ENV = {
    "N8N_BLOCK_ENV_ACCESS_IN_NODE": "false",   # the workflow reads its endpoints from $env
    "WEBHOOK_URL": N8N + "/",
    "N8N_DIAGNOSTICS_ENABLED": "false",
    "LLM_BASE_URL": MOCK + "/v1", "LLM_API_KEY": "test-key", "LLM_MODEL": "mock",
    "NOTIFY_URL": MOCK + "/notify", "PUBLISH_URL": MOCK + "/publish", "AUDIT_URL": MOCK + "/audit",
}


def sh(*cmd, check=True):
    p = subprocess.run(cmd, capture_output=True, text=True)
    if check and p.returncode != 0:
        sys.exit(f"command failed: {' '.join(cmd)}\n{p.stdout[-600:]}\n{p.stderr[-600:]}")
    return p


def http(method, url, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            raw = r.read().decode()
            return r.status, (json.loads(raw) if raw else {})
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        try:
            return e.code, json.loads(raw)
        except ValueError:
            return e.code, {"raw": raw}


def wait_for(cond, what, timeout=60):
    end = time.time() + timeout
    while time.time() < end:
        try:
            v = cond()
        except (urllib.error.URLError, ConnectionError, OSError):
            v = None          # the service is not up yet
        if v:
            return v
        time.sleep(0.5)
    raise AssertionError(f"timed out waiting for: {what}")


def state():
    return http("GET", MOCK + "/state")[1]


results = []


def check(name, ok, detail=""):
    ok = bool(ok)
    results.append(ok)
    print(("PASS  " if ok else "FAIL  ") + name + (f"   [{detail}]" if detail and not ok else ""))


def start_stack():
    mock = subprocess.Popen([sys.executable, os.path.join(HERE, "mock_server.py"), "8089"],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    wait_for(lambda: http("GET", MOCK + "/state")[0] == 200, "mock server")
    sh("docker", "rm", "-f", NAME, check=False)
    sh("docker", "volume", "rm", "-f", VOLUME, check=False)
    common = ["-v", f"{VOLUME}:/home/node/.n8n", "-v", f"{HERE}:/work:ro", "--entrypoint", "n8n"]
    sh("docker", "run", "--rm", *common, IMAGE, "import:workflow", "--input=/work/workflow.json")
    sh("docker", "run", "--rm", *common, IMAGE, "publish:workflow", "--id=contentReview01")
    envs = [x for k, v in ENV.items() for x in ("-e", f"{k}={v}")]
    sh("docker", "run", "-d", "--name", NAME, "--network", "host", "-v", f"{VOLUME}:/home/node/.n8n", *envs, IMAGE)
    wait_for(lambda: http("GET", N8N + "/healthz")[0] == 200, "n8n health", timeout=120)
    # a published workflow registers its webhooks a few seconds after the health check passes
    wait_for(lambda: http("POST", N8N + "/webhook/content-request", {"client": "?", "topic": "?"})[0] == 400,
             "webhook registration", timeout=90)
    return mock


def request(client, topic, facts=None):
    body = {"client": client, "topic": topic}
    if facts is not None:
        body["facts"] = facts
    return http("POST", N8N + "/webhook/content-request", body)


def nth_notification(n):
    return wait_for(lambda: (state()["notifications"][n:n + 1] or [None])[0], f"notification #{n + 1}")


def main():
    mock = start_stack()
    try:
        # 1. invalid input is rejected before any model call
        http("POST", MOCK + "/reset")
        code, out = request("no-such-client", "x")
        check("invalid input returns 400", code == 400 and "errors" in out, f"{code} {out}")
        check("invalid input makes no model call", state()["llm_calls"] == 0)

        # 2. happy path with one revision round
        http("POST", MOCK + "/reset")
        code, out = request("retail-brand", "Spring sale starts Friday", ["Free returns within 30 days"])
        check("valid request is accepted (202) with a request id", code == 202 and out.get("request_id"), f"{code} {out}")
        n1 = nth_notification(0)
        check("reviewer is notified with draft, checks and a resume link",
              n1["attempt"] == 1 and n1["checks_passed"] is True and "/webhook-waiting/" in n1["resume_url"], n1)
        check("nothing is published before approval", state()["published"] == [])
        code, _ = http("POST", n1["resume_url"], {"decision": "revise", "feedback": "make it warmer", "reviewer": "Sam"})
        n2 = nth_notification(1)
        check("revise triggers a second draft that reflects the feedback",
              n2["attempt"] == 2 and "make it warmer" in n2["draft"], n2)
        code, _ = http("POST", n2["resume_url"], {"decision": "approve", "reviewer": "Sam"})
        pub = wait_for(lambda: state()["published"] or None, "publish call")
        check("approval publishes exactly the approved draft", len(pub) == 1 and pub[0]["content"] == n2["draft"], pub)
        aud = wait_for(lambda: state()["audit"] or None, "audit record")
        check("audit record says published after 2 attempts",
              aud[-1]["outcome"] == "published" and aud[-1]["attempts"] == 2 and aud[-1]["reviewer"] == "Sam", aud[-1])

        # 3. guardrails flag unsupported numbers and banned words, reviewer rejects
        http("POST", MOCK + "/reset")
        request("board-advisor", "overclaim banned post about growth")
        n = nth_notification(0)
        failed = {c["name"] for c in n["checks"] if not c["ok"]}
        check("unsupported number and banned word are both flagged",
              n["checks_passed"] is False and {"numbers_supported_by_facts", "no_banned_words"} <= failed, n["checks"])
        http("POST", n["resume_url"], {"decision": "reject", "reviewer": "Ana"})
        aud = wait_for(lambda: state()["audit"] or None, "audit record")
        check("rejected draft is never published", state()["published"] == [] and aud[-1]["outcome"] == "rejected", aud[-1])

        # 4. revision limit: the third revise request ends the loop without publishing
        http("POST", MOCK + "/reset")
        request("startup-coach", "Launch week lessons")
        for i in range(3):
            n = nth_notification(i)
            http("POST", n["resume_url"], {"decision": "revise", "feedback": f"round {i + 1}", "reviewer": "Lee"})
        aud = wait_for(lambda: state()["audit"] or None, "audit record")
        check("revision limit stops the loop, nothing published",
              aud[-1]["outcome"] == "revision_limit_reached" and state()["published"] == [] and aud[-1]["attempts"] == 3,
              aud[-1])

        # 5. an unrecognised decision is treated as 'expired', not as approval
        http("POST", MOCK + "/reset")
        request("retail-brand", "Autumn collection preview")
        n = nth_notification(0)
        http("POST", n["resume_url"], {"decision": "yes please"})
        aud = wait_for(lambda: state()["audit"] or None, "audit record")
        check("unrecognised decision is not treated as approval",
              aud[-1]["outcome"] == "expired_no_decision" and state()["published"] == [], aud[-1])
    finally:
        mock.terminate()
        logs = sh("docker", "logs", "--tail", "15", NAME, check=False)
        if not all(results):
            print("\n--- n8n log tail ---\n" + logs.stdout[-1500:] + logs.stderr[-1500:])
        sh("docker", "rm", "-f", NAME, check=False)
        sh("docker", "volume", "rm", "-f", VOLUME, check=False)
    print(f"\n{sum(results)}/{len(results)} checks passed")
    sys.exit(0 if all(results) else 1)


if __name__ == "__main__":
    main()
