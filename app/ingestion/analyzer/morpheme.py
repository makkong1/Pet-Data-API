from kiwipiepy import Kiwi

_kiwi = Kiwi()

STOPWORDS = {
    "강아지", "고양이", "반려동물", "반려", "추천", "후기", "정보",
    "소개", "리뷰", "구매", "사용", "사용기", "제품", "브랜드",
}


def extract_nouns(text: str) -> list[str]:
    tokens = _kiwi.tokenize(text)
    return [
        t.form
        for t in tokens
        if t.tag in ("NNG", "NNP") and t.form not in STOPWORDS and len(t.form) > 1
    ]
