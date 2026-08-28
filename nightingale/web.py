"""Development web server: static UI + PostgreSQL JSON API."""
from __future__ import annotations

import json
import os
import re
from decimal import Decimal
from datetime import date, datetime
from http.cookies import SimpleCookie
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from time import perf_counter
from urllib.parse import parse_qs, urlparse

from .domain import Actor, ClinicianKind, Role
from .clinical import (
    AI_SCRIBE_LOG,
    DOCTOR_PATIENT_CONSULT,
    NURSE_PATIENT_CONSULT,
    ai_summary_type,
    attach_consult_source,
    authorised_summary_sources,
)
from .qwen import generate_glance, generate_scribe
from .postgres import PostgresStore
from .redaction import redact_glance_timeline
from .service import redact_for_llm

ROOT = Path(__file__).parent.parent / "frontend"
SESSION_COOKIE = "nightingale_session"


class AuthenticationError(PermissionError):
    pass


def serialise(value):
    if isinstance(value, (datetime, date)): return value.isoformat()
    if isinstance(value, Decimal): return float(value)
    raise TypeError(f"not JSON serialisable: {type(value)!r}")


class App(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs): super().__init__(*args, directory=str(ROOT), **kwargs)
    def session_token(self) -> str:
        cookie = SimpleCookie(self.headers.get("Cookie", ""))
        return cookie[SESSION_COOKIE].value if SESSION_COOKIE in cookie else ""
    def current_user(self) -> dict | None:
        if not hasattr(self, "_current_user"):
            self._current_user = self.store().session_user(self.session_token())
        return self._current_user
    def actor(self) -> Actor:
        user = self.current_user()
        if not user:
            raise AuthenticationError("authentication required")
        kind = ClinicianKind(user["clinician_kind"]) if user["clinician_kind"] else None
        return Actor(user["id"], Role(user["role"]), user["clinic_id"], kind)
    def store(self): return PostgresStore()
    def body(self):
        length = int(self.headers.get("Content-Length", "0")); return json.loads(self.rfile.read(length) or b"{}")
    def send_json(self, value, status=200, headers: dict[str, str] | None = None):
        data = json.dumps(value, default=serialise).encode(); self.send_response(status); self.send_header("Content-Type", "application/json"); self.send_header("Cache-Control", "no-store"); self.send_header("Content-Length", str(len(data)))
        for name, content in (headers or {}).items(): self.send_header(name, content)
        self.end_headers(); self.wfile.write(data)
    def fail(self, message, status=400): self.send_json({"error": message}, status)
    def redirect(self, location: str):
        self.send_response(302); self.send_header("Location", location); self.send_header("Cache-Control", "no-store"); self.end_headers()
    def do_GET(self):
        path = urlparse(self.path).path
        try:
            if path == "/":
                return self.redirect("/app.html" if self.current_user() else "/login.html")
            if path == "/api/auth/me":
                user = self.current_user()
                if not user: return self.fail("authentication required", 401)
                return self.send_json({key: user[key] for key in ("id","username","role","clinic_id","clinician_kind","patient_id","expires_at")})
            if path in {"/app.html", "/notifications.html"}:
                if not self.current_user(): return self.redirect("/login.html")
                content = (ROOT / path.removeprefix("/")).read_text(encoding="utf-8").replace("Llama 3.2", "Qwen2.5").replace("Built with Llama", "")
                encoded = content.encode("utf-8")
                self.send_response(200); self.send_header("Content-Type", "text/html; charset=utf-8"); self.send_header("Content-Length", str(len(encoded))); self.end_headers(); self.wfile.write(encoded)
                return
            if path == "/app-live.js":
                content = (ROOT / "app-live.js").read_text(encoding="utf-8")
                content = content.replace("<mark>v${e.version}</mark>", "<mark>Entry ID: ${e.id}<br>v${e.version}</mark>")
                content += r'''
const clinicalKind = document.createElement("select");
clinicalKind.id = "clinicalKind";
clinicalKind.innerHTML = '<option value="doctor">Doctor</option><option value="nurse">Nurse</option>';
role.after(clinicalKind);
const nativeFetch = window.fetch;
window.fetch = (input, init = {}) => {
  init.headers = {...(init.headers || {}), "X-Clinician-Kind": clinicalKind.value};
  return nativeFetch(input, init);
};
const recordTypes = {
  doctor: [['doctor_daily','Doctor daily note'],['doctor_patient_consult','Doctor–patient consult'],['doctor_other','Doctor other']],
  nurse: [['nurse_daily','Nurse daily note'],['nurse_patient_consult','Nurse–patient consult'],['nurse_other','Nurse other']]
};
function refreshRecordTypes() {
  entryType.innerHTML = recordTypes[clinicalKind.value].map(([value,label]) => `<option value="${value}">${label}</option>`).join('');
}
clinicalKind.onchange = refreshRecordTypes;
refreshRecordTypes();
const baseRenderTimeline = renderTimeline;
renderTimeline = function () {
  baseRenderTimeline();
  if (role.value === "patient") {
    document.querySelectorAll(".comments-btn,.versions,.save").forEach(button => button.remove());
  }
};
aiGlance.onclick = async () => {
  if (!state.patient) return say('Create a patient page first');
  if (aiGlance.dataset.running === 'true') return;
  try {
    aiGlance.dataset.running = 'true';
    aiGlance.disabled = true;
    aiGlance.textContent = 'Generating…';
    const result = await api(`/api/patients/${state.patient.id}/ai-glance`, {method:'POST', body:'{}'});
    aiGlanceOutput.innerHTML = `<div class="ai-output"><b>✦ Qwen2.5 AI Glance</b><pre>${esc(result.summary)}</pre><div class="ai-sources"></div></div>`;
    const holder = aiGlanceOutput.querySelector('.ai-sources');
    result.sources.forEach(source => {
      const button = document.createElement('button');
      button.className = 'jump';
      button.textContent = `View source: ${source.entry_id}`;
      button.title = source.label;
      button.onclick = () => document.querySelector(`#entry-${source.entry_id}`)?.scrollIntoView({behavior:'smooth', block:'center'});
      holder.append(button);
    });
    latency.textContent = `AI glance ${result.generation_ms} ms`;
    say(result.sources.length ? 'AI glance generated with authorized source links' : 'AI glance generated with no accessible source links');
  } catch (err) { say(err.message); }
  finally {
    aiGlance.dataset.running = 'false';
    aiGlance.disabled = false;
    aiGlance.textContent = '✦ Generate AI glance';
  }
};
let autoGlancePending = true;
const baseSelectPatient = selectPatient;
selectPatient = async function (patient) {
  await baseSelectPatient(patient);
  if (autoGlancePending) {
    autoGlancePending = false;
    latency.textContent = 'Generating AI glance…';
    aiGlance.click();
  }
};
const baseLoadTimeline = loadTimeline;
loadTimeline = async function () {
  await baseLoadTimeline();
  if (!state.patient) return;
  state.highlights = await api(`/api/patients/${state.patient.id}/highlights`);
  renderTimeline();
};
const previousRenderTimeline = renderTimeline;
renderTimeline = function () {
  previousRenderTimeline();
  state.entries.filter(entry => entry.section === 'ai_scribed' && entry.provenance_pointer?.startsWith('entry:')).forEach(entry => {
    const sourceId = entry.provenance_pointer.slice('entry:'.length);
    const sourceIsVisible = state.entries.some(candidate => candidate.id === sourceId);
    const article = document.querySelector(`#entry-${entry.id}`);
    if (!article || !sourceIsVisible) return;
    const actions = article.querySelector('.actions');
    if (!actions || actions.querySelector('.source-consult-link')) return;
    const button = document.createElement('button');
    button.className = 'source-consult-link';
    button.textContent = `View source consult: ${sourceId}`;
    button.onclick = () => document.querySelector(`#entry-${sourceId}`)?.scrollIntoView({behavior:'smooth', block:'center'});
    actions.prepend(button);
  });
  (state.highlights || []).forEach(highlight => {
    const article = document.querySelector(`#entry-${highlight.entry_id}`);
    if (!article) return;
    const text = article.querySelector('.text');
    const raw = text.textContent;
    text.innerHTML = `${esc(raw.slice(0, highlight.span_start))}<button class="keyword-highlight" title="${esc(highlight.risk_reason)}">${esc(raw.slice(highlight.span_start, highlight.span_end))}</button>${esc(raw.slice(highlight.span_end))}`;
    const keyword = text.querySelector('.keyword-highlight');
    keyword.onclick = () => {
      if (highlight.reason_visible) document.querySelector(`#entry-${highlight.reason_entry_id}`)?.scrollIntoView({behavior:'smooth', block:'center'});
      else say('The source entry is not available for your role.');
    };
    if (role.value === 'clinician') {
      const actions = article.querySelector('.actions');
      const button = document.createElement('button');
      button.textContent = 'Highlight keyword';
      button.onclick = async () => {
        const keyword = prompt('Keyword in this AI-scribed note:');
        const reason = prompt('Why is this important?');
        const reasonEntry = prompt('Reason source Entry ID (optional):');
        if (!keyword || !reason) return;
        await api(`/api/entries/${highlight.entry_id}/highlights`, {method:'POST', body:JSON.stringify({patient_id:state.patient.id,keyword,reason,reason_entry_id:reasonEntry||null})});
        await loadTimeline();
      };
      actions.append(button);
    }
  });
  if (role.value === 'clinician') state.entries.filter(entry => entry.section === 'ai_scribed').forEach(entry => {
    const actions = document.querySelector(`#entry-${entry.id} .actions`);
    if (!actions || actions.querySelector('.manual-highlight')) return;
    const button = document.createElement('button');
    button.className = 'manual-highlight';
    button.textContent = 'Highlight keyword';
    button.onclick = async () => {
      const keyword = prompt('Keyword in this AI-scribed note:');
      const reason = prompt('Why is this important?');
      const reasonEntry = prompt('Reason source Entry ID (optional):');
      if (!keyword || !reason) return;
      await api(`/api/entries/${entry.id}/highlights`, {method:'POST', body:JSON.stringify({patient_id:state.patient.id,keyword,reason,reason_entry_id:reasonEntry||null})});
      await loadTimeline();
    };
    actions.append(button);
  });
};
'''
                encoded = content.encode("utf-8")
                self.send_response(200); self.send_header("Content-Type", "application/javascript; charset=utf-8"); self.send_header("Content-Length", str(len(encoded))); self.end_headers(); self.wfile.write(encoded)
                return
            if path == "/api/patients": return self.send_json(self.store().patients(self.actor()))
            if path == "/api/notifications": return self.send_json(self.store().notifications(self.actor()))
            if path == "/api/mentionable-users":
                entry_id = parse_qs(urlparse(self.path).query).get("entry_id", [""])[0]
                if not entry_id: return self.fail("entry_id is required", 400)
                return self.send_json(self.store().mentionable_users(self.actor(), entry_id))
            m = re.fullmatch(r"/api/patients/([^/]+)/timeline", path)
            if m: return self.send_json(self.store().timeline(self.actor(), m.group(1)))
            m = re.fullmatch(r"/api/patients/([^/]+)/highlights", path)
            if m: return self.send_json(self.store().highlights(self.actor(), m.group(1)))
            m = re.fullmatch(r"/api/entries/([^/]+)/versions", path)
            if m: return self.send_json(self.store().versions(self.actor(), m.group(1)))
            m = re.fullmatch(r"/api/entries/([^/]+)/comments", path)
            if m: return self.send_json(self.store().comments(self.actor(), m.group(1)))
            return super().do_GET()
        except AuthenticationError as exc: return self.fail(str(exc), 401)
        except Exception as exc: return self.fail(str(exc), 403)
    def do_POST(self):
        path = urlparse(self.path).path
        try:
            data, store = self.body(), self.store()
            if path == "/api/auth/login":
                token, user = store.login(str(data.get("username", "")).strip(), str(data.get("password", "")))
                cookie = f"{SESSION_COOKIE}={token}; Path=/; HttpOnly; SameSite=Strict; Max-Age=28800"
                return self.send_json({key: user[key] for key in ("id","username","role","clinic_id","clinician_kind","patient_id","expires_at")}, 200, {"Set-Cookie": cookie})
            if path == "/api/auth/logout":
                store.logout(self.session_token())
                return self.send_json({"logged_out": True}, 200, {"Set-Cookie": f"{SESSION_COOKIE}=; Path=/; HttpOnly; SameSite=Strict; Max-Age=0"})
            actor = self.actor()
            if path == "/api/patients": return self.send_json(store.create_patient(actor, data["display_label"]), 201)
            m = re.fullmatch(r"/api/patients/([^/]+)/patient-access", path)
            if m:
                store.bind_patient_account(actor, m.group(1), data["patient_user_id"])
                return self.send_json({"patient_id": m.group(1), "patient_user_id": data["patient_user_id"]}, 201)
            m = re.fullmatch(r"/api/patients/([^/]+)/entries", path)
            if m:
                entry_type = data.get("entry_type", "note")
                if entry_type == AI_SCRIBE_LOG:
                    return self.fail("AI scribe logs must be generated from a source consult through the AI scribe endpoint", 400)
                entry = store.create_entry(actor, m.group(1), data["section"], data["content"], entry_type, int(data.get("risk_level", 0)), data.get("tags"), bool(data.get("open_action")), data.get("provenance_pointer"))
                summary_type = ai_summary_type(entry_type)
                if summary_type:
                    summary = generate_scribe(redact_for_llm(data["content"]), entry_type)
                    summary = attach_consult_source(summary, entry["id"])
                    system = Actor("qwen2.5-0.5b", Role.SYSTEM, actor.clinic_id)
                    ai_entry = store.create_entry(system, m.group(1), "ai_scribed", summary, summary_type, 0, [], False, f"entry:{entry['id']}")
                    if data.get("auto_highlights", False):
                        store.auto_highlight(system, m.group(1), ai_entry["id"], entry["id"])
                    return self.send_json({"entry": entry, "ai_summary": ai_entry}, 201)
                return self.send_json(entry, 201)
            m = re.fullmatch(r"/api/patients/([^/]+)/ai-scribe", path)
            if m:
                if actor.role not in {Role.SYSTEM, Role.ADMIN}:
                    return self.fail("only the system or an admin can explicitly generate an AI scribe log", 403)
                source_entry_id = data.get("source_entry_id")
                if not source_entry_id:
                    return self.fail("source_entry_id is required for an AI scribe log", 400)
                source_entry = next((entry for entry in store.timeline(actor, m.group(1)) if entry["id"] == source_entry_id), None)
                consult_types = {DOCTOR_PATIENT_CONSULT, NURSE_PATIENT_CONSULT}
                if not source_entry or source_entry["entry_type"] not in consult_types:
                    return self.fail("the source must be an accessible Doctor–Patient or Nurse–Patient Consult", 403)
                summary = generate_scribe(redact_for_llm(source_entry["content"]), source_entry["entry_type"])
                summary = attach_consult_source(summary, source_entry_id)
                system = Actor("qwen2.5-0.5b", Role.SYSTEM, actor.clinic_id)
                ai_entry = store.create_entry(system, m.group(1), "ai_scribed", summary, AI_SCRIBE_LOG, int(data.get("risk_level", 0)), data.get("tags", []), False, f"entry:{source_entry_id}")
                if data.get("auto_highlights", False): store.auto_highlight(system, m.group(1), ai_entry["id"], None)
                return self.send_json(ai_entry, 201)
            m = re.fullmatch(r"/api/entries/([^/]+)/highlights", path)
            if m:
                result = store.create_highlight(actor, patient_id=data["patient_id"], entry_id=m.group(1), keyword=data["keyword"], reason=data["reason"], reason_entry_id=data.get("reason_entry_id"))
                return self.send_json(result, 201)
            m = re.fullmatch(r"/api/patients/([^/]+)/ai-glance", path)
            if m:
                entries = store.timeline(actor, m.group(1))
                # PHI-filter each record first; append validated source IDs only
                # afterward so redaction cannot erase Glance citations.
                source = redact_glance_timeline(entries)
                started_at = perf_counter()
                summary = generate_glance(source)
                generation_ms = round((perf_counter() - started_at) * 1000)
                # `entries` is already RLS-filtered for this request. Never return
                # a source link solely because the model mentioned its ID.
                sources = authorised_summary_sources(summary, entries)
                return self.send_json({"summary": summary, "model": "Qwen2.5-0.5B-Instruct", "sources": sources, "generation_ms": generation_ms})
            m = re.fullmatch(r"/api/entries/([^/]+)/comments", path)
            if m: return self.send_json(store.add_comment(actor, m.group(1), data["body"], data.get("mention")), 201)
            m = re.fullmatch(r"/api/entries/([^/]+)/revert", path)
            if m: return self.send_json({"version": store.revert(actor, m.group(1), int(data["version"]))})
            return self.fail("not found", 404)
        except AuthenticationError as exc: return self.fail(str(exc), 401)
        except Exception as exc: return self.fail(str(exc), 403)
    def do_PATCH(self):
        path = urlparse(self.path).path
        notification = re.fullmatch(r"/api/notifications/([^/]+)", path)
        if notification:
            try:
                return self.send_json(self.store().mark_notification_read(self.actor(), notification.group(1)))
            except AuthenticationError as exc: return self.fail(str(exc), 401)
            except PermissionError as exc: return self.fail(str(exc), 403)
            except Exception as exc: return self.fail(str(exc), 409)
        m = re.fullmatch(r"/api/entries/([^/]+)", path)
        if not m: return self.fail("not found", 404)
        try:
            data = self.body(); version = self.store().edit_with_version(self.actor(), m.group(1), data["content"], int(data["expected_version"]))
            return self.send_json({"version": version})
        except AuthenticationError as exc: return self.fail(str(exc), 401)
        except PermissionError as exc: return self.fail(str(exc), 403)
        except Exception as exc: return self.fail(str(exc), 409)

    def do_DELETE(self):
        path = urlparse(self.path).path
        m = re.fullmatch(r"/api/highlights/([^/]+)", path)
        if m:
            try:
                deleted = self.store().delete_highlight(self.actor(), m.group(1))
                return self.send_json({"deleted": deleted})
            except AuthenticationError as exc: return self.fail(str(exc), 401)
            except PermissionError as exc: return self.fail(str(exc), 403)
            except Exception as exc: return self.fail(str(exc), 409)
        m = re.fullmatch(r"/api/patients/([^/]+)", path)
        if not m: return self.fail("not found", 404)
        try:
            deleted = self.store().delete_patient(self.actor(), m.group(1))
            return self.send_json({"deleted": deleted})
        except AuthenticationError as exc: return self.fail(str(exc), 401)
        except PermissionError as exc: return self.fail(str(exc), 403)
        except Exception as exc: return self.fail(str(exc), 409)


def main():
    os.environ.setdefault("DATABASE_URL", "postgresql://nightingale_app:nightingale_local@127.0.0.1:5432/nightingale")
    port = int(os.environ.get("PORT", "8000"))
    server = ThreadingHTTPServer(("127.0.0.1", port), App)
    print(f"Nightingale running at http://127.0.0.1:{port}")
    server.serve_forever()

if __name__ == "__main__": main()
