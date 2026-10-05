from pathlib import Path

import yaml
from pydantic import BaseModel, Field


class Adjustments(BaseModel):
    """Points subtracted from the model's fit score by work mode (remote is never reduced)."""

    mostly_remote_local: int = -3
    mostly_remote_relocation: int = -10
    hybrid_local: int = -10
    onsite_local: int = -15
    hybrid_relocation: int = -20
    onsite_relocation: int = -30


class AvoidSkill(BaseModel):
    """A skill the candidate lacks. Vacancies that REQUIRE it lose points."""

    name: str
    aliases: list[str] = Field(default_factory=list)
    # When this applies, the skill does NOT count as required (checked by Claude).
    exception: str | None = None


def _default_avoid_skills() -> list[AvoidSkill]:
    return [
        AvoidSkill(
            name="Penetration testing",
            aliases=[
                "Penetration testing", "Pentest", "Penetrationstest", "Penetrationstests",
                "Security testing", "Sicherheitstest", "Sicherheitstests",
            ],
        ),
        AvoidSkill(
            name="Load and performance testing",
            aliases=[
                "Load testing", "Performance testing", "Stress testing", "Lasttest",
                "Lasttests", "Performancetest", "Performancetests", "Stresstest",
                "Belastungstest", "JMeter", "Gatling", "k6", "Locust",
            ],
        ),
        AvoidSkill(
            name="Selenium, Cypress, Appium",
            aliases=["Selenium", "Cypress", "Appium"],
            exception=(
                "Not required if the vacancy accepts or names Playwright, for example "
                "'Playwright, Selenium or similar'. Required only if it demands one of "
                "these tools and does not accept Playwright."
            ),
        ),
    ]


class SearchConfig(BaseModel):
    keywords: list[str] = ["QA Engineer", "Software Tester", "QA Analyst"]
    location: str = "Frankfurt am Main"
    radius_km: int = 50  # also the commuting radius: farther away counts as relocation
    published_within_days: int = 14
    exclude_keywords: list[str] = ["Praktikum", "Werkstudent"]
    max_per_query: int = 25
    # Nationwide search only keeps vacancies that allow home office (saves money).
    nationwide_requires_home_office: bool = True


class ScoringConfig(BaseModel):
    model: str = "claude-sonnet-5-5"
    min_score: int = 60
    max_new_per_run: int = 40  # safety cap on paid scoring calls per run
    adjustments: Adjustments = Field(default_factory=Adjustments)
    avoid_skills: list[AvoidSkill] = Field(default_factory=_default_avoid_skills)
    skill_penalty: int = -10  # per REQUIRED avoided skill
    max_skill_penalty: int = -30  # total cap


class DouConfig(BaseModel):
    feeds: list[str] = Field(default_factory=list)  # RSS feed URLs from jobs.dou.ua


class SourcesConfig(BaseModel):
    dou: DouConfig = Field(default_factory=DouConfig)


class Config(BaseModel):
    search: SearchConfig = Field(default_factory=SearchConfig)
    scoring: ScoringConfig = Field(default_factory=ScoringConfig)
    sources: SourcesConfig = Field(default_factory=SourcesConfig)


def load_config(path: str | Path = "config.yaml") -> Config:
    """Load config.yaml; missing file or keys fall back to defaults."""
    path = Path(path)
    if not path.exists():
        return Config()
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return Config.model_validate(data)


def skill_penalty(avoided: list[str] | tuple, config: Config) -> int:
    """Penalty for required skills from the avoid list. Unknown names are ignored."""
    known = {skill.name.lower() for skill in config.scoring.avoid_skills}
    count = len({name.lower() for name in avoided if name.lower() in known})
    return max(count * config.scoring.skill_penalty, config.scoring.max_skill_penalty)


def adjust_score(
    score: int,
    work_mode: str,
    distance_km: int | None,
    config: Config,
    avoided: list[str] | tuple = (),
) -> int:
    """Apply work-mode and avoided-skill penalties. Unknown distance counts as relocation."""
    total = score + skill_penalty(avoided, config)
    if work_mode != "remote":
        local = distance_km is not None and distance_km <= config.search.radius_km
        key = f"{work_mode}_{'local' if local else 'relocation'}"
        total += getattr(config.scoring.adjustments, key)
    return max(0, min(100, total))
