# SideKick
# Heads-Up 📅

**When the family changes Grandma's plans by text, Heads-Up makes sure she actually hears about it.**

![Status](https://img.shields.io/badge/status-pitch%20done%20·%20build%20in%20progress-orange)
![Python](https://img.shields.io/badge/python-3.11+-blue)
![LLM](https://img.shields.io/badge/LLM-Groq%20·%20Llama%203.3%2070B-purple)
![UI](https://img.shields.io/badge/UI-Streamlit-red)
![Data](https://img.shields.io/badge/data-100%25%20sample-green)

Heads-Up is a persona-driven AI agent built for the **ShiftKey Side Quest** (beta-tester cohort, November 2026). It reads texts from trusted family members, spots changes to plans already on the calendar, moves the right event, sets an alert, and checks that the change was seen. If it wasn't seen, it asks the family to call.

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
- [Project structure](#project-structure)
- [Getting started](#getting-started)
- [Roadmap](#roadmap)
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
 Family text ──▶ 1. Detect ──▶ 2. Update calendar ──▶ 3. Notify Gloria ──▶ 4. Escalate if unconfirmed
```

1. **Detect.** It spots a change to an event already on her calendar and pulls out the date and new time. The LLM returns structured **JSON**, and plain code checks it; the model's output is never trusted on its own.
2. **Update the calendar.** If **exactly one** occurrence matches, it moves only that occurrence, labels it `CHANGED by Michelle, was 3:15`, and adds an alert **30 minutes before**. If the date or time is unclear, or there are zero or several matches, it changes nothing and asks her instead.
3. **Notify Gloria.** The calendar alert is the main nudge, since it shows on her lock screen with no app to open. A **large-print email from a VIP sender** is the backup and the written record. It has a **"Got it"** button on a unique, expiring link, so no one else can confirm for her.
4. **Escalate.** If she hasn't confirmed **60 minutes before** the event, it emails the person who sent the change and asks them to *call her*. This fits how Gloria actually likes to communicate. It prompts a call but can't guarantee she hears the change.

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
| Changes **less than 2 hours away** go out right away | There's no time to wait for a scheduled briefing |
| LLM output is **JSON that code validates** | This blocks prompt injection (e.g. a text saying "ignore your instructions") and malformed results |
| Only **trusted contacts** can trigger actions | Strangers and scammers can't move her calendar |

## Consent

- **Gloria opts in.** She picks her trusted contacts and which events can be changed, and she can **pause** Heads-Up at any time.
- **Michelle (or any sender) opts in separately.** She only learns whether *that one change* was confirmed, and never sees Gloria's other messages or phone activity.

## Tech stack

| Layer | Tool |
|---|---|
| Language | Python |
| LLM | [Groq](https://console.groq.com) with **Llama 3.3 70B** (free tier), and Gemini as a backup |
| Calendar | Google Calendar API (test account) |
| Email | Gmail API (test account) |
| Interface | [Streamlit](https://docs.streamlit.io) for the consent screen, simulated inbox, decision log, briefing preview, confirmation page and simulated clock |
| Testing | pytest |
| Stretch goal | Twilio confirmation call |

## How it's shown working

### 1. Replaying the real incident on a simulated clock

```
Wed 10:48 PM  📩 Michelle's text arrives in the simulated inbox
              ✅ Thursday "Pick up Ava" moved 3:15 → 2:30, alert set for 2:00
Thu  8:00 AM  📧 Large-print email sent to Gloria with a "Got it" button
              ⏳ No confirmation...
Thu  1:30 PM  📞 Email to Michelle: "Gloria hasn't confirmed, please call her"
Thu  2:00 PM  🔔 Lock-screen alert: CHANGED by Michelle, was 3:15
```

It's followed by a **before-and-after comparison**: Thursday as it actually happened vs. Thursday with Heads-Up.

### 2. A test set of about 20 texts

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

Results are reported as **expected vs. actual**. The targets are ✅ correct changes, ✅ **0** edits when unclear, and ✅ **0** edits from unknown senders.

## Project structure

*Planned layout. It will be updated as the build progresses.*

```
heads-up/
├── app.py                 # Streamlit UI (consent, inbox, log, simulated clock)
├── agent/
│   ├── detect.py          # LLM call → JSON change detection
│   ├── validate.py        # Code-side checks on the LLM output
│   ├── calendar_sync.py   # Google Calendar: match & move one occurrence
│   ├── notify.py          # Gmail: large-print email + "Got it" link
│   ├── escalate.py        # 60-min-before check → email sender
│   └── rules.py           # Time rules, trusted contacts, guardrails
├── data/
│   └── sample_inbox.json  # Sample texts rebuilt from persona screenshots
├── tests/
│   └── test_cases.py      # ~20-text test set, expected vs. actual
├── requirements.txt
└── README.md
```

## Getting started

*Setup steps will be finalised once the build is complete.*

```bash
git clone https://github.com/<your-username>/<repo-name>.git
cd <repo-name>
pip install -r requirements.txt
```

Create a `.env` file (never commit it):

```env
GROQ_API_KEY=your_groq_key
GEMINI_API_KEY=your_gemini_key   # optional backup
```

Then add your Google OAuth `credentials.json` for a **test** Google account (see the [Calendar](https://developers.google.com/workspace/calendar/api/quickstart/python) and [Gmail](https://developers.google.com/workspace/gmail/api/quickstart/python) quickstarts), and run:

```bash
streamlit run app.py   # launch the demo
pytest                 # run the test set
```

## Roadmap

- [x] Persona analysis (Gloria Benoit)
- [x] Pitch, after two review rounds
- [ ] Pitch approval
- [ ] Work plan
- [ ] Build: detection, calendar sync, notifications, escalation
- [ ] Test set (~20 texts) passing targets
- [ ] Streamlit demo with simulated-clock replay
- [ ] Showcase video
- [ ] *Stretch:* deadline reminders, suspicious-text flags, Twilio confirmation call

## Privacy note

Gloria Benoit and her family are **fictional personas** provided by ShiftKey. All data in this repo is **sample data** rebuilt from the persona screenshots. It uses only test accounts, with no real passwords, messages or personal information.

---

*Built by Vikram for the ShiftKey Side Quest: Persona-Driven AI Agent project, November 2026.*

> *Michelle's text was on Gloria's phone all along. Heads-Up puts the change on her calendar with an alert, and if she hasn't confirmed, asks the family to call her.*