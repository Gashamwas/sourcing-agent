"""Extractors: innerText -> structured data via cheap model.

Two extractors:
1. extract_snippets_from_list_innertext() - results list innerText -> CandidateSnippets
2. extract_profile_from_innertext() - profile innerText -> CandidateProfileSummary

These receive innerText (clean labeled text), NOT raw HTML/DOM.
"""

import time
from schemas import CandidateSnippet, CandidateProfileSummary, Experience, Education
from llm_clients import cheap_llm


# ---------------------------------------------------------------------------
# Stage 1: List view innerText -> CandidateSnippets
# ---------------------------------------------------------------------------

LIST_EXTRACTION_SYSTEM = """You are a precise data extractor. You receive innerText from a LinkedIn Recruiter search results page. The text is structured with labeled fields per candidate card:

Each card follows this pattern:
- "Select {Name}" then "{Name}" (the candidate's full name)
- Connection degree
- Headline text
- Location and field/industry
- Experience section: titles, companies, dates
- Education section: schools, degrees, dates
- "Save to pipeline" button text

Extract every candidate visible.

Return a JSON object with key "candidates" containing an array. Each object:
- "name": Full name (string)
- "headline": Headline text (string)
- "current_title": Current job title (string, from first experience entry or headline)
- "current_company": Current employer (string)
- "location": Location (string)
- "education_snippet": Visible education info (string, empty if not shown)
- "profile_url": LinkedIn profile URL if visible (string, usually /talent/profile/...)
- "result_rank": Position in results, 1-indexed (integer)
- "experience_entries": Array of ALL visible experience entries as compact strings in format "Title at Company (dates)" (array of strings). Extract every line matching "Title at Company · dates". IGNORE decoration lines: "Profile experience", "Similar skills to saved candidates", "Enhanced by resume", "Show all (N)", "Experience". Only extract actual role entries.

Rules:
- Extract ALL candidates, not just the first few
- If a field is not visible, use empty string ""
- Parse current_title and current_company from Experience section or headline ("Title at Company")
- Do NOT invent data. Only extract what's in the text.
- Return valid JSON only. No markdown, no explanation."""


def _chunk_innertext(innertext: str, max_cards_per_chunk: int = 10) -> list[str]:
    """Split results innertext into chunks by candidate card boundaries.

    LinkedIn Recruiter cards start with 'Select {Name}' (the checkbox label).
    Splitting on this boundary keeps each card's data intact.
    """
    import re
    # Split on the "Select " pattern that precedes each candidate name
    parts = re.split(r'(?=\nSelect )', innertext)
    # First part may be page header / nav — keep it as prefix
    prefix = parts[0] if parts else ""
    cards = parts[1:] if len(parts) > 1 else [innertext]

    if not cards:
        return [innertext]

    chunks = []
    for i in range(0, len(cards), max_cards_per_chunk):
        batch = cards[i:i + max_cards_per_chunk]
        # Prepend prefix only to first chunk (it has nav/header context)
        if i == 0:
            chunks.append(prefix + "".join(batch))
        else:
            chunks.append("".join(batch))

    return chunks


def extract_snippets_from_list_innertext(
    innertext: str,
    string_id: int,
    string_name: str,
    page: int,
) -> list[CandidateSnippet]:
    """Extract candidate snippets from LinkedIn Recruiter results list innerText.

    For large pages (>10KB), splits into chunks to avoid LLM timeouts.
    """
    chunks = _chunk_innertext(innertext) if len(innertext) > 10_000 else [innertext]
    print(f"  [extract] {len(innertext)/1024:.0f} KB innertext → {len(chunks)} chunk(s)", flush=True)

    all_snippets: list[CandidateSnippet] = []
    rank_offset = 0

    for ci, chunk in enumerate(chunks):
        user_prompt = f"""Extract all candidates from this LinkedIn Recruiter search results text.

Search context: String #{string_id} "{string_name}", page {page}{f' (chunk {ci+1}/{len(chunks)})' if len(chunks) > 1 else ''}.

Results text:
{chunk}"""

        print(f"  [extract] Chunk {ci+1}/{len(chunks)}: {len(user_prompt)/1024:.0f} KB prompt...", flush=True)
        t0 = time.time()
        result = cheap_llm(LIST_EXTRACTION_SYSTEM, user_prompt, expect_json=True)
        print(f"  [extract] Chunk {ci+1} returned in {time.time()-t0:.1f}s", flush=True)

        candidates_raw = result.get("candidates", []) if isinstance(result, dict) else result
        for c in candidates_raw:
            try:
                snippet = CandidateSnippet(
                    name=c.get("name", ""),
                    headline=c.get("headline", ""),
                    current_title=c.get("current_title", ""),
                    current_company=c.get("current_company", ""),
                    location=c.get("location", ""),
                    education_snippet=c.get("education_snippet", ""),
                    profile_url=c.get("profile_url", ""),
                    source_string_id=string_id,
                    source_string_name=string_name,
                    page=page,
                    result_rank=c.get("result_rank", 0) + rank_offset,
                    experience_entries=c.get("experience_entries", []),
                )
                if snippet.name:
                    all_snippets.append(snippet)
            except Exception as e:
                print(f"  [warn] Failed to parse candidate: {e}")
                continue

        rank_offset += len(candidates_raw)

    return all_snippets


# Legacy alias for orchestrator compatibility
def extract_snippets_from_list_dom(
    dom_text: str, string_id: int, string_name: str, page: int,
) -> list[CandidateSnippet]:
    return extract_snippets_from_list_innertext(dom_text, string_id, string_name, page)


# ---------------------------------------------------------------------------
# Stage 3: Profile innerText -> CandidateProfileSummary
# ---------------------------------------------------------------------------

PROFILE_EXTRACTION_SYSTEM = """You are a precise data extractor. You receive innerText from a LinkedIn Recruiter profile slide-in panel. The text has labeled sections:

- Header: Name, headline, company, university, location
- Summary section: plain text bio
- Experience entries with labeled fields: "Position title", "Company name", "Dates employed and Duration", "Position location", "Position summary", "Skills: ..."
- Education entries: school, degree, dates

Return a JSON object:
- "name": Full name (string)
- "headline": Profile headline (string)
- "experiences": Array of objects with: "title", "company", "location", "start", "end", "summary_bullets" (array of strings)
- "education": Array of objects with: "degree", "school", "field", "start", "end"
- "skills_snippet": Array of skill strings from Skills labels in experience entries

Rules:
- Extract ALL experiences and education, most recent first
- For summary_bullets, use actual text from position summaries
- If a field is not visible, use empty string ""
- Return valid JSON only."""


def extract_profile_from_innertext(
    innertext: str,
    profile_url: str,
) -> CandidateProfileSummary:
    """Extract structured profile summary from LinkedIn Recruiter profile innerText."""

    user_prompt = f"""Extract structured profile data from this LinkedIn Recruiter profile text.

Profile URL: {profile_url}

Profile text:
{innertext}"""

    result = cheap_llm(PROFILE_EXTRACTION_SYSTEM, user_prompt, expect_json=True)

    return CandidateProfileSummary(
        name=result.get("name", ""),
        profile_url=profile_url,
        headline=result.get("headline", ""),
        experiences=[
            Experience(**{k: v for k, v in e.items() if k in Experience.__dataclass_fields__})
            for e in result.get("experiences", [])
        ],
        education=[
            Education(**{k: v for k, v in e.items() if k in Education.__dataclass_fields__})
            for e in result.get("education", [])
        ],
        skills_snippet=result.get("skills_snippet", []),
    )


# Legacy alias
def extract_profile_from_dom(dom_text: str, profile_url: str) -> CandidateProfileSummary:
    return extract_profile_from_innertext(dom_text, profile_url)
