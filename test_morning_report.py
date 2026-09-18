from datetime import datetime, timezone, timedelta
import morning_report

JST = timezone(timedelta(hours=9))

# ============================================================
# テスト用の現在時刻
# ============================================================
FAKE_NOW = datetime(
    2026,
    9,
    9,
    8,
    0,
    0,
    tzinfo=JST,
)

TEST_START = datetime(
    2026,
    9,
    9,
    1,
    0,
    0,
    tzinfo=JST,
)

TEST_RELEASE = datetime(
    2026,
    9,
    9,
    7,
    0,
    0,
    tzinfo=JST,
)

# ============================================================
# テスト用 state (通行止めデータ)
# ============================================================
TEST_STATE = {
    "closures": [
        {
            "id": "TEST_OVERNIGHT_001",
            "route": "東北自動車道",
            "direction": "上り",
            "section": "盛岡南～水沢",
            "reason": "事故",
            "start_time": TEST_START.isoformat(),
            "release_detected": TEST_RELEASE.isoformat(),
            "matched_facilities": [
                "矢巾PA",
                "紫波SA",
                "北上金ヶ崎PA",
                "前沢SA",
            ],
            "report_candidate": True,
        }
    ]
}

# ============================================================
# テスト用 facilities (SAPAデータ)
# ============================================================
TEST_FACILITIES = [
    {
        "name": "矢巾PA",
        "road": "E4",
        "prefecture": "岩手県",
        "staffed": True,
    },
    {
        "name": "紫波SA",
        "road": "E4",
        "prefecture": "岩手県",
        "staffed": True,
    },
    {
        "name": "北上金ヶ崎PA",
        "road": "E4",
        "prefecture": "岩手県",
        "staffed": True,
    },
    {
        "name": "前沢SA",
        "road": "E4",
        "prefecture": "岩手県",
        "staffed": True,
    },
]

# ============================================================
# morning_report.py の現在時刻をテスト時刻に差し替える
# ============================================================
class FakeDateTime(datetime):
    @classmethod
    def now(cls, tz=None):
        return FAKE_NOW

morning_report.datetime = FakeDateTime

# ============================================================
# state.json / facilities.json をテストデータに差し替える
# （スプレッドシートの取得処理やsettings.jsonはそのまま本番の挙動を確認）
# ============================================================
_original_load_json = morning_report.load_json

def test_load_json(filename):
    if filename == "state.json":
        return TEST_STATE
    if filename == "facilities.json":
        return TEST_FACILITIES
    return _original_load_json(filename)

morning_report.load_json = test_load_json

# ============================================================
# ntfy送信（3つの引数 `topic, message, has_candidates` に対応）
# ============================================================
_original_send_ntfy = morning_report.send_ntfy

def test_send_ntfy(topic, message, has_candidates):
    print()
    print("=" * 60)
    print(f"TEST通知を送信します (トピック: {topic})")
    print("=" * 60)
    print(message)
    print("=" * 60)
    
    # 実際にntfyへPOST送信（テスト環境からもスマホ等へ通知が飛ぶか確認）
    _original_send_ntfy(topic, message, has_candidates)
    
    print("TEST通知送信成功")

morning_report.send_ntfy = test_send_ntfy

# ============================================================
# 実行
# ============================================================
print("=" * 60)
print("夜間6時間以上 → 朝までに解除 テスト (スプレッドシート連携版)")
print("=" * 60)
print()
print("テスト時刻：2026/09/09 08:00")
print("通行止開始：2026/09/09 01:00")
print("通行止解除：2026/09/09 07:00")
print("経過時間：6時間")
print()

morning_report.main()

print()
print("=" * 60)
print("テスト終了")
print("=" * 60)
