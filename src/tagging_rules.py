"""Tagging principles for topic tag generation.

This file is the single source of truth for how Claude should generate tags.
It is imported by both the real-time summarizer and the batch retag script.

Edit the rules here — no code to accidentally break.
"""

TAGGING_PRINCIPLES = """
Tags are used for navigation — a reader clicks a tag to find all related content.
Choose tags that a reader would actually search for,
not tags that describe the content's angle.

WHAT TO TAG:
- Tag the TOPIC, not the angle. Ask: "what would a reader type to find this?"
- Tag every named tool, product, company, conference, or event individually.
  If a video compares two tools, BOTH get their own tag — do not combine them.
- Use broad, stable concept tags — prefer the shortest accurate noun phrase.

WHAT NOT TO DO:
- Do not prefix concept tags with "AI" — use the concept itself.
  Bad: "AI Governance", "AI Strategy", "AI Coding Tools"
  Good: "Governance", "Strategy", "Coding Tools"
  OK: "AI Agents", "AI Safety" (where AI is the essential subject, not just context)
- Do not add qualifier suffixes like "Challenges", "Updates", "Analysis", "News",
  "Overview", "Recap", "Techniques", "Methods" — tag the subject, not the framing.
  Bad: "AI Implementation Challenges", "Anthropic Updates", "AI Prompting Techniques"
  Good: "AI Implementation", "Anthropic", "Prompt Engineering"
- Do not combine two named things into one tag.
  Bad: "Claude Code vs GSD2", "OpenAI vs Anthropic"
  Good: "Claude Code", "GSD2", "OpenAI", "Anthropic"
- Do not use sentiment or opinion framings.
  Bad: "AI Hype Vs Reality", "AI Optimism Vs Pessimism", "AI Criticism"
  Good: "AI Hype", "AI Limitations"
- Do not use Business, Corporate, or Enterprise as tag prefixes.
  Bad: "Business Strategy", "Corporate Governance", "Enterprise AI Strategy"
  Good: "Strategy", "Governance", "Enterprise AI"
  Exception: "Enterprise Software" is a valid domain tag.
- Do not tag aspects or sub-concepts of a topic — tag the topic itself.
  Bad: "Agent Coordination", "Agent Loops", "Agentic Workflows"
  Good: "AI Agents"
""".strip()
