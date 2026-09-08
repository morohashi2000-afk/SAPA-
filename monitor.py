import json
import os
import re
import urllib.request
from datetime import datetime, timezone, timedelta
from html.parser import HTMLParser

URL = "https://www.drivetraffic.jp/road_closed_information.html"
STATE_FILE = "state.json"
FACILITIES_FILE = "facilities.json"

JST = timezone(timedelta(hours=9))


class TableParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.in_td = False
        self.in_th = False
        self.current = []
        self.rows = []
        self.row = []

    def handle_starttag(self, tag, attrs):
        if tag == "tr":
            self.row = []
        elif tag in ("td", "th"):
            self.in_td = tag == "td"
            self.in_th = tag == "th"
            self.current = []

    def handle_endtag(self, tag):
        if tag in ("td", "th"):
            text = "".join(self.current).strip()
            self.row.append(text)
            self.in_td = False
            self.in_th = False

        elif tag == "tr":
            if self.row:
                self.rows.append(self.row)
            self.row = []

    def handle_data(self, data):
        if self.in_td or self.in_th:
            self.current.append(data)


def fetch_page():
    request = urllib.request.Request(
        URL,
        headers={
            "User-Agent": (
                "Mozilla/5.0 "
                "(iPhone; CPU iPhone OS 18_0 like Mac OS X) "
                "AppleWebKit/605.1.15 Safari/605.1.15"
            )
        },
    )

    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read().decode("utf-8", errors="replace")


def parse_closures(html):
    parser = TableParser()
    parser.feed(html)

    closures = []

    headers = [
        "route",
        "direction",
        "section",
        "reason",
        "status",
        "start_time",
        "update_time",
        "work",
        "expected_release",
        "note",
    ]

    for row in parser.rows:
        if len(row) < 6:
            continue

        if "路線名" in row[0]:
            continue

        row = row[:10] + [""] * (10 - len(row))

        item = dict(zip(headers, row))

        if not item["route"]:
            continue

        closures.append(item)

    return closures


def load_json(filename, default):
    if not os.path.exists(filename):
        return default

    try:
        with open(filename, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def load_state():
    return load_json(
        STATE_FILE,
        {
            "active": {},
            "released": []
        }
    )


def load_facilities():
    return load_json(FACILITIES_FILE, [])


def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(
            state,
            f,
            ensure_ascii=False,
            indent=2
        )


def make_id(item):
    values = [
        item.get("route", ""),
        item.get("direction", ""),
        item.get("section", ""),
        item.get("start_time", ""),
    ]

    return "|".join(values)


def now_jst():
    return datetime.now(JST).isoformat(timespec="seconds")


def normalize_text(text):
    return (
        text
        .replace("　", "")
        .replace(" ", "")
        .replace("ＪＣＴ", "JCT")
        .replace("ＩＣ", "IC")
    )


def find_facility_mentions(item, facilities):
    """
    現段階では通行止め情報の文字列に
    SAPA名が直接出ている場合だけ検出する。

    IC間による正式な位置判定は次段階で実装する。
    """
    section = normalize_text(item.get("section", ""))

    matches = []

    for facility in facilities:
        name = normalize_text(facility.get("name", ""))

        if not name:
            continue

        if name in section:
            matches.append(facility)

    return matches


def main():
    print("SAPA通行止め監視くん 起動")

    state = load_state()
    facilities = load_facilities()

    print(f"有人SAPAマスター: {len(facilities)}件")

    try:
        html = fetch_page()
        closures = parse_closures(html)
    except Exception as e:
        print("NEXCO情報の取得に失敗しました")
        print(e)
        raise

    print(f"現在の通行止め件数: {len(closures)}")

    current = {}

    for item in closures:
        event_id = make_id(item)

        matched_facilities = find_facility_mentions(
            item,
            facilities
        )

        current[event_id] = {
            **item,
            "first_seen": (
                state["active"]
                .get(event_id, {})
                .get("first_seen", now_jst())
            ),
            "matched_facilities": [
                facility["name"]
                for facility in matched_facilities
            ],
        }

    previous_ids = set(state["active"].keys())
    current_ids = set(current.keys())

    released_ids = previous_ids - current_ids

    for event_id in released_ids:
        event = state["active"][event_id]

        event["release_detected"] = now_jst()

        print(
            "通行止め解除を検知:",
            event.get("route"),
            event.get("section")
        )

        state["released"].append(event)

    state["released"] = state["released"][-2000:]

    state["active"] = current

    save_state(state)

    print("状態保存完了")


if __name__ == "__main__":
    main()
