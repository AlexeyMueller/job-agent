# job-agent

A command-line job search agent. It collects vacancies from public sources, skips the ones it
has already seen, scores each new vacancy against your profile with Claude, applies your own
scoring rules, and stores the results locally so you can review the best matches and apply
yourself.

The agent never submits applications and never invents experience: it may only use facts from
your `profile.yaml`.

## What it does today

1. **Collect** vacancies from several sources into one common format:
   - Bundesagentur für Arbeit (Germany)
   - jobs.dou.ua (RSS feeds)
2. **Filter**: drops excluded keywords (e.g. `Praktikum`, `Werkstudent`) and vacancies already
   stored in the local database.
3. **Score** every new vacancy with Claude. The model gets your profile and the vacancy text and
   returns a structured result: score (0-100), apply yes/no, matches, gaps, red flags, work mode
   and language requirement.
4. **Adjust** the score with deterministic rules from `config.yaml`: penalties for hybrid/onsite
   work (remote is never reduced) and for required skills you have marked as missing.
5. **Store** everything in SQLite (`jobs.db`), so each vacancy is scored, and paid for, only once.

## Planned

- A PDF package per vacancy (vacancy summary, link, resume tailored from `profile.yaml` facts only)
- More countries and job sources

## Design notes

- **Public APIs and RSS only**, no browser scraping.
- **Structured output**: Claude is called with a tool schema, and the answer is validated with
  pydantic before it is used.
- **Rules live in code and config, not in the prompt**: the model reports facts (work mode,
  required skills); the penalty arithmetic is plain, tested code.
- **Vacancy text is treated as untrusted data**: the prompt tells the model to ignore any
  instructions found inside it.
- **Cost control**: SQLite deduplication and a `max_new_per_run` cap on paid scoring calls.
- Formal education requirements are ignored by the scorer (configurable in the prompt).

## Setup

Requires Python 3.11+.

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
```

Then create your local files (all three are git-ignored):

```bash
cp .env.example .env                       # put ANTHROPIC_API_KEY in it
cp config.example.yaml config.yaml         # search and scoring settings
cp profile.example.yaml profile.yaml       # your real experience and skills
```

On Windows PowerShell use `Copy-Item` instead of `cp`.

## Usage

```bash
job-agent search "QA Engineer" --wo "Frankfurt am Main" --days 14   # raw Bundesagentur search
job-agent run --dry-run      # search and filter only, shows what would be scored, no API cost
job-agent run                # search, score new vacancies, store results
job-agent list               # best stored vacancies (final score >= min_score)
job-agent explain <ref>      # stored evaluation of one vacancy, free
job-agent score <ref>        # score a single Bundesagentur vacancy
```

To use DOU, open a filtered vacancy list on jobs.dou.ua, copy its RSS link and add it under
`sources.dou.feeds` in `config.yaml`.

## Configuration

`config.example.yaml` documents every setting: search keywords, location and radius, how many
days back to look, excluded keywords, minimum score, work-mode penalties, and the list of skills
you lack, with German and English names. Anything you leave out falls back to a default.

## Limitations

- The Bundesagentur endpoint is the public service used by the agency's own apps and documented
  by the community ([bundesAPI/jobsuche-api](https://github.com/bundesAPI/jobsuche-api)). It is
  not officially supported, so fields may change.
- Scores are an aid for prioritising, not a verdict. Read the vacancy before applying.

## Development

```bash
pytest
ruff check .
```

Tests mock the network and the Claude API, so they run offline and cost nothing. CI runs both
commands on every push.
