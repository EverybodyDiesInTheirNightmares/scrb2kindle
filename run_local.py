#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""run_local.py — 一键本地运行（除授权码外全自动）。

做的事：
    1. 安装依赖（requests、beautifulsoup4）；
    2. 首次运行交互式询问 SMTP 服务器 / 发件邮箱 / 授权码 / Kindle 邮箱，
       并写入 .env（已被 .gitignore 忽略，不会提交到仓库）；
    3. 把 .env 注入环境变量后调用 scrb2kindle.py 抓取并发送。

回家后只需：
    python run_local.py
首次按提示粘贴授权码等三项即可；之后直接重跑，配置从 .env 读取不再询问。
想先只测抓取不发邮件，可单独运行：python scrb2kindle.py
"""

import os
import re
import sys
import subprocess

# 合法的邮箱地址：有且仅有一个 @，两侧非空白
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def valid_email(value):
    """校验邮箱格式（必须且只能有一个 @），避免把非法地址写进 .env。"""
    return bool(EMAIL_RE.match((value or "").strip()))


def main():
    # 1) 安装依赖
    print("==> 1/3 安装依赖（requests, beautifulsoup4）")
    subprocess.run(
        [sys.executable, "-m", "pip", "install", "-r", "requirements.txt"],
        check=True,
    )

    # 2) 读取或创建 .env
    env_file = ".env"
    cfg = {}
    if os.path.exists(env_file):
        with open(env_file, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line and "=" in line and not line.startswith("#"):
                    k, v = line.split("=", 1)
                    cfg[k.strip()] = v.strip()

    def ask(key, label, default="", validate=None, error="格式不正确", secret=False):
        """读取配置：.env 中有且合法则复用，否则交互式询问并校验。"""
        cached = cfg.get(key, "").strip()
        if cached:
            if validate is None or validate(cached):
                shown = "******" if secret else cached
                print(f"  {label} = {shown}  （来自 .env，无需重复输入）")
                cfg[key] = cached
                return cached
            print(f"  [警告] .env 中的 {key} 不合法: {cached!r}，请重新输入。")

        while True:
            hint = f" [{default}]" if default else ""
            val = input(f"  {label}{hint}: ").strip() or default
            if validate is None or validate(val):
                cfg[key] = val
                return val
            print(f"  [错误] {label} {error}，请重新输入。")

    print("==> 2/3 配置（仅首次需输入；授权码请粘贴，其余可回车用默认）")
    ask("SMTP_SERVER", "SMTP 服务器", "smtp.qq.com")
    ask(
        "SMTP_USER",
        "发件 QQ 邮箱（如 123456789@qq.com）",
        validate=valid_email,
        error="格式不正确（需形如 123456789@qq.com）",
    )
    ask("SMTP_PASS", "QQ 邮箱授权码（非登录密码）", secret=True)
    ask(
        "KINDLE_ADDR",
        "Kindle 接收邮箱（如 xxx@kindle.com）",
        validate=valid_email,
        error="格式不正确（必须且只能有一个 @，如 xxx@kindle.com）",
    )

    # 写回 .env，便于下次免输入
    with open(env_file, "w", encoding="utf-8") as fh:
        for k in ("SMTP_SERVER", "SMTP_USER", "SMTP_PASS", "KINDLE_ADDR"):
            fh.write(f"{k}={cfg[k]}\n")

    # 注入当前进程环境变量
    for k in ("SMTP_SERVER", "SMTP_USER", "SMTP_PASS", "KINDLE_ADDR"):
        os.environ[k] = cfg[k]

    # 3) 运行主脚本（透传命令行参数，如 --date 20260911）
    print("==> 3/3 抓取并发送至 Kindle")
    subprocess.run([sys.executable, "scrb2kindle.py"] + sys.argv[1:], check=True)
    print("==> 完成。Kindle 稍后同步即可收到头版正文。")


if __name__ == "__main__":
    main()
