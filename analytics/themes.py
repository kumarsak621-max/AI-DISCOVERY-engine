"""Theme helpers wrapping clustering persistence."""

from __future__ import annotations

from sqlalchemy.orm import Session

from ai.clustering import cluster_and_store
from ai.openrouter import OpenRouterClient
from database.models import Analysis, Theme


def rebuild_themes(
    session: Session,
    analyses: list[Analysis],
    llm_client: OpenRouterClient | None = None,
) -> list[Theme]:
    return cluster_and_store(session, analyses, llm_client=llm_client)
