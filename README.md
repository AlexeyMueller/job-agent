# job-agent

AI-assisted job search agent. Finds vacancies via official APIs, scores them against
your profile with Claude, and prepares an application package per vacancy
(vacancy summary, link, tailored resume as PDF).

> Status: early scaffold.

## How it works (planned)

1. Fetch vacancies from official APIs (Bundesagentur für Arbeit and others)
2. Score each vacancy against `profile.yaml`
3. Tailor the resume using only facts from `profile.yaml`
4. Render a PDF package per vacancy
5. Track everything in SQLite

## Limitations

- The agent never submits applications. You review and apply yourself.
- It must not invent experience: tailoring only rearranges facts from your profile.

## Development

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
pytest
```
