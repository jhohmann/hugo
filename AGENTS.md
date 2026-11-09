# AGENTS.md — Hugo

## Mission

Hugo is a **proactive personal assistant**, not a chatbot clone or a passive question-answering interface. The user wants Hugo to **independently help organize life and work**, notice opportunities and risks, keep track of commitments and evolving plans, and suggest useful next actions at the right time.

The defining product question is: **“What should Hugo notice or do for the user, even when the user has not just asked a question?”**

Optimize for genuine assistance and reliable initiative, not for accumulating chat features.

## Product priorities (in order)

1. **Time awareness and planning.** Understand dates, deadlines, lead times, dependencies, preparation windows, calendar constraints, and the difference between tentative plans and commitments. Proactively detect when a decision or action is becoming time-critical.
2. **Long-running threads.** Maintain continuity across conversations for projects, travel, household matters, recurring responsibilities, and other ongoing intentions. Track state, next actions, open questions, deadlines, dependencies, and what is waiting on whom.
3. **Proactive assistance.** Surface timely, specific, actionable observations: upcoming deadlines, conflicts, neglected plans, useful preparation steps, and opportunities. Avoid generic nudges and unnecessary notifications.
4. **Long-term memory.** Remember durable user context, preferences, decisions, and changes. Retrieve relevant memories when useful; update outdated information rather than accumulating contradictory duplicates.
5. **Natural conversation.** Keep responses short, direct, and in German by default. Hugo should use memory seamlessly, without talking about internal storage, IDs, or confirmation status unless asked.
6. **Controlled action.** Suggest and prepare actions autonomously, but require explicit user approval before modifying external systems (e.g. creating/moving calendar events, sending messages, or making commitments).

A successful Hugo is measured by **useful, timely interventions**, not by how much it talks or how many facts it stores.

## Design principles

- **Model-led, tool-enabled:** Let the LLM interpret context, connect facts, choose tools, and decide whether a memory or thread should be created/updated. Python provides dependable tools, validation, persistence, scheduling, and authorization boundaries.
- **Do not recreate an LLM in Python.** Avoid brittle keyword rules, special-case resolution of references (“the trip”), rigid multi-agent pipelines, and elaborate decision trees where model tool-calling suffices.
- **Use structured state for durable facts and execution.** Conversations are not a substitute for a reliable database, real calendar, or scheduled job runner.
- **Separate observation, suggestion, and action.** Hugo may independently discover and propose. External side effects need authorization. Distinguish internal bookkeeping from external commitments.
- **Preserve uncertainty.** “Considering a trip” is not “booked a trip”; a suggested deadline is not a confirmed appointment. Never invent dates or mark speculation as decided.
- **Be proactive, not intrusive.** Prioritize relevance, timing, confidence, and notification fatigue. No obligatory follow-up question after every reply.
- **Favor the simplest coherent architecture.** One central agent with tools is preferred over separate overlapping agents unless evidence shows a clear need.
- **Design for eventual unattended operation.** Proactivity requires a scheduler/worker that can evaluate time-based triggers without an incoming chat message.
- **Make behavior observable.** Log tool names, outcomes, errors, and token usage appropriately, without exposing secrets. Keep important state changes auditable.
- **Keep the user in control.** Easy inspection, correction, confirmation, and dismissal of memories, threads, and suggestions.

## User experience

- Default language: **German (de-DE)**.
- Be concise, practical, and straightforward. Avoid emojis, decorative graphics, and unsolicited long explanations.
- Hugo's chat replies should focus on timing: dates, deadlines, lead times,
  conflicts and other ongoing activities. Usually 2–4 short sentences and at
  most one useful next step; no unsolicited general guides or checklists.
  Detailed advice remains available when explicitly requested. Concise output
  must not replace checking relevant calendars and other open plans.
- Hugo should not narrate its internal database operations in normal conversation.
- Public thread references use `V-<id>` (for example `V-42`). These identifiers
  may be shown in the UI and used in chat for explicit, unambiguous references;
  they are distinct from narrating internal storage details.
- Ask only questions that materially unblock progress.
- Decide autonomously whether and when reminders are useful; do not ask the user
  to approve internal memory/thread bookkeeping or choose warning thresholds.
  Assess criticality from priorities, target dates, consequences of delay,
  dependencies and actually usable time across ongoing plans. Reassess when
  circumstances change; a distant deadline can already require action.
  Keep this model-led and domain-independent, and respect explicit deferrals.
- When the user says “weiter”, continue with the next sensible, testable development increment rather than revisiting settled decisions.
- Prefer end-to-end, small, verifiable steps. Provide exact filenames and code changes when implementing.

## Repository and documentation

This local Windows checkout is the development environment; PostgreSQL runs in Docker.
The future target is Docker Engine on a Proxmox guest. No production deployment has
occurred. One user and one worker; eventual work/private separation is desirable.
No email-reading integration is wanted.

[README.md](README.md) is the authoritative technical and operational documentation:
setup, authentication, architecture, schema, API, deployment, updates, backups,
verification history, known limitations and roadmap. Read the relevant sections
and actual source before editing; historical observations are not current guarantees.

### Documentation policy

Before creating ANY new Markdown file, search existing Markdown documentation and
check whether the information already exists or belongs in an existing section.
Update README.md for product/technical/operational information and AGENTS.md for
agent instructions. Merge duplicates without losing unique facts, decisions,
limitations or verification history. Correct obsolete claims and label historical
observations. Do not create separate status, audit, quick-start or implementation
summary files. A new document needs a genuinely separate purpose that cannot be
served by these files; explain that purpose before creating it. Maintain links.

Keep application code under backend/app, automated tests under tests, and manual
diagnostics/operations under scripts. Manual scripts must not execute at import.
Use the existing domain folders; keep runtime and development dependencies separate.
Keep local credentials, generated caches, logs and backups out of version control
and Docker build contexts. See README for the repository layout.

## Working agreement

1. Read AGENTS.md, relevant README sections, source and the schema before changes.
2. Keep the proactive time-planning mission central; explain architectural trade-offs briefly.
3. Implement the smallest coherent vertical slice and verify through tests or an observable API result.
4. Preserve existing data and APIs. The pre-deployment schema is consolidated in
   backend/migrations/001_initial.sql. Once applied, migration files are immutable;
   add numbered migrations for subsequent schema changes. Never reset volumes to update.
5. Keep local and Docker operation supported. Local entry point: python -m app.dev
   from backend; it loads the root .env and migrates before starting. Docker uses
   a dedicated migration service before web/worker. See README for exact commands.
6. Keep credentials in environment configuration, out of logs, source and images.
7. Prefer the central model-driven tool loop. Python enforces validation,
   authorization and safe side effects. Do not restore the obsolete memory-agent pipeline.
8. Do not claim success without evidence. State what works, what remains untested
   and the next logical milestone after each step.

## Important anti-goals

- Do not build a ChatGPT imitation or accumulate chat-centric features.
- Do not hardcode life-domain logic such as travel rules in Python.
- Do not turn every message into a task or require manual curation of every memory.
- Semantic similarity alone is not sufficient evidence for an update target.
- Avoid complex agent orchestration or infrastructure without a demonstrated need.
- Never automatically edit external calendars or send messages without approval.
- A successful chat is not proof of autonomous proactivity; verify scheduled runs
  and useful, timely interventions separately.

## Resume point

Password-only login and persistent sessions work locally, confirmed by the user.
The current cleanup consolidates schema and documentation and prepares the shared
local/Docker startup and update path. Verification results are recorded in README.
Next operational milestone: first deployment on Proxmox, including HTTPS, a real
backup/restore exercise and observation of scheduled evaluations. Deployment and
external calendar/model behavior must not be claimed tested by mocked unit tests.
