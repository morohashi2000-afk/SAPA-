import json
import os
import urllib.request
from datetime import datetime, timezone, timedelta


STATE_FILE = "state.json"
FACILITIES_FILE = "facilities.json"

JST = timezone(timedelta(hours=9))

# =========================================================
# 通知対象にする都道府県
# =========================================================

TARGET_PREFECTURES = {
    "青森県",
    "岩手県",
    "秋田県",
    # "宮城県",
    # "山形県",
    # "福島県",
}


# =========================================================
# JSON
# =========================================================

def load_json(filename, default):
    if not os.path.exists(filename):
        return default

    try:
        with open(
            filename,
            "r",
            encoding="utf-8",
        ) as f:
            return json.load(f)

    except Exception as e:
        print(
            f"{filename} の読み込みに失敗しました: {e}"
        )
        return default


# =========================================================
# 通知
# =========================================================

def send_ntfy(message):
    topic = os.environ.get(
        "NTFY_TOPIC",
        "",
    )

    if not topic:
        raise RuntimeError(
            "NTFY_TOPIC が設定されていません。"
        )

    url = (
        f"https://ntfy.sh/{topic}"
    )

    req = urllib.request.Request(
        url,
        data=message.encode("utf-8"),
        headers={
            "Title": "本社報告確認（08:00）",
            "Priority": "high",
            "Tags": "highway",
            "Content-Type": "text/plain; charset=utf-8",
        },
        method="POST",
    )

    with urllib.request.urlopen(
        req,
        timeout=30,
    ) as response:

        if response.status < 200 or response.status >= 300:
            raise RuntimeError(
                f"ntfy通知失敗: HTTP {response.status}"
            )


# =========================================================
# メイン
# =========================================================

def main():

    print("=" * 60)
    print("SAPA通行止め監視くん 08:00 REPORT")
    print("=" * 60)

    state = load_json(
        STATE_FILE,
        {},
    )

    facilities = load_json(
        FACILITIES_FILE,
        [],
    )

    if not isinstance(state, dict):
        raise RuntimeError(
            "state.json が辞書形式ではありません。"
        )

    if not isinstance(facilities, list):
        raise RuntimeError(
            "facilities.json がリスト形式ではありません。"
        )

    # =====================================================
    # SAPA名 → 都道府県
    # =====================================================

    facility_prefecture = {}

    for facility in facilities:

        if not isinstance(
            facility,
            dict,
        ):
            continue

        name = facility.get(
            "name",
            "",
        )

        prefecture = facility.get(
            "prefecture",
            "",
        )

        if name and prefecture:
            facility_prefecture[name] = prefecture

    # =====================================================
    # 現在も継続している報告候補を抽出
    # =====================================================

    candidates = []

    for closure_id, item in state.items():

        if not isinstance(
            item,
            dict,
        ):
            continue

        # 解除済みは対象外
        if item.get(
            "release_detected"
        ):
            continue

        # 6時間以上 + SAPA該当
        if not item.get(
            "report_candidate",
            False,
        ):
            continue

        matched = item.get(
            "matched_facilities",
            [],
        )

        if not matched:
            continue

        # =================================================
        # 該当SAPAの都道府県を調べる
        # =================================================

        matched_target_facilities = []

        for sapa in matched:

            prefecture = facility_prefecture.get(
                sapa
            )

            if prefecture in TARGET_PREFECTURES:
                matched_target_facilities.append(
                    sapa
                )

        # 選択県に該当するSAPAがなければ通知対象外
        if not matched_target_facilities:
            continue

        item_copy = dict(item)

        item_copy[
            "notification_facilities"
        ] = matched_target_facilities

        candidates.append(
            item_copy
        )

    # =====================================================
    # 通知本文
    # =====================================================

    if not candidates:

        message = (
            "本社報告確認（08:00）\n"
            "\n"
            "本日、報告対象となる通行止めはありません。"
        )

    else:

        lines = [
            "本社報告確認（08:00）",
            "",
            f"報告対象：{len(candidates)}件",
            "",
        ]

        for i, item in enumerate(
            candidates,
            start=1,
        ):

            route_name = item.get(
                "route_name",
                "不明",
            )

            direction = item.get(
                "direction",
                "不明",
            )

            section = item.get(
                "section",
                "不明",
            )

            start_time = item.get(
                "start_time",
                "不明",
            )

            reason = item.get(
                "reason",
                "不明",
            )

            duration = item.get(
                "duration_hours",
                None,
            )

            if duration is not None:
                duration_text = (
                    f"{duration:.1f}時間"
                )
            else:
                duration_text = "不明"

            matched = item.get(
                "notification_facilities",
                [],
            )

            lines.append(
                f"【{i}】"
            )

            lines.append(
                f"都道府県："
                f"{', '.join(sorted(set("
                f"facility_prefecture.get(x, '不明') "
                f"for x in matched"
                f")))}"
            )

            lines.append(
                f"路線：{route_name}"
            )

            lines.append(
                f"方向：{direction}"
            )

            lines.append(
                f"区間：{section}"
            )

            lines.append(
                f"開始：{start_time}"
            )

            lines.append(
                f"経過：{duration_text}"
            )

            lines.append(
                f"原因：{reason}"
            )

            lines.append(
                f"該当SAPA："
                f"{', '.join(matched)}"
            )

            lines.append(
                "→ 本社報告対象"
            )

            lines.append("")

        message = "\n".join(lines)

    # =====================================================
    # ログ
    # =====================================================

    print()
    print(message)
    print()

    print(
        f"通知対象件数: {len(candidates)}"
    )

    print(
        "ntfyへ通知します。"
    )

    send_ntfy(
        message
    )

    print(
        "通知成功"
    )

    print("=" * 60)


if __name__ == "__main__":
    main()
