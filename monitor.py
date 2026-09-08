import json
import os
import re
import urllib.request
from datetime import datetime, timezone, timedelta

from html.parser import HTMLParser


URL = "https://www.drivetraffic.jp/road_closed_information.html"
STATE_FILE = "state.json"
FACILITIES_FILE = "facilities.json"
POSITIONS_FILE = "facility_positions.json"

JST = timezone(timedelta(hours=9))


# =========================================================
# 道路ごとのIC順
# 数字が小さいほど東京・いわき・村田方面
# 数字が大きいほど青森・秋田・庄内方面
# =========================================================

ROUTE_ORDERS = {

    "E4": [
        "矢吹",
        "鏡石スマート",
        "須賀川",
        "郡山南",
        "郡山中央スマート",
        "郡山",
        "本宮",
        "二本松",
        "福島松川スマート",
        "福島西",
        "福島JCT",
        "福島飯坂",
        "桑折JCT",
        "国見",
        "白石",
        "村田",
        "仙台南",
        "仙台宮城",
        "泉PAスマート",
        "泉",
        "大和",
        "大衡",
        "三本木スマート",
        "古川",
        "長者原スマート",
        "築館",
        "若柳金成",
        "一関",
        "平泉スマート",
        "平泉前沢",
        "奥州スマート",
        "水沢",
        "北上金ヶ崎",
        "北上江釣子",
        "花巻南",
        "花巻",
        "紫波",
        "矢巾スマート",
        "盛岡南",
        "盛岡",
        "滝沢中央スマート",
        "滝沢",
        "西根",
        "松尾八幡平",
        "安代",
        "鹿角八幡平",
        "十和田",
        "小坂",
        "小坂JCT",
        "碇ヶ関",
        "大鰐弘前",
        "黒石",
        "浪岡",
        "青森",
    ],

    "E4A": [
        "浄法寺",
        "一戸",
        "九戸",
        "軽米",
        "南郷",
        "八戸",
        "八戸北",
        "八戸西スマート",
        "八戸JCT",
    ],

    "E46": [
        "北上西",
        "湯田",
        "横手",
        "横手北スマート",
        "大曲",
        "西仙北スマート",
        "協和",
        "秋田南",
        "秋田中央",
        "秋田北",
        "昭和男鹿半島",
        "五城目八郎潟",
        "琴丘森岳",
    ],

    "E48": [
        "宮城川崎",
        "笹谷",
        "関沢",
        "山形蔵王",
        "山形北",
        "寒河江",
        "西川",
        "湯殿山",
        "鶴岡",
        "庄内あさひ",
    ],

    "E49": [
        "いわき三和",
        "小野",
        "田村スマート",
        "船引三春",
        "郡山東",
        "磐梯熱海",
        "猪苗代磐梯高原",
        "磐梯河東",
        "会津若松",
        "新鶴スマート",
        "会津坂下",
        "西会津",
        "津川",
        "三川",
        "安田",
        "新津",
        "新津西スマート",
        "新潟中央",
    ],

    "E6": [
        "いわき勿来",
        "いわき小名浜",
        "いわき湯本",
        "いわき中央",
        "いわき四倉",
        "広野",
        "ならはスマート",
        "常磐富岡",
        "大熊",
        "常磐双葉",
        "浪江",
        "南相馬",
        "南相馬鹿島スマート",
        "相馬",
        "新地",
    ],
}


# ドラとらの表記と、こちらの道路コードを対応
ROAD_MAP = {
    "東北自動車道": "E4",
    "八戸自動車道": "E4A",
    "秋田自動車道": "E46",
    "山形自動車道": "E48",
    "磐越自動車道": "E49",
    "常磐自動車道": "E6",
}


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
            "User-Agent":
                "Mozilla/5.0 "
                "(iPhone; CPU iPhone OS 18_0 like Mac OS X) "
                "AppleWebKit/605.1.15 Safari/605.1.15"
        },
    )

    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read().decode(
            "utf-8",
            errors="replace"
        )


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

    return load_json(
        FACILITIES_FILE,
        []
    )


def load_positions():

    return load_json(
        POSITIONS_FILE,
        []
    )


def save_state(state):

    with open(
        STATE_FILE,
        "w",
        encoding="utf-8"
    ) as f:

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

    return datetime.now(
        JST
    ).isoformat(
        timespec="seconds"
    )


def normalize_name(text):

    text = text.strip()

    text = text.replace(
        "　",
        ""
    )

    text = text.replace(
        " ",
        ""
    )

    text = text.replace(
        "ＩＣ",
        "IC"
    )

    text = text.replace(
        "ＪＣＴ",
        "JCT"
    )

    text = text.replace(
        "スマートIC",
        "スマート"
    )

    text = text.replace(
        "ＰＡ",
        "PA"
    )

    text = text.replace(
        "ＳＡ",
        "SA"
    )

    return text


def canonical_ic_name(name):

    name = normalize_name(name)

    aliases = {

        "村田JCT": "村田",
        "富谷JCT": "富谷",
        "北上JCT": "北上金ヶ崎",
        "郡山JCT": "郡山",
        "福島JCT": "福島JCT",

        "矢巾スマートIC": "矢巾スマート",
        "鏡石スマートIC": "鏡石スマート",
        "長者原スマートIC": "長者原スマート",
        "泉PAスマートIC": "泉PAスマート",
        "滝沢中央スマートIC": "滝沢中央スマート",
        "西仙北スマートIC": "西仙北スマート",
        "横手北スマートIC": "横手北スマート",
        "田村スマートIC": "田村スマート",
        "ならはスマートIC": "ならはスマート",
        "南相馬鹿島スマートIC": "南相馬鹿島スマート",

    }

    return aliases.get(
        name,
        name
    )


def get_route_code(route):

    route = normalize_name(route)

    for name, code in ROAD_MAP.items():

        if normalize_name(name) in route:
            return code

    if route in ROUTE_ORDERS:
        return route

    return None


def split_section(section):

    section = normalize_name(section)

    parts = re.split(
        r"[～〜~ー－\-→]+",
        section
    )

    parts = [
        p.strip()
        for p in parts
        if p.strip()
    ]

    if len(parts) < 2:
        return None, None

    return (
        canonical_ic_name(parts[0]),
        canonical_ic_name(parts[-1])
    )


def route_index(route_code, ic_name):

    if route_code not in ROUTE_ORDERS:
        return None

    ic_name = canonical_ic_name(
        ic_name
    )

    order = ROUTE_ORDERS[
        route_code
    ]

    normalized_order = [
        canonical_ic_name(x)
        for x in order
    ]

    try:
        return normalized_order.index(
            ic_name
        )

    except ValueError:
        return None


def facility_position(
    route_code,
    position
):

    before = route_index(
        route_code,
        position.get("before", "")
    )

    after = route_index(
        route_code,
        position.get("after", "")
    )

    if before is None or after is None:
        return None

    return (
        before + after
    ) / 2


def find_facilities_in_closure(
    item,
    facilities,
    positions
):

    route_code = get_route_code(
        item.get("route", "")
    )

    if not route_code:
        return []

    start_ic, end_ic = split_section(
        item.get("section", "")
    )

    if not start_ic or not end_ic:
        return []

    start_index = route_index(
        route_code,
        start_ic
    )

    end_index = route_index(
        route_code,
        end_ic
    )

    if start_index is None or end_index is None:
        print(
            "IC位置を判定できません:",
            item.get("section")
        )
        return []

    low = min(
        start_index,
        end_index
    )

    high = max(
        start_index,
        end_index
    )

    position_map = {
        p.get("name"): p
        for p in positions
    }

    matches = []

    for facility in facilities:

        if facility.get("road") != route_code:
            continue

        if not facility.get("staffed", False):
            continue

        position = position_map.get(
            facility.get("name")
        )

        if not position:
            continue

        facility_index = facility_position(
            route_code,
            position
        )

        if facility_index is None:
            continue

        if low < facility_index < high:

            matches.append(
                facility
            )

    return matches


def parse_datetime(text):

    if not text:
        return None

    formats = [
        "%Y/%m/%d %H:%M",
        "%Y/%m/%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d %H:%M:%S",
    ]

    for fmt in formats:

        try:

            dt = datetime.strptime(
                text.strip(),
                fmt
            )

            return dt.replace(
                tzinfo=JST
            )

        except ValueError:
            pass

    return None


def duration_hours(start_text):

    start = parse_datetime(
        start_text
    )

    if not start:
        return None

    now = datetime.now(JST)

    seconds = (
        now - start
    ).total_seconds()

    return seconds / 3600


def main():

    print(
        "SAPA通行止め監視くん 起動"
    )

    state = load_state()

    facilities = load_facilities()

    positions = load_positions()

    print(
        f"有人SAPAマスター: "
        f"{len(facilities)}件"
    )

    try:

        html = fetch_page()

        closures = parse_closures(
            html
        )

    except Exception as e:

        print(
            "NEXCO情報の取得に失敗しました"
        )

        print(e)

        raise

    print(
        f"現在の通行止め件数: "
        f"{len(closures)}"
    )

    current = {}

    for item in closures:

        event_id = make_id(
            item
        )

        matched = find_facilities_in_closure(
            item,
            facilities,
            positions
        )

        hours = duration_hours(
            item.get("start_time", "")
        )

        report_candidate = (
            hours is not None
            and hours >= 6
            and len(matched) > 0
        )

        current[event_id] = {

            **item,

            "first_seen":
                state["active"]
                .get(event_id, {})
                .get(
                    "first_seen",
                    now_jst()
                ),

            "matched_facilities": [
                facility["name"]
                for facility in matched
            ],

            "duration_hours":
                round(hours, 2)
                if hours is not None
                else None,

            "report_candidate":
                report_candidate,
        }

        if matched:

            print(
                "有人SAPA該当:",
                item.get("route"),
                item.get("section"),
                "→",
                ", ".join(
                    facility["name"]
                    for facility in matched
                )
            )

        if report_candidate:

            print(
                "★ 6時間以上・報告候補:",
                item.get("route"),
                item.get("section")
            )

    previous_ids = set(
        state["active"].keys()
    )

    current_ids = set(
        current.keys()
    )

    released_ids = (
        previous_ids
        - current_ids
    )

    for event_id in released_ids:

        event = state["active"][
            event_id
        ]

        event[
            "release_detected"
        ] = now_jst()

        print(
            "通行止め解除を検知:",
            event.get("route"),
            event.get("section")
        )

        state["released"].append(
            event
        )

    state["released"] = (
        state["released"][-2000:]
    )

    state["active"] = current

    save_state(
        state
    )

    print(
        "状態保存完了"
    )


if __name__ == "__main__":
    main()
