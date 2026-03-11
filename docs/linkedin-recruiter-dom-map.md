# LinkedIn Recruiter DOM Map — Extracted 2026-03-09

## Search Results Page

### Results List Container
- Selector: `ol.profile-list`
- Each item: `li.profile-list__border-bottom`
- Data attribute: `data-test-paginated-profile-list-item-container`
- Article inside: `article.profile-list-item.hp-core-temp`
- Items per page: 26 (observed)

### Candidate Card Fields (from innerText structure)
Each card renders this text sequence:
```
Select {Name}
{Name}
{Connection degree}
· {degree}
{Headline}
{Location} · {Field/Industry}
Experience
Profile experience
[Enhanced by resume]
{Title} at {Company} · {Start} – {End}
{Title} at {Company} · {Start} – {End}
...
[Show all ({N})]
Education
Profile education
{School}, {Degree} · {Start} – {End}
...
[Skills Match]
[Interest]
Save to pipeline
[Save to pipeline Select pipeline stage to save to]
Hide {N} candidate(s)
Message {Name}
More actions for {Name}
```

### Confirmed Selectors
| Element | Selector |
|---------|----------|
| Results list | `ol.profile-list` |
| Result item | `li.profile-list__border-bottom` |
| Result article | `article.profile-list-item` |
| Candidate name | `[class*="lockup__title"] a` (inside article) |
| Headline | `[class*="lockup__subtitle"]` (artdeco-entity-lockup__subtitle) |
| Location + field | Part of innerText, near headline — no dedicated class found |
| Experience section | `history-group__definition` label, `history-group__term` parent |
| Save to pipeline (main button) | `button.save-to-pipeline__button` |
| Save dropdown (arrow) | `button.save-to-pipeline__dropdown-trigger` |
| Hide button | `button.profile-item-actions__item` |
| Pagination Next | `button[aria-label="Next"]` |
| Pagination Previous | `button[aria-label="Previous"]` |
| Keywords input | `input[aria-label="Search by job title, ideal candidate, keyword, or boolean"]` (class: `artdeco-typeahead__input ts-common-typeahead__input`) |

### Save Button Detail
- Main button class: `save-to-pipeline__button save-to-pipeline__button--with-trigger artdeco-button artdeco-button--secondary`
- Dropdown trigger class: `artdeco-dropdown__trigger save-to-pipeline__dropdown-trigger artdeco-button artdeco-button--secondary`
- Per the brief: "Do NOT use the dropdown arrow next to 'Save to pipeline' or try to select a stage. Just click the main button."
- 12 save buttons found on page (one per visible result card × 2: main + dropdown)

### Lockup Component Structure
LinkedIn uses `artdeco-entity-lockup` components:
- `artdeco-entity-lockup--size-5` and `--size-7` variants
- `artdeco-entity-lockup__title` → contains name link
- `artdeco-entity-lockup__subtitle` → contains headline
- `artdeco-entity-lockup__badge` → connection degree
- `artdeco-entity-lockup__image` → avatar

### Other UI Elements
- "Hide filters" / "Show filters" toggle button
- "Clear search" button at bottom of sidebar (FORBIDDEN — wipes all filters)
- Individual "Clear" button per filter section
- AI Search textarea: `textarea.copilot-chat-input__textbox` (never use)
- Result count: "293 RESULTS" text near top

### Pagination
- `button[aria-label="Previous"]` — disabled when on first page
- `button[aria-label="Next"]` — standard artdeco button
- No page number buttons observed

## Profile Page (Slide-In Panel)

The profile does NOT open as a separate page. It opens as a slide-in panel on top of search results. The URL changes to include `/recruiterSearch/profile/{memberID}` but the search results DOM stays loaded underneath.

### Container Hierarchy
```
div.profile-slidein__container          ← outermost wrapper
  div.pagination-header.profile-slidein__pagination-header-wrapper  ← prev/next + header
  div.profile.profile-slidein__profile  ← the profile itself
    div.profile__main-container         ← main content area (47K+ chars text)
```

### Navigation Between Candidates
- Previous: `button.skyline-pagination-button` (text: "Previous candidate")
- Next: also `button.skyline-pagination-button` (text: "Next candidate")
- Counter text: "1 of 293" / "Showing result 1 of 293"

### Profile Header (Lockup)
Inside `section.lockup.liha-inline-feedback`:
- Name, connection degree, headline, current company · university · location · field · connection count
- Contact buttons: "Add email", "Add phone number", "Public profile"
- Save to pipeline button (same `button.save-to-pipeline__button` as in search results)
- Hide, Message, Share, More actions buttons

### Section Structure
Sections identified by `h2` headings within `profile__main-container`:
1. **Summary** — `section.summary-card` — plain text bio
2. **Experience** — `section` with `expandable-list expandable-stepper` classes
3. **Volunteer Experience** (if present)
4. **Accomplishments** — `accomplishments-expandable-list` classes
5. **Personal Information**
6. **Education** — may or may not be a separate section (varies by profile)

### Experience Entry Structure
Each experience entry lives in a `[class*="position-item"]` container. The innerText structure:
```
Position title
{Job Title}
Company name
{Company Name} · {Employment Type}
Dates employed and Duration
{Month Year} – {Present|Month Year} • {Duration}
Position location
{City, State, Country}
Position summary
{Description text...}
Skills: {Skill1} • {Skill2} • {Skill3}
```

Internally uses `dl/dt/dd` pairs (41 dl elements across the full profile). Key stable class: `background-entity__description-container`.

### Key Semantic Classes (stable, not obfuscated)
Experience: `position-item`, `background-entity__description-container`, `background-entity__*`
Summary: `summary-card`
Accomplishments: `accomplishments-base-entity__title`, `accomplishments-base-entity__company-name`, `accomplishments-base-entity__date`, `accomplishments-base-entity__description`, `accomplishments-expandable-list`
Layout: `expandable-list`, `expandable-stepper`, `profile-list`, `lockup`
Actions: `save-to-pipeline__button`, `save-to-pipeline__dropdown-trigger`, `profile-item-actions__item`

Note: Many classes are obfuscated/hashed (e.g., `GXCgsZhlEEvscXaUIzFnTHWyTnuoyYvKcPdk`). These change between LinkedIn deployments. Only rely on the semantic class names listed above.

### Tabs in Profile Panel
Profile, Projects (0), Messages (0), Greenhouse, Feedback (0), More — rendered as tab-like navigation within the slide-in panel.

### Profile innerText for Cheap Model
The full `div.profile.profile-slidein__profile` innerText is ~50K chars. It's cleanly structured with labeled sections and labeled fields within experience entries. The cheap model can extract from innerText directly rather than parsing HTML — much more token-efficient and resilient to class name changes.

## Notes for Pipeline Build

### Selector Corrections (browser.py)
Every selector in the pipeline scaffold is wrong. Correct mappings:

| Function | Wrong (scaffold) | Correct (verified) |
|----------|-------------------|---------------------|
| Results container | `[class*="search-results"]` | `ol.profile-list` |
| Result item | generic | `article.profile-list-item` inside `li.profile-list__border-bottom` |
| Keywords input | `input[placeholder*="keyword" i]` | `input[aria-label*="keyword" i]` |
| Next page | `button:has-text("Next")` | `button[aria-label="Next"]` |
| Prev page | `button:has-text("Previous")` | `button[aria-label="Previous"]` |
| Save button | `button:has-text("Save")` | `button.save-to-pipeline__button` (NOT the dropdown trigger!) |
| Profile container | N/A (assumed new page) | `div.profile.profile-slidein__profile` (slide-in panel, not page nav) |
| Profile prev/next | N/A | `button.skyline-pagination-button` |

### Architecture Implications
1. **Profile is a slide-in, not a page navigation.** `browser.open_profile()` should click the candidate name link in the results list — the profile loads as a panel overlay. `browser.go_back_to_results()` should close/dismiss the panel, not `page.go_back()`.
2. **50K chars of profile text is too much for the cheap model.** Extract only `profile__main-container` sections: header lockup + Summary + Experience + Education (if present). Skip Accomplishments, Volunteer Experience, Personal Information, Similar Profiles, Projects/Messages/Greenhouse tabs.
3. **innerText is the correct extraction method** for both results cards and profiles. The text is cleanly structured with labeled fields. Parsing HTML class names is fragile (obfuscated classes change). innerText is stable.
4. **Save button exists in both views** — on the result card and in the profile slide-in. The brief says to read the full profile first, then save from the profile panel.
5. **Results count text** "293 RESULTS" is near the top but not in a dedicated element with a stable class. Parse from page text.
6. **26 results per page** observed (not 25 as assumed in SKILL.md).
