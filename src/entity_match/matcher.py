"""RapidFuzz-backed entity matching for fetched articles."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import yaml
from rapidfuzz import fuzz

from src.config import load_settings
from src.fetcher.models import Article

DEFAULT_THEMES_PATH = Path(__file__).resolve().parents[2] / "config" / "themes.yaml"
SYMBOL_RE = re.compile(r"^[A-Z0-9./-]{2,10}$")


@dataclass(frozen=True)
class EntityDefinition:
    entity: str
    aliases: tuple[str, ...]


@dataclass(frozen=True)
class EntityMatch:
    entity: str
    score: float
    method: str


@dataclass(frozen=True)
class _MatchMetadata:
    title_hits: int
    total_hits: int
    first_position: int


class EntityMatcher:
    """Match articles to configured entities using exact symbols and fuzzy aliases."""

    def __init__(
        self,
        entities: list[EntityDefinition],
        *,
        threshold: float,
    ) -> None:
        self.entities = entities
        self.threshold = threshold

    @classmethod
    def from_themes_file(
        cls,
        *,
        themes_path: str | Path | None = None,
        threshold: float | None = None,
    ) -> "EntityMatcher":
        matcher_threshold = (
            load_settings().entity_match_threshold if threshold is None else threshold
        )
        return cls(
            load_entity_definitions(themes_path or DEFAULT_THEMES_PATH),
            threshold=matcher_threshold,
        )

    def match(self, article: Article) -> list[EntityMatch]:
        ranked_matches: list[tuple[_MatchMetadata, EntityMatch]] = []
        for entity in self.entities:
            scored = self._score_entity(article, entity)
            if scored is None:
                continue
            metadata, match = scored
            if match.score >= self.threshold:
                ranked_matches.append((metadata, match))

        ranked_matches.sort(
            key=lambda item: (
                -item[1].score,
                -item[0].title_hits,
                -item[0].total_hits,
                item[0].first_position,
                item[1].entity,
            )
        )
        return [match for _, match in ranked_matches]

    def _score_entity(
        self,
        article: Article,
        entity: EntityDefinition,
    ) -> tuple[_MatchMetadata, EntityMatch] | None:
        title = article.title
        body = article.body
        raw_tags = tuple(article.raw_tags)

        best_match: EntityMatch | None = None
        best_metadata: _MatchMetadata | None = None

        for term in (entity.entity, *entity.aliases):
            if _is_symbol_term(term):
                metadata = _exact_metadata(
                    term,
                    title=title,
                    body=body,
                    raw_tags=raw_tags,
                )
                if metadata.total_hits == 0:
                    continue
                candidate = EntityMatch(
                    entity=entity.entity,
                    score=100.0,
                    method="ticker",
                )
            else:
                metadata, score = _alias_metadata(
                    term,
                    title=title,
                    body=body,
                    raw_tags=raw_tags,
                )
                if score == 0:
                    continue
                candidate = EntityMatch(
                    entity=entity.entity,
                    score=score,
                    method="alias",
                )

            if _is_better_candidate(
                metadata=metadata,
                candidate=candidate,
                current_metadata=best_metadata,
                current_match=best_match,
            ):
                best_match = candidate
                best_metadata = metadata

        if best_match is None or best_metadata is None:
            return None
        return best_metadata, best_match


def load_entity_definitions(path: str | Path) -> list[EntityDefinition]:
    payload = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    entities = payload.get("entities", {})
    return [
        EntityDefinition(
            entity=entity,
            aliases=tuple(config.get("aliases", [])),
        )
        for entity, config in entities.items()
    ]


def _is_symbol_term(term: str) -> bool:
    return bool(SYMBOL_RE.fullmatch(term))


def _exact_metadata(
    term: str,
    *,
    title: str,
    body: str,
    raw_tags: tuple[str, ...],
) -> _MatchMetadata:
    title_positions = _term_positions(term, title)
    body_positions = _term_positions(term, body)
    tag_hits = sum(1 for tag in raw_tags if tag.casefold() == term.casefold())
    positions = title_positions + [len(title) + 1 + pos for pos in body_positions]
    first_position = min(positions) if positions else 10**9
    return _MatchMetadata(
        title_hits=len(title_positions),
        total_hits=len(title_positions) + len(body_positions) + tag_hits,
        first_position=first_position,
    )


def _alias_metadata(
    term: str,
    *,
    title: str,
    body: str,
    raw_tags: tuple[str, ...],
) -> tuple[_MatchMetadata, float]:
    title_positions = _substring_positions(term, title)
    body_positions = _substring_positions(term, body)
    tag_hits = sum(1 for tag in raw_tags if tag.casefold() == term.casefold())
    positions = title_positions + [len(title) + 1 + pos for pos in body_positions]
    first_position = min(positions) if positions else 10**9

    if positions or tag_hits:
        return (
            _MatchMetadata(
                title_hits=len(title_positions),
                total_hits=len(title_positions) + len(body_positions) + tag_hits,
                first_position=first_position,
            ),
            95.0,
        )

    alias_lower = term.casefold()
    candidate_texts = [
        title.casefold(),
        body.casefold(),
        *(tag.casefold() for tag in raw_tags),
    ]
    score = max(
        (
            max(
                fuzz.partial_ratio(alias_lower, text),
                fuzz.token_set_ratio(alias_lower, text),
            )
            for text in candidate_texts
            if text
        ),
        default=0.0,
    )
    return (
        _MatchMetadata(title_hits=0, total_hits=0, first_position=10**9),
        float(score),
    )


def _is_better_candidate(
    *,
    metadata: _MatchMetadata,
    candidate: EntityMatch,
    current_metadata: _MatchMetadata | None,
    current_match: EntityMatch | None,
) -> bool:
    if current_metadata is None or current_match is None:
        return True
    if candidate.score != current_match.score:
        return candidate.score > current_match.score
    if metadata.title_hits != current_metadata.title_hits:
        return metadata.title_hits > current_metadata.title_hits
    if metadata.total_hits != current_metadata.total_hits:
        return metadata.total_hits > current_metadata.total_hits
    if metadata.first_position != current_metadata.first_position:
        return metadata.first_position < current_metadata.first_position
    return candidate.entity < current_match.entity


def _term_positions(term: str, text: str) -> list[int]:
    if not text:
        return []
    pattern = re.compile(
        rf"(?<![A-Za-z0-9])\$?{re.escape(term)}(?![A-Za-z0-9])"
    )
    return [match.start() for match in pattern.finditer(text)]


def _substring_positions(term: str, text: str) -> list[int]:
    if not term or not text:
        return []
    positions: list[int] = []
    haystack = text.casefold()
    needle = term.casefold()
    start = 0
    while True:
        index = haystack.find(needle, start)
        if index == -1:
            return positions
        positions.append(index)
        start = index + len(needle)
