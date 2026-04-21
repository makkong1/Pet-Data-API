from collections import Counter
from app.analyzer.morpheme import extract_nouns


def aggregate_keywords(items: list[dict]) -> Counter:
    counter: Counter = Counter()
    for item in items:
        text = f"{item.get('title', '')} {item.get('description', '')}"
        counter.update(extract_nouns(text))
    return counter
