import os
import json
import csv
import urllib.request
from datetime import datetime, timedelta, timezone

JST = timezone(timedelta(hours=9), 'JST')
# 実際のスプレッドシートURLを設定してください
# 変更前
SPREADSHEET_URL = "YOUR_SPREADSHEET_URL_HERE"

# 変更後（↓これをコピペしてください）
SPREADSHEET_URL = "https://docs.google.com/spreadsheets/d/1SGD4RrHxX7BlbeeRIY1-bL0kC1TbUjqe50OHzBsYdlI/export?format=csv&gid=307854761"

STATE_FILE = "state.json"

# 有人拠点が存在する市町村のリスト（全件精査済み・管轄外除外済み・文字化け修正済み）
TARGET_MUNICIPALITIES = [
    # 北海道・東北
    "砂川市", "岩見沢市", "江別市", "北広島市", "苫小牧市", "伊達市", "札幌市手稲区",
    "平川市", "鹿角市", "軽米町", "大仙市", "八幡平市", "滝沢市", "矢巾町", "紫波町", "北上市", "西和賀町", "奥州市",
    "栗原市", "大崎市", "大和町", "村田町", "川崎町", "寒河江市", "鶴岡市",
    "国見町", "福島市", "本宮市", "郡山市", "鏡石町", "田村市", "磐梯町", "南相馬市", "いわき市",
    # 関東
    "北茨城市", "日立市", "東海村", "笠間市", "小美玉市", "かすみがうら市", "つくば市", "守谷市", "坂東市",
    "那須塩原市", "那須町", "宇都宮市", "矢板市", "栃木市", "佐野市",
    "羽生市", "蓮田市", "三郷市", "和光市", "三芳町", "東松山市", "嵐山町", "寄居町", "深谷市", "上里町", "狭山市", "久喜市",
    "吉岡町", "昭和村", "みなかみ町", "安中市", "甘楽町", "太田市", "伊勢崎市",
    "横浜市港北区", "横浜市保土ケ谷区", "横浜市神奈川区", "横浜市戸塚区", "横須賀市",
    "市川市", "千葉市花見川区", "千葉市若葉区", "市原市", "千葉市美浜区", "酒々井町", "成田市",
    # 信越・北陸
    "阿賀町", "南魚沼市", "小千谷市", "長岡市", "妙高市", "糸魚川市", "上越市", "柏崎市", "三条市", "新潟市西区",
    "東御市", "佐久市", "坂城町", "長野市", "小布施町", "千曲市", "朝日町"
]

SPECIAL_PAS = {
    "寄居PA": {"up": "寄居町", "down": "深谷市"},
    "保土ヶ谷PA": {"up": "横浜市神奈川区", "down": "横浜市保土ケ谷区"}
}

def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"notified_closures": [], "notified_earthquakes": []}

def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)

def send_teams_webhook(webhook_url, title, text):
    if not webhook_url: return
    payload = {"title": title, "text": text}
    req = urllib.request.Request(webhook_url, data=json.dumps(payload).encode("utf-8"), headers={"Content-Type": "application/json"})
    try: 
        urllib.request.urlopen(req)
        print(f"Teams送信完了: {title}")
    except Exception as e: 
        print(f"Teams送信エラー: {e}")

def scale_to_shindo(scale):
    mapping = {10: "1", 20: "2", 30: "3", 40: "4", 45: "5弱", 50: "5強", 55: "6弱", 60: "6強", 70: "7"}
    return mapping.get(scale, "不明")

def get_config_from_spreadsheet():
    """スプレッドシート(CSV形式)からWebhookと時間設定を取得"""
    config = []
    if SPREADSHEET_URL == "YOUR_SPREADSHEET_URL_HERE":
        return config
        
    try:
        req = urllib.request.Request(SPREADSHEET_URL)
        with urllib.request.urlopen(req) as res:
            content = res.read().decode('utf-8').splitlines()
            reader = csv.DictReader(content)
            for row in reader:
                config.append({
                    "branch": row.get("担当拠点", ""),
                    "time": row.get("送信時間", ""),
                    "webhook": row.get("Teams Webhook URL", "")
                })
    except Exception as e:
        print(f"スプレッドシート取得エラー: {e}")
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
                    has_up = up_muni in hit_muni
                    has_down = down_muni in hit_muni
                    
                    if has_up and has_down:
                        max_scale = max(hit_muni[up_muni], hit_muni[down_muni])
                        hit_areas.append(f"・{pa_name} (震度{scale_to_shindo(max_scale)})")
                        del hit_muni[up_muni]
                        del hit_muni[down_muni]
                    elif has_up:
                        hit_areas.append(f"・{pa_name}(上り線) (震度{scale_to_shindo(hit_muni[up_muni])})\n　※下り線は市町村が異なるほか、震度が3以下であったため対象外")
                        del hit_muni[up_muni]
                    elif has_down:
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
    except Exception as e:
        print(f"地震取得エラー: {e}")

def fetch_road_closures():
    """
    通行止め情報（JSON等）を取得し、共通フォーマットの辞書リストで返す。
    ※ 実際の運用環境のURL・仕様に合わせて実装してください。
    """
    # 戻り値の形式例:
    # return [
    #     {
    #         "id": "event_001",
    #         "start": datetime(2023, 10, 1, 10, 0, tzinfo=JST),
    #         "end": None, # 未解除の場合はNone
    #         "status": "closed", # 継続中は"closed"、解除済みは"resolved"
    #         "branch": "盛岡支部"
    #     }
    # ]
    return []

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
        
        # 条件：6時間以上の通行止めが対象
        if duration_hours < 6:
            continue
            
        target_config = next((c for c in config if c["branch"] in [branch_name, "全拠点"]), None)
        if not target_config:
            continue
            
        webhook_url = target_config["webhook"]
        scheduled_time = target_config["time"] # "7:30" or "7:45"
        
        should_notify = False
        report_type = ""
        
        notified_key_morning = f"{c_id}_morning"
        notified_key_instant = f"{c_id}_instant"
        
        # 1. 朝の定例報告
        if current_time_str == scheduled_time and notified_key_morning not in state["notified_closures"]:
            # 朝までに解除、または継続中のもの
            if status == "closed" or (status == "resolved" and end_time.time() <= datetime.strptime(scheduled_time, "%H:%M").time()):
                should_notify = True
                report_type = "🌅 【朝の定例報告】通行止め情報"
                state["notified_closures"].append(notified_key_morning)
        
        # 2. 即時報告（10分・5分間隔での検知）
        if notified_key_instant not in state["notified_closures"]:
            if status == "resolved":
                # 解除時は即時報告（夜間〜昼間17:30まで、通知後〜9:00など）
                should_notify = True
                report_type = "✅ 【即時報告】通行止め解除"
                state["notified_closures"].append(notified_key_instant)
            elif status == "closed" and 9 <= now.hour < 17 and duration_hours >= 6:
                # 昼間（9:00〜17:30）に発生・継続して6時間を経過した瞬間
                should_notify = True
                report_type = "⚠️ 【即時報告】長期間通行止め（6時間経過）"
                state["notified_closures"].append(notified_key_instant)

        if should_notify:
            text = f"**担当拠点:** {branch_name}\n\n**開始:** {start_time.strftime('%Y/%m/%d %H:%M')}\n\n**状態:** {'解除済' if status == 'resolved' else '継続中'}"
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
        print("設定が存在しないか、スプレッドシートURLが未設定です。")

if __name__ == "__main__":
    main()
