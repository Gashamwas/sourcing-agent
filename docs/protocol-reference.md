# Communication Protocol — WhatsApp

Sam monitors your work through WhatsApp messages and steers you with mid-run nudges. Your reports are his only visibility into what you're doing. Be specific, be evaluative, and never go silent.

**Platform formatting:** No markdown tables. Use bullets. Bold or CAPS for emphasis. No headers (WhatsApp doesn't render them).

---

## Reporting Unit: The Page Report

The atomic unit of communication is one message per page of results. Every page report is a single WhatsApp message containing everything about that page. Do not send separate messages for individual candidates.

**Every page report contains:**

**1. Header**
String number, keyword cluster name, page X of Y, total result count for this string.

**2. Page Overview**
2-3 sentences: general composition of this page. How much signal vs. noise? Patterns? (e.g., "Heavy annotation worker population from Outlier and Scale. 3 profiles with genuine post-training signal. Rest is web dev noise from ORM collision.")

**3. SAVED candidates (detailed)**
For every candidate you opened and saved:
- Name, current role, company
- What they've actually built — the substance of the work, not keywords
- Which archetype(s) they map to and why
- Experience depth: years, seniority, nature of hands-on work
- Why you saved them: the specific signal that crossed the threshold

**4. SKIPPED candidates — profiles opened (detailed)**
For every candidate whose profile you opened but skipped:
- Name, current role, company
- What you found when you looked closer
- Why it didn't meet the bar — what was missing or disqualifying

**5. Skipped from preview (grouped)**
Candidates obviously not fits from the preview card, grouped by pattern:
"8 annotation workers (Outlier ×3, Scale ×2, Appen ×2, Telus ×1), 4 frontend devs, 2 HR/L&D professionals"

**6. Running totals**
Saves this string, saves this session, strings completed this session.

---

## Example Page Report

> **String #5 | TRL / Transformer Reinforcement Learning | Page 2 of 3 | 67 results**
>
> Page 2 is mixed — about half annotation workers from Outlier/Scale, a cluster of web devs matching on "transformer" (the JS library), and 4 genuine ML profiles worth opening.
>
> **SAVED:**
> ✅ Luana Guedes — Sr Research Scientist, CEIA/UFG (6yr). Built deep RL pipelines for production recommendation systems, then transitioned to RLHF on LLMs. Custom reward model training, LLM-as-judge evaluation framework. Post-Training Data Engineer archetype — strong on both RL infrastructure and data quality axes. Published at BRACIS.
>
> ✅ Bryan Lincoln — AI Research Scientist, CEIA/UFG (6yr9mo). RL with human feedback in production, offline RL (behavior cloning, conservative Q-learning), distributed training with Ray RLlib. MSc CS UFG. RL Environment Builder archetype — deep hands-on RL infra experience.
>
> **SKIPPED (opened):**
> ❌ Pedro Rodrigues — SWE, UBS (3yr). Headline says "SFT/DPO" but actual experience is banking IT — API integrations, database management. No ML work in any role. Keyword match only.
>
> ❌ Miguel Neves — Head of AI/ML Research, Samsung (8yr). PhD CS UFRGS. Opened because of Samsung R&D title, but actual work is networking, IoT, military messaging systems, SLA prediction. No post-training or LLM signal.
>
> **Skipped from preview:** 12 annotation workers (Outlier ×5, Scale ×3, Appen ×2, Telus ×2), 5 web devs ("transformer" collision), 2 L&D professionals ("post training" collision)
>
> **Running totals:** 4 saves this string | 12 saves this session | 3 strings complete

---

## Escalation Triggers (immediate, separate message)

These get their own message the moment they happen — do not wait for the page report:

- **Noisy term discovered:** What term, what it collided with, what you did about it, result count before and after.
- **Navigation error:** Clicked similar profiles, got redirected, or any UI state that isn't the search results. Report what you see and what you're doing to recover.
- **Strategic decision:** Switching from individual clusters to a Copy All mega-string, or skipping an entire string. Report what and why.
- **Stuck state:** If any browser action takes longer than 30 seconds without a state change, screenshot, report what you see, and attempt recovery (back button, re-navigate to search URL). If recovery fails twice, stop and report.
- **Exceptional candidate:** Someone who is an outstanding match — call it out immediately so Sam knows.

---

## /stop Behavior

When you receive /stop or any stop command:
1. Immediately halt all browser actions. Do not finish the current page.
2. Save the progress file with current state.
3. Send one confirmation message: "Stopped at String X, Page Y of Z. [N] candidates saved this string, [M] total this session. Progress file updated. Ready to resume on your signal."
4. Do not send queued messages. Do not send a summary. Just the stop confirmation.

---

## Silence Rule

Never go silent for more than one page of results. If a page has zero saves and nothing notable, still send a brief page report: "String #12 | Page 3 of 4 | 25 profiles, all noise — annotation workers and web devs. 0 saves. Moving to page 4."

If you are actively working but processing is slow (e.g., loading profiles), send a brief status: "Still on String #12, Page 3 — loading profiles, 3 evaluated so far."

---

## Why This Protocol Exists

WhatsApp messages queue during tool chains. Sam's mid-run corrections are only received when your current turn completes and a new turn begins. Page-level reporting creates the turn boundaries where you pick up incoming messages. Without page reports, Sam cannot steer you and you cannot receive corrections. This is not optional overhead — it is the mechanism that makes human oversight possible.
