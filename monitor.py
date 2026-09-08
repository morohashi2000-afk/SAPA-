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
# IC・JCTの並び
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
        "北上JCT",
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
        "寒河江SAスマート",
        "西川",
        "西川本線",
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


ROAD_MAP = {
    "東北自動車道": "E4",
    "八戸自動車道": "E4A",
    "秋田自動車道": "E46",
    "山形自動車道": "E48",
    "磐越自動車道": "E49",
    "常磐自動車道": "E6",
}


# =========================================================
# HTML解析
# =========================================================

class TableParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.in_td = False
        self.in_th = False
        self.current_row = []
        self.rows = []
        self.buffer = ""

    def handle_starttag(self, tag, attrs):
        if tag == "td" or tag == "th":
            self.in_td = tag == "td"
            self.in_th = tag == "th"
            self.buffer = ""

        elif tag == "tr":
            self.current_row = []

    def handle_data(self, data):
        if self.in_td or self.in_th:
            self.buffer += data

    def handle_endtag(self, tag):
        if tag == "td" or tag == "th":
            text = self.buffer.strip()
            self.current_row.append(text)
            self.in_td = False
            self.in_th = False

        elif tag == "tr":
            if self.current_row:
                self.rows.append(self.current_row)


def fetch_page(url):
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 SAPA-monitor"
        },
    )

    with urllib.request.urlopen(req, timeout=30) as response:
        return response.read().decode("utf-8", errors="ignore")


def parse_closures(html):
    parser = TableParser()
    parser.feed(html)

    closures = []

    for row in parser.rows:
        if len(row) < 6:
            continue

        # Drivetrafficの現在の表
        # 路線名 / 方向 / 区間 / 理由 / 処理状況 / 通行止開始時間 ...
        route_name = row[0]
        direction = row[1]
        section = row[2]
        reason = row[3]
        status = row[4]
        start_time = row[5]

        if route_name not in ROAD_MAP:
            continue

        if not section:
            continue

        if not start_time:
            continue

        closures.append({
            "route_name": route_name,
            "route_code": ROAD_MAP[route_name],
            "direction": direction,
            "section": section,
            "reason": reason,
            "status": status,
            "start_time": start_time,
        })

    return closures


# =========================================================
# JSON
# =========================================================

def load_json(filename, default):
    if not os.path.exists(filename):
        return default

    try:
        with open(filename, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def load_state():
    return load_json(STATE_FILE, {})


def load_facilities():
    return load_json(FACILITIES_FILE, [])


def load_positions():
    return load_json(POSITIONS_FILE, [])


def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(
            state,
            f,
            ensure_ascii=False,
            indent=2,
        )


# =========================================================
# 名前処理
# =========================================================

def normalize_name(name):
    if not name:
        return ""

    name = name.strip()

    # 全角スペース・半角スペース除去
    name = name.replace("　", "")
    name = name.replace(" ", "")

    # 表記ゆれ
    name = name.replace("ＩＣ", "IC")
    name = name.replace("ＪＣＴ", "JCT")
    name = name.replace("ＰＡ", "PA")
    name = name.replace("ＳＡ", "SA")

    name = name.replace("スマートIC", "スマート")
    name = name.replace("スマートＩＣ", "スマート")

    return name


def canonical_ic_name(name):
    name = normalize_name(name)

    aliases = {
        "村田JCT": "村田",
        "富谷JCT": "富谷",
        "郡山JCT": "郡山",
        "福島JCT": "福島JCT",

        "鏡石スマートIC": "鏡石スマート",
        "郡山中央スマートIC": "郡山中央スマート",
        "福島松川スマートIC": "福島松川スマート",
        "泉PAスマートIC": "泉PAスマート",
        "長者原スマートIC": "長者原スマート",
        "矢巾スマートIC": "矢巾スマート",
        "滝沢中央スマートIC": "滝沢中央スマート",
        "平泉スマートIC": "平泉スマート",
        "奥州スマートIC": "奥州スマート",
        "花巻南スマートIC": "花巻南",
        "新鶴スマートIC": "新鶴スマート",
        "田村スマートIC": "田村スマート",
        "南相馬鹿島スマートIC": "南相馬鹿島スマート",
        "ならはスマートIC": "ならはスマート",
        "横手北スマートIC": "横手北スマート",
        "西仙北スマートIC": "西仙北スマート",
        "八戸西スマートIC": "八戸西スマート",
    }

    return aliases.get(name, name)


# =========================================================
# 通行止め区間
# =========================================================

def get_route_code(route_name):
    return ROAD_MAP.get(route_name)


def split_section(section):
    if not section:
        return []

    parts = re.split(r"[～〜~ー－\-→]", section)

    return [
        canonical_ic_name(x)
        for x in parts
        if x.strip()
    ]


def route_index(route_code, ic_name):
    ic_name = canonical_ic_name(ic_name)

    order = ROUTE_ORDERS.get(route_code, [])

    normalized_order = [
        canonical_ic_name(x)
        for x in order
    ]

    try:
        return normalized_order.index(ic_name)
    except ValueError:
        return None


# =========================================================
# SAPA位置
# =========================================================

def facility_position(facility, positions):
    name = facility.get("name")

    # 北上金ヶ崎PAは公式施設情報上、
    # 上り線で「北上JCT～水沢」の間。
    # 現在のJSONに古い値が残っていても、
    # ここでは正しい位置を優先する。
    if name == "北上金ヶ崎PA":
        return {
            "before": "北上JCT",
            "after": "水沢",
        }

    for item in positions:
        if item.get("name") == name:
            return {
                "before": item.get("before"),
                "after": item.get("after"),
            }

    return None


def find_facilities_in_closure(
    route_code,
    section,
    facilities,
    positions,
):
    endpoints = split_section(section)

    if len(endpoints) < 2:
        return []

    start = route_index(route_code, endpoints[0])
    end = route_index(route_code, endpoints[1])

    if start is None or end is None:
        return []

    low = min(start, end)
    high = max(start, end)

    matched = []

    for facility in facilities:
        if not facility.get("staffed"):
            continue

        if facility.get("road") != route_code:
            continue

        position = facility_position(
            facility,
            positions,
        )

        if not position:
            continue

        before = route_index(
            route_code,
            position["before"],
        )

        after = route_index(
            route_code,
            position["after"],
        )

        if before is None or after is None:
            continue

        facility_low = min(before, after)
        facility_high = max(before, after)

        # SAPAが通行止め区間内にあるか判定
        if facility_high >= low and facility_low <= high:
            matched.append(facility["name"])

    return matched


# =========================================================
# 日時
# =========================================================

def parse_datetime(value):
    if not value:
        return None

    value = value.strip()

    formats = [
        "%Y/%m/%d %H:%M",
        "%Y/%m/%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d %H:%M:%S",
    ]

    for fmt in formats:
        try:
            return datetime.strptime(
                value,
                fmt,
            ).replace(tzinfo=JST)
        except ValueError:
            pass

    return None


def now_jst():
    return datetime.now(JST)


def duration_hours(start_time):
    start = parse_datetime(start_time)

    if start is None:
        return None

    seconds = (
        now_jst() - start
    ).total_seconds()

    return seconds / 3600


# =========================================================
# ID
# =========================================================

def make_id(item):
    raw = "|".join([
        item.get("route_code", ""),
        item.get("direction", ""),
        item.get("section", ""),
        item.get("start_time", ""),
    ])

    return raw


# =========================================================
# テストモード
# =========================================================

def run_test_mode():
    print("=" * 60)
    print("SAPA通行止め監視くん TEST MODE")
    print("=" * 60)
    print("NEXCOの実データは取得しません。")
    print("仮想通行止めを使ってSAPA判定をテストします。")
    print()

    facilities = load_facilities()
    positions = load_positions()

    if not facilities:
        raise RuntimeError(
            "facilities.json が読み込めません。"
        )

    if not positions:
        raise RuntimeError(
            "facility_positions.json が読み込めません。"
        )

    print(
        f"対象SAPA数: {len(facilities)}"
    )

    if len(facilities) != 28:
        raise RuntimeError(
            f"SAPA数が28ではありません: {len(facilities)}"
        )

    # 7時間前の時刻を作る
    test_start = (
        now_jst() - timedelta(hours=7)
    ).strftime("%Y/%m/%d %H:%M")

    test_cases = [
        {
            "name": "東北道・盛岡南～水沢",
            "route_code": "E4",
            "direction": "東京方面",
            "section": "盛岡南～水沢",
            "expected": [
                "矢巾PA",
                "紫波SA",
                "北上金ヶ崎PA",
                "前沢SA",
            ],
        },
        {
            "name": "秋田道・湯田～協和",
            "route_code": "E46",
            "direction": "秋田方面",
            "section": "湯田～協和",
            "expected": [
                "錦秋湖SA",
                "西仙北SA",
            ],
        },
        {
            "name": "磐越道・小野～磐梯河東",
            "route_code": "E49",
            "direction": "新潟方面",
            "section": "小野～磐梯河東",
            "expected": [
                "阿武隈高原SA",
                "磐梯山SA",
            ],
        },
        {
            "name": "常磐道・いわき勿来～広野",
            "route_code": "E6",
            "direction": "仙台方面",
            "section": "いわき勿来～広野",
            "expected": [
                "四倉PA",
            ],
        },
        {
            "name": "山形道・笹谷～宮城川崎",
            "route_code": "E48",
            "direction": "山形方面",
            "section": "笹谷～宮城川崎",
            "expected": [
                "古関PA",
            ],
        },
        {
            "name": "東北道・築館～一関",
            "route_code": "E4",
            "direction": "青森方面",
            "section": "築館～一関",
            "expected": [
                "金成PA",
            ],
        },
        {
            "name": "東北道・白石～国見",
            "route_code": "E4",
            "direction": "東京方面",
            "section": "白石～国見",
            "expected": [
                "国見SA",
            ],
        },
        {
            "name": "山形道・鶴岡～庄内あさひ",
            "route_code": "E48",
            "direction": "鶴岡方面",
            "section": "鶴岡～庄内あさひ",
            "expected": [
                "櫛引PA",
            ],
        },
    ]

    passed = 0

    print()

    for i, case in enumerate(test_cases, start=1):
        print("-" * 60)
        print(
            f"TEST {i}: {case['name']}"
        )
        print(
            f"区間: {case['section']}"
        )

        matched = find_facilities_in_closure(
            case["route_code"],
            case["section"],
            facilities,
            positions,
        )

        matched_sorted = sorted(matched)
        expected_sorted = sorted(
            case["expected"]
        )

        print(
            f"検出: {matched_sorted}"
        )
        print(
            f"期待: {expected_sorted}"
        )

        if matched_sorted != expected_sorted:
            print("❌ FAIL")
            raise RuntimeError(
                f"TEST {i} failed: "
                f"expected={expected_sorted}, "
                f"actual={matched_sorted}"
            )

        # 7時間経過している想定なので
        # 6時間以上判定も確認
        hours = duration_hours(
            test_start
        )

        report_candidate = (
            hours is not None
            and hours >= 6
            and len(matched) > 0
        )

        if not report_candidate:
            print(
                "❌ FAIL: "
                "6時間以上の報告対象判定に失敗"
            )

            raise RuntimeError(
                f"TEST {i} report_candidate failed"
            )

        print(
            f"経過時間: {hours:.2f}時間"
        )
        print(
            "報告対象判定: True"
        )
        print("✅ PASS")

        passed += 1

    print()
    print("=" * 60)
    print(
        f"TEST COMPLETE: {passed}/{len(test_cases)} PASS"
    )
    print("=" * 60)
    print(
        "SAPA判定・6時間判定ともに正常です。"
    )
    print(
        "state.json は変更していません。"
    )
    print()


# =========================================================
# 通常監視
# =========================================================

def main():
    # TEST_MODE=true のときはテストだけ実行
    if os.environ.get(
        "TEST_MODE",
        ""
    ).lower() == "true":
        run_test_mode()
        return

    print("=" * 60)
    print("SAPA通行止め監視くん")
    print("=" * 60)

    state = load_state()
    facilities = load_facilities()
    positions = load_positions()

    print(
        f"現在の状態件数: {len(state)}"
    )
    print(
        f"対象SAPA数: {len(facilities)}"
    )

    html = fetch_page(URL)
    closures = parse_closures(html)

    print(
        f"現在の通行止め件数: {len(closures)}"
    )

    current_ids = set()

    for closure in closures:
        route_code = closure["route_code"]

        matched = find_facilities_in_closure(
            route_code,
            closure["section"],
            facilities,
            positions,
        )

        hours = duration_hours(
            closure["start_time"]
        )

        report_candidate = (
            hours is not None
            and hours >= 6
            and len(matched) > 0
        )

        closure_id = make_id(
            closure
        )

        current_ids.add(closure_id)

        state[closure_id] = {
            **closure,
            "matched_facilities": matched,
            "duration_hours": hours,
            "report_candidate": report_candidate,
            "last_seen": now_jst().isoformat(),
        }

        print()
        print(
            f"通行止め: "
            f"{closure['route_name']} "
            f"{closure['section']}"
        )

        print(
            f"理由: {closure['reason']}"
        )

        print(
            f"開始: {closure['start_time']}"
        )

        print(
            f"経過時間: "
            f"{hours:.2f}時間"
            if hours is not None
            else "不明"
        )

        print(
            f"該当SAPA: "
            f"{matched}"
        )

        print(
            f"報告候補: "
            f"{report_candidate}"
        )

    # =====================================================
    # 前回存在していたが、今回消えた通行止め
    # =====================================================

    disappeared = []

    for closure_id, old in list(state.items()):
        if closure_id not in current_ids:
            if not old.get(
                "release_detected"
            ):
                old["release_detected"] = (
                    now_jst().isoformat()
                )

                disappeared.append(
                    old
                )

    if disappeared:
        print()
        print(
            f"解除を検知した通行止め: "
            f"{len(disappeared)}件"
        )

        for item in disappeared:
            print(
                f"- {item.get('route_name')} "
                f"{item.get('section')}"
            )
            print(
                f"  解除検知: "
                f"{item.get('release_detected')}"
            )

    save_state(state)

    print()
    print(
        "状態を保存しました。"
    )
    print()


if __name__ == "__main__":
    main()
