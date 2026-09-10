from datetime import datetime, timezone, timedelta

import morning_report


JST = timezone(timedelta(hours=9))


# ============================================================
# テスト用の現在時刻
#
# 2026/09/09 01:00 に通行止め開始
# 2026/09/09 07:00 に解除
#
# → 6時間
# → 08:00までに解除
# → 本社報告対象
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
# テスト用 state
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
# テスト用 facilities
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
# morning_report.py の現在時刻を
# テスト時刻に差し替える
# ============================================================

class FakeDateTime(datetime):

    @classmethod
    def now(cls, tz=None):
        return FAKE_NOW


morning_report.datetime = FakeDateTime


# ============================================================
# state.json / facilities.json
# だけテストデータに差し替える
#
# settings.json は実際のファイルを読む！
# ============================================================

_original_load_json = morning_report.load_json


def test_load_json(filename):

    if filename == "state.json":
        return TEST_STATE

    if filename == "facilities.json":
        return TEST_FACILITIES

    # settings.json は実際の settings.json を読む
    return _original_load_json(filename)


morning_report.load_json = test_load_json


# ============================================================
# ntfy送信
# 実際にiPhoneへ通知する
# ============================================================

_original_send_ntfy = morning_report.send_ntfy


def test_send_ntfy(message):

    print()
    print("=" * 60)
    print("TEST通知を送信します")
    print("=" * 60)

    print(message)

    print("=" * 60)

    _original_send_ntfy(message)

    print("TEST通知送信成功")


morning_report.send_ntfy = test_send_ntfy


# ============================================================
# 実行
# ============================================================

print("=" * 60)
print("夜間6時間以上 → 朝までに解除 テスト")
print("=" * 60)

print()
print("テスト時刻：2026/09/09 08:00")
print("通行止開始：2026/09/09 01:00")
print("通行止解除：2026/09/09 07:00")
print("経過時間：6時間")
print()
print("settings.json の実際の設定を使用します")
print()

morning_report.main()

print()
print("=" * 60)
print("テスト終了")
print("=" * 60)
