import json
import os
import urllib.request
from datetime import datetime, timedelta, timezone

JST = timezone(timedelta(hours=9))


def now_jst():
    return datetime.now(JST)


def load_json(filename):
    with open(filename, "r", encoding="utf-8") as f:
        return json.load(f)


def load_settings():
    settings = load_json("settings.json")

    prefectures = settings.get("notification_prefectures")

    if not isinstance(prefectures, list):
        raise RuntimeError(
            "settings.json の notification_prefectures がリストになっていません。"
        )

    valid_prefectures = {
        "北海道",
        "青森県",
        "岩手県",
        "宮城県",
        "秋田県",
        "山形県",
        "福島県",
        "茨城県",
        "栃木県",
        "群馬県",
        "埼玉県",
        "千葉県",
        "東京都",
        "神奈川県",
        "新潟県",
        "長野県",
    }

    invalid = [p for p in prefectures if p not in valid_prefectures]

    if invalid:
        raise RuntimeError(
            "settings.json に不正な都道府県があります: "
            + ", ".join(invalid)
        )

    if not prefectures:
        raise RuntimeError(
            "notification_prefectures が空です。"
            "少なくとも1つ都道府県を設定してください。"
        )

    return set(prefectures)


def parse_datetime(value):
    if not value:
        return None

    value = value.strip()

    # ISO形式
    try:
        dt = datetime.fromisoformat(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=JST)
        return dt.astimezone(JST)
    except ValueError:
        pass

    # よくあるNEXCO表記
    formats = [
        "%Y/%m/%d %H:%M",
        "%Y/%m/%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d %H:%M:%S",
    ]

    for fmt in formats:
        try:
            return datetime.strptime(value, fmt).replace(tzinfo=JST)
        except ValueError:
            continue

    return None


def duration_hours(start, end):
    if not start or not end:
        return None

    seconds = (end - start).total_seconds()

    if seconds < 0:
        return None

    return seconds / 3600


def format_dt(dt):
    if not dt:
        return "不明"

    return dt.strftime("%Y/%m/%d %H:%M")


def format_duration(hours):
    if hours is None:
        return "不明"

    total_minutes = round(hours * 60)
    h = total_minutes // 60
    m = total_minutes % 60

    if m == 0:
        return f"{h}時間"

    return f"{h}時間{m}分"


def send_ntfy(message):
    topic = os.environ.get("NTFY_TOPIC", "")

    if not topic:
        raise RuntimeError("NTFY_TOPIC が設定されていません。")

    url = "https://ntfy.sh"

    payload = {
        "topic": topic,
        "title": "本社報告確認（08:00）",
        "message": message,
        "priority": 4,
        "tags": ["highway"],
    }

    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")

    request = urllib.request.Request(
        url,
        data=data,
        headers={
            "Content-Type": "application/json; charset=utf-8"
        },
        method="POST",
    )

    with urllib.request.urlopen(request, timeout=30) as response:
        if response.status < 200 or response.status >= 300:
            raise RuntimeError(
                f"ntfy通知失敗: HTTP {response.status}"
            )


def facility_matches_prefecture(facility, target_prefectures):
    return (
        facility.get("staffed") is True
        and facility.get("prefecture") in target_prefectures
    )


def get_release_time(item):
    """
    現時点では release_detected を使用。
    これは監視側が「通行止め一覧から消えた」と確認した時刻であり、
    NEXCO公式の実解除時刻そのものではない。
    """
    return parse_datetime(item.get("release_detected"))


def main():
    now = now_jst()

    settings = load_settings()
    state = load_json("state.json")
    facilities = load_json("facilities.json")

    # state.json が旧形式のリストの場合にも対応
    if isinstance(state, list):
        state_items = state
    elif isinstance(state, dict):
        state_items = state.get("closures", [])
    else:
        raise RuntimeError("state.json の形式が不正です。")

    # 前日17:30 ～ 当日08:00
    report_start = now.replace(
        hour=17,
        minute=30,
        second=0,
        microsecond=0,
    ) - timedelta(days=1)

    report_end = now.replace(
        hour=8,
        minute=0,
        second=0,
        microsecond=0,
    )

    candidates = []

    for item in state_items:
        matched_facilities = []

        for facility in facilities:
            if not facility_matches_prefecture(
                facility,
                settings,
            ):
                continue

            matched_names = item.get("matched_facilities", [])

            if facility.get("name") in matched_names:
                matched_facilities.append(facility)

        if not matched_facilities:
            continue

        start = parse_datetime(
            item.get("start_time")
            or item.get("closure_start")
        )

        if not start:
            continue

        release = get_release_time(item)

        # 現在も通行止め中
        if release is None:
            hours = duration_hours(start, now)

            if hours is not None and hours >= 6:
                candidates.append(
                    {
                        "item": item,
                        "facilities": matched_facilities,
                        "start": start,
                        "release": None,
                        "hours": hours,
                    }
                )

            continue

        # 08:00時点までに解除されたもの
        # かつ、解除時刻が前日17:30～当日08:00
        if report_start <= release <= report_end:
            hours = duration_hours(start, release)

            if hours is not None and hours >= 6:
                candidates.append(
                    {
                        "item": item,
                        "facilities": matched_facilities,
                        "start": start,
                        "release": release,
                        "hours": hours,
                    }
                )

    # 重複除去
    unique = {}

    for candidate in candidates:
        item = candidate["item"]

        key = (
            item.get("id")
            or item.get("closure_id")
            or (
                item.get("route"),
                item.get("section"),
                item.get("start_time"),
            )
        )

        unique[key] = candidate

    candidates = list(unique.values())

    lines = [
        "【08:00 本社報告確認】",
        "",
        f"通知対象都道府県：{'、'.join(sorted(settings))}",
        "",
    ]

    if not candidates:
        lines.append("本社報告対象の通行止めはありません。")

    else:
        lines.append(
            f"本社報告対象：{len(candidates)}件"
        )
        lines.append("")

        for i, candidate in enumerate(candidates, 1):
            item = candidate["item"]
            facilities_matched = candidate["facilities"]

            route = (
                item.get("route")
                or item.get("road")
                or "不明"
            )

            direction = item.get("direction") or "不明"

            section = (
                item.get("section")
                or item.get("区間")
                or "不明"
            )

            reason = (
                item.get("reason")
                or item.get("cause")
                or item.get("理由")
                or "不明"
            )

            prefectures = sorted(
                {
                    f.get("prefecture")
                    for f in facilities_matched
                    if f.get("prefecture")
                }
            )

            facility_names = [
                f.get("name")
                for f in facilities_matched
            ]

            lines.append(f"【{i}】")
            lines.append(
                f"都道府県：{'、'.join(prefectures)}"
            )
            lines.append(f"路線：{route}")
            lines.append(f"方向：{direction}")
            lines.append(f"区間：{section}")
            lines.append(
                f"通行止開始：{format_dt(candidate['start'])}"
            )

            if candidate["release"]:
                lines.append(
                    f"解除確認：{format_dt(candidate['release'])}"
                )
            else:
                lines.append("解除確認：未解除")

            lines.append(
                f"通行止め時間：{format_duration(candidate['hours'])}"
            )
            lines.append(f"原因：{reason}")
            lines.append(
                f"対象SAPA：{'、'.join(facility_names)}"
            )
            lines.append("→ 本社報告対象")
            lines.append("")

    message = "\n".join(lines)

    print(message)

    send_ntfy(message)


if __name__ == "__main__":
    main()
