# How We Found the v13 FDE Pool (March 2026 Campaign Snapshot)

Historical campaign artifact preserved for context.

## Why this run focused on edge cases first

The starting assumption in the brief was that the obvious Forward Deployed Engineer market was already heavily worked. Because of that, the run was designed to open on edge-case transfer populations rather than canonical FDE titles. The brief was explicit about this: the first set of searches should be majority adjacent pools, and the opening should be judged on novelty as well as productivity.

That changed the shape of the run in a pretty practical way. Instead of starting with `Forward Deployed Engineer`, Palantir-style populations, or generic "agentic + production" searches, v13 went looking for people who were doing the work under different labels: backend engineers who had moved into GenAI delivery, product/problem-language builders, consulting engineers who still built for clients, founding/0-to-1 builders, and people integrating AI into messy enterprise systems.

## What in the brief turned into strategy

The brief had a few ingredients that drove the strategization directly.

First, the hard bar was production GenAI delivery plus architectural ownership. That is what pushed the search toward backend/platform builders, enterprise integration work, orchestration, and deployed-system language rather than research-heavy AI profiles.

Second, the brief explicitly said to search both product-language and systems-language populations. That is where themes like document understanding, intelligent search, workflow orchestration, support automation, and knowledge systems came from. The point was to find people describing real deployments even if they did not brand themselves around GenAI vocabulary.

Third, the brief treated client-facing delivery as a confidence booster, not a substitute for build evidence. That is why consulting, field-delivery, customer engineering, and implementation-style populations showed up in the strategy, but only when AND-gated with evidence that they had actually built and shipped systems.

Fourth, the brief called out founding engineers, hands-on CTOs, and people who could translate ambiguity into implemented systems. That became the founding / 0-to-1 theme.

Fifth, the brief cared about reusable delivery patterns, not just one-off builds. That is why the strategy included delivery accelerators, reference architectures, observability, evals, and operationalization topics even though those were never likely to be the biggest LinkedIn buckets.

The strategization output was not one generic Boolean. It was a set of focused search themes: backend-to-GenAI pivots, product/problem-language builders, reusable delivery tooling builders, consulting/customer-delivery builders, founding/0-to-1 builders, and enterprise integration builders.

## How those themes actually turned into searches and results

### Backend/platform builders who had moved into GenAI

This came straight from the brief's emphasis on production delivery plus architecture. The idea was that a strong senior backend engineer who had moved into LLM applications was often closer to the real bar for the role than someone with a more obvious AI-facing title.

Representative string:

```text
#4: ("Temporal" OR "FastAPI" OR "Celery") AND ("LLM" OR "AI" OR "agent" OR "agents" OR "GenAI" OR "copilot") AND ("production" OR "deployed" OR "built")
```

This ended up being the best raw-volume lane in the run. `#4` produced 17 saves from 6 pages and was the highest absolute save-count string in v13. It validated the core bet that backend engineers who had already crossed into production GenAI delivery were better opening territory than direct FDE-title searches. A nearby string, `#16`, tested the same idea through RAG + production evidence; that one timed out after one page, so it should be treated as unfinished rather than disproven.

### Product/problem-language builders

This theme came from the brief's instruction to search beyond explicit GenAI vocabulary and look for people who described the actual business problem they solved. In practice, that meant searching around things like document understanding, intelligent search, workflow orchestration, support automation, and knowledge systems.

Representative string:

```text
#2: ("document understanding" OR "document intelligence" OR "contract analysis" OR "intelligent document") AND ("architect" OR "technical lead" OR "senior engineer" OR "staff engineer" OR "lead engineer")
```

This was one of the cleanest themes in the entire run. `#2` produced 10 saves from 5 pages, and the raw report called it one of the highest-precision lanes in the session. The adjacent workflow/orchestration theme also worked: `#5` produced 3 saves from 2 pages. The important lesson here was that work-language beat title-language. People describing document systems and orchestration engines often mapped to the role better than people using more obvious AI branding.

### Reusable delivery tooling / operationalization builders

This theme was pulled from the brief's focus on reusable modules, reference architectures, accelerators, eval harnesses, tracing, and observability. It was important because the role is not just about shipping one deployment; it is also about improving the delivery machine for the next one.

Representative string:

```text
#1: ("delivery accelerator" OR "reference architecture" OR "reference implementation" OR "deployment toolkit" OR "reusable module" OR "reusable modules" OR "delivery playbook") AND ("AI" OR "LLM" OR "GenAI")
```

This theme mattered more as a strategic filter than as a large save engine. `#1` produced 2 saves from 3 pages, which is enough to show the brief was directionally right but not enough to make LinkedIn the best channel for this bucket. The run's retrospective points more toward open-source and GitHub follow-up here than another broad LinkedIn pass.

### Consulting, field-delivery, and customer-facing technical builders

This was one of the most important themes in the brief. It came from the instruction to use adjacent titles aggressively, but only when paired with real build evidence. The point was not "find solutions architects." The point was "find the people in consulting, field, and customer-delivery contexts who still actually build."

The theme started here:

```text
#15: ("technical lead" OR "tech lead" OR "engineering lead") AND ("consulting" OR "consultancy" OR "professional services" OR "client engagement" OR "client delivery") AND ("built" OR "implemented" OR "architected" OR "deployed") AND ("AI" OR "ML" OR "LLM" OR "NLP")
```

`#15` itself produced 4 saves, but the important part was the pattern it uncovered. It showed that consulting and delivery engineers with GenAI build history were real signal, which led to the strongest adaptation chain in the run: `#59` through `#64`, plus the later generalized customer-facing lane `#66`. That chain produced 16 additional saves, and `#66` alone produced 15 saves while still in progress when the session ended.

It is also the clearest example of what did and did not work inside one theme. The title-led spinout `#62`, which zeroed in on field solutions architect language, got over-narrowed into a 25-result pool and died at 0 saves. The broader generalization worked much better. So the lesson was not "this archetype is noisy." The lesson was "this archetype works when searched as a delivery pattern, not when squeezed into a tiny company-title box."

### Founding and 0-to-1 builders

This theme came directly from the brief's emphasis on ambiguity tolerance, end-to-end ownership, and founding or early-builder profiles at vertical AI startups. The search logic here was that some of the best FDE-adjacent people are not in delivery titles at all; they are the people who had to build the whole thing from scratch.

Representative opening string:

```text
#19: ("founding engineer" OR "first engineer" OR "engineer #1" OR "employee #1") AND ("AI" OR "LLM" OR "NLP" OR "machine learning") AND ("startup" OR "seed" OR "Series A" OR "founded")
```

This theme only started working after the noise was stripped out. `#19` initially skewed junior and needed three rounds of tightening before it became productive. Once tightened, though, it produced 5 saves from 2 pages. The broader 0-to-1 archetype string, `#37`, then extended the same idea beyond literal founding titles and produced 6 saves from 4 pages.

That combination ended up validating the theme in two ways. `#19` showed that true founding-engineer language could work once the junior noise was removed. `#37` showed that the more durable signal was not the title itself, but the pattern of "I built this from scratch for an enterprise or customer setting."

### Enterprise integration builders

This theme came from one of the most literal parts of the brief: translating ambiguous customer needs into technical specs and integrating models into real systems. That is the center of gravity of the role, so the search needed a bucket built around integration work rather than just generic AI delivery.

The initial theme showed up in adjacent-title form:

```text
#20: ("implementation engineer" OR "delivery engineer" OR "deployment engineer" OR "integration engineer") AND ("AI" OR "LLM" OR "ML" OR "GenAI" OR "generative") AND ("customer" OR "client" OR "enterprise")
```

The stronger expression of the same idea ended up being the later integration-pattern search, `#65`, which produced 5 saves from 6 pages. That shift matters. The adjacent-title version was directionally useful, but the better performers were the searches framed around what these people had actually done: integrated GenAI into existing enterprise systems under production constraints. This theme also connects to the fintech and enterprise follow-ons that surfaced later in the run.

## What the run said to do next

The biggest retrospective point is that adjacent builder pools should remain the center of gravity. The best-performing lanes in v13 were not exact-title FDE searches. They were backend/platform pivots, product/problem-language builders, founding/0-to-1 builders, consulting/customer-delivery builders, and enterprise integration builders.

The second clear recommendation is to keep leading with work-language instead of title-language. The run consistently got better signal from descriptions of shipped systems, document processing, orchestration, integrations, and delivery patterns than from obvious AI-forward titles.

The third recommendation is to go deeper on consulting, customer-delivery, and field-engineering variants, because that was the highest-value adaptive theme in the session. The `#15` lineage proved the archetype was real; the only major miss inside it was over-narrowing `#62`. The raw report specifically recommends starting the next run with consulting-firm variants and vendor field-engineering teams.

The fourth recommendation is to expand fintech and other regulated enterprise verticals. `#63` produced 7 saves from a 100-result pool, and the full run report explicitly points to fintech as a rich vein, with healthcare/pharma as the next analogous space to test.

The fifth recommendation is to add customer/client qualifiers earlier. One of the cleanest separators in the run was whether a technically credible builder had actual delivery context. The raw report explicitly suggests injecting `customer`, `client`, or `engagement` earlier into enterprise/internal-builder strings to improve precision.

Finally, two strings should be retried rather than written off: `#12`, which stopped after one page with 1 save, and `#16`, which timed out on page one despite a 3.7K-result pool. Both looked directionally useful, and the raw report treats them as infrastructure-truncated rather than failed ideas.
