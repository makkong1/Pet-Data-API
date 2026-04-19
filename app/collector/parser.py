from datetime import date


def parse_animal_item(raw: dict) -> dict:
    notice_date_str = raw.get("noticeSdt")
    notice_date = None
    if notice_date_str and len(notice_date_str) == 8:
        try:
            notice_date = date(
                int(notice_date_str[:4]),
                int(notice_date_str[4:6]),
                int(notice_date_str[6:8]),
            )
        except ValueError:
            pass

    return {
        "notice_no": raw.get("noticeNo"),
        "animal_type": raw.get("upKindNm"),
        "breed": raw.get("kindNm"),
        "age": raw.get("age"),
        "gender": raw.get("sexCd"),
        "region": raw.get("orgNm"),
        "shelter_name": raw.get("careNm"),
        "status": raw.get("processState"),
        "notice_date": notice_date,
    }


def extract_items(response: dict) -> list[dict]:
    try:
        items = response["response"]["body"]["items"]["item"]
        if isinstance(items, dict):
            items = [items]
        return [parse_animal_item(item) for item in items]
    except (KeyError, TypeError):
        return []
