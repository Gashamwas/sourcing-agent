"""Extractors: DOM → structured data via cheap model.

Two extractors:
1. extract_snippets_from_list_dom() — list view DOM → list of CandidateSnippet
2. extract_profile_from_dom() — profile DOM → CandidateProfileSummary
"""

from schemas import CandidateSnippet, CandidateProfileSummary, Experience, Education
from llm_clients import cheap_llm


# ---------------------------------------------------------------------------
# Stage 1: List view DOM → CandidateSnippets
# ---------------------------------------------------------------------------

LIST_EXTRACTION_SYSTEM = """You are a precise data extractor. You receive raw HTML/DOM from a LinkedIn Recruiter search results page. Extract every candidate visible in the results list.

Return a JSON object with a single key "candidates" containing an array. Each candidate object has these fields:
- "name": Full name (string)
- "headline": Their headline text (string)
- "current_title": Current job title (string, extract from headline or role info)
- "current_company": Current employer (string)
- "location": Location shown (string)
- "education_snippet": Any visible education info (string, empty if not shown)
- "profile_url": The LinkedIn profile URL from the link (string)
- "result_rank": Position in the results list, 1-indexed (integer)

Rules:
- Extract ALL candidates visible, not just the first few
- If a field is not visible, use empty string ""
- For profile_url, extract the href from the candidate's name link. It usually looks like /talent/profile/...
- For current_title and current_company, parse from the headline or subtitle line. The headline often shows "Title at Company"
- Do NOT invent or hallucinate data. Only extract what's actually in the DOM.
- Return valid JSON only. No markdown, no explanation."""


def extract_snippets_from_list_dom(
    dom_text: str,
    string_id: int,
    string_name: str,
    page: int,
) -> list[CandidateSnippet]:
    """Extract candidate snippets from a LinkedIn Recruiter search results page DOM."""

    user_prompt = f"""Extract all candidates from this LinkedIn Recruiter search results DOM.

Search context: String #{string_id} "{string_name}", page {page}.

DOM content:
{dom_text}"""

    result = cheap_llm(LIST_EXTRACTION_SYSTEM, user_prompt, expect_json=True)

    candidates_raw = result.get("candidates", []) if isinstance(result, dict) else result
    snippets = []
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
                result_rank=c.get("result_rank", 0),
            )
            if snippet.name:  # skip empty extractions
                snippets.append(snippet)
        except Exception as e:
            print(f"  [warn] Failed to parse candidate: {e}")
            continue

    return snippets


# ---------------------------------------------------------------------------
# Stage 3: Profile DOM → CandidateProfileSummary
# ---------------------------------------------------------------------------

PROFILE_EXTRACTION_SYSTEM = """You are a precise data extractor. You receive raw HTML/DOM from a LinkedIn Recruiter candidate profile page. Extract structured information about this person.

Return a JSON object with these fields:
- "name": Full name (string)
- "headline": Profile headline (string)
- "experiences": Array of experience objects, each with:
  - "title": Job title (string)
  - "company": Company name (string)
  - "location": Location (string, empty if not shown)
  - "start": Start date as "YYYY-MM" or "YYYY" (string)
  - "end": End date as "YYYY-MM" or "Present" (string)
  - "summary_bullets": Array of strings — key responsibilities/achievements visible
- "education": Array of education objects, each with:
  - "degree": Degree name (string, e.g., "PhD Computer Science")
  - "school": School name (string)
  - "field": Field of study (string)
  - "start": Start year (string)
  - "end": End year (string)
- "skills_snippet": Array of skill strings visible on the profile

Rules:
- Extract ALL experiences and education entries visible, in chronological order (most recent first)
- For summary_bullets, extract actual visible text — NOT the full job description, just key points
- If a field is not visible, use empty string ""
- Return valid JSON only. No markdown, no explanation."""


def extract_profile_from_dom(
    dom_text: str,
    profile_url: str,
) -> CandidateProfileSummary:
    """Extract a structured profile summary from a LinkedIn Recruiter profile DOM."""

    user_prompt = f"""Extract structured profile data from this LinkedIn Recruiter profile DOM.

Profile URL: {profile_url}

DOM content:
{dom_text}"""

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
