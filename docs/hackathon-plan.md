# NOVA decision notes — November 7, 2026

Based on the two organizer documents supplied by Michael, plus the official technical references linked below. These are judgments about scope and fit, not predictions of judging results or claims that the ideas are novel in the market.

## Recommendation: independent project, with a narrow sponsor option

For your stated interests and a two-person team, choose an independent project. You have six clock hours, 11 AM–5 PM, with lunch inside that window. A problem you both understand is more valuable than spending the first hour learning an unfamiliar industry or security domain. Target a single interaction that yields a visible, inspectable result.

The general awards include Most InNOVAtive, Beyond Limits, Looks Good Works Good, Community Favorite and the $2,000 grand prize. The supplied text does not give the sponsor prize amounts, exact judging rubric, whether tracks can be combined, or the number of teams entering each track. “Everyone will do DoorDash” is a plausible concern, not evidence. Track selection alone does not determine distinctiveness.

| Route | What it offers | Main risk for this team | My judgment |
| --- | --- | --- | --- |
| Independent | Freedom to pick a familiar pain point and a distinctive interaction | Open-ended brainstorming consumes the event | Best fit if you choose the problem before hacking starts |
| DoorDash front house | Concrete packing/pickup pain; visual demos | Reliable camera recognition and live restaurant integration are hard in six hours | Consider only a tightly bounded assistive workflow |
| DoorDash back house | Messy invoices, sales notes and receipts naturally need interpretation | A generic “chat with sales” dashboard is forgettable; calculations must be correct | Most credible sponsor fallback |
| Sandia | Could be interesting if the actual challenge is approachable | The supplied guide omits the problem statement; zero-trust talk is not enough to infer requirements | Do not commit until you see the actual brief |

I disagree slightly with “AI has little application potential at DoorDash.” The strongest fit in this brief is translating inconsistent documents into a common structure and explaining exceptions. For example, compare a supplier invoice with an agreed price list, calculate discrepancies in code, then present the relevant line items and a draft clarification. This is useful even without autonomous restaurant control. Missing-item detection is also a plausible assistive task, but packaging, occlusion and high error costs make a credible demo harder. Ordinary queues, totals and stock thresholds should be ordinary code.

If you independently love a document-reconciliation idea, it may fit back house with little extra scope. Do not force-fit your whole project for a prize. Verify sponsor-specific submission requirements before claiming eligibility. The Sandia details are deferred to the November 6, 6–8 PM talk; nothing in the pasted guide establishes that all acceptable projects require advanced cybersecurity.

## What to take from the tech guide

**Use:** organizer-issued OpenRouter key; a server-side model call; React/FastAPI separation; streamed text when useful; optional image input; the conceptual tool-call cycle. These are reusable across most ideas. The guide explicitly calls itself highly opinionated, so its architecture is a starting point, not a stated event requirement.

**Improve or verify:**

1. Remove the example that prints `OPENROUTER_API_KEY`. Keys belong only on the server.
2. Use `httpx.AsyncClient` for network operations inside async FastAPI routes. The guide uses blocking `requests` calls, including during streaming. [HTTPX async documentation](https://www.python-httpx.org/async/).
3. Treat network chunks as arbitrary bytes. Preserve UTF-8 decoder state, buffer event boundaries, handle comments, `[DONE]`, pre-stream HTTP failures and in-stream errors. The guide's frontend creates a new decoder for every chunk; its referenced parsing utilities are absent from the paste. [OpenRouter streaming](https://openrouter.ai/docs/api/reference/streaming).
4. Validate a model's requested capabilities. Do not request all of its possible output modalities merely because they exist. Structured mode needs a compatible endpoint, and image input is a separate capability. Avoid fetching the entire model catalog on each user request. [Structured outputs](https://openrouter.ai/docs/guides/features/structured-outputs).
5. Use a JSON Schema and backend validation when the UI needs fields. Parseable JSON and a matching quotation are not guarantees that reasoning is correct. Keep a small set of expected outcomes to check quality.
6. PDF support can involve a separate parser/OCR engine, costs and limitations. The guide's `pdf-text` engine is now documented as deprecated and redirected to `cloudflare-ai`. For a first version, paste text; add OCR only if scans are central. The audio/PDF modality table should not be treated as a permanent universal capability matrix. [OpenRouter PDF inputs](https://openrouter.ai/docs/guides/overview/multimodal/pdfs).
7. MCP is optional. An app can call a normal API directly; tool calling does not require MCP. The pasted MCP code references missing helpers/configuration, recursively resumes without an explicit step budget, and has an exception-flattening issue: it tries to iterate each sublist before filtering whether that sublist is an exception. It is educational scaffolding, not a complete plug-in component.
8. The React query key uses only `lastMessage`; distinct conversations/models with the same last message can share a cache key. The hook also refers to utility files/types not included in the paste. For a user-triggered paid workflow, direct fetch + AbortController is enough and easier to debug.

The pasted text loses some formatting and hyperlinks, so indentation defects may be copy artifacts. The important architectural issues above still apply. The starter implements the reliable core rather than depending on those incomplete snippets.

## Four project directions

These are scoped MVP proposals, not researched claims of market novelty. Validate interest with a couple of classmates, then choose based on what you want to demonstrate.

### 1. ConstraintLens — “These two instructions cannot both be right”

**User:** student or club organizer reconciling an event brief, assignment instructions and later messages.

**Interaction:** paste two or three excerpts → see side-by-side conflicting passages → choose an authoritative source or mark unresolved → generate a clarified checklist. AI extracts and compares constraints; code tracks decisions and renders the resolved state. Preserve dates, units, negations and exceptions.

**90-second demo:** one note says 4 PM/three minutes, another says 4:30 PM/five minutes. The app surfaces both discrepancies with exact quotes. Resolve one and watch the checklist change, then show the unresolved issue instead of pretending to know the answer.

**Six-hour MVP:** pasted text, time/duration/location conflicts, quote-linked cards, human resolution and export. No PDF parsing, live calendar, broad web search, or automatic messages. Evaluation: five prepared pairs, including an agreement, an ambiguous update and a false-conflict trap. Require a quoted passage from both sources for each alleged conflict; one-sided citations are insufficient.

**Why it could stand out:** the product's value is identifying disagreement and helping resolve it. A generic summary tends to hide disagreement. Main risk: different scopes can look contradictory; let users reject false positives and never infer source authority silently.

**My first pick for feasibility and usefulness.** The starter's sources and provenance checks are a natural base, but the conflict schema, comparison logic and resolution UI still need to be built.

### 2. Handoff — recover the state of an interrupted project

**User:** project partners returning after a gap or handing work to another teammate.

**Interaction:** paste a messy meeting note and update log → receive “decided / attempted / blocked / next owner” cards → inspect evidence and confirm one next action. AI reconstructs state; the user approves the handoff.

**Demo:** an old note proposes one library; a later message abandons it. The app distinguishes the rejected attempt from the final decision and flags a missing owner.

**Six-hour MVP:** two text inputs, chronological evidence-backed cards, editable owner, export a handoff sheet. Evaluate whether it confuses plans with completed actions. No Slack/GitHub integration or actual task assignment.

**Why AI:** interpreting informal chronology, intent and reversals. Main risk: becoming another note summarizer; state transitions and evidence must be the centerpiece.

### 3. FrictionLab — rehearse one interface task

**User:** student builders who want a quick usability review before demo day.

**Interaction:** upload a UI screenshot and write a specific task → receive three concrete obstacles tied to visible labels → upload a revision and compare which obstacles remain. It is a heuristic review, not a substitute for testing with real users.

**Demo:** use an intentionally confusing club signup page; revise its ambiguous action and show the before/after review.

**Six-hour MVP:** one screenshot at a time, task-specific findings, simple numbered markers or textual regions, before/after cards. Avoid browser automation and exact pixel localization unless you have it working early. Prefer explicit visible evidence and abstention to invented interface elements.

**Why AI:** interpreting the relationship between a human task and a visual interface. Main risk: subjective or fabricated feedback. Keep a small set of seeded defects and test whether it finds them.

**Best visual-demo option** if you enjoy frontend work and have a vision-capable model.

### 4. MakeDo — a tiny challenge from the objects on your desk

**User:** friends who want a quick creative or cooperative game with materials they already have.

**Interaction:** photograph a few ordinary objects → confirm the detected inventory → pick a time limit and constraint → receive three feasible mini-challenges with a visual challenge card.

**Demo:** paper, cups and tape become a ten-minute bridge challenge. Remove tape and ask it to adapt. Use code to enforce confirmed materials/time constraints; do not trust an image model's inventory automatically.

**Six-hour MVP:** photo, editable inventory, three challenge cards and timer. Use harmless tabletop tasks. No real-time video, physics simulation or automatic judging.

**Why AI:** mapping visual objects into creative combinations under constraints. Main risk: vague/impossible challenges. Confirmation of materials and a live physical attempt give the demo substance.

**Most playful option**, potentially a good fit for an audience vote; that is a design judgment, not a win prediction.

## Decision and six-hour execution plan

Pick the idea for which you can name a real user, obtain representative inputs now, and explain the before/after in one sentence. Give yourselves a 20-minute decision deadline before the event. If neither teammate has a strong preference, choose ConstraintLens; if the team strongly prefers a visual experience, choose FrictionLab.

| Time, November 7 (Eastern) | Deliverable |
| --- | --- |
| Before 11 AM | Read updated rules; disclose starter; confirm idea, one user journey and sample inputs |
| 11–11:30 | Add team key; make one successful real call; lock the result schema and one success metric |
| 11:30–1 PM | Teammate A: model/prompt/checks. Teammate B: product-specific interaction using fixed JSON |
| 1–2 PM | Integrate one complete input → useful output → user decision flow |
| 2–3 PM | Run five cases, including missing/ambiguous evidence and a failure; fix the biggest issues |
| 3–4 PM | Improve clarity, feedback and the one distinctive interaction; stop adding features |
| 4–4:30 PM | Rehearse a 90-second demo; capture a real successful run as a clearly labeled backup |
| 4:30–5 PM | Submission, disclosure, final smoke check; preserve the working demo |

Aim to show: who has the problem → one realistic input → the revealing result → a human decision → why the result can be trusted and where it can fail. Do not present mock fixtures as model performance.
