from collections import Counter
from app.ingestion.analyzer.morpheme import extract_nouns


def aggregate_keywords(items: list) -> Counter:
    """list[PostRecord] → 키워드 빈도 Counter."""
    counter: Counter = Counter()
    for r in items:
        text = f"{r.title} {r.description}"
        counter.update(extract_nouns(text))
    return counter
