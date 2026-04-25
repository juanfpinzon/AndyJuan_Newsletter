"""Capture live Phase 3 LLM outputs into fixture directories."""

from __future__ import annotations

import json
import os
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

FIXTURES_ROOT = PROJECT_ROOT / "tests" / "fixtures" / "llm"
DEFAULT_SPIKE_DB_PATH = PROJECT_ROOT / "data" / "phase3_spike.db"


@dataclass(frozen=True)
class CaptureRecord:
    kind: str
    scenario: str
    model: str
    tokens_in: int
    tokens_out: int
    cost_usd: str
    output_path: str
    normalized_path: str


class LiveLLMRecorder:
    """Wrap the OpenRouter caller to retain raw response metadata per scenario."""

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.last_response = None

    def __call__(
        self,
        prompt: str,
        model: str,
        max_tokens: int,
        fallback_model: str | None = None,
    ):
        from src.utils.llm import call_openrouter

        response = call_openrouter(
            prompt,
            model=model,
            max_tokens=max_tokens,
            fallback_model=fallback_model,
            db_path=self.db_path,
        )
        self.last_response = response
        return response


def main() -> int:
    load_dotenv(PROJECT_ROOT / ".env")
    _require_env("OPENROUTER_API_KEY")

    db_path = Path(os.getenv("SPIKE_DATABASE_PATH", str(DEFAULT_SPIKE_DB_PATH)))
    records: list[CaptureRecord] = []
    total_cost = Decimal("0")

    records.extend(_capture_ranker(db_path))
    records.extend(_capture_theme_flash(db_path))
    records.extend(_capture_synthesis(db_path))
    records.extend(_capture_fact_checker(db_path))

    for record in records:
        total_cost += Decimal(record.cost_usd)

    report_path = FIXTURES_ROOT / "spike_report.json"
    report_path.write_text(
        json.dumps(
            {
                "captured_at": datetime.now(timezone.utc).isoformat(),
                "db_path": str(db_path),
                "total_cost_usd": str(total_cost.quantize(Decimal("0.000001"))),
                "captures": [asdict(record) for record in records],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    print(f"Captured {len(records)} live LLM outputs")
    print(f"Total cost USD: {total_cost.quantize(Decimal('0.000001'))}")
    print(f"Report: {report_path.relative_to(PROJECT_ROOT)}")
    return 0


def _capture_ranker(db_path: Path) -> list[CaptureRecord]:
    from src.analyzer.ranker import ArticleCandidate, rank_news
    from src.config import load_settings
    from src.exposure.models import ExposureEntry
    from src.fetcher.models import Article

    results: list[CaptureRecord] = []
    for scenario_dir in sorted((FIXTURES_ROOT / "ranker").iterdir()):
        payload = _load_json(scenario_dir / "input.json")
        recorder = LiveLLMRecorder(db_path)
        output = rank_news(
            [
                ArticleCandidate(
                    article=Article(
                        title=str(item["title"]),
                        body=str(item["body"]),
                        url=str(item["url"]),
                        source=str(item["source"]),
                        published_at=str(item["published_at"]),
                        raw_tags=tuple(str(tag) for tag in item.get("raw_tags", [])),
                    ),
                    matched_entities=tuple(
                        str(entity) for entity in item.get("matched_entities", [])
                    ),
                )
                for item in payload["articles"]
            ],
            {
                entity: ExposureEntry(
                    entity=entity,
                    composite_weight=Decimal(str(entry["composite_weight"])),
                    paths=tuple(
                        {
                            "source": str(path["source"]),
                            "weight": Decimal(str(path["weight"])),
                        }
                        for path in entry["paths"]
                    ),
                )
                for entity, entry in payload["exposure_map"].items()
            },
            llm_caller=recorder,
            settings=load_settings(),
        )
        results.append(
            _persist_capture(
                kind="ranker",
                scenario_dir=scenario_dir,
                recorder=recorder,
                normalized_payload=[
                    {
                        "title": item.article.title,
                        "primary_entity": item.primary_entity,
                        "matched_entities": list(item.matched_entities),
                        "composite_weight": str(item.composite_weight),
                        "llm_score": item.llm_score,
                        "included_by": item.included_by,
                        "rationale": item.rationale,
                    }
                    for item in output
                ],
            )
        )
    return results


def _capture_theme_flash(db_path: Path) -> list[CaptureRecord]:
    from src.analyzer.ranker import RankedArticle
    from src.analyzer.theme_flash import generate_theme_flash
    from src.config import load_settings
    from src.fetcher.models import Article

    results: list[CaptureRecord] = []
    for scenario_dir in sorted((FIXTURES_ROOT / "theme_flash").iterdir()):
        payload = _load_json(scenario_dir / "input.json")
        recorder = LiveLLMRecorder(db_path)
        output = generate_theme_flash(
            str(payload["theme"]),
            [
                RankedArticle(
                    article=Article(
                        title=str(item["title"]),
                        body=str(item.get("body", "")),
                        url=str(item.get("url", f"https://example.com/{index}")),
                        source=str(item.get("source", "Fixture")),
                        published_at=str(
                            item.get("published_at", "2026-04-25T00:00:00Z")
                        ),
                        raw_tags=tuple(str(tag) for tag in item.get("raw_tags", [])),
                    ),
                    primary_entity=str(item.get("primary_entity") or ""),
                    matched_entities=(str(item.get("primary_entity") or ""),),
                    composite_weight=Decimal(str(item["composite_weight"])),
                    llm_score=int(item.get("llm_score", 80)),
                    included_by=str(item.get("included_by", "rank")),
                    rationale=str(item.get("rationale", "Fixture rationale.")),
                )
                for index, item in enumerate(payload["articles"])
            ],
            llm_caller=recorder,
            settings=load_settings(),
        )
        results.append(
            _persist_capture(
                kind="theme_flash",
                scenario_dir=scenario_dir,
                recorder=recorder,
                normalized_payload=asdict(output),
            )
        )
    return results


def _capture_synthesis(db_path: Path) -> list[CaptureRecord]:
    from src.analyzer.ranker import RankedArticle
    from src.analyzer.synthesis import generate_synthesis
    from src.analyzer.theme_flash import ThemeFlash
    from src.config import load_settings
    from src.exposure.models import ExposureEntry
    from src.fetcher.models import Article

    results: list[CaptureRecord] = []
    for scenario_dir in sorted((FIXTURES_ROOT / "synthesis").iterdir()):
        payload = _load_json(scenario_dir / "input.json")
        recorder = LiveLLMRecorder(db_path)
        output = generate_synthesis(
            [
                ThemeFlash(
                    theme=str(item["theme"]),
                    text=str(item["text"]),
                    sentence_count=int(item["sentence_count"]),
                )
                for item in payload["theme_flashes"]
            ],
            [
                RankedArticle(
                    article=Article(
                        title=str(item["title"]),
                        body=str(item.get("body", "")),
                        url=str(item.get("url", f"https://example.com/{index}")),
                        source=str(item.get("source", "Fixture")),
                        published_at=str(
                            item.get("published_at", "2026-04-25T00:00:00Z")
                        ),
                        raw_tags=tuple(str(tag) for tag in item.get("raw_tags", [])),
                    ),
                    primary_entity=str(item.get("primary_entity") or ""),
                    matched_entities=(str(item.get("primary_entity") or ""),),
                    composite_weight=Decimal(str(item["composite_weight"])),
                    llm_score=int(item.get("llm_score", 80)),
                    included_by=str(item.get("included_by", "rank")),
                    rationale=str(item.get("rationale", "Fixture rationale.")),
                )
                for index, item in enumerate(payload["ranked_articles"])
            ],
            {
                entity: ExposureEntry(
                    entity=entity,
                    composite_weight=Decimal(str(entry["composite_weight"])),
                    paths=tuple(
                        {
                            "source": str(path["source"]),
                            "weight": Decimal(str(path["weight"])),
                        }
                        for path in entry["paths"]
                    ),
                )
                for entity, entry in payload["exposure_map"].items()
            },
            llm_caller=recorder,
            settings=load_settings(),
        )
        results.append(
            _persist_capture(
                kind="synthesis",
                scenario_dir=scenario_dir,
                recorder=recorder,
                normalized_payload={
                    "text": output.text,
                    "paragraphs": list(output.paragraphs),
                },
            )
        )
    return results


def _capture_fact_checker(db_path: Path) -> list[CaptureRecord]:
    from src.analyzer.fact_checker import fact_check_ai_take
    from src.config import load_settings

    results: list[CaptureRecord] = []
    for scenario_dir in sorted((FIXTURES_ROOT / "fact_checker").iterdir()):
        payload = _load_json(scenario_dir / "input.json")
        recorder = LiveLLMRecorder(db_path)
        output = fact_check_ai_take(
            str(payload["rendered_content"]),
            str(payload["ai_take_text"]),
            llm_caller=recorder,
            settings=load_settings(),
        )
        results.append(
            _persist_capture(
                kind="fact_checker",
                scenario_dir=scenario_dir,
                recorder=recorder,
                normalized_payload=asdict(output),
            )
        )
    return results


def _persist_capture(
    *,
    kind: str,
    scenario_dir: Path,
    recorder: LiveLLMRecorder,
    normalized_payload: Any,
) -> CaptureRecord:
    if recorder.last_response is None:
        raise RuntimeError(f"No LLM response captured for {kind}/{scenario_dir.name}")

    output_path = scenario_dir / "live_output.txt"
    output_path.write_text(
        recorder.last_response.content.strip() + "\n",
        encoding="utf-8",
    )

    normalized_path = scenario_dir / "live_normalized.json"
    normalized_path.write_text(
        json.dumps(normalized_payload, indent=2) + "\n",
        encoding="utf-8",
    )

    metadata_path = scenario_dir / "capture_metadata.json"
    metadata_path.write_text(
        json.dumps(
            {
                "captured_at": datetime.now(timezone.utc).isoformat(),
                "model": recorder.last_response.model,
                "tokens_in": recorder.last_response.tokens_in,
                "tokens_out": recorder.last_response.tokens_out,
                "cost_usd": recorder.last_response.cost_usd,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    return CaptureRecord(
        kind=kind,
        scenario=scenario_dir.name,
        model=recorder.last_response.model,
        tokens_in=recorder.last_response.tokens_in,
        tokens_out=recorder.last_response.tokens_out,
        cost_usd=str(recorder.last_response.cost_usd),
        output_path=str(output_path.relative_to(PROJECT_ROOT)),
        normalized_path=str(normalized_path.relative_to(PROJECT_ROOT)),
    )


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _require_env(name: str) -> None:
    if os.getenv(name):
        return
    raise RuntimeError(f"Required environment variable is missing: {name}")


if __name__ == "__main__":
    raise SystemExit(main())
