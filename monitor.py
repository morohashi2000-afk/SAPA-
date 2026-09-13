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
# IC・JCTの並び (NEXCO東日本管内のみ・位置関係検証済み)
# =========================================================

ROUTE_ORDERS = {
    # --- 北海道エリア ---
    "E5": [ # 道央自動車道
        "大沼公園", "赤井川", "森", "落部", "八雲", "国縫", "長万部", "黒松内JCT", "豊浦", 
        "虻田洞爺湖", "伊達", "室蘭", "登別室蘭", "登別東", "白老", "苫小牧西", "苫小牧中央", 
        "苫小牧東", "沼ノ端", "新千歳空港", "千歳", "恵庭", "輪厚スマート", "北広島", "札幌南", 
        "大谷地", "札幌", "江別西", "江別東", "岩見沢", "三笠", "美唄", "奈井江砂川", "滝川", 
        "深川", "音江スマート", "旭川鷹栖", "旭川北", "和寒", "士別剣淵"
    ],
    "E5A": [ # 札樽自動車道
        "小樽", "朝里", "銭函", "手稲", "札幌西", "新川", "伏古", "札幌JCT"
    ],
    "E38": [ # 道東自動車道
        "千歳恵庭JCT", "千歳東", "追分町", "むかわ穂別", "夕張", "占冠", "トマム", "新得", "十勝清水", "芽室", "帯広JCT"
    ],

    # --- 東北エリア ---
    "E4": [ # 東北自動車道 (青森～川口JCT)
        "川口JCT", "浦和", "岩槻", "蓮田スマート", "久喜", "加須", "羽生", "館林", "佐野藤岡", 
        "岩舟JCT", "栃木", "栃木都賀JCT", "鹿沼", "宇都宮", "矢板", "矢板北スマート", "西那須野塩原", 
        "黒磯板室", "那須", "那須高原スマート", "白河", "矢吹", "鏡石スマート", "須賀川", "郡山南", 
        "郡山中央スマート", "郡山", "郡山JCT", "本宮", "二本松", "福島松川スマート", "福島西", "福島JCT", 
        "福島飯坂", "桑折JCT", "国見", "白石", "村田JCT", "村田", "仙台南", "仙台宮城", "泉PAスマート", 
        "泉", "富谷JCT", "大和", "大衡", "三本木スマート", "古川", "長者原スマート", "築館", "若柳金成", 
        "一関", "平泉スマート", "平泉前沢", "奥州スマート", "水沢", "北上金ヶ崎", "北上JCT", "北上江釣子", 
        "花巻南", "花巻", "花巻JCT", "紫波", "矢巾スマート", "盛岡南", "盛岡", "滝沢中央スマート", 
        "滝沢", "西根", "松尾八幡平", "安代JCT", "安代", "鹿角八幡平", "十和田", "小坂", "小坂JCT", 
        "碇ヶ関", "大鰐弘前", "黒石", "浪岡", "青森"
    ],
    "E4A": [ # 八戸自動車道
        "安代JCT", "浄法寺", "一戸", "九戸", "軽米", "南郷", "八戸JCT", "八戸", "八戸西スマート", "八戸北"
    ],
    "E46": [ # 秋田自動車道
        "北上JCT", "北上西", "湯田", "横手", "横手北スマート", "大曲", "西仙北スマート", "協和", 
        "秋田南", "秋田中央", "秋田北", "昭和男鹿半島", "五城目八郎潟", "琴丘森岳"
    ],
    "E48": [ # 山形自動車道
        "村田JCT", "宮城川崎", "笹谷", "関沢", "山形蔵王", "山形JCT", "山形北", "寒河江", 
        "寒河江SAスマート", "西川", "湯殿山", "庄内あさひ", "鶴岡"
    ],
    "E49": [ # 磐越自動車道
        "いわきJCT", "いわき三和", "小野", "田村スマート", "船引三春", "郡山東", "郡山JCT", 
        "磐梯熱海", "猪苗代磐梯高原", "磐梯河東", "会津若松", "新鶴スマート", "会津坂下", "西会津", 
        "津川", "三川", "安田", "新津", "新津西スマート", "新潟中央JCT"
    ],
    "E6": [ # 常磐自動車道 (三郷JCT～仙台)
        "三郷JCT", "流山", "柏", "守谷スマート", "谷和原", "谷田部", "つくばJCT", "桜土浦", 
        "土浦北", "千代田石岡", "小美玉スマート", "岩間", "友部JCT", "水戸", "那珂", "東海", 
        "日立南太田", "日立中央", "高萩", "北茨城", "いわき勿来", "いわき小名浜", "いわき湯本", 
        "いわきJCT", "いわき四倉", "広野", "ならはスマート", "常磐富岡", "大熊", "常磐双葉", 
        "浪江", "南相馬", "南相馬鹿島スマート", "相馬", "新地", "山元", "鳥の海スマート", "亘理", "岩沼"
    ],

    # --- 関東・信越・富山エリア ---
    "E8": [ # 北陸自動車道 (NEXCO東日本管轄: 朝日IC以東～新潟)
        "朝日", "糸魚川", "能生", "名立谷浜", "上越JCT", "柿崎", "米山", "柏崎", 
        "長岡JCT", "長岡北スマート", "見附中之島", "三条燕", "巻潟東", "黒埼スマート", "新潟西", "新潟中央JCT"
    ],
    "E17": [ # 関越自動車道 (練馬～長岡JCT)
        "練馬", "所沢", "川越", "坂戸西スマート", "東松山", "嵐山小川", "花園", "本庄児玉", 
        "上里スマート", "藤岡JCT", "高崎", "高崎JCT", "前橋", "駒寄スマート", "渋川伊香保", 
        "赤城", "昭和", "沼田", "月夜野", "水上", "湯沢", "塩沢石打", "六日町", "大和スマート", 
        "小出", "越後川口", "小千谷", "長岡JCT"
    ],
    "E18": [ # 上信越自動車道 (藤岡JCT～上越JCT)
        "藤岡JCT", "藤岡", "吉井", "富岡", "下仁田", "碓氷軽井沢", "佐久平スマート", "佐久", 
        "小諸", "東部湯の丸", "上田菅平", "坂城", "千曲川さかき", "更埴JCT", "長野", "須坂長野東", 
        "小布施スマート", "信州中野", "信濃町", "妙高高原", "中郷", "新井スマート", "上越JCT"
    ],
    "E19": [ # 長野自動車道 (岡谷JCT以北～更埴JCT)
        "岡谷JCT", "塩尻", "塩尻北", "松本", "安曇野", "麻績", "筑北スマート", "姨捨スマート", "更埴", "更埴JCT"
    ],
    "C3": [ # 東京外環自動車道
        "大泉JCT", "和光", "和光北", "戸田西", "戸田東", "外環浦和", "川口西", "川口中央", "川口JCT", "草加", "外環三郷西", "三郷JCT"
    ],
    "C4": [ # 首都圏中央連絡自動車道 (圏央道・NEXCO東日本区間)
        "茅ヶ崎JCT", "海老名JCT", "厚木", "相模原", "八王子JCT", "青梅", "狭山日高", 
        "鶴ヶ島JCT", "桶川北本", "白岡菖蒲", "久喜白岡JCT", "五霞", "境古河", "つくば中央", "つくばJCT", "阿見東", "稲敷", "神崎", "大栄JCT"
    ],
    "E14": [ # 京葉道路・館山自動車道
        "一之江", "市川", "船橋", "武石", "千葉", "蘇我", "市原", "姉崎袖ケ浦", "木更津JCT", "君津", "富津竹岡"
    ],
    "E51": [ # 東関東自動車道
        "高谷JCT", "湾岸市川", "湾岸千葉", "宮野木JCT", "千葉北", "四街道", "佐倉", "酒々井", "富里", "成田", "新空港", "大栄JCT", "潮来"
    ],
}


ROAD_MAP = {
    # 北海道
    "道央自動車道": "E5",
    "札樽自動車道": "E5A",
    "道東自動車道": "E38",
    # 東北
    "東北自動車道": "E4",
    "八戸自動車道": "E4A",
    "秋田自動車道": "E46",
    "山形自動車道": "E48",
    "磐越自動車道": "E49",
    "常磐自動車道": "E6",
    # 関東・信越・富山
    "北陸自動車道": "E8",
    "関越自動車道": "E17",
    "上信越自動車道": "E18",
    "長野自動車道": "E19",
    "東京外環自動車道": "C3",
    "首都圏中央連絡自動車道": "C4",
    "京葉道路": "E14",
    "館山自動車道": "E14",
    "東関東自動車道": "E51",
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

        route_name = row[0]
        direction = row[1]
        section = row[2]
        reason = row[3]
        status = row[4]
        start_time = row[5]

        if route_name not in ROAD_MAP:
            continue

        if not section or not start_time:
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
    raw = load_json(STATE_FILE, {})

    if isinstance(raw, dict):
        return raw

    if isinstance(raw, list):
        state = {}
        for item in raw:
            if not isinstance(item, dict):
                continue
            closure_id = make_id(item)
            if closure_id:
                state[closure_id] = item
        print(f"旧形式のstate.jsonを検出しました。{len(state)}件を新形式へ変換します。")
        return state

    print("state.jsonの形式が不正なので、空の状態として開始します。")
    return {}


def load_facilities():
    return load_json(FACILITIES_FILE, [])


def load_positions():
    return load_json(POSITIONS_FILE, [])


def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


# =========================================================
# 名前処理
# =========================================================

def normalize_name(name):
    if not name:
        return ""
    name = name.strip()
    name = name.replace("　", "").replace(" ", "")
    name = name.replace("ＩＣ", "IC").replace("ＪＣＴ", "JCT")
    name = name.replace("ＰＡ", "PA").replace("ＳＡ", "SA")
    name = name.replace("スマートIC", "スマート").replace("スマートＩＣ", "スマート")
    return name


def canonical_ic_name(name):
    name = normalize_name(name)

    aliases = {
        "村田JCT": "村田JCT",
        "富谷JCT": "富谷JCT",
        "郡山JCT": "郡山JCT",
        "福島JCT": "福島JCT",
        "長岡JCT": "長岡JCT",
        "上越JCT": "上越JCT",
        "藤岡JCT": "藤岡JCT",
        "更埴JCT": "更埴JCT",
        "川口JCT": "川口JCT",
        "三郷JCT": "三郷JCT",
        
        "鏡石スマートIC": "鏡石スマート",
        "郡山中央スマートIC": "郡山中央スマート",
        "福島松川スマートIC": "福島松川スマート",
        "泉PAスマートIC": "泉PAスマート",
        "長者原スマートIC": "長者原スマート",
        "矢巾スマートIC": "矢巾スマート",
        "滝沢中央スマートIC": "滝沢中央スマート",
        "平泉スマートIC": "平泉スマート",
        "奥州スマートIC": "奥州スマート",
        "新鶴スマートIC": "新鶴スマート",
        "田村スマートIC": "田村スマート",
        "南相馬鹿島スマートIC": "南相馬鹿島スマート",
        "ならはスマートIC": "ならはスマート",
        "横手北スマートIC": "横手北スマート",
        "西仙北スマートIC": "西仙北スマート",
        "八戸西スマートIC": "八戸西スマート",
        "蓮田スマートIC": "蓮田スマート",
        "矢板北スマートIC": "矢板北スマート",
        "那須高原スマートIC": "那須高原スマート",
        "三本木スマートIC": "三本木スマート",
        "黒埼スマートIC": "黒埼スマート",
        "長岡北スマートIC": "長岡北スマート",
        "坂戸西スマートIC": "坂戸西スマート",
        "上里スマートIC": "上里スマート",
        "駒寄スマートIC": "駒寄スマート",
        "大和スマートIC": "大和スマート",
        "佐久平スマートIC": "佐久平スマート",
        "小布施スマートIC": "小布施スマート",
        "新井スマートIC": "新井スマート",
        "筑北スマートIC": "筑北スマート",
        "姨捨スマートIC": "姨捨スマート",
        "輪厚スマートIC": "輪厚スマート",
        "音江スマートIC": "音江スマート",
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
    return [canonical_ic_name(x) for x in parts if x.strip()]


def route_index(route_code, ic_name):
    ic_name = canonical_ic_name(ic_name)
    order = ROUTE_ORDERS.get(route_code, [])
    normalized_order = [canonical_ic_name(x) for x in order]

    try:
        return normalized_order.index(ic_name)
    except ValueError:
        return None


# =========================================================
# SAPA位置
# =========================================================

def facility_position(facility, positions):
    name = facility.get("name")

    # 特殊な位置補正（北上金ヶ崎PA等の境界例外処理）
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


def find_facilities_in_closure(route_code, section, facilities, positions):
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

        position = facility_position(facility, positions)
        if not position:
            continue

        before = route_index(route_code, position["before"])
        after = route_index(route_code, position["after"])

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
            return datetime.strptime(value, fmt).replace(tzinfo=JST)
        except ValueError:
            pass

    return None


def now_jst():
    return datetime.now(JST)


def duration_hours(start_time):
    start = parse_datetime(start_time)
    if start is None:
        return None
    seconds = (now_jst() - start).total_seconds()
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
        raise RuntimeError("facilities.json が読み込めません。")
    if not positions:
        raise RuntimeError("facility_positions.json が読み込めません。")

    print(f"対象SAPA数: {len(facilities)}")

    test_start = (now_jst() - timedelta(hours=7)).strftime("%Y/%m/%d %H:%M")

    test_cases = [
        {
            "name": "東北道・盛岡南～水沢",
            "route_code": "E4",
            "direction": "東京方面",
            "section": "盛岡南～水沢",
            "expected": ["矢巾PA", "紫波SA", "北上金ヶ崎PA", "前沢SA"],
        },
        {
            "name": "北陸道・朝日～糸魚川 (富山県内NEXCO東区間)",
            "route_code": "E8",
            "direction": "新潟方面",
            "section": "朝日～糸魚川",
            "expected": ["越中境PA"],
        },
        {
            "name": "関越道・高崎～赤城",
            "route_code": "E17",
            "direction": "新潟方面",
            "section": "高崎～赤城",
            "expected": ["赤城高原SA"],
        },
    ]

    passed = 0
    print()

    for i, case in enumerate(test_cases, start=1):
        print("-" * 60)
        print(f"TEST {i}: {case['name']}")
        print(f"区間: {case['section']}")

        matched = find_facilities_in_closure(
            case["route_code"],
            case["section"],
            facilities,
            positions,
        )

        matched_sorted = sorted(matched)
        expected_sorted = sorted(case["expected"])

        print(f"検出: {matched_sorted}")
        print(f"期待: {expected_sorted}")

        if matched_sorted != expected_sorted:
            print("❌ FAIL")
            raise RuntimeError(
                f"TEST {i} failed: expected={expected_sorted}, actual={matched_sorted}"
            )

        hours = duration_hours(test_start)
        report_candidate = hours is not None and hours >= 6 and len(matched) > 0

        if not report_candidate:
            print("❌ FAIL: 6時間以上の報告対象判定に失敗")
            raise RuntimeError(f"TEST {i} report_candidate failed")

        print(f"経過時間: {hours:.2f}時間")
        print("報告対象判定: True")
        print("✅ PASS")
        passed += 1

    print()
    print("=" * 60)
    print(f"TEST COMPLETE: {passed}/{len(test_cases)} PASS")
    print("=" * 60)
    print("SAPA判定・6時間判定ともに正常です。")
    print("state.json は変更していません。")
    print()


# =========================================================
# 通常監視
# =========================================================

def main():
    if os.environ.get("TEST_MODE", "").lower() == "true":
        run_test_mode()
        return

    print("=" * 60)
    print("SAPA通行止め監視くん")
    print("=" * 60)

    state = load_state()
    facilities = load_facilities()
    positions = load_positions()

    print(f"現在の状態件数: {len(state)}")
    print(f"対象SAPA数: {len(facilities)}")

    # -----------------------------------------
    # NEXCOデータ取得
    # -----------------------------------------
    html = fetch_page(URL)
    closures = parse_closures(html)

    print(f"現在の通行止め件数: {len(closures)}")
    current_ids = set()

    # -----------------------------------------
    # 現在の通行止めを処理
    # -----------------------------------------
    for closure in closures:
        route_code = closure["route_code"]

        matched = find_facilities_in_closure(
            route_code,
            closure["section"],
            facilities,
            positions,
        )

        hours = duration_hours(closure["start_time"])
        report_candidate = hours is not None and hours >= 6 and len(matched) > 0

        closure_id = make_id(closure)
        current_ids.add(closure_id)

        state[closure_id] = {
            **closure,
            "matched_facilities": matched,
            "duration_hours": hours,
            "report_candidate": report_candidate,
            "last_seen": now_jst().isoformat(),
        }

        print()
        print(f"通行止め: {closure['route_name']} {closure['section']}")
        print(f"理由: {closure['reason']}")
        print(f"開始: {closure['start_time']}")
        print(f"経過時間: {hours:.2f}時間" if hours is not None else "経過時間: 不明")
        print(f"該当SAPA: {matched}")
        print(f"報告候補: {report_candidate}")

    # =====================================================
    # 解除検知処理
    # =====================================================
    disappeared = []

    for closure_id, old in list(state.items()):
        if not isinstance(old, dict):
            continue

        if closure_id not in current_ids:
            if not old.get("release_detected"):
                old["release_detected"] = now_jst().isoformat()
                disappeared.append(old)

    if disappeared:
        print()
        print(f"解除を検知した通行止め: {len(disappeared)}件")
        for item in disappeared:
            print(f"- {item.get('route_name')} {item.get('section')}")
            print(f"  解除検知: {item.get('release_detected')}")

    save_state(state)
    print()
    print("状態を保存しました。")
    print()


# =========================================================
# 実行
# =========================================================

if __name__ == "__main__":
    main()
