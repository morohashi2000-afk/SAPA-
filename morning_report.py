import json
import os
import urllib.request
from datetime import datetime, timezone, timedelta


STATE_FILE = "state.json"
FACILITIES_FILE = "facilities.json"

JST = timezone(timedelta(hours=9))


# ============================================================
# 通知対象の都道府県
# ============================================================

TARGET_PREFECTURES = {
    "青森県",
    "岩手県",
    "秋田県",
}


# ============================================================
# JSON読み込み
# ============================================================

def load_json(filename, default):
    if not os.path.exists(filename):
        return default

    try:
        with open(filename, "r", encoding="utf-8") as f:
            return json.load(f)

    except Exception as e:
        print(f"{filename} の読み込みに失敗しました: {e}")
        return default


# ============================================================
# 日時処理
# ============================================================

def parse_datetime(value):
    if not value:
        return None

    try:
        dt = datetime.fromisoformat(value)

        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=JST)

        return dt.astimezone(JST)

    except Exception as e:
        print(f"日時の解析に失敗しました: {value} / {e}")
        return None


def format_datetime(value):
    dt = parse_datetime(value)

    if dt is None:
        return "不明"

    return dt.strftime("%m/%d %H:%M")


def calculate_duration_hours(start_time, end_time):
    start = parse_datetime(start_time)
    end = parse_datetime(end_time)

    if start is None or end is None:
        return None

    seconds = (end - start).total_seconds()

    if seconds < 0:
        return None

    return seconds / 3600


# ============================================================
# 解除時刻が「前日17:30～当日08:00」か
# ============================================================

def is_overnight_release(release_dt, now):
    if release_dt is None:
        return False

    today_0800 = now.replace(
        hour=8,
        minute=0,
        second=0,
        microsecond=0,
    )

    yesterday_1730 = today_0800 - timedelta(days=1)

    return yesterday_1730 <= release_dt <= today_0800


# ============================================================
# 対象都道府県の有人SAPAを取得
# ============================================================

def get_notification_facilities(item, facility_prefecture):

    matched = item.get("matched_facilities", [])

    if not isinstance(matched, list):
        return []

    result = []

    for sapa in matched:
        prefecture = facility_prefecture.get(sapa)

        if prefecture in TARGET_PREFECTURES:
            result.append(sapa)

    return result


# ============================================================
# ntfy通知
#
# HTTPヘッダーに日本語を入れるとurllibがlatin-1で
# エラーになるため、JSON APIとしてUTF-8で送信する。
# ============================================================

def send_ntfy(message):

    topic = os.environ.get("NTFY_TOPIC", "")

    if not topic:
        raise RuntimeError(
            "NTFY_TOPIC が設定されていません。"
        )

    url = "https://ntfy.sh"

    payload = {
        "topic": topic,
        "title": "本社報告確認（08:00）",
        "message": message,
        "priority": 4,
        "tags": ["highway"],
    }

    data = json.dumps(
        payload,
        ensure_ascii=False,
    ).encode("utf-8")

    request = urllib.request.Request(
        url,
        data=data,
        headers={
            "Content-Type": "application/json; charset=utf-8",
        },
        method="POST",
    )

    with urllib.request.urlopen(
        request,
        timeout=30,
    ) as response:

        if response.status < 200 or response.status >= 300:
            raise RuntimeError(
                f"ntfy通知失敗: HTTP {response.status}"
            )


# ============================================================
# メイン処理
# ============================================================

def main():

    print("=" * 60)
    print("SAPA通行止め監視くん 08:00 REPORT")
    print("=" * 60)

    now = datetime.now(JST)

    print(
        "現在時刻："
        + now.strftime("%Y-%m-%d %H:%M:%S")
    )

    # --------------------------------------------------------
    # ファイル読み込み
    # --------------------------------------------------------

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

    # --------------------------------------------------------
    # SAPA → 都道府県
    # --------------------------------------------------------

    facility_prefecture = {}

    for facility in facilities:

        if not isinstance(facility, dict):
            continue

        name = facility.get("name", "")
        prefecture = facility.get("prefecture", "")

        if name and prefecture:
            facility_prefecture[name] = prefecture

    print(
        "通知対象都道府県："
        + ", ".join(sorted(TARGET_PREFECTURES))
    )

    # --------------------------------------------------------
    # 報告候補
    # --------------------------------------------------------

    candidates = []

    for closure_id, item in state.items():

        if not isinstance(item, dict):
            continue

        # ----------------------------------------------------
        # 開始時刻
        # ----------------------------------------------------

        start_time = item.get("start_time")

        start_dt = parse_datetime(start_time)

        if start_dt is None:
            continue

        # ----------------------------------------------------
        # 該当SAPA
        # ----------------------------------------------------

        notification_facilities = (
            get_notification_facilities(
                item,
                facility_prefecture,
            )
        )

        # 対象都道府県の有人SAPAがなければ通知しない
        if not notification_facilities:
            continue

        # ----------------------------------------------------
        # 解除時刻
        # ----------------------------------------------------

        release_value = item.get(
            "release_detected"
        )

        release_dt = parse_datetime(
            release_value
        )

        # ====================================================
        # ① 現在も通行止め中
        # ====================================================

        if release_dt is None:

            duration_hours = (
                calculate_duration_hours(
                    start_time,
                    now.isoformat(),
                )
            )

            if duration_hours is None:
                continue

            # 6時間未満なら対象外
            if duration_hours < 6:
                continue

            item_copy = dict(item)

            item_copy[
                "notification_facilities"
            ] = notification_facilities

            item_copy[
                "notification_release"
            ] = None

            item_copy[
                "notification_duration"
            ] = duration_hours

            item_copy[
                "notification_type"
            ] = "継続中"

            candidates.append(item_copy)

            print(
                "報告候補（継続中）："
                + str(
                    item.get(
                        "route_name",
                        "不明",
                    )
                )
                + " "
                + str(
                    item.get(
                        "section",
                        "不明",
                    )
                )
                + f" {duration_hours:.1f}時間"
            )

            continue

        # ====================================================
        # ② 解除済み
        #
        # 前日17:30～当日08:00に解除
        # かつ6時間以上
        # ====================================================

        if is_overnight_release(
            release_dt,
            now,
        ):

            duration_hours = (
                calculate_duration_hours(
                    start_time,
                    release_value,
                )
            )

            if duration_hours is None:
                continue

            # 6時間未満なら対象外
            if duration_hours < 6:
                continue

            item_copy = dict(item)

            item_copy[
                "notification_facilities"
            ] = notification_facilities

            item_copy[
                "notification_release"
            ] = release_dt

            item_copy[
                "notification_duration"
            ] = duration_hours

            item_copy[
                "notification_type"
            ] = "解除済み"

            candidates.append(item_copy)

            print(
                "報告候補（解除済み）："
                + str(
                    item.get(
                        "route_name",
                        "不明",
                    )
                )
                + " "
                + str(
                    item.get(
                        "section",
                        "不明",
                    )
                )
                + f" {duration_hours:.1f}時間"
                + " 解除 "
                + release_dt.strftime(
                    "%m/%d %H:%M"
                )
            )

    # ========================================================
    # 通知本文作成
    # ========================================================

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

        for index, item in enumerate(
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

            duration_hours = item.get(
                "notification_duration"
            )

            notification_type = item.get(
                "notification_type",
                "不明",
            )

            matched = item.get(
                "notification_facilities",
                [],
            )

            # ------------------------------------------------
            # 都道府県
            # ------------------------------------------------

            prefectures = sorted(
                set(
                    facility_prefecture.get(
                        sapa,
                        "不明",
                    )
                    for sapa in matched
                )
            )

            prefecture_text = ", ".join(
                prefectures
            )

            # ------------------------------------------------
            # 経過時間
            # ------------------------------------------------

            if duration_hours is not None:

                duration_text = (
                    f"{duration_hours:.1f}時間"
                )

            else:

                duration_text = "不明"

            # ------------------------------------------------
            # 解除時刻
            # ------------------------------------------------

            if notification_type == "解除済み":

                release_text = format_datetime(
                    item.get(
                        "release_detected"
                    )
                )

            else:

                release_text = "通行止め継続中"

            # ------------------------------------------------
            # 本文
            # ------------------------------------------------

            lines.append(
                f"【{index}】"
            )

            lines.append(
                f"都道府県：{prefecture_text}"
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
                f"開始：{format_datetime(start_time)}"
            )

            lines.append(
                f"解除：{release_text}"
            )

            lines.append(
                f"経過：{duration_text}"
            )

            lines.append(
                f"原因：{reason}"
            )

            lines.append(
                "該当SAPA："
                + ", ".join(matched)
            )

            lines.append(
                "→ 本社報告対象"
            )

            lines.append("")

        message = "\n".join(lines)

    # ========================================================
    # ログ出力
    # ========================================================

    print()
    print("-" * 60)
    print(message)
    print("-" * 60)

    print(
        f"通知対象件数：{len(candidates)}件"
    )

    # ========================================================
    # ntfy通知
    # ========================================================

    print("ntfyへ通知します。")

    send_ntfy(message)

    print("通知成功")

    print("=" * 60)


if __name__ == "__main__":
    main()
