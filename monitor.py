import os
import json
import csv
import urllib.request
import re
from datetime import datetime, timedelta, timezone

JST = timezone(timedelta(hours=9), 'JST')
SPREADSHEET_URL = "https://docs.google.com/spreadsheets/d/1SGD4RrHxX7BlbeeRIY1-bL0kC1TbUjqe50OHzBsYdlI/export?format=csv&gid=307854761"

HISTORY_FILE = "notify_history.json"
CLOSURES_FILE = "state.json"
FACILITIES_FILE = "facilities.json"

TARGET_MUNICIPALITIES = [
    "砂川市", "岩見沢市", "江別市", "北広島市", "苫小牧市", "伊達市", "札幌市手稲区",
    "平川市", "鹿角市", "軽米町", "大仙市", "八幡平市", "滝沢市", "矢巾町", "紫波町", "北上市", "西和賀町", "奥州市",
    "栗原市", "大崎市", "大和町", "村田町", "川崎町", "寒河江市", "鶴岡市",
    "国見町", "福島市", "本宮市", "郡山市", "鏡石町", "田村市", "磐梯町", "南相馬市", "いわき市",
    "北茨城市", "日立市", "東海村", "笠間市", "小美玉市", "かすみがうら市", "つくば市", "守谷市", "坂東市",
    "那須塩原市", "那須町", "宇都宮市", "矢板市", "栃木市", "佐野市",
    "羽生市", "蓮田市", "三郷市", "和光市", "三芳町", "東松山市", "嵐山町", "寄居町", "深谷市", "上里町", "狭山市", "久喜市",
    "吉岡町", "昭和村", "みなかみ町", "安中市", "甘楽町", "太田市", "伊勢崎市",
    "横浜市港北区", "横浜市保土ケ谷区", "横浜市神奈川区", "横浜市戸塚区", "横須賀市",
    "市川市", "千葉市花見川区", "千葉市若葉区", "市原市", "千葉市美浜区", "酒々井町", "成田市",
    "阿賀町", "南魚沼市", "小千谷市", "長岡市", "妙高市", "糸魚川市", "上越市", "柏崎市", "三条市", "新潟市西区",
    "東御市", "佐久市", "坂城町", "長野市", "小布施町", "千曲市", "朝日町"
]

SPECIAL_PAS = {
    "寄居PA": {"up": "寄居町", "down": "深谷市"},
    "保土ヶ谷PA": {"up": "横浜市神奈川区", "down": "横浜市保土ケ谷区"}
}

def get_branches_for_facility(fac_name, prefecture):
    """施設名や都道府県から担当拠点を判定する（例外ルール対応）"""
    # 1. 特定PA/SAの例外ルール
    if fac_name == "坂東PA": return ["関東西支店"]
    if fac_name == "横川SA": return ["長野支部"]
    if fac_name == "谷川岳PA": return ["新潟支店"]
    
    # 2. 都道府県ベースの基本ルール
    if prefecture == "北海道": return ["札幌支店"]
    if prefecture in ["宮城県", "福島県", "山形県"]: return ["東北支店"]
    if prefecture in ["青森県", "岩手県", "秋田県"]: return ["盛岡支部"]
    if prefecture in ["新潟県", "富山県"]: return ["新潟支店"]
    if prefecture == "栃木県": return ["宇都宮支部"]
    if prefecture == "長野県": return ["長野支部"]
    if prefecture in ["群馬県", "埼玉県"]: return ["関東西支店"]
    if prefecture in ["茨城県", "千葉県", "東京都", "神奈川県"]: return ["関東東支店"]
    
    return []

def load_json(filename):
    if os.path.exists(filename):
        with open(filename, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def load_state():
    state = load_json(HISTORY_FILE)
    if not isinstance(state, dict):
        return {"notified_closures": [], "notified_earthquakes": []}
    return state.get("notified_closures") and state or {"notified_closures": [], "notified_earthquakes": []}

def save_state(state):
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)

def send_teams_webhook(webhook_url, title, text):
    if not webhook_url: return
    payload = {"title": title, "text": text}
    req = urllib.request.Request(webhook_url, data=json.dumps(payload).encode("utf-8"), headers={"Content-Type": "application/json"})
    try: urllib.request.urlopen(req)
    except Exception as e: print(f"Teams送信エラー: {e}")

def scale_to_shindo(scale):
    mapping = {10: "1", 20: "2", 30: "3", 40: "4", 45: "5弱", 50: "5強", 55: "6弱", 60: "6強", 70: "7"}
    return mapping.get(scale, "不明")

def parse_datetime(value):
    if not value: return None
    value = value.strip()
    try:
        dt = datetime.fromisoformat(value)
        if dt.tzinfo is None: dt = dt.replace(tzinfo=JST)
        return dt.astimezone(JST)
    except ValueError: pass
    formats = ["%Y/%m/%d %H:%M", "%Y/%m/%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S"]
    for fmt in formats:
        try: return datetime.strptime(value, fmt).replace(tzinfo=JST)
        except ValueError: continue
    return None

def get_config_from_spreadsheet():
    config = []
    try:
        req = urllib.request.Request(SPREADSHEET_URL)
        with urllib.request.urlopen(req) as res:
            content = res.read().decode('utf-8').splitlines()
            reader = csv.DictReader(content)
            for row in reader:
                config.append({
                    "branch": re.sub(r'^\d+\.\s*', '', row.get("担当拠点", "")).strip(),
                    "time": row.get("送信時間", "").strip(),
                    "webhook": row.get("Teams Webhook URL", "").strip()
                })
    except Exception as e: print(f"スプレッドシート取得エラー: {e}")
    return config

def check_earthquakes(state, config):
    try:
        url = "https://api.p2pquake.net/v2/history?codes=551&limit=5"
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req) as res:
            data = json.loads(res.read().decode('utf-8'))
            for quake in data:
                quake_id = quake.get("id")
                if quake_id in state["notified_earthquakes"]: continue
                
                earthquake = quake.get("earthquake", {})
                if earthquake.get("maxScale", -1) < 40: continue
                
                hit_muni = {pt["addr"]: pt["scale"] for pt in quake.get("points", []) 
                            if pt.get("scale", -1) >= 40 and pt.get("addr") in TARGET_MUNICIPALITIES}
                
                hit_areas = []
                for pa_name, dirs in SPECIAL_PAS.items():
                    up_muni = dirs["up"]
                    down_muni = dirs["down"]
                    if up_muni in hit_muni and down_muni in hit_muni:
                        max_scale = max(hit_muni[up_muni], hit_muni[down_muni])
                        hit_areas.append(f"・{pa_name} (震度{scale_to_shindo(max_scale)})")
                        del hit_muni[up_muni], hit_muni[down_muni]
                    elif up_muni in hit_muni:
                        hit_areas.append(f"・{pa_name}(上り線) (震度{scale_to_shindo(hit_muni[up_muni])})\n　※下り線は市町村が異なるほか、震度が3以下であったため対象外")
                        del hit_muni[up_muni]
                    elif down_muni in hit_muni:
                        hit_areas.append(f"・{pa_name}(下り線) (震度{scale_to_shindo(hit_muni[down_muni])})\n　※上り線は市町村が異なるほか、震度が3以下であったため対象外")
                        del hit_muni[down_muni]
                
                for muni, scale in hit_muni.items():
                    hit_areas.append(f"・{muni} (震度{scale_to_shindo(scale)})")
                
                if hit_areas:
                    title = "🚨 【地震速報】有人拠点で震度4以上を観測"
                    text = (f"**発生時刻:** {earthquake.get('time', '不明')}\n\n"
                            f"**震源地:** {earthquake.get('hypocenter', {}).get('name', '不明')} "
                            f"(M{earthquake.get('hypocenter', {}).get('magnitude', '不明')})\n\n"
                            f"**対象エリアの観測震度:**\n" + "\n".join(hit_areas) + "\n\n※自動配信")
                    for c in config: send_teams_webhook(c["webhook"], title, text)
                
                state["notified_earthquakes"].append(quake_id)
            state["notified_earthquakes"] = state["notified_earthquakes"][-100:]
    except Exception as e: print(f"地震取得エラー: {e}")

def fetch_road_closures():
    state_data = load_json(CLOSURES_FILE)
    facilities = load_json(FACILITIES_FILE)
    
    if not state_data or not facilities: return []
    
    state_items = state_data if isinstance(state_data, list) else state_data.get("closures", [])
    closures = []
    
    for item in state_items:
        matched_facility_names = item.get("matched_facilities", [])
        if not matched_facility_names: continue

        matched_fac_details = [fac for fac in facilities if fac.get("staffed") and fac.get("name") in matched_facility_names]
        
        affected_branches = set()
        for fac in matched_fac_details:
            affected_branches.update(get_branches_for_facility(fac.get("name"), fac.get("prefecture")))
            
        if not affected_branches: continue

        start = parse_datetime(item.get("start_time") or item.get("closure_start"))
        release = parse_datetime(item.get("release_detected"))
        if not start: continue

        status = "resolved" if release else "closed"
        c_id = item.get("id") or item.get("closure_id") or f"{item.get('route')}_{item.get('section')}_{start.timestamp()}"

        for branch in affected_branches:
            fac_names = []
            for fac in matched_fac_details:
                if branch in get_branches_for_facility(fac.get("name"), fac.get("prefecture")):
                    fac_names.append(fac.get("name"))
            
            if not fac_names: continue
            
            closures.append({
                "id": str(c_id),
                "start": start,
                "end": release,
                "status": status,
                "branch": branch,
                "route": item.get("route") or item.get("road") or "不明",
                "direction": item.get("direction") or "不明",
                "section": item.get("section") or item.get("区間") or "不明",
                "reason": item.get("reason") or item.get("cause") or item.get("理由") or "不明",
                "facilities": fac_names
            })
    return closures

def check_road_closures(state, config):
    now = datetime.now(JST)
    current_time_str = now.strftime("%H:%M")
    closures = fetch_road_closures()
    
    for closure in closures:
        c_id = closure["id"]
        start_time = closure["start"]
        end_time = closure["end"]
        status = closure["status"]
        branch_name = closure["branch"]
        
        calc_end = end_time if end_time else now
        duration_hours = (calc_end - start_time).total_seconds() / 3600
        
        if duration_hours < 6: continue
            
        target_config = next((c for c in config if c["branch"] in [branch_name, "全拠点"]), None)
        if not target_config: continue
            
        webhook_url = target_config["webhook"]
        scheduled_time = target_config["time"]
        
        should_notify = False
        report_type = ""
        notified_key_morning = f"{c_id}_{branch_name}_morning"
        notified_key_instant = f"{c_id}_{branch_name}_instant"
        
        if current_time_str == scheduled_time and notified_key_morning not in state["notified_closures"]:
            if status == "closed" or (status == "resolved" and end_time.time() <= datetime.strptime(scheduled_time, "%H:%M").time()):
                should_notify = True
                report_type = "🌅 【朝の定例報告】本社報告対象"
                state["notified_closures"].append(notified_key_morning)
        
        if notified_key_instant not in state["notified_closures"]:
            if status == "resolved":
                should_notify = True
                report_type = "✅ 【即時報告】通行止め解除"
                state["notified_closures"].append(notified_key_instant)
            elif status == "closed" and 9 <= now.hour < 17 and duration_hours >= 6:
                should_notify = True
                report_type = "⚠️ 【即時報告】長期間通行止め（6時間経過）"
                state["notified_closures"].append(notified_key_instant)

        if should_notify:
            text = (f"**対象拠点:** {branch_name}\n\n"
                    f"**路線:** {closure['route']} ({closure['direction']})\n\n"
                    f"**区間:** {closure['section']}\n\n"
                    f"**原因:** {closure['reason']}\n\n"
                    f"**対象SAPA:** {'、'.join(closure['facilities'])}\n\n"
                    f"**開始:** {start_time.strftime('%Y/%m/%d %H:%M')}\n\n"
                    f"**状態:** {'解除済' if status == 'resolved' else '継続中'}")
            if end_time:
                text += f"\n\n**解除:** {end_time.strftime('%Y/%m/%d %H:%M')}"
            
            send_teams_webhook(webhook_url, report_type, text)

def main():
    state = load_state()
    config = get_config_from_spreadsheet()
    if config:
        check_earthquakes(state, config)
        check_road_closures(state, config)
        save_state(state)
    else:
        print("設定が存在しないか、スプレッドシートが未設定です。")

if __name__ == "__main__":
    main()
