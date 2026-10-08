#!/usr/bin/env python3
"""Reviewer inbox for the n8n content pipeline: one small page to try the whole loop.

It is the receiver for the workflow's three outgoing calls (NOTIFY_URL, PUBLISH_URL, AUDIT_URL) and
gives a human a place to submit requests and to approve, revise or reject drafts.
State is kept in a JSON file. Standard library only. Bind it to localhost or put auth in front of it:
there is no login here."""
import html
import json
import os
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

N8N_URL = os.environ.get("N8N_URL", "http://n8n:5678").rstrip("/")
STATE_FILE = os.environ.get("STATE_FILE", "/data/state.json")
CLIENTS = ["board-advisor", "startup-coach", "retail-brand"]
LOCK = threading.Lock()


def load():
    try:
        with open(STATE_FILE) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {"pending": [], "published": [], "audit": [], "inflight": []}


def save(state):
    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
    tmp = STATE_FILE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(state, f)
    os.replace(tmp, STATE_FILE)


def post_json(url, obj):
    req = urllib.request.Request(url, data=json.dumps(obj).encode(), method="POST",
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, r.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()
    except OSError as e:
        return 0, str(e)


e = html.escape


def page(state, flash=""):
    opts = "".join(f"<option>{c}</option>" for c in CLIENTS)
    out = ["""<!doctype html><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1">
<title>Review inbox</title><style>
body{font:15px/1.5 system-ui,sans-serif;max-width:860px;margin:24px auto;padding:0 16px;color:#1b1f23}
h1{font-size:22px}h2{font-size:17px;margin-top:28px;border-bottom:1px solid #ddd;padding-bottom:4px}
.card{border:1px solid #d0d7de;border-radius:8px;padding:12px 14px;margin:10px 0;background:#fafbfc}
pre{white-space:pre-wrap;background:#fff;border:1px solid #e1e4e8;border-radius:6px;padding:10px;margin:8px 0}
input,select,textarea{font:inherit;padding:6px;margin:3px 0;width:100%;box-sizing:border-box}
button{font:inherit;padding:6px 14px;margin-right:6px;cursor:pointer}
.ok{color:#1a7f37}.bad{color:#cf222e}.muted{color:#6a737d;font-size:13px}.flash{background:#ddf4ff;padding:8px 12px;border-radius:6px}
</style><h1>Content pipeline - review inbox</h1>"""]
    if flash:
        out.append(f"<p class=flash>{e(flash)}</p>")
    out.append(f"""<h2>New request</h2><form method=post action=/submit>
<label>Client <select name=client>{opts}</select></label>
<label>Topic <input name=topic required minlength=5 placeholder="e.g. Why we review every AI-written post"></label>
<label>Facts the post may use, one per line (numbers in the draft must come from here)
<textarea name=facts rows=3></textarea></label><button>Send to pipeline</button></form>""")
    inflight = state.get("inflight", [])
    if inflight:
        out.append(f"<h2>Drafting ({len(inflight)})</h2>")
        for x in inflight:
            out.append(f"<div class=card><b>{e(str(x['client']))}</b> - {e(str(x['topic']))} "
                       f"<span class=muted>(sent {int(time.time() - x['since'])}s ago; the model is writing, "
                       f"this page updates by itself)</span></div>")
    out.append(f"<h2>Waiting for review ({len(state['pending'])})</h2>")
    for p in reversed(state["pending"]):
        checks = "".join(
            f"<li class={'ok' if c['ok'] else 'bad'}>{e(c['name'])}: {'ok' if c['ok'] else 'FAILED'} "
            f"{e(str(c.get('detail', '')))}</li>" for c in p["checks"])
        out.append(f"""<div class=card><b>{e(p['client'])}</b> - {e(p['topic'])}
<span class=muted>(attempt {p['attempt']}, request {e(str(p['request_id']))})</span>
<pre>{e(p['draft'])}</pre><ul>{checks}</ul>
<form method=post action=/decide><input type=hidden name=id value="{e(p['id'])}">
<input name=feedback placeholder="feedback (needed for Revise)"><input name=reviewer placeholder="your name" value="reviewer">
<button name=decision value=approve>Approve</button><button name=decision value=revise>Revise</button>
<button name=decision value=reject>Reject</button></form></div>""")
    if not state["pending"]:
        out.append("<p class=muted>Nothing waiting.</p>")
    out.append(f"<h2>Published ({len(state['published'])})</h2>")
    for p in reversed(state["published"]):
        out.append(f"<div class=card><b>{e(p['client'])}</b> <span class=muted>(request {e(str(p['request_id']))}, "
                   f"attempt {p['attempt']}, approved by {e(str(p['reviewer']))})</span><pre>{e(p['content'])}</pre></div>")
    out.append(f"<h2>Audit log ({len(state['audit'])})</h2>")
    for a in reversed(state["audit"]):
        out.append(f"<div class=card><span class=muted>{e(json.dumps({k: v for k, v in a.items() if k != 'final_text'}))}</span></div>")
    out.append("<script>\nconst sig = s => [(s.inflight||[]).length, s.pending.length, s.published.length, s.audit.length].join('-');\nlet last = null;\nsetInterval(async () => {\n  try {\n    const s = await (await fetch('/state')).json();\n    const now = sig(s);\n    if (last === null) { last = now; return; }\n    const typing = [...document.querySelectorAll('input:not([type=hidden]),textarea')].some(i => i.value.trim() && i.defaultValue !== i.value);\n    if (now !== last && !typing) location.href = '/';\n    else if (now !== last) document.title = '(new) Review inbox';\n  } catch (e) {}\n}, 3000);\n</script>")
    return "".join(out).encode()


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _html(self, body, code=200):
        self.send_response(code)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _redirect(self, flash=""):
        self.send_response(303)
        self.send_header("Location", "/?" + urllib.parse.urlencode({"m": flash}) if flash else "/")
        self.end_headers()

    def do_GET(self):
        q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        if self.path.startswith("/state"):
            body = json.dumps(load()).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        with LOCK:
            self._html(page(load(), (q.get("m") or [""])[0]))

    def do_POST(self):
        raw = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        ctype = self.headers.get("Content-Type", "")
        if self.path in ("/notify", "/publish", "/audit"):
            data = json.loads(raw or b"{}")
            with LOCK:
                st = load()
                if self.path == "/notify":
                    data["id"] = f"{data['request_id']}-{data['attempt']}"
                    st["pending"].append(data)
                    st["inflight"] = [x for x in st.get("inflight", []) if x["request_id"] != str(data["request_id"])]
                elif self.path == "/publish":
                    st["published"].append(data)
                else:
                    st["audit"].append(data)
                save(st)
            body = b'{"ok":true}'
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        form = {k: v[0] for k, v in urllib.parse.parse_qs(raw.decode()).items()} if "form" in ctype else {}
        if self.path == "/submit":
            facts = [x.strip() for x in form.get("facts", "").splitlines() if x.strip()]
            code, out = post_json(N8N_URL + "/webhook/content-request",
                                  {"client": form.get("client"), "topic": form.get("topic"), "facts": facts})
            if code == 202:
                try:
                    rid = str(json.loads(out)["request_id"])
                    with LOCK:
                        st = load()
                        st.setdefault("inflight", []).append(
                            {"request_id": rid, "client": form.get("client"), "topic": form.get("topic"), "since": time.time()})
                        save(st)
                except (ValueError, KeyError):
                    pass
            return self._redirect("Sent to the pipeline; the draft appears below in a few seconds (reload)."
                                  if code == 202 else f"Pipeline answered {code}: {out[:200]}")
        if self.path == "/decide":
            with LOCK:
                st = load()
                item = next((p for p in st["pending"] if p["id"] == form.get("id")), None)
            if not item:
                return self._redirect("That draft is no longer waiting.")
            decision = form.get("decision")
            if decision not in ("approve", "revise", "reject"):
                return self._redirect("Unknown decision.")
            if decision == "revise" and not form.get("feedback", "").strip():
                return self._redirect("Revise needs feedback.")
            code, out = post_json(item["resume_url"], {"decision": decision, "feedback": form.get("feedback", ""),
                                                       "reviewer": form.get("reviewer", "reviewer")})
            if code and code < 300:
                with LOCK:
                    st = load()
                    st["pending"] = [p for p in st["pending"] if p["id"] != item["id"]]
                    save(st)
                return self._redirect(f"Sent: {decision}.")
            return self._redirect(f"n8n answered {code}: {out[:200]}")
        self.send_response(404)
        self.end_headers()


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", 8089), H).serve_forever()
