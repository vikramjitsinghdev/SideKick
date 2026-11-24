"""Heads-Up demo: the Streamlit frontend.

    streamlit run ui.py

It only draws agent.snapshot() and calls the agent's actions (step, press_1,
tap_link, receive, pause/resume). Every rule lives in the backend.

Accessibility: Atkinson Hyperlegible (made for low-vision readers), 24 px text
and 56 px buttons in Gloria's phone panel, every colour pair at 7:1 or better,
status always in words (never colour alone), times as "2:30 PM", visible focus.
"""
from __future__ import annotations

import html
import json
from datetime import datetime

import streamlit as st

from app import build_agent
from heads_up.config import ROOT, load_sample
from heads_up.timeutil import parse_dt

END = parse_dt(load_sample("sms_inbox_replay.json")["_meta"]["replay_window"]["end"])
THURSDAY = parse_dt("2026-10-22T12:00:00-03:00").date()

st.set_page_config(page_title="Heads-Up for Gloria", page_icon="📞", layout="wide")

# ---- look and feel ------------------------------------------------------------------
INK, PAGE, AMBER, AMBER_TINT = "#14213D", "#F5F7FA", "#F4B400", "#FFF4CC"
GREEN, GREEN_TINT, RED, RED_TINT, SLATE = "#14633A", "#E3F2E9", "#A4262C", "#FBE9EA", "#4A5568"

st.markdown(f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Atkinson+Hyperlegible:ital,wght@0,400;0,700;1,400&display=swap');
.stApp {{ background: {PAGE}; color: {INK}; font-family: 'Atkinson Hyperlegible', system-ui, sans-serif; }}
.stApp p, .stApp li, .stApp label {{ font-size: 1.125rem; line-height: 1.6; }}
.stApp h1, .stApp h2, .stApp h3 {{ color: {INK}; font-family: 'Atkinson Hyperlegible', system-ui, sans-serif; letter-spacing: 0; }}
:focus-visible {{ outline: 3px solid {INK} !important; outline-offset: 3px !important; }}
.stButton button, .stFormSubmitButton button {{ min-height: 48px; font-size: 1.125rem; border-radius: 12px;
  border: 2px solid {INK}; color: {INK}; background: #fff; }}
.stButton button:disabled {{ border-color: #C9D1DD; color: {SLATE}; }}

/* Clock bar */
.clock {{ display: flex; align-items: baseline; gap: 1rem; flex-wrap: wrap; margin: 0 0 .25rem; }}
.clock .time {{ font-size: 3rem; font-weight: 700; line-height: 1; }}
.clock .day {{ font-size: 1.5rem; }}
.next {{ color: {SLATE}; font-size: 1.125rem; margin-bottom: 1rem; }}

/* Gloria's phone: the one bold element (st.container(key="phone") -> .st-key-phone) */
.st-key-phone {{ background: #fff; border: 3px solid {INK}; border-radius: 32px; padding: 1.5rem; }}
.st-key-phone .who {{ color: {SLATE}; font-size: 1.125rem !important; margin: 0; }}
.st-key-phone p, .st-key-phone li {{ font-size: 1.5rem !important; line-height: 1.5 !important; }}
.st-key-phone h3 {{ font-size: 2rem !important; line-height: 1.2; margin: 0 0 .75rem; }}
.ring {{ background: {AMBER}; border-radius: 20px; padding: 1.25rem; margin-bottom: 1rem; }}
.ring h3 {{ margin: 0 0 .5rem; }}
.note {{ border-left: 8px solid {INK}; padding: .75rem 1rem; margin: 0 0 1rem; border-radius: 0; }}
.note.good {{ background: {GREEN_TINT}; border-color: {GREEN}; }}
.note.warn {{ background: {AMBER_TINT}; border-color: {AMBER}; }}
.note.bad {{ background: {RED_TINT}; border-color: {RED}; }}
.email {{ border: 2px solid {INK}; border-radius: 16px; padding: 1rem 1.25rem; white-space: pre-wrap; }}
.email .subject {{ font-weight: 700; }}
.quiet {{ color: {SLATE}; }}

/* Gloria's buttons: big and unmistakable */
.st-key-press1 button, .st-key-gotit button {{ min-height: 64px; }}
.st-key-press1 button p, .st-key-gotit button p {{ font-size: 1.5rem !important; font-weight: 700; }}
button[kind="primary"], [data-testid="stBaseButton-primary"], [data-testid="baseButton-primary"] {{
  background: {GREEN} !important; border-color: {GREEN} !important; color: #fff !important; }}

/* Timeline and calendar */
.timeline {{ list-style: none; padding: 0; margin: 0; }}
.timeline li {{ display: grid; grid-template-columns: 6.5rem 1fr; gap: .75rem; padding: .5rem 0 .5rem .75rem;
  border-left: 3px solid #C9D1DD; }}
.timeline li.key {{ border-left-color: {AMBER}; }}
.timeline .t {{ font-weight: 700; }}
.timeline .day {{ border: 0; padding: 1rem 0 .25rem; font-weight: 700; font-size: 1.25rem; display: block; }}
.event {{ background: #fff; border: 2px solid #C9D1DD; border-radius: 12px; padding: .75rem 1rem; margin-bottom: .5rem; }}
.event.changed {{ border-color: {INK}; background: {AMBER_TINT}; }}
.event .when {{ font-weight: 700; font-size: 1.25rem; }}
.tag {{ display: inline-block; border: 2px solid {INK}; border-radius: 999px; padding: 0 .6rem; font-size: 1rem; margin-left: .5rem; }}
.decision {{ font-weight: 700; }}
/* Form fields, dropdowns, expanders: always a light surface with dark text,
   even if Streamlit is switched to its dark theme. */
.stApp label, .stApp [data-testid="stWidgetLabel"] p {{ color: {INK} !important; font-weight: 700; }}
.stApp [data-baseweb="select"] > div, .stApp textarea, .stApp input {{
  background: #fff !important; color: {INK} !important; border: 2px solid {INK} !important; border-radius: 12px; }}
.stApp [data-baseweb="select"] span, .stApp [data-baseweb="select"] div {{ color: {INK} !important; }}
.stApp [data-baseweb="select"] svg {{ fill: {INK} !important; }}
.stApp [data-baseweb="textarea"], .stApp [data-baseweb="base-input"] {{ background: #fff !important; border: 0 !important; }}
.stApp textarea::placeholder, .stApp input::placeholder {{ color: {SLATE} !important; opacity: 1; }}
.stApp [data-testid="InputInstructions"] {{ color: {SLATE} !important; }}
[data-baseweb="popover"] ul, [data-baseweb="popover"] li, [data-baseweb="menu"] {{
  background: #fff !important; color: {INK} !important; }}
[data-baseweb="popover"] li[aria-selected="true"], [data-baseweb="popover"] li:hover {{
  background: {AMBER_TINT} !important; color: {INK} !important; }}
.stApp [data-testid="stExpander"] details, .stApp [data-testid="stExpander"] summary {{
  background: #fff !important; color: {INK} !important; }}
.stApp [data-testid="stExpander"] summary p, .stApp [data-testid="stExpander"] summary span,
.stApp [data-testid="stExpander"] summary svg {{ color: {INK} !important; fill: {INK} !important; }}
.stApp [data-testid="stExpander"] summary:hover p {{ text-decoration: underline; }}
.stApp [data-testid="stExpander"] blockquote p {{ color: {INK} !important; }}
@media (prefers-reduced-motion: reduce) {{ * {{ transition: none !important; animation: none !important; }} }}
</style>
""", unsafe_allow_html=True)


# ---- small helpers --------------------------------------------------------------------
def esc(text) -> str:
    return html.escape(str(text))


def clock_time(iso: str | datetime) -> str:
    dt = parse_dt(iso) if isinstance(iso, str) else iso
    return f"{dt.hour % 12 or 12}:{dt.minute:02d} {'AM' if dt.hour < 12 else 'PM'}"


def day_and_time(iso: str | datetime) -> str:
    dt = parse_dt(iso) if isinstance(iso, str) else iso
    return f"{dt:%a %b} {dt.day}, {clock_time(dt)}"


ACTION_WORDS = {
    "edit_one_occurrence": ("Moved one event", "good"),
    "ask_gloria": ("Asked Gloria instead", "warn"),
    "no_action": ("No action", "quiet"),
}
CODE_WORDS = {
    "edit": "A trusted family member gave a clear date and time, and exactly one event matched.",
    "unknown_sender": "Not from a trusted family member, so the AI never read it.",
    "not_a_change": "Not a change to her plans.",
    "paused": "Heads-Up was paused, so the text was only logged.",
    "unclear_date": "The day wasn't clear, so nothing was changed.",
    "vague_time": "The new time wasn't clear, so nothing was changed.",
    "match_count": "No single matching event, so nothing was changed.",
    "llm_error": "The text couldn't be read, so nothing was changed.",
    "series_request": "It asked to change every repeat, which Heads-Up never does.",
    "cancellation": "A cancellation, which Heads-Up never makes itself.",
    "multiple_changes": "More than one change in one text, so nothing was changed.",
    "category_not_allowed": "Gloria hasn't allowed changes to this kind of event.",
}
CONTACTS = {
    "Michelle (daughter)": ("+19025550123", "Michelle"),
    "Ray (husband)": ("+19025550102", "Ray"),
    "A number Gloria doesn't know": ("+19025550999", None),
}


# ---- the agent lives in the session -------------------------------------------------------
def restart() -> None:
    s = st.session_state
    try:
        s.agent = build_agent(
            "press_1" if s.get("scenario") == "Gloria answers and presses 1" else "no_answer",
            live=s.get("live", False), google=s.get("google", False))
        s.flash = s.last_sent = None
    except Exception as err:  # e.g. missing API key or Google sign-in
        s.agent = build_agent("no_answer")
        s.live = s.google = False
        s.flash = ("bad", f"Couldn't start that mode ({err}). Running offline instead.")


def act(fn, success: str | None = None) -> None:
    """Run an agent action from a button and show what happened."""
    try:
        result = fn()
        st.session_state.flash = ("good", success.format(result=result)) if success else None
    except Exception as err:
        st.session_state.flash = ("bad", str(err))


def send_text() -> None:
    """Form callback: runs before the page is drawn, so the phone panel shows the result at once."""
    s = st.session_state
    body = (s.get("new_text") or "").strip()
    if not body:
        s.last_sent = {"tone": "bad", "text": "Type a message first."}
        return
    phone, name = CONTACTS[s.get("new_sender") or next(iter(CONTACTS))]
    item = s.agent.receive(phone, body, name)
    words, tone = ACTION_WORDS.get(item.decision.action, (item.decision.action, ""))
    s.last_sent = {"tone": tone or "warn", "log": item.decision.log,
                   "text": f"{words}. {CODE_WORDS.get(item.decision.code, item.decision.reason)}"}
    s.new_text = ""


if "agent" not in st.session_state:
    restart()
agent = st.session_state.agent

# ---- sidebar: demo setup -----------------------------------------------------------------
with st.sidebar:
    st.header("Demo setup")
    st.radio("When the phone rings", ["Gloria doesn't answer", "Gloria answers and presses 1"],
             key="scenario", on_change=restart,
             help="What simulated Gloria does when Heads-Up calls. You can also press 1 yourself.")
    st.toggle("Read texts with the live AI (Groq)", key="live", on_change=restart,
              help="Off: uses saved readings, no internet needed.")
    st.toggle("Use the test Google Calendar", key="google", on_change=restart,
              help="Edits the Gloria test account. Run try_google_edit.py --reset first.")
    st.button("Restart the replay", on_click=restart, width="stretch")
    st.divider()
    paused = agent.profile["consent"]["agent_paused"]
    st.markdown(f"Heads-Up is **{'paused' if paused else 'on'}**.")
    st.button("Turn Heads-Up back on" if paused else "Pause Heads-Up", width="stretch",
              on_click=lambda: act(agent.resume if paused else agent.pause),
              help="Gloria's own switch. While paused, new texts are only logged.")
    st.caption("All people and messages are fictional sample data from the ShiftKey persona.")

snap = agent.snapshot(days=[THURSDAY])

# ---- clock bar --------------------------------------------------------------------------
st.title("Heads-Up for Gloria")
clock = parse_dt(snap["clock"])
st.markdown(
    f'<div class="clock" role="status" aria-live="polite"><span class="time">{clock_time(clock)}</span>'
    f'<span class="day">{clock:%A, %B} {clock.day}</span></div>', unsafe_allow_html=True)
nxt = snap["next_event_at"]
st.markdown(f'<p class="next">{"Next: " + day_and_time(nxt) if nxt else "The replay is finished."}</p>',
            unsafe_allow_html=True)

b1, b2, _ = st.columns([1, 1, 2])
b1.button("Next event", on_click=lambda: act(agent.step), disabled=nxt is None, width="stretch")
b2.button("Run to Thursday 4 PM", on_click=lambda: act(lambda: agent.advance_to(max(END, agent.clock))),
          disabled=agent.clock >= END, width="stretch")

if st.session_state.get("flash"):
    tone, text = st.session_state.flash
    st.markdown(f'<div class="note {tone}" role="status"><p>{esc(text)}</p></div>', unsafe_allow_html=True)

replay_tab, without_tab, try_tab, results_tab, settings_tab = st.tabs(
    ["Thursday with Heads-Up", "Thursday without it", "Send a test text", "Test results", "Gloria's settings"])


# ---- Gloria's phone ------------------------------------------------------------------------
def gloria_phone() -> None:
    change = snap["changes"][-1] if snap["changes"] else None
    ringing = snap["ringing_call"]
    calls = [o for o in snap["outbox"] if o["channel"] == "call"]
    emails = [o for o in snap["outbox"] if o["channel"] == "email"]
    questions = [o for o in snap["outbox"] if o["channel"] == "question"]

    phone = st.container(key="phone")
    phone.markdown('<p class="who">Gloria\'s phone</p>', unsafe_allow_html=True)
    with phone:
        _phone_body(change, ringing, calls, emails, questions)


def _phone_body(change, ringing, calls, emails, questions) -> None:

    if ringing:
        script = calls[-1]["body"]
        st.markdown(f'<div class="ring" role="status" aria-live="assertive"><h3>Heads-Up is calling</h3>'
                    f'<p>{esc(script)}</p></div>', unsafe_allow_html=True)
        st.button("Press 1: I got it", type="primary", key="press1", width="stretch",
                  on_click=lambda: act(agent.press_1, "Gloria pressed 1. The pickup change is confirmed."))
        st.markdown('<p class="quiet">To let it ring, press Next event.</p>', unsafe_allow_html=True)

    if change:
        status = change["status"]
        if status == "confirmed":
            via = "by pressing 1" if change["confirmed_via"] == "press_1_on_call" else "with the Got it button"
            st.markdown(f'<div class="note good"><p>Confirmed {via} at {clock_time(change["confirmed_at"])}. '
                        f'Michelle has been told.</p></div>', unsafe_allow_html=True)
        elif status == "family_asked":
            st.markdown('<div class="note bad"><p>Not confirmed yet. Michelle has been asked to call.</p></div>',
                        unsafe_allow_html=True)
        elif status == "ended_unconfirmed":
            st.markdown('<div class="note bad"><p>Never confirmed. The calendar alert and '
                        'Michelle\'s call were the last nudges.</p></div>', unsafe_allow_html=True)

        alert_at = next(s["at"] for s in change["steps"] if s["kind"] == "calendar_alert")
        start_at = next(s["at"] for s in change["steps"] if s["kind"] == "event_start")
        if parse_dt(alert_at) <= clock < parse_dt(start_at):
            st.markdown(f'<div class="note warn"><p>Reminder: Pick up Ava at {clock_time(start_at)} '
                        f'today. Changed by Michelle.</p></div>', unsafe_allow_html=True)

    if emails:
        e = emails[-1]
        st.markdown(f'<div class="email"><p class="subject">{esc(e["meta"]["subject"])}</p>'
                    f'<p>{esc(e["body"])}</p></div>', unsafe_allow_html=True)
        can_tap = change and change["status"] in ("waiting", "family_asked")
        token = e["meta"]["link"].rsplit("/", 1)[-1]
        st.button("Got it", key="gotit", type="primary" if can_tap else "secondary", disabled=not can_tap,
                  width="stretch",
                  on_click=lambda: act(lambda: agent.tap_link(token), "Got it: {result}."))

    for q in questions[-2:]:
        st.markdown(f'<div class="note warn"><p>{esc(q["body"])}</p></div>', unsafe_allow_html=True)

    if not (ringing or change or questions):
        st.markdown('<p class="quiet">Nothing needs Gloria right now.</p>', unsafe_allow_html=True)


def michelle_phone() -> None:
    family = [o for o in snap["outbox"] if o["channel"] == "family_message"]
    st.subheader("Michelle's phone")
    if not family:
        st.markdown('<p class="quiet">No messages from Heads-Up. She only hears about this one change.</p>',
                    unsafe_allow_html=True)
    for m in family:
        st.markdown(f'<div class="note"><p><strong>{clock_time(m["at"])}</strong> {esc(m["body"])}</p></div>',
                    unsafe_allow_html=True)


# ---- what Heads-Up did ----------------------------------------------------------------------
KEY_KINDS = {"calendar", "call", "family", "confirm", "alert"}


def timeline() -> None:
    st.subheader("What Heads-Up did")
    entries = [e for e in snap["timeline"] if parse_dt(e["at"]) >= parse_dt("2026-10-21T18:00:00-03:00")]
    if not entries:
        st.markdown('<p class="quiet">Waiting for texts. Press Next event.</p>', unsafe_allow_html=True)
        return
    rows, last_day = [], None
    for e in entries:
        at = parse_dt(e["at"])
        if at.date() != last_day:
            rows.append(f'<li class="day">{at:%A, %B} {at.day}</li>')
            last_day = at.date()
        cls = "key" if e["kind"] in KEY_KINDS else ""
        rows.append(f'<li class="{cls}"><span class="t">{clock_time(at)}</span><span>{esc(e["text"])}</span></li>')
    st.markdown(f'<ol class="timeline">{"".join(rows)}</ol>', unsafe_allow_html=True)


def calendar() -> None:
    st.subheader("Thursday, October 22")
    for ev in snap["calendar"][THURSDAY.isoformat()]:
        alert = f"Alert {ev['alert_minutes'][0]} minutes before" if ev["alert_minutes"] else "No alert"
        tag = '<span class="tag">Changed</span>' if ev["changed"] else ""
        st.markdown(f'<div class="event {"changed" if ev["changed"] else ""}">'
                    f'<p class="when">{clock_time(ev["start"])} to {clock_time(ev["end"])}{tag}</p>'
                    f'<p>{esc(ev["summary"])}<br><span class="quiet">{esc(ev["location"] or "")}. {alert}.</span></p>'
                    f'</div>', unsafe_allow_html=True)


def inbox() -> None:
    st.subheader("Texts and decisions")
    for item in reversed(snap["inbox"]):
        d = item["decision"]
        who = item["contact_name"] or item["from_phone"]
        words, _ = ACTION_WORDS.get(d["action"], (d["action"], "")) if d else ("Not handled yet", "")
        with st.expander(f"{day_and_time(item['received_at'])}, {who}: {words}"):
            st.markdown(f"> {esc(item['body'])}")
            if d:
                st.markdown(f'<p class="decision">{esc(words)}</p>'
                            f'<p>{esc(CODE_WORDS.get(d["code"], d["reason"]))}</p>', unsafe_allow_html=True)
                st.caption("Step by step")
                st.code("\n".join(d["log"]), language=None)


with replay_tab:
    left, right = st.columns([3, 2], gap="large")
    with right:
        gloria_phone()
        michelle_phone()
    with left:
        timeline()
        calendar()
        inbox()

# ---- without Heads-Up -------------------------------------------------------------------------
with without_tab:
    st.subheader("What really happened on Thursday")
    st.markdown('<p>Michelle\'s text arrived at 10:48 PM. Gloria had already used her phone for the day, '
                'and her "Pick up Ava" event had no alert.</p>', unsafe_allow_html=True)
    rows, last_day = [], None
    for e in load_sample("replay_timeline.json")["without_heads_up"]:
        at = parse_dt(e["at"])
        if at.date() != last_day:
            rows.append(f'<li class="day">{at:%A, %B} {at.day}</li>')
            last_day = at.date()
        cls = "key" if e["type"] in ("missed", "missed_call") else ""
        rows.append(f'<li class="{cls}"><span class="t">{clock_time(at)}</span><span>{esc(e["detail"])}</span></li>')
    st.markdown(f'<ol class="timeline">{"".join(rows)}</ol>', unsafe_allow_html=True)

# ---- send a test text ---------------------------------------------------------------------------
with try_tab:
    st.subheader("Send Gloria a test text")
    st.markdown(f'<p>It arrives at {day_and_time(clock)} on the demo clock and goes through the same '
                'checks as the real texts.</p>', unsafe_allow_html=True)
    if not st.session_state.get("live"):
        st.markdown('<div class="note warn"><p>Offline mode can only read the saved texts. A new text '
                    'will make Heads-Up ask Gloria instead of guessing. Turn on the live AI in the '
                    'sidebar to read new texts.</p></div>', unsafe_allow_html=True)
    with st.form("send_text"):
        st.selectbox("From", list(CONTACTS), key="new_sender")
        st.text_area("Message", key="new_text",
                     placeholder="Mom can you get Ava at 3:00 tomorrow instead of 3:15?")
        st.form_submit_button("Send text", on_click=send_text)
    sent = st.session_state.get("last_sent")
    if sent:
        st.markdown(f'<div class="note {sent["tone"]}"><p>{esc(sent["text"])}</p></div>', unsafe_allow_html=True)
        if sent.get("log"):
            st.code("\n".join(sent["log"]), language=None)

# ---- test results --------------------------------------------------------------------------------
with results_tab:
    st.subheader("22 test texts, read by the real AI")
    path = ROOT / "results" / "llm_eval.json"
    if not path.exists():
        st.markdown('<p>No results yet. Run <code>python scripts/eval_llm.py</code> and reload.</p>',
                    unsafe_allow_html=True)
    else:
        data = json.loads(path.read_text(encoding="utf-8"))
        s = data["summary"]
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Handled correctly", f"{s['end_to_end_pass']} of {s['cases']}")
        m2.metric("Edits when unclear", s["edits_when_unclear"])
        m3.metric("Edits from strangers", s["edits_from_unknown_senders"])
        m4.metric("Never sent to the AI", s["texts_kept_from_llm"])
        st.caption(f"Model: {s['model']}. Fields read exactly as expected: {s['reading_field_accuracy']:.0%}.")
        st.dataframe([{
            "Test": r["id"], "Kind": r["category"].replace("_", " "),
            "Expected": r["expected"], "Actual": r["actual"],
            "Result": "Pass" if r["pass"] else "Fail",
            "Read by AI": "Yes" if r["llm_called"] else "No (blocked first)",
        } for r in data["rows"]], hide_index=True, width="stretch")

# ---- Gloria's settings ------------------------------------------------------------------------------
with settings_tab:
    consent = snap["consent"]
    st.subheader("What Gloria agreed to")
    st.markdown(f'<div class="note {"warn" if consent["agent_paused"] else "good"}"><p>Heads-Up is '
                f'{"paused" if consent["agent_paused"] else "on"}. She can pause it any time from the sidebar.'
                f'</p></div>', unsafe_allow_html=True)
    people = "".join(f"<li>{esc(c['name'])}, her {esc(c['relationship'])}</li>"
                     for c in agent.profile["trusted_contacts"])
    kinds = "".join(f"<li>{esc(k.replace('_', ' ').capitalize())}</li>" for k in consent["changeable_event_categories"])
    st.markdown(f"<p><strong>Texts it may act on</strong></p><ul>{people}</ul>"
                f"<p><strong>Events it may move, one day at a time</strong></p><ul>{kinds}</ul>"
                f"<p><strong>What Michelle learns</strong></p><p>{esc(consent['share_with_family'])}</p>",
                unsafe_allow_html=True)
