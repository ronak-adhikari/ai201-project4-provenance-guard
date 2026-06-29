# Provenance Guard

A backend system for classifying submitted creative content as human-written or AI-generated. 
Built as a pluggable API that any creative sharing platform could integrate to surface 
transparency labels, handle creator appeals, and maintain a structured audit log of every 
attribution decision.

---

## Architecture

### System Overview

A creator submits text to `POST /submit`. The rate limiter checks their quota first — if 
exceeded, the request is rejected with a 429. If not, the text enters a two-signal detection 
pipeline running in sequence: an LLM call to Groq (semantic/stylistic analysis) and a set of 
stylometric heuristics computed locally (sentence length variance, type-token ratio, punctuation 
density). Each signal returns a score between 0.0–1.0. A weighted confidence scorer blends 
those scores into a final value, which maps to one of four transparency label variants. The 
decision and label are written to the audit log and returned to the caller.

For appeals, a creator submits to `POST /appeal` with their submission ID and written reasoning. 
The system updates the content status to "under_review", logs the appeal alongside the original 
decision, and returns a 202 confirmation.

SUBMISSION FLOW
Client → Rate Limiter → POST /submit

|

+---------+---------+

|                   |

Signal 1: LLM       Signal 2: Stylometrics

(Groq semantic)     (TTR, sentence variance,

|             punctuation density)

+---------+---------+

|

Confidence Scorer

(weighted blend)

|

Transparency Label Generator

|

+---------+---------+

|                   |

Audit Log          API Response

(result + score + label)
APPEAL FLOW
POST /appeal → Validate content_id

|

Status → "under_review"

|

Audit Log → 202 response

---

## Detection Signals

### Signal 1 — LLM Semantic Analysis (Groq, weight: 0.65)

Uses `llama-3.3-70b-versatile` via Groq to assess whether a piece of text reads as 
AI-generated. The model evaluates semantic coherence, tonal consistency, structural balance, 
and vocabulary naturalness holistically — the same way a human reader notices something feels 
"off." Returns a score between 0.0 (definitely human) and 1.0 (definitely AI).

**Why this signal:** It captures properties that are nearly impossible to measure statistically 
— the feeling of unnatural smoothness, generic confidence, or overly balanced paragraph 
structure. No heuristic can replicate this.

**Why 0.65 weight:** This is the richer signal. It understands meaning, not just structure, 
so it deserves more influence in the final score.

**Blind spot:** Short texts give the model little to work with. A skilled writer deliberately 
mimicking AI style could also fool it.

---

### Signal 2 — Stylometric Heuristics (pure Python, weight: 0.35)

Computes three statistical properties of the text:

- **Sentence length variance** — AI writes more uniform sentence lengths; humans vary more. 
  High variance → more human.
- **Type-token ratio (TTR)** — unique words divided by total words. AI reuses safe vocabulary 
  more, producing a lower TTR.
- **Punctuation density** — counts varied punctuation (dashes, ellipses). AI defaults to 
  clean periods and commas; humans use more expressive punctuation.

Each metric is normalized to 0.0–1.0 and averaged into a single signal score.

**Why this signal:** It's structurally independent from the LLM signal — one measures meaning, 
one measures shape. When they agree, confidence is higher. When they disagree, the system 
correctly produces an uncertain result.

**Why 0.35 weight:** It can't detect meaning, only structure. A human writing formal academic 
prose scores AI-like on all three metrics due to the nature of that register.

**Blind spot:** Formal writing styles (legal, academic, technical) produce false positives. 
See Known Limitations.

---

## Confidence Scoring

### Formula
confidence = (llm_score × 0.65) + (stylo_score × 0.35)

### Thresholds

| Confidence Range | Attribution | Meaning |
|-----------------|-------------|---------|
| 0.0 – 0.40 | `likely_human` | No significant AI indicators |
| 0.41 – 0.52 | `uncertain_leaning_human` | Mixed signals, leaning human |
| 0.53 – 0.64 | `uncertain_leaning_ai` | Mixed signals, leaning AI |
| 0.65 – 1.0 | `likely_ai` | Strong AI indicators |

The uncertain band is intentionally wide. On a creative platform, a false positive — labeling 
a human's work as AI — is more damaging than a false negative. When signals conflict, the 
system defaults toward caution rather than accusation. The likely_human threshold is set at 
0.40 rather than 0.50 to further reflect this asymmetry.

### Example Scores from Testing

**High-confidence AI** (clearly AI-generated text):
```json
{
  "attribution": "likely_ai",
  "confidence": 0.7974,
  "llm_score": 0.9,
  "stylo_score": 0.6123
}
```

**Low-confidence human** (casual conversational text):
```json
{
  "attribution": "likely_human",
  "confidence": 0.3252,
  "llm_score": 0.2,
  "stylo_score": 0.5723
}
```

These two examples show meaningful variation across the confidence range — the system is not 
producing constant or near-constant scores.

---

## Transparency Labels

All four label variants, written exactly as they appear in API responses:

**Likely human** (confidence ≤ 0.40):
> "Our system found no significant indicators of AI generation in this content."

**Uncertain, leaning human** (confidence 0.41–0.52):
> "Our system could not confidently determine whether this content was written by a human or 
> generated by AI, however it is leaning toward human-written."

**Uncertain, leaning AI** (confidence 0.53–0.64):
> "Our system could not confidently determine whether this content was written by a human or 
> generated by AI, however it is leaning toward AI-generated."

**Likely AI** (confidence ≥ 0.65):
> "Our system found strong indicators that this content may have been AI-generated. The author 
> can contest this below."

---

## Appeals Workflow

**Endpoint:** `POST /appeal`

**Who can appeal:** Any creator with a valid `content_id` from a prior submission.

**Required fields:**
- `content_id` — the ID of the submission being contested
- `creator_reasoning` — written explanation of why the classification is wrong

**What happens:**
1. The system locates the original submission in the audit log by `content_id`
2. Updates its status from `"classified"` to `"under_review"`
3. Appends the creator's reasoning and an appeal timestamp to the log entry
4. Returns a 202 confirmation

**Example appeal request:**
```json
{
  "content_id": "98dfa456-afff-4756-b2c1-4f8a283aafe3",
  "creator_reasoning": "I wrote this myself from personal experience. I am an economics 
  researcher and my academic writing style may appear more formal than typical."
}
```

**Example response:**
```json
{
  "content_id": "98dfa456-afff-4756-b2c1-4f8a283aafe3",
  "message": "Appeal received. Your submission is now under review.",
  "status": "under_review"
}
```

---

## Rate Limiting

Applied to `POST /submit`:
- **10 requests per minute**
- **100 requests per day**

**Reasoning:** A real creator submitting their own work would rarely need more than a few 
submissions per minute — even bulk uploading a portfolio would be paced. 10/minute prevents 
automated flooding while giving legitimate users generous headroom. 100/day allows a 
productive creator to submit frequently without hitting a wall, while making large-scale 
scraping or abuse expensive.

**Rate limit test output** (12 rapid requests — first 10 succeed, last 2 are rejected):
1. 200
2. 200
3. 200
4. 200
5. 200
6. 200
7. 200
8. 200
9. 200
10. 200
11. 429
12. 429

---

## Audit Log

Every attribution decision and appeal is recorded as a structured JSON entry.

**Sample entries** (`GET /log`):

```json
[
  {
      "attribution": "likely_ai",
      "confidence": 0.7974,
      "content_id": "cf82eb54-186b-4d92-942e-3eb8b591f392",
      "creator_id": "test-user-1",
      "llm_score": 0.9,
      "status": "classified",
      "stylo_score": 0.6069,
      "timestamp": "2026-06-29T01:39:56.107606+00:00"
  },
  {
      "attribution": "likely_human",
      "confidence": 0.3252,
      "content_id": "eb0ba235-cb7e-4d4e-b634-c121255fa1db",
      "creator_id": "test-user-2",
      "llm_score": 0.2,
      "status": "classified",
      "stylo_score": 0.5577,
      "timestamp": "2026-06-29T01:39:56.515382+00:00"
  },
  {
      "appeal_reasoning": "I wrote this myself from personal experience. I am an economics researcher and my academic writing style may appear more formal than typical, which could trigger false AI detection.",
      "appeal_timestamp": "2026-06-29T02:08:30.535941+00:00",
      "attribution": "likely_ai",
      "confidence": 0.7343,
      "content_id": "98dfa456-afff-4756-b2c1-4f8a283aafe3",
      "creator_id": "test-user-3",
      "llm_score": 0.8,
      "status": "under_review",
      "stylo_score": 0.6123,
      "timestamp": "2026-06-29T02:06:21.341227+00:00"
  }
]
```

---

## Known Limitations

**1. Formal writing styles produce false positives**

Academic, legal, and technical writing shares structural properties with AI-generated text: 
uniform sentence lengths, conservative vocabulary (low TTR), and minimal expressive 
punctuation. A real economics researcher submitting a literature review will score 
AI-like on stylometrics regardless of authorship. This is a property of the signal itself, 
not a data problem — stylometrics cannot distinguish "AI uniform" from "register uniform." 
Our Milestone 4 testing confirmed this: a formal monetary policy paragraph scored 0.7343 
despite being human-written.

**2. Non-native English speaker writing**

Careful, conservative sentence construction and limited vocabulary range — common in writing 
by non-native speakers avoiding words they're uncertain about — produces low TTR and uniform 
sentence structure. Both signals can fire incorrectly here. This is the most ethically 
significant failure mode: the population most likely to be falsely accused is already a 
marginalized group in many creative spaces.

---

## Spec Reflection

**Where the spec helped:** Writing out the three label variants in planning.md before building 
forced a concrete decision about what "uncertain" means to a non-technical user. Without that 
upfront work, it would have been easy to implement a binary label and call it done. Having the 
exact text written before Milestone 5 meant label implementation took minutes rather than 
requiring design decisions mid-build.

**Where implementation diverged:** The spec defined three label variants, but during 
implementation we split the uncertain band into two sub-variants (leaning human vs leaning AI). 
The spec's false-positive guidance made it clear that a single "uncertain" label was too blunt 
— a score of 0.42 and a score of 0.63 mean very different things to a creator reading their 
result, even if both technically fall in the uncertain range.

---

## AI Usage

**Instance 1 — Flask app skeleton and Signal 1**

Provided the detection signals section of planning.md and the architecture diagram and asked 
for a Flask app skeleton with a `POST /submit` route stub and a Groq signal function returning 
a 0.0–1.0 score. The generated code had the correct structure but used `temperature=0.7` for 
the Groq call, which introduced unnecessary randomness in detection scores. Changed to 
`temperature=0.1` so the same text produces consistent scores across runs.

**Instance 2 — Stylometrics function**

Provided the Signal 2 description from planning.md and asked for a Python function computing 
TTR, sentence length variance, and punctuation density normalized to 0.0–1.0. The generated 
function computed TTR correctly but did not invert it — a high TTR (diverse vocabulary, more 
human) was returning a high score (AI-like), which was backwards from the spec. Corrected the 
inversion logic so high TTR produces a low AI-likelihood score.

**Instance 3 — Formatting and writing for planning.md and README.md**

Used AI assistance to help structure and format the planning.md and README.md documents. 
Provided the raw design decisions and technical details we had worked out (signal choices, 
confidence thresholds, label variants, appeals workflow) and asked for help organizing them 
into clearly written, well-structured markdown documents. Reviewed the output and revised 
the label variant wording to better reflect the false-positive concern, and added the fourth 
label variant (uncertain leaning human/AI split) which was not in the initial output.

---

## Setup

```bash
git clone https://github.com/ronak-adhikari/Provenance-Guard_Ronak-A.git
cd ai201-project4-provenance-guard
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Create a `.env` file in the repo root:
GROQ_API_KEY=your_key_here

Run the server:
```bash
python3 app.py
```

## API Reference

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/submit` | POST | Submit text for attribution analysis |
| `/appeal` | POST | Contest a classification decision |
| `/log` | GET | Retrieve audit log entries |

**POST /submit**
```json
{ "text": "string", "creator_id": "string" }
```

**POST /appeal**
```json
{ "content_id": "string", "creator_reasoning": "string" }
```