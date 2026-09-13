#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""bark_notify.py — 将工作流结果通过 Bark 推送到手机，并遵守免打扰时段。

设计要点：
    - Bark 密钥从环境变量 BARK_KEY 读取（GitHub Secrets 注入），绝不写进代码；
    - BARK_SERVER 可选，默认官方 https://api.day.app，自建服务器时覆盖即可；
    - 免打扰规则按北京时间判断（固定 UTC+8，不依赖 runner 的系统时区）：
        13:00-14:30、22:30-次日 08:00 之间直接跳过，不发任何请求；
    - 推送失败只打印警告、退出码恒为 0，不影响工作流整体成败。

用法（GitHub Actions 内）：
    python bark_notify.py --outcome success --date 20260913 --stats "成功 10 篇，失败 0 篇"
"""

import argparse
import datetime
import json
import os
import urllib.parse
import urllib.request

BARK_SERVER_DEFAULT = "https://api.day.app"
GROUP = "scrb2kindle"      # iOS 通知分组名
HTTP_TIMEOUT = 10          # 单次请求超时（秒）

# 北京时间（固定 UTC+8），不依赖 runner 系统时区
BJT = datetime.timezone(datetime.timedelta(hours=8))

# 免打扰时段（北京时间）；跨天的区间 start > end
QUIET_WINDOWS = (
    (datetime.time(13, 0), datetime.time(14, 30)),
    (datetime.time(22, 30), datetime.time(8, 0)),
)


def in_quiet_hours(now):
    """判断当前时刻是否处于免打扰时段。"""
    for start, end in QUIET_WINDOWS:
        if start <= end:
            if start <= now < end:
                return True
        elif now >= start or now < end:   # 跨天区间（如 22:30-08:00）
            return True
    return False


def main():
    parser = argparse.ArgumentParser(description="Bark 推送工作流结果（带免打扰时段）")
    parser.add_argument(
        "--outcome", required=True,
        choices=["success", "failure", "cancelled", "skipped"],
    )
    parser.add_argument("--date", default="", help="推送日期 YYYYMMDD，留空则用北京时间今天")
    parser.add_argument("--stats", default="", help="附加说明，如「成功 10 篇，失败 0 篇」")
    args = parser.parse_args()

    key = os.environ.get("BARK_KEY", "").strip()
    if not key:
        print("[Bark] 未配置 BARK_KEY，跳过推送。")
        return 0

    now = datetime.datetime.now(BJT)
    if in_quiet_hours(now.time()):
        print(
            f"[Bark] 北京时间 {now:%H:%M} 处于免打扰时段"
            "（13:00-14:30 / 22:30-次日 08:00），跳过推送。"
        )
        return 0

    title = "四川日报推送成功" if args.outcome == "success" else "四川日报推送失败"
    date_str = args.date or now.strftime("%Y%m%d")
    body = f"{date_str} {args.stats}".strip()

    server = os.environ.get("BARK_SERVER", BARK_SERVER_DEFAULT).strip().rstrip("/")
    url = (
        f"{server}/{key}"
        f"/{urllib.parse.quote(title)}"
        f"/{urllib.parse.quote(body)}"
        f"?group={GROUP}"
    )

    try:
        with urllib.request.urlopen(url, timeout=HTTP_TIMEOUT) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        if data.get("code") == 200:
            print(f"[Bark] 推送成功: {title} | {body}")
        else:
            print(f"[Bark] 服务器返回异常（忽略）: {data}")
    except Exception as exc:  # noqa: BLE001 - 通知失败不影响主流程
        print(f"[Bark] 推送失败（忽略，不影响工作流结果）: {exc}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
