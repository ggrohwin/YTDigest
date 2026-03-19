# YTDigest — Portfolio Talking Points

A record of technically and professionally notable achievements from this project,
framed for use in interviews, client conversations, and career positioning.

---

## AI Application Development

### Built a full-stack AI content digest application from scratch
- Fetches YouTube transcripts and web articles, generates summaries via Claude API,
  serves results through a FastAPI + Jinja2 web interface
- Demonstrates end-to-end AI application development: data ingestion, LLM integration,
  vector embeddings, semantic search, and a user-facing UI
- **Talking point:** "I built a personal AI application that ingests content from 20+
  sources daily, generates summaries using the Anthropic API, and surfaces them in a
  searchable web interface — designed and implemented entirely by me."

### Designed and iterated an AI output pipeline for tag normalization
- Identified that Claude generates tags in isolation without awareness of existing
  vocabulary, producing 2,000+ unique tags for 600 items (82% singletons)
- Diagnosed the problem as two distinct failure modes: conceptual inconsistency
  (prompt problem) and linguistic inconsistency (normalization problem)
- Designed a two-stage pipeline: Claude-based retag with tagging principles,
  followed by structural normalization using Voyage AI embeddings
- Iterated through multiple approaches, evaluating tradeoffs between embedding
  similarity thresholds, structural rules, and prompt design
- **Talking point:** "I designed and debugged an AI output pipeline for tag
  normalization — learning firsthand how to diagnose specification gaming,
  tune embedding similarity thresholds, and balance prompt engineering vs.
  post-processing guardrails."

### Developed intuition for prompt engineering and model alignment
- Identified that models optimize for literal instructions, not intent — and learned
  to frame prompts around the end-user outcome rather than a rule list
- Recognized the distinction between general-purpose and fine-tuned embeddings
  through hands-on experience: semantic similarity works for topic clustering but
  fails for canonical term enforcement
- Applied the fast/cheap + smart/slow model layering pattern: use embedding
  similarity for bulk matching, escalate to Claude for ambiguous cases
- **Talking point:** "Working on this project gave me practical experience with the
  gap between what you tell a model and what you mean — and how to close that gap
  through iterative prompt refinement, few-shot examples, and architectural design."

---

## Software Engineering

### Implemented semantic search using vector embeddings
- Integrated Voyage AI embeddings to power semantic video/article search
- Built an in-memory `TagNormalizer` class that snaps new tags to canonical
  forms at generation time, preventing vocabulary drift over time
- **Talking point:** "I implemented semantic search and real-time tag normalization
  using Voyage AI embeddings — understanding cosine similarity, vector caching,
  and the tradeoffs between embedding-based and rule-based approaches."

### Built a CI/CD pipeline with GitHub Actions
- Automated linting (ruff), formatting (black), and test runs on every push
- **Talking point:** "I set up a CI/CD pipeline from scratch, learning how
  automated quality gates work and why they matter for team development."

### Applied Agile practices to a solo project
- Used GitHub Issues, a Project board, and sprint-style work cycles
- Wrote user stories with acceptance criteria, practiced Definition of Done
- **Talking point:** "I ran this project using Agile ceremonies — GitHub Issues
  as stories, a Project board as the sprint board, and explicit acceptance criteria
  — giving me hands-on experience with the workflow used by most engineering teams."

---

## Learning & Meta-Skills

### Developed a collaborative AI workflow
- Learned to use Claude as a thought partner rather than an executor — drafting
  intent, then iterating on prompt construction collaboratively
- Identified where human judgment adds more value than automation: requirements
  clarity, evaluation of outputs, and identifying specification mismatches
- **Talking point:** "I've developed a working methodology for human-AI collaboration:
  I own the requirements and evaluation; the AI owns the implementation detail.
  This division makes both more effective."

---

## In Progress / Coming Soon
- Docker containerization and cloud deployment (Fly.io)
- Postgres migration with Alembic
- AI evaluation framework for summary quality
- User feedback loop for tag correction