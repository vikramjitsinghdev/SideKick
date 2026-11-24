# SideKick
# Heads-Up 📅

**When the family changes Grandma's plans by text, Heads-Up makes sure she actually hears about it.**

![Status](https://img.shields.io/badge/status-rules%20engine%20done%20·%20build%20in%20progress-orange)
![Python](https://img.shields.io/badge/python-3.11+-blue)
![LLM](https://img.shields.io/badge/LLM-Groq%20·%20GPT--OSS%20120B-purple)
![UI](https://img.shields.io/badge/UI-Streamlit-red)
![Data](https://img.shields.io/badge/data-100%25%20sample-green)

Heads-Up is a persona-driven AI agent built for the **ShiftKey Side Quest** (beta-tester cohort, November 2026). It reads texts from trusted family members, spots changes to plans already on the calendar, moves the right event, sets an alert, and **phones Gloria** about the change. If she doesn't confirm, it asks the family to call her.

> *Ava was waiting at the school office. The text that would have prevented it had been on Grandma's phone since 10:48 the night before.*

---

## Contents

- [The person](#the-person)
- [The problem, from the data](#the-problem-from-the-data)
- [What Heads-Up does](#what-heads-up-does)
- [What Heads-Up will never do](#what-heads-up-will-never-do)
- [Guardrails and calendar rules](#guardrails-and-calendar-rules)
- [Consent](#consent)
- [Tech stack](#tech-stack)
- [How it's shown working](#how-its-shown-working)
- [How the code decides](#how-the-code-decides)
- [Project structure](#project-structure)
- [Getting started](#getting-started)
- [Roadmap](#roadmap)
- [Progress log](#progress-log)
- [Privacy note](#privacy-note)

---

## The person

**Gloria Benoit**, 68, is a retired Grade 3 teacher who lives in the Halifax area with her husband Ray. She's the family's go-to driver:

- 🎒 Picks up her granddaughter **Ava** from Oakwood Elementary (Tue/Thu at 3:15)
- 🧸 Picks up her grandson **Noah** from daycare (Fri)
- 🚗 Drives **Ray** to his appointments

She uses a hand-me-down iPhone SE and **prefers calls to texts**.

## The problem, from the data

Texts from family that change Gloria's plans can go unseen until it's too late, and nothing puts the change on her calendar or checks that she knows about it.

**What happened on Oct 21–22** (from the persona's phone screenshots):

| When | What happened |
|---|---|
| Wed 10:48 PM | Michelle texts: *"Mom can you get Ava at 2:30 tomorrow instead of 3:15? Early dismissal."* |
| Thu 2:47 PM | 2 missed calls from Michelle |
| Thu 2:52 PM | *"Mom?? School called, Ava's waiting at the office."* |
| Thu 3:58 PM | *"Did you not see my text last night?"* |

**Why it happened:**

- 📱 **She rarely picks up her phone:** about 2 pickups a day, and on that Wednesday the first one was at 7:01 PM.
- 🔕 **Her repeating "Pick up Ava" event has `Alert: None`**, and nothing updates it when plans change.
- 📬 **Important messages get lost in the noise:** 190 notifications that week, 23 unread texts and 1,284 unread emails.

> ⚠️ *This is an inference, not proof. A late text plus rare pickups could explain the miss, but the data doesn't show when she last checked her phone.*

## What Heads-Up does

For texts from family members Gloria has approved (in a simulated inbox), Heads-Up runs a four-step loop:

```
 Family text ──▶ 1. Detect ──▶ 2. Update calendar ──▶ 3. Call Gloria ──▶ 4. Ask family to call if unconfirmed
```

1. **Detect.** It spots a change to an event already on her calendar. The LLM only fills in a fixed **JSON** form (which event, the date words, the new time). Plain code checks every field, works out the date and makes every decision; the model's output is never trusted on its own.
2. **Update the calendar.** If **exactly one** occurrence matches, it moves only that occurrence, labels it `CHANGED by Michelle, was 3:15`, and adds an alert **30 minutes before**. If the date or time is unclear, or there are zero or several matches, it changes nothing and asks her instead.
3. **Call Gloria.** She prefers calls and picks up her phone only about twice a day, so a **phone call is the main channel**. At 8 AM (never during quiet hours, 9 PM–8 AM) Heads-Up calls, reads the change aloud and asks her to **press 1** to confirm. If she doesn't answer, it calls again 2 hours later; voicemail doesn't count as confirmed. A **large-print email** goes out with the first call as the written record, with a **"Got it"** button on a unique, expiring link as a second way to confirm. The calendar alert still fires on her lock screen.
4. **Ask the family to call.** If she hasn't confirmed **60 minutes before** the event, it texts or emails the person who sent the change and asks them to *call her*. This prompts a call but can't guarantee she hears the change.

> *Changed after pitch review:* the reviewer pointed out that an email could go unseen just like Michelle's text did, so the call is now the main way Heads-Up reaches Gloria and email is the backup. In the prototype the call runs on a simulated call screen; a real Twilio call is a stretch goal.

**Optional extensions** (if time allows):

- 💊 **Deadline reminders.** For example, the pharmacy's "3rd reminder" to pick up a prescription by Fri Oct 23, which her own undated reminder would never catch.
- 📦 **Suspicious-text flags.** For example, a fake "Canada Post" text asking for a $1.99 fee. Heads-Up suggests checking with the official source and never calls a message a scam outright.

## What Heads-Up will never do

A focused agent beats one that tries to do everything. Heads-Up will **not**:

- ❌ Act on texts from unknown senders
- ❌ Edit a whole repeating series, or delete events
- ❌ Reply to texts, pay for anything, or tap links
- ❌ Share her messages or phone activity
- ❌ Say a text is *definitely* a scam
- ❌ Give medical advice
- ❌ Read real SMS. iPhone apps can't do that, so this prototype openly simulates the inbox.

## Guardrails and calendar rules

| Rule | Why |
|---|---|
| "Tomorrow" is worked out from **when the text was sent**, in Halifax time | A 10:48 PM text saying "tomorrow" means the next day |
| "Tomorrow" sent between **midnight and 5 AM** counts as unclear, so Heads-Up asks | At 12:30 AM, "tomorrow" could mean today or the next day |
| Only **one occurrence** of a repeating event is ever changed | An early dismissal shouldn't rewrite every Thursday |
| **No match or more than one match means no change** | When it's unsure, it asks rather than guessing |
| Changes **less than 2 hours away** trigger a call right away | There's no time to wait until morning |
| **No calls between 9 PM and 8 AM** (unless the event is under 2 hours away) | A 10:48 PM text shouldn't wake her up |
| A new time outside **7 AM–9 PM** means ask, not edit | Catches AM/PM misreads like "2:30" read as 02:30 |
| Series edits, cancellations and **two changes in one text** mean no edit | The agent never deletes, and keeps one change at a time |
| LLM output is **JSON that code validates** | This blocks prompt injection (e.g. a text saying "ignore your instructions") and malformed results |
| Only **trusted contacts** can trigger actions, and their texts are the **only ones the LLM ever sees** | Strangers and scammers can't move her calendar or reach the model |
| If the LLM is down or returns bad JSON, Heads-Up **asks Gloria** | It never guesses |

## Consent

- **Gloria opts in.** She picks her trusted contacts and which events can be changed, and she can **pause** Heads-Up at any time.
- **Michelle (or any sender) opts in separately.** She only learns whether *that one change* was confirmed, and never sees Gloria's other messages or phone activity.

## Tech stack

| Layer | Tool |
|---|---|
| Language | Python |
| LLM | [Groq](https://console.groq.com) with **`openai/gpt-oss-120b`** in strict JSON-schema mode, and Gemini (`gemini-2.5-flash`) as a backup. The pitch named Llama 3.3 70B, but Groq shut it down in August 2026 and recommends GPT-OSS 120B as the replacement. |
| Calendar | Google Calendar API (test account) |
| Email | Gmail API (test account) |
| Calls | Simulated call screen in Streamlit (press 1 to confirm); real Twilio call as a stretch goal |
| Interface | [Streamlit](https://docs.streamlit.io) for the consent screen, simulated inbox, call screen, decision log and simulated clock |
| Testing | pytest (offline), plus a live LLM eval script |

## How it's shown working

### 1. Replaying the real incident on a simulated clock

```
Wed 10:48 PM  📩 Michelle's text arrives in the simulated inbox
              ✅ Thursday "Pick up Ava" moved 3:15 → 2:30, alert set for 2:00
              🌙 Quiet hours: the call waits until morning
Thu  8:00 AM  📞 Heads-Up calls Gloria: "...press 1 if you got this." No answer
              📧 Large-print record email with a "Got it" button
Thu 10:00 AM  📞 Second call. Voicemail (doesn't count as confirmed)
Thu  1:30 PM  💬 Message to Michelle: "Your mom hasn't confirmed, please call her"
Thu  2:00 PM  🔔 Lock-screen alert: CHANGED by Michelle, was 3:15
```

It's followed by a **before-and-after comparison**: Thursday as it actually happened vs. Thursday with Heads-Up. A second branch shows Gloria answering the 8 AM call and pressing 1, which cancels the rest of the ladder. Both are in `sample_data/replay_timeline.json`.

### 2. A test set of 22 texts

| Case | Expected behaviour |
|---|---|
| "Tomorrow" sent at 10:48 PM | Moves the next day's event |
| "Tomorrow" sent at 12:30 AM | Unclear, so it asks without editing |
| Zero matching events | No edit, asks |
| One matching event | Edits that occurrence only |
| Two matching events | No edit, asks |
| Vague time ("sometime after lunch") | No edit, asks |
| Unknown sender | Ignored |
| "Ignore your instructions and…" | Ignored, no edit |
| Ordinary chit-chat | Does nothing |

The full set (`sample_data/test_messages.json`) also covers a cancellation, a change to choir (which Gloria hasn't allowed), a change under 2 hours away, two changes in one text, "quarter to five", the agent being paused, and the pharmacy and Canada Post texts.

Results are reported as **expected vs. actual**. The targets are ✅ correct changes, ✅ **0** edits when unclear, and ✅ **0** edits from unknown senders.

It's tested in two layers:

| Layer | Command | What it proves |
|---|---|---|
| Rules, offline | `pytest` | With a correct reading of each text, the code takes the right action **for the right reason**. No network or API key needed. |
| Real LLM | `python scripts/eval_llm.py` | How accurately the real model reads each text, and whether the end-to-end decision is still right. Saves `results/llm_eval.json`. |

## How the code decides

```
text ─▶ consent + trusted sender? ─▶ LLM fills the JSON form ─▶ code validates it
     ─▶ kind of change OK? ─▶ date resolved from sent time ─▶ time plausible?
     ─▶ exactly one matching event? ─▶ edit that one occurrence
```

Each step can stop with **no action** or **ask Gloria**, and every decision carries a reason code (e.g. `unclear_date`, `match_count`, `unknown_sender`) and a step-by-step log for the demo. The consent and sender checks run **before** the LLM, so a stranger's text never reaches it.

## Project structure

```
AI Agent Dev/
├── app.py                 # Entry point: build_agent() for the UI; `python app.py` replays Thursday
├── ui.py                  # Streamlit demo: draws agent.snapshot(), buttons call the agent
├── heads_up/
│   ├── agent.py           # HeadsUpAgent: the orchestrator (clock, inbox, decisions, ladders, snapshot)
│   ├── rules.py           # decide(): the pipeline above. apply(): moves one occurrence
│   ├── extractor.py       # The only LLM call: Groq (GPT-OSS 120B) → Gemini backup
│   ├── escalation.py      # Call-first ladder: when to call, retry, email, ask family
│   ├── confirm.py         # One-time, expiring "Got it" links
│   ├── notifier.py        # Simulated outbox for calls, emails and family messages
│   ├── extraction.py      # The JSON form the LLM fills in, and its validator
│   ├── dates.py           # "tomorrow", "Thursday", "Oct 23" → a date, or "unclear"
│   ├── calendar_store.py  # In-memory calendar (Google Calendar shape), one-occurrence edits
│   ├── google_calendar.py # Same interface on the real Google Calendar (test account)
│   ├── google_auth.py     # Google sign-in (credentials.json / token.json)
│   ├── config.py          # Loads sample data; per-case profile overrides
│   └── timeutil.py        # Halifax time helpers (DST-safe)
├── scripts/
│   ├── eval_llm.py        # Runs the real LLM on all 22 texts and scores it
│   ├── seed_calendar.py   # Loads the sample calendar onto the test Google account
│   └── try_google_edit.py # Runs Michelle's text against the real test calendar
├── sample_data/           # Profile, calendar, inbox, replay timeline, 22 test texts, offline readings
├── tests/
│   ├── test_rules.py      # 22 texts + fail-safe, date and schema tests
│   ├── test_extractor.py  # Extractor with fake Groq/Gemini clients
│   ├── test_escalation.py # Ladder timings, both Thursday replays, links, edge cases
│   ├── test_google_calendar.py # Google adapter against a fake Google service
│   ├── test_agent.py      # Orchestrator end to end, both Thursday scenarios
│   └── fixtures/gold_extractions.json
├── setup_google.py        # Google OAuth setup for the test account
├── requirements.txt
└── README.md
```

Gmail and a real Twilio call are stretch goals; `notifier.py` is where they plug in.

## Getting started

```bash
git clone https://github.com/<your-username>/<repo-name>.git
cd <repo-name>
python -m venv venv
venv\Scripts\activate          # Windows (macOS/Linux: source venv/bin/activate)
pip install -r requirements.txt
```

Create a `.env` file (never commit it):

```env
GROQ_API_KEY=your_groq_key
GEMINI_API_KEY=your_gemini_key   # optional backup
# GROQ_MODEL=openai/gpt-oss-120b   # optional override
# GEMINI_MODEL=gemini-2.5-flash    # optional override
```

Then add your Google OAuth `credentials.json` for a **test** Google account (see the [Calendar](https://developers.google.com/workspace/calendar/api/quickstart/python) and [Gmail](https://developers.google.com/workspace/gmail/api/quickstart/python) quickstarts), and run:

```bash
pytest                          # offline tests, no API key needed
python scripts/eval_llm.py      # real LLM on all 22 texts (needs GROQ_API_KEY)
python app.py                   # replay Wed night to Thu afternoon in the terminal (offline)
python app.py --press-1         # same, but Gloria answers the 8 AM call and presses 1
python app.py --live --google   # real LLM + the TEST Google Calendar
streamlit run ui.py             # the demo UI
```

**How the backend is driven.** `app.build_agent()` returns a `HeadsUpAgent`. A frontend moves the simulated clock (`step()`, `advance_to()`), lets Gloria act (`press_1()`, `tap_link()`, `pause()`), can inject a new text (`receive()`), and draws `snapshot()`: plain JSON with the clock, inbox and decisions, calendar, each change's ladder, the outbox (calls, emails, family messages) and a timeline. Offline mode needs no network: it uses saved LLM readings (`sample_data/offline_readings.json`) and an in-memory calendar; a text with no saved reading makes the agent ask Gloria.

**Google Calendar (test account only).** Put the OAuth client file `credentials.json` in the repo root (it and `token.json` are git-ignored), then:

```bash
python scripts/seed_calendar.py            # load the sample calendar (safe to re-run, never deletes)
python scripts/try_google_edit.py          # Michelle's 10:48 PM text → moves only Thu Oct 22
python scripts/try_google_edit.py --reset  # put Thursday back to 3:15 for the next run
```
The first run opens a browser to sign in as the Gloria test account.

## Roadmap

- [x] Persona analysis (Gloria Benoit)
- [x] Pitch, after two review rounds
- [x] Pitch approval
- [x] Work plan (call-first contact plan after review)
- [x] Rules engine with offline tests (22 texts, 0 edits when unclear, 0 from unknown senders)
- [x] LLM extractor (Groq GPT-OSS 120B + Gemini backup) and live eval script
- [x] Live LLM eval run: 22/22 end to end, 0 edits when unclear or from unknown senders
- [x] Call ladder: escalation and confirmation (press 1 / "Got it")
- [x] Google Calendar adapter (test account): one occurrence at a time, never the series
- [ ] *Stretch:* real Gmail email and Twilio call
- [x] Backend orchestrator (`HeadsUpAgent`, `app.py`) with a terminal replay
- [x] Streamlit demo with simulated-clock replay (accessible: large print, 7:1 contrast, 64 px buttons in Gloria's view)
- [ ] Showcase video
- [ ] *Stretch:* deadline reminders, suspicious-text flags, Twilio confirmation call

## Progress log

**Nov 24, 2026**
- Pitch approved. Reviewer feedback: Gloria prefers calls, so an email could go unseen. The contact plan is now **call-first**, with email as the written record. Work plan written.
- Built the rules engine (`rules.py`, `dates.py`, `extraction.py`, `calendar_store.py`). All 22 sample texts pass offline, checked by action **and** reason code; breaking a rule on purpose makes a real case fail.
- Added `scope` and `change_count` to the LLM's JSON form, so code can refuse series edits (T05) and catch two changes in one text (T18).
- Added the 7 AM–9 PM plausibility check for AM/PM misreads.
- Built `extractor.py`: strict JSON-schema call to Groq, plain-JSON retry, Gemini backup; texts are passed as data inside `<text>` tags. Switched from Llama 3.3 70B (shut down on Groq in Aug 2026) to `openai/gpt-oss-120b`.
- Added `scripts/eval_llm.py` to score the real model, and updated the sample data (profile, replay timeline, test timings) for the call-first ladder.
- 61 offline tests passing.
- Live eval with `openai/gpt-oss-120b`: **22/22** texts handled correctly end to end, **0** edits when unclear, **0** edits from unknown senders, 94.8% of fields read exactly as expected. Every misread was caught by code.
- Built the call-first ladder (`escalation.py`, `confirm.py`, `notifier.py`): quiet hours, an urgent "call now" rule, a retry call, the large-print record email, and the family request. Pressing 1 or tapping the one-time "Got it" link cancels the rest. Tested against the T01/T13 timings and both Thursday branches in `replay_timeline.json`, word for word.
- Prompt fix: `old_time` is only filled in when the text states it (T03).
- 79 offline tests passing.
- Built the Google Calendar adapter (`google_calendar.py`): same interface as the test calendar, lists one Halifax day with `singleEvents=True` so each repeat is its own occurrence, and patches only that occurrence (it refuses if Google ever reports a series edit). `seed_calendar.py` loads the sample calendar onto the test account, updating the events `setup_google.py` made instead of duplicating them. `try_google_edit.py` runs Michelle's text against the real calendar, with `--reset` to undo.
- 85 offline tests passing.
- Built the orchestrator (`heads_up/agent.py`) and entry point (`app.py`): one object runs the inbox on a simulated clock, sends each text through the rules, applies edits, runs each change's call ladder, and exposes `snapshot()` for the frontend. Works offline (saved readings + in-memory calendar) or live (Groq + test Google Calendar). `python app.py` replays the whole of Thursday in the terminal.
- 98 offline tests passing.
- Built the Streamlit demo (`ui.py`). Gloria's phone panel shows the ringing call with a large **Press 1** button, the large-print email with **Got it**, reminders and "I wasn't sure" notes. Beside it: what Heads-Up did, Thursday's calendar, every text with its decision and step-by-step reasons, Thursday without Heads-Up, a box to send new test texts, the live test results, and Gloria's consent settings. Designed for an older reader: Atkinson Hyperlegible, 24 px text and 64 px buttons in her panel, colour pairs at 7:1 or better, status always in words, times as "2:30 PM".

## Privacy note

Gloria Benoit and her family are **fictional personas** provided by ShiftKey. All data in this repo is **sample data** rebuilt from the persona screenshots. It uses only test accounts, with no real passwords, messages or personal information.

---

*Built by Vikram for the ShiftKey Side Quest: Persona-Driven AI Agent project, November 2026.*

> *Michelle's text was on Gloria's phone all along. Heads-Up puts the change on her calendar with an alert, and if she hasn't confirmed, asks the family to call her.*