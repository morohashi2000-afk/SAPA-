import json
import os
import urllib.request
import csv
import io
import re
from datetime import datetime, timedelta, timezone

JST = timezone(timedelta(hours=9))

# スプレッドシートのCSV公開URL
SHEET_ID = "1SGD4RrHxX7BlbeeRIY1-bL0kC1TbUjqe50OHzBsYdlI"
CSV_URL = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/export?format=csv&gid=307854761"

# 拠点のプルダウンと対象都道府県の紐付け
BRANCH_PREFECTURES = {
    "札幌支店": ["北海道"],
    "東北支店": ["宮城県", "山形県", "福島県"],
    "盛岡支部": ["青森県", "岩手県", "秋田県"],
    "新潟支店": ["新潟県", "長野県"],
    "関東西支店": ["群馬県", "埼玉県", "東京都", "神奈川県"],
    "宇都宮支部": ["栃木県"], # 茨城県も含む場合は追加してください
    "長野支部": ["長野県"],
    "関東東支店": ["茨城県", "千葉県"],
    "全拠点": [
        "北海道", "青森県", "岩手県", "宮城県", "秋田県", "山形県", "福島県",
        "茨城県", "栃木県", "群馬県", "埼玉県", "千葉県", "東京都", "神奈川県",
        "新潟県", "長野県"
    ]
}

def clean_text(text):
    """フォームの選択肢にある '1. ' などのプレフィックスを取り除く"""
    return re.sub(r'^\d+\.\s*', '', text).strip()

def now_jst():
    return datetime.now(JST)

def load_json(filename):
    with open(filename, "r", encoding="utf-8") as f:
        return json.load(f)

def get_subscribers():
    """スプレッドシートから配信先リストを取得する"""
    subscribers = []
    try:
        req = urllib.request.Request(CSV_URL, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=15) as response:
            csv_data = response.read().decode("utf-8")

        reader = csv.reader(io.StringIO(csv_data))
        next(reader, None)  # 1行目（ヘッダー）をスキップ

        for row in reader:
            # フォームの列順: [0:タイムスタンプ, 1:拠点, 2:時間, 3:トピック]
            if len(row) >= 4:
                subscribers.append({
                    "branch": clean_text(row[1]),
                    "time": clean_text(row[2]),
                    "topic": clean_text(row[3]),
                })
        return subscribers
    except Exception as e:
        print(f"スプレッドシートの読み込みエラー: {e}")
        return []

def parse_datetime(value):
    if not value:
        return None
    value = value.strip()
    try:
        dt = datetime.fromisoformat(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=JST)
        return dt.astimezone(JST)
    except ValueError:
        pass
    formats = ["%Y/%m/%d %H:%M", "%Y/%m/%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S"]
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

def facility_matches_prefecture(facility, target_prefectures):
    return (
        facility.get("staffed") is True
        and facility.get("prefecture") in target_prefectures
    )

def send_ntfy(topic, message, has_candidates):
    if not topic:
        return
    url = f"https://ntfy.sh/{topic}"
    title = "(報告対象アリ) 本社報告確認" if has_candidates else "(報告対象ナシ) 本社報告確認"
    payload = {
        "topic": topic,
        "title": title,
        "message": message,
        "priority": 4 if has_candidates else 3,
        "tags": ["highway"],
    }
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json; charset=utf-8"}, method="POST"
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            pass
    except Exception as e:
        print(f"ntfy通知失敗 ({topic}): {e}")

def main():
    now = now_jst()
    subscribers = get_subscribers()

    if not subscribers:
        print("有効な購読者がいません。")
        return

    state = load_json("state.json")
    facilities = load_json("facilities.json")

    if isinstance(state, list):
        state_items = state
    elif isinstance(state, dict):
        state_items = state.get("closures", [])
    else:
        raise RuntimeError("state.json の形式が不正です。")

    for sub in subscribers:
        target_time_str = sub.get("time", "")
        if not target_time_str:
            continue
        
        try:
            t_hour, t_min = map(int, target_time_str.split(":"))
        except ValueError:
            continue
        
                # 手動実行（workflow_dispatch）のときは時間のズレを無視して強制実行する
        is_manual_run = os.environ.get("GITHUB_EVENT_NAME") == "workflow_dispatch"
        
        target_minutes = t_hour * 60 + t_min
        now_minutes = now.hour * 60 + now.minute
        if not is_manual_run and not (0 <= (now_minutes - target_minutes) <= 15):
            print(f"スキップ: {sub['branch']} ({sub['topic']}) (希望 {target_time_str} / 現在 {now.strftime('%H:%M')})")
            continue


        target_prefectures = BRANCH_PREFECTURES.get(sub["branch"], [])
        if not target_prefectures:
            print(f"未定義の拠点: {sub['branch']}")
            continue

        # 判定基準時間をセット（前日17:30 ～ 各拠点の通知希望時間）
        report_end = now.replace(hour=t_hour, minute=t_min, second=0, microsecond=0)
        report_start = report_end.replace(hour=17, minute=30) - timedelta(days=1)

        candidates = []
        for item in state_items:
            matched_facilities = []
            for facility in facilities:
                if facility_matches_prefecture(facility, target_prefectures):
                    if facility.get("name") in item.get("matched_facilities", []):
                        matched_facilities.append(facility)

            if not matched_facilities:
                continue

            start = parse_datetime(item.get("start_time") or item.get("closure_start"))
            if not start:
                continue

            release = parse_datetime(item.get("release_detected"))

            if release is None:
                hours = duration_hours(start, now)
                if hours is not None and hours >= 6:
                    candidates.append({"item": item, "facilities": matched_facilities, "start": start, "release": None, "hours": hours})
                continue

            if report_start <= release <= report_end:
                hours = duration_hours(start, release)
                if hours is not None and hours >= 6:
                    candidates.append({"item": item, "facilities": matched_facilities, "start": start, "release": release, "hours": hours})

        unique = {}
        for candidate in candidates:
            item = candidate["item"]
            key = item.get("id") or item.get("closure_id") or (item.get("route"), item.get("section"), item.get("start_time"))
            unique[key] = candidate
        candidates = list(unique.values())

        has_candidates = len(candidates) > 0
        header_tag = "(報告対象アリ)" if has_candidates else "(報告対象ナシ)"
        lines = [
            f"{header_tag} 【{target_time_str} 本社報告確認】",
            f"対象拠点：{sub['branch']}",
            "",
        ]

        if not candidates:
            lines.append("本社報告対象の通行止めはありません。")
        else:
            lines.append(f"本社報告対象：{len(candidates)}件\n")
            for i, candidate in enumerate(candidates, 1):
                item = candidate["item"]
                route = item.get("route") or item.get("road") or "不明"
                direction = item.get("direction") or "不明"
                section = item.get("section") or item.get("区間") or "不明"
                reason = item.get("reason") or item.get("cause") or item.get("理由") or "不明"
                
                facilities_matched = candidate["facilities"]
                prefectures = sorted({f.get("prefecture") for f in facilities_matched if f.get("prefecture")})
                facility_names = [f.get("name") for f in facilities_matched]

                lines.extend([
                    f"【{i}】",
                    f"都道府県：{'、'.join(prefectures)}",
                    f"路線：{route}",
                    f"方向：{direction}",
                    f"区間：{section}",
                    f"通行止開始：{format_dt(candidate['start'])}",
                    f"解除確認：{format_dt(candidate['release']) if candidate['release'] else '未解除'}",
                    f"通行止め時間：{format_duration(candidate['hours'])}",
                    f"原因：{reason}",
                    f"対象SAPA：{'、'.join(facility_names)}",
                    "→ 本社報告対象",
                    ""
                ])

        message = "\n".join(lines)
        print(f"送信中: {sub['branch']} -> トピック: {sub['topic']}")
        send_ntfy(sub["topic"], message, has_candidates)

if __name__ == "__main__":
    main()
