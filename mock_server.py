#!/usr/bin/env python3
"""Tiny stand-in for the outside world so the workflow can be tested offline and deterministically:
an OpenAI-compatible /v1/chat/completions, plus /notify (reviewer channel), /publish (CMS) and /audit (log).
Everything it receives is kept in memory and shown at GET /state."""
import json, sys
from http.server import BaseHTTPRequestHandler, HTTPServer

STATE = {"notifications": [], "published": [], "audit": [], "llm_calls": 0}

def fake_draft(system, user):
    topic = user.split("Topic: ", 1)[1].split("\n", 1)[0]
    facts = user.split("Facts you may use: ", 1)[1].split("\n", 1)[0]
    text = f"{topic}."
    if "(none)" not in facts:
        text += f" Worth knowing: {facts}."
    if "overclaim" in topic.lower():
        text += " We grew 300% last year."          # unsupported number, should be flagged
    if "banned" in topic.lower():
        text += " Results are guaranteed."          # banned word for every profile that lists it
    if "REVISION FEEDBACK" in user:
        fb = user.split("REVISION FEEDBACK from the human reviewer:\n", 1)[1].split("\n", 1)[0]
        text = f"[revised for: {fb}] {topic}."
    return text

class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def _send(self, code, obj):
        body = json.dumps(obj).encode()
        self.send_response(code); self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)
    def do_GET(self):
        if self.path == "/state": return self._send(200, STATE)
        self._send(404, {"error": "not found"})
    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0)); data = json.loads(self.rfile.read(n) or b"{}")
        if self.path == "/v1/chat/completions":
            STATE["llm_calls"] += 1
            msgs = data["messages"]
            content = fake_draft(msgs[0]["content"], msgs[1]["content"])
            return self._send(200, {"choices": [{"message": {"role": "assistant", "content": content}}]})
        if self.path == "/notify": STATE["notifications"].append(data); return self._send(200, {"ok": True})
        if self.path == "/publish": STATE["published"].append(data); return self._send(200, {"ok": True})
        if self.path == "/audit": STATE["audit"].append(data); return self._send(200, {"ok": True})
        if self.path == "/reset":
            for k in ("notifications", "published", "audit"): STATE[k].clear()
            STATE["llm_calls"] = 0; return self._send(200, {"ok": True})
        self._send(404, {"error": "not found"})

if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8089
    HTTPServer(("0.0.0.0", port), H).serve_forever()
