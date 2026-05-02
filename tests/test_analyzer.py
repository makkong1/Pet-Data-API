from collections import Counter
from app.ingestion.analyzer.morpheme import extract_nouns
from app.ingestion.analyzer.trend import aggregate_keywords


def test_extract_nouns_returns_nouns():
    text = "강아지 간식 오리젠 추천 후기"
    nouns = extract_nouns(text)
    assert "오리젠" in nouns


def test_extract_nouns_filters_stopwords():
    text = "강아지 고양이 반려동물 추천 후기 정보"
    nouns = extract_nouns(text)
    stopwords = {"강아지", "고양이", "반려동물", "추천", "후기", "정보"}
    assert not stopwords.intersection(set(nouns))


def test_extract_nouns_filters_single_char():
    text = "개 고양이 밥 먹기"
    nouns = extract_nouns(text)
    assert all(len(n) > 1 for n in nouns)


def test_aggregate_keywords_counts_frequency():
    items = [
        {"title": "오리젠 간식 후기", "description": "오리젠 추천"},
        {"title": "로얄캐닌 사료", "description": "오리젠 비교"},
    ]
    counter = aggregate_keywords(items)
    assert isinstance(counter, Counter)
    assert counter["오리젠"] >= 2


def test_aggregate_keywords_empty_input():
    counter = aggregate_keywords([])
    assert len(counter) == 0
