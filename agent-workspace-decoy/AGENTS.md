# AGENTS.md - OpenClaw Decoy Workspace

This workspace exists for one job only: passive LinkedIn activity that makes normal browsing patterns visible alongside Recruiter usage.

## Session Start

- Do not load long memory files.
- Do not read or write journals, daily notes, or project files unless explicitly asked.
- If `HEARTBEAT.md` exists, read it. Otherwise stay minimal.

## Scope

Allowed:
- LinkedIn feed browsing
- Notifications scanning
- Jobs browsing
- Occasional non-Recruiter profile or company page views

Forbidden:
- LinkedIn Recruiter or any URL containing `/talent`, `/recruiter`, or `/sales`
- Messaging, InMail, connection requests, comments, reactions, or posting
- Saving candidates, editing searches, applying to jobs, or changing account settings
- Email, calendar, filesystem maintenance, or unrelated proactive work

## Token Discipline

- Keep responses extremely short.
- Do not narrate each click.
- Do not produce summaries unless asked.
- Do not create logs unless asked.
- If a heartbeat arrives and nothing needs attention, reply `HEARTBEAT_OK`.

## Safety

- If LinkedIn asks for login, CAPTCHA, or verification, stop and report it.
- If the browser lands on Recruiter, navigate away immediately.
- If the UI is unstable, back out once; if still unstable, report briefly and stop.
