# Requirement coverage

A map from each requirement in the Module 5 brief to the thing in this repository that answers
it, so coverage can be checked without hunting.

**One caveat, stated up front.** The copy of the brief this was built from had four sections
arrive as headings with no body: *"💡 Example Extensions"*, *"5. Reflection and Ethics"*,
*"🚀 Optional: Stretch Features for Extra Points"*, and *"6. Presentation and Portfolio"*. The
required sections (0–4 and the submission checklist) came through in full and are mapped
exactly below. For the four collapsed ones, the extras in the second table are **inferred**
from the module's established conventions and from the detail that did survive in the
checklist. If the real stretch list names something specific, it may not be here — the gap
analysis at the bottom is the place to check.

---

## Required deliverables

| Brief requirement | Where it is | Notes |
|---|---|---|
| **0. Dedicated repo**, new and public, cloned from the original so history is preserved, remote repointed | [`Eri-py/applied-ai-system-final`](https://github.com/Eri-py/applied-ai-system-final) | Cloned from the Module 3 repo; all 12 original commits present beneath the new work |
| **0. `assets/` folder** | [`assets/`](../assets) | Reproducible command output, a full JSONL run log, the regeneration script |
| **0. `diagrams/` folder with Mermaid source** (`.mmd`, or `.md` with a Mermaid block) | [`diagrams/architecture.mmd`](../diagrams/architecture.mmd), [`diagrams/agent_loop.mmd`](../diagrams/agent_loop.mmd) | Plus [`diagrams/README.md`](../diagrams/README.md), generated from those sources, which GitHub renders inline — the second accepted form |
| **1. Does something useful with AI** | `src/app.py` — plain-English request → explained playlist | |
| **1. At least one advanced feature: RAG** | `src/retrieval.py` + [`data/notes/`](../data/notes) | BM25 over 14 notes; hints seed the profile, so retrieval changes behaviour rather than printing alongside it |
| **1. At least one advanced feature: agentic workflow** | `src/agent.py` (plan→act→check→repair), `src/tool_loop.py` (model-driven) | Two implementations, deliberately comparable |
| **1. At least one advanced feature: reliability/testing** | `evaluation/`, `tests/`, `.github/workflows/ci.yml` | 285 tests, 29 labelled cases, 3 experiments |
| **1. Feature integrated into main logic, not a standalone script** | Measured, not asserted: the retrieval ablation drops the pass rate 100% → 55% | [EVALUATION.md](../EVALUATION.md) experiment 2 |
| **1. Runs correctly and reproducibly** | Verified from a fresh clone; CI on Python 3.10/3.11/3.12; no API key needed | Reproducibility experiment: 29/29 byte-identical over 3 runs |
| **1. Logging or guardrails** | `src/obs.py` (JSONL per run), `src/guardrails.py` | Injection refusal, two-stage domain check, profile clamping, output sanitising |
| **1. Clear setup steps** | [README § Setup](../README.md#setup) | Verified by following them verbatim in a clean clone |
| **2. System diagram: components** | `diagrams/architecture.mmd` | Retriever, planner, tools, critic, repairs, confidence, logger |
| **2. System diagram: data flow** | same | Input → process → output, left to right |
| **2. System diagram: where humans/testing check results** | same | The `Verification` subgraph |
| **3. README names the original project + 2–3 sentence summary** | [README § The project this extends](../README.md#the-project-this-extends) | Named, linked, with a what-1.0-could-not-do paragraph and a comparison table |
| **3. Title and summary** | README top | |
| **3. Architecture overview** | [README § Architecture](../README.md#architecture) | Prose walkthrough of the five stages |
| **3. Setup instructions** | README § Setup | |
| **3. 2–3 sample interactions** | [README § Sample interactions](../README.md#sample-interactions) — 3 | Six more in [`assets/sample-output.md`](../assets/sample-output.md) |
| **3. Design decisions and trade-offs** | [README § Design decisions](../README.md#design-decisions) | Six decisions, each with its trade-off stated |
| **3. Testing summary** | [README § Testing summary](../README.md#testing-summary) | Leads with the ablation, not the pass rate |
| **3. Reflection (brief, in README)** | [README § Reflection](../README.md#reflection) | Graded reflection is in the model card, as the brief directs |
| **4. At least one reliability measure** | All four the brief lists: automated tests, confidence scoring, logging/error handling, human evaluation | |
| **4. Testing summarised in a few lines** | README § Testing summary, first paragraph | |
| **4. Human evaluation in a parseable format** | [`docs/human_eval.md`](human_eval.md) | Markdown tables: 4-criterion scorecard across 12 cases, plus a second-rater table |
| **5. Reflection and ethics** *(section body was collapsed)* | [`model_card.md`](../model_card.md) §5 biases, §7 reflection | Covers the checklist's stated prompts: AI collaboration, biases, testing results, limitations |
| **5. `model_card.md` answers the reflection prompts** | §7: how I collaborated; one suggestion accepted; one rejected; one revised; limitations | |
| **6. Presentation and portfolio** *(section body was collapsed)* | [`docs/portfolio.md`](portfolio.md) | Portfolio copy at three lengths, skills table, five-minute demo script, expected questions |

## Submission checklist

| Item | Status |
|---|---|
| Code pushed to the correct GitHub repository | yes |
| Repo is public | yes |
| Functional code | `src/`, ~3,800 lines |
| Comprehensive `README.md` | yes |
| `model_card.md` for reflections | yes |
| Architecture diagram as Mermaid source in `diagrams/` | yes — two, plus a rendered page |
| Reproducible command outputs / interaction logs as `.md` or `.txt` | [`assets/sample-output.md`](../assets/sample-output.md) (9 runs), [`assets/sample-run-winddown.jsonl`](../assets/sample-run-winddown.jsonl) |
| Diagram source and supplementary images in `/assets` or `/diagrams` | yes |
| Commit history shows multiple meaningful commits | 14+ on top of the Module 3 history |
| README identifies the base project | yes |
| `model_card.md` answers AI collaboration, biases, testing results | yes |
| 2–3 example inputs with outputs as fenced code blocks, no video needed | 3 in the README, 9 in `assets/` |
| Loom walkthrough (optional) | not recorded — script ready in [`docs/portfolio.md`](portfolio.md) |

---

## Extras (inferred — the stretch list was collapsed)

Built on top of the required set. These are what the module's earlier stretch features and the
surviving checklist detail implied; none is claimed to match a specific numbered stretch item.

| Extra | Where | Why it was worth doing |
|---|---|---|
| **A second, model-driven agent loop** | `src/tool_loop.py`, `--tool-loop` | Makes "the Python loop is the right default" a comparison rather than an assertion |
| **A measured ablation** | [EVALUATION.md](../EVALUATION.md) exp. 2 | Turns "this project uses RAG" from a claim into a finding |
| **A reproducibility experiment** | exp. 1 | 29 cases × 3 runs, byte-identical |
| **Confidence calibration, reported negatively** | exp. 3 | Found and published a real weakness (0.05 separation) instead of tuning it away |
| **CI on three Python versions** | `.github/workflows/ci.yml` | Continuous evidence the no-key claim holds |
| **A staleness gate in CI** | same, step 3 | No number in the docs can drift from what the code produces; it caught a stale report immediately |
| **Generated artifacts with regeneration scripts** | `assets/regenerate.sh`, `diagrams/build_readme.py`, `--write` | Evidence is checkable, not pasted once and trusted |
| **Full JSONL run logs** | `src/obs.py`, `assets/sample-run-winddown.jsonl` | Every number on screen traceable to a logged event |
| **Graceful degradation with a real fallback** | `src/llm.py` `ResilientBackend` | The repo runs, tests and ships numbers with no API key |
| **Prompt-injection guardrail + tests** | `src/guardrails.py`, `tests/test_guardrails.py` | 9 attack phrasings, unicode-normalised matching |
| **A cold-start path** | `src/agent.py` | Refuses to fake precision on a request that specified nothing |
| **Human-evaluation protocol with a second-rater table** | [`docs/human_eval.md`](human_eval.md) | The one measurement the automated suite structurally cannot make |
| **Portfolio copy and a demo script** | [`docs/portfolio.md`](portfolio.md) | For the presentation half of section 6 |
| **Module 3 model card preserved** | [`docs/model_card_v1.md`](model_card_v1.md) | Shows the continuity: its Future Work predicted the failure 2.0's human review found |

## Known gaps

Stated rather than hidden, since a reviewer will find them anyway:

1. **No exported PNG of the diagrams.** Rendering needed a package install that was not
   available in the build environment. The brief requires Mermaid *source* and says a PNG alone
   is insufficient, so the requirement is met — and `diagrams/README.md` renders both diagrams
   inline on GitHub. To produce images:
   `mmdc -i diagrams/architecture.mmd -o assets/architecture.png -b transparent -s 2`.
2. **No Loom walkthrough.** Explicitly optional. The script is in `docs/portfolio.md`.
3. **The live Claude path is unverified against the real API.** Its request shape is pinned by
   tests with a fake client; no test has made a real call, because no key was available. Stated
   in the model card and in EVALUATION.md.
4. **The human evaluation has one rater, who is not independent.** Protocol and table for a
   second rater are in place.
5. **If the real stretch list names items not above**, they are not implemented. The four
   collapsed sections are the reason; this table is the inference that filled the gap.
