#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""scrb2kindle.py — 抓取《四川日报》电子版头版文章并推送至 Kindle。

工作流程：
    1. 抓取头版索引页（/shtml/scrb/{YYYYMMDD}/v01.html），解析全部文章链接；
    2. 逐篇抓取正文，提取标题（h1/h2）与段落（<p>，按 <br> 切分）；
    3. 合并为 UTF-8 纯文本 txt，每段段首加两个全角空格，标题用【】包裹；
    4. 通过 SMTP_SSL 将 txt 作为附件发送到 Kindle 邮箱。

敏感信息（SMTP 服务器、账号、授权码、Kindle 邮箱）均从环境变量读取，
本地测试未配置环境变量时仅生成本地 txt、不发送邮件。
"""

import os
import re
import sys
import time
import smtplib
import datetime
import argparse

import requests
from bs4 import BeautifulSoup
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email import encoders

# --------------------------------------------------------------------------- #
# 常量配置
# --------------------------------------------------------------------------- #
BASE_URL = "https://epaper.scdaily.cn"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)
HTTP_TIMEOUT = 15          # 单次请求超时（秒）
HTTP_RETRIES = 2           # 失败重试次数
RETRY_WAIT = 5             # 重试间隔（秒）
FULL_SPACE = "　"          # 全角空格（U+3000），报纸段落缩进
INDENT = FULL_SPACE * 2    # 段首两个全角空格

# 需要读取的环境变量
ENV_KEYS = ("SMTP_SERVER", "SMTP_USER", "SMTP_PASS", "KINDLE_ADDR")

# 合法的邮箱地址：有且仅有一个 @，两侧非空白且不以 @ 相邻
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def normalize_email(value, env_name):
    """去除首尾空白与引号并校验邮箱格式，返回规范化后的地址。

    配置来自环境变量 / .env，可能夹带空格或粘贴错误（例如出现两个 @）。
    这里提前校验并给出中文提示，避免把非法地址交给 SMTP 后抛出
    SMTPRecipientsRefused 这类难以定位的底层异常。
    """
    addr = (value or "").strip().strip('"').strip("'")
    if not EMAIL_RE.match(addr):
        raise ValueError(
            f"环境变量 {env_name} 不是合法邮箱地址: {addr!r}"
            "（必须且只能有一个 @，例如 xxx@kindle.com）"
        )
    return addr


# --------------------------------------------------------------------------- #
# 基础工具
# --------------------------------------------------------------------------- #
def beijing_today():
    """返回北京时间的当天 date 对象（非 UTC）。

    使用固定 UTC+8 时区，避免依赖系统时区设置。
    """
    tz = datetime.timezone(datetime.timedelta(hours=8))
    return datetime.datetime.now(tz).date()


def http_get(url, timeout=HTTP_TIMEOUT, retries=HTTP_RETRIES, wait=RETRY_WAIT):
    """带浏览器 UA、超时与重试的 GET 请求，返回解码后的页面文本。

    失败时按 RETRY_WAIT 间隔重试，全部失败后向上抛出异常。
    """
    last_err = None
    for attempt in range(retries + 1):
        try:
            resp = requests.get(
                url, headers={"User-Agent": USER_AGENT}, timeout=timeout
            )
            resp.raise_for_status()
            # 该站点编码为 utf-8，用 apparent_encoding 兜底
            resp.encoding = resp.apparent_encoding or "utf-8"
            return resp.text
        except Exception as exc:  # noqa: BLE001 - 网络层异常统一重试
            last_err = exc
            if attempt < retries:
                print(f"  [重试 {attempt + 1}/{retries}] 请求失败: {url} ({exc})")
                time.sleep(wait)
    raise last_err


# --------------------------------------------------------------------------- #
# 抓取：索引页
# --------------------------------------------------------------------------- #
def fetch_index_links(date):
    """抓取头版索引页，解析并返回去重、保序的文章绝对链接列表。

    站点结构（已勘察确认）：
      - 索引页上半部分是版面整图（<img>）与 <map><area> 热点区域；
      - 先 decompose() 删除这些节点；
      - 剩余 <a href> 中，匹配 /shtml/scrb/{YYYYMMDD}/\\d+\\.html 的即为文章链接
        （如 .../20260911/1089386.html）。文章 ID 不连续，必须从页面解析。
      - 文章链接会以 class="selectBox" 覆盖层与 class="title_art" 标题列表
        两种方式重复出现，需要去重。
    """
    ymd = date.strftime("%Y%m%d")
    url = f"{BASE_URL}/shtml/scrb/{ymd}/v01.html"
    print(f"[索引] 抓取头版索引页: {url}")

    html = http_get(url)
    soup = BeautifulSoup(html, "html.parser")

    # 删除版面整图与非正文节点（保留 <a>，链接从中解析）
    for tag in soup.find_all(["img", "map", "script", "style", "nav", "header", "footer", "iframe"]):
        tag.decompose()

    pattern = re.compile(rf"/shtml/scrb/{ymd}/(\d+)\.html")
    seen = set()
    links = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if not pattern.search(href):
            continue
        abs_url = href if href.startswith("http") else BASE_URL + href
        if abs_url not in seen:
            seen.add(abs_url)
            links.append(abs_url)

    print(f"[索引] 解析到 {len(links)} 篇文章链接")
    return links


# --------------------------------------------------------------------------- #
# 抓取：单篇文章
# --------------------------------------------------------------------------- #
def fetch_article(url):
    """抓取单篇文章，返回 (title_lines, paragraphs)。

    title_lines: 标题行列表（已用【】包裹，按文档顺序，含引题/副题）；
    paragraphs : 正文段落列表（每段段首已加两个全角空格）。

    正文本质上位于一个含 <br> 的 <p> 内，需将 <br> 切分为独立段落。
    提取前先删除 script/style/img/nav/header/footer/iframe/a 等噪声节点。
    单篇失败抛异常，由调用方决定跳过。
    """
    print(f"[文章] 抓取: {url}")
    html = http_get(url)
    soup = BeautifulSoup(html, "html.parser")

    # 删除非正文节点（含 <a>，正文不依赖链接）
    for tag in soup.find_all(["script", "style", "img", "nav", "header", "footer", "iframe", "a", "map"]):
        tag.decompose()

    # 标题：h2（引题/副题，取有内容者）+ h1（主标题），按文档顺序
    title_lines = []
    for h2 in soup.find_all("h2"):
        t = h2.get_text(strip=True)
        if t:
            title_lines.append(f"【{t}】")
    h1 = soup.find("h1")
    if h1:
        t = h1.get_text(strip=True)
        if t:
            title_lines.append(f"【{t}】")
    if not title_lines:
        raise ValueError("未解析到标题（h1/h2）")

    # 正文：所有 <p>，将 <br> 替换为换行后逐段提取。
    # 噪声处理：
    #   - 跳过仅含装饰符号（如 ·）的空行（部分版面整图区会残留）；
    #   - 站点会在页面内重复存放一份正文，需对段落去重，避免正文翻倍。
    paragraphs = []
    seen_lines = set()
    for p in soup.find_all("p"):
        for br in p.find_all("br"):
            br.replace_with("\n")
        for raw in p.get_text().split("\n"):
            line = raw.strip()
            if not line:
                continue
            # 纯装饰字符（无中英文/数字）视为噪声，跳过
            if not re.search(r"[\u4e00-\u9fffA-Za-z0-9]", line):
                continue
            if not line.startswith(FULL_SPACE):
                line = INDENT + line
            if line in seen_lines:
                continue
            seen_lines.add(line)
            paragraphs.append(line)

    if not paragraphs:
        raise ValueError("未解析到正文段落")
    return title_lines, paragraphs


# --------------------------------------------------------------------------- #
# 组装文本
# --------------------------------------------------------------------------- #
def build_text(date, articles):
    """将 [(title_lines, paragraphs), ...] 组装为最终纯文本。

    格式：
        四川日报头版 2026-09-11
        =======================
        <空行>
        【标题一】
        <空行>
        　　第一段……
        　　第二段……
        <空行>
        【标题二】
        <空行>
        　　……
    """
    lines = [f"四川日报头版 {date.strftime('%Y-%m-%d')}", "=======================", ""]
    for title_lines, paragraphs in articles:
        lines.extend(title_lines)
        lines.append("")           # 标题与正文之间空一行
        lines.extend(paragraphs)
        lines.append("")           # 文章之间空一行
    # 末尾会多出一个空行，去除后统一补一个换行
    return "\n".join(lines).rstrip("\n") + "\n"


# --------------------------------------------------------------------------- #
# 邮件发送
# --------------------------------------------------------------------------- #
def send_email(txt_path, date):
    """使用 SMTP_SSL 将 txt 附件发送至 Kindle 邮箱。

    附件名仅用 ASCII（scrb_front_{YYYYMMDD}.txt），避免亚马逊拒收。
    敏感信息全部来自环境变量，本函数不做硬编码。
    """
    smtp_server = os.environ["SMTP_SERVER"].strip()
    smtp_user = normalize_email(os.environ["SMTP_USER"], "SMTP_USER")
    smtp_pass = os.environ["SMTP_PASS"].strip()
    kindle_addr = normalize_email(os.environ["KINDLE_ADDR"], "KINDLE_ADDR")
    ymd = date.strftime("%Y%m%d")

    msg = MIMEMultipart()
    msg["From"] = smtp_user
    msg["To"] = kindle_addr
    msg["Subject"] = f"四川日报头版 {date.strftime('%Y-%m-%d')}"
    msg.attach(MIMEText("《四川日报》头版正文，请见附件（纯文本）。", "plain", "utf-8"))

    with open(txt_path, "rb") as fh:
        part = MIMEBase("application", "octet-stream")
        part.set_payload(fh.read())
        encoders.encode_base64(part)
        part.add_header(
            "Content-Disposition",
            f'attachment; filename="scrb_front_{ymd}.txt"',
        )
        msg.attach(part)

    print(f"[邮件] 通过 {smtp_server} 发送至 {kindle_addr} ...")
    with smtplib.SMTP_SSL(smtp_server, 465, timeout=HTTP_TIMEOUT) as server:
        server.login(smtp_user, smtp_pass)
        server.sendmail(smtp_user, [kindle_addr], msg.as_string())
    print(f"[邮件] 发送成功: scrb_front_{ymd}.txt")


# --------------------------------------------------------------------------- #
# 主流程
# --------------------------------------------------------------------------- #
def main():
    """主流程：抓索引 → 抓各篇 → 组装 → 写文件 → （可选）发邮件。

    返回进程退出码：0 成功/正常跳过，1 全部文章抓取失败。
    """
    parser = argparse.ArgumentParser(description="四川日报头版抓取并推送 Kindle")
    parser.add_argument(
        "--date",
        default=None,
        help="指定日期 YYYYMMDD（默认使用北京时间当天，用于本地测试）",
    )
    args = parser.parse_args()

    if args.date:
        date = datetime.datetime.strptime(args.date, "%Y%m%d").date()
    else:
        date = beijing_today()

    print(f"=== scrb2kindle 启动 | 目标日期(北京时间): {date} ===")

    # 1) 抓索引页（不可达/未出报按“无报纸”优雅退出）
    try:
        links = fetch_index_links(date)
    except Exception as exc:  # noqa: BLE001
        print(f"[提示] 头版索引页暂不可达或当日未出报（{exc}），正常退出。")
        return 0

    if not links:
        print(f"[提示] {date} 头版暂无可抓取文章（可能未出报或版面调整），正常退出。")
        return 0

    print("[索引] 文章链接列表:")
    for link in links:
        print("  -", link)

    # 2) 逐篇抓取，单篇失败跳过
    articles = []
    failed = 0
    for url in links:
        try:
            title_lines, paragraphs = fetch_article(url)
            articles.append((title_lines, paragraphs))
            head = title_lines[-1].strip("【】") if title_lines else "(无标题)"
            print(f"[OK] {head} （{len(paragraphs)} 段）")
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print(f"[警告] 抓取失败，跳过: {url} ({exc})")

    if not articles:
        print(f"[失败] 全部 {len(links)} 篇文章均抓取失败，退出码 1。")
        return 1

    print(f"[统计] 成功 {len(articles)} 篇，失败 {failed} 篇。")

    # 3) 组装并写出 txt
    text = build_text(date, articles)
    ymd = date.strftime("%Y%m%d")
    out_path = f"scrb_front_{ymd}.txt"
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write(text)
    print(f"[写出] 文件已生成: {out_path}（{len(text.encode('utf-8'))} 字节）")

    # 4) 仅当四个环境变量齐全时才发邮件（本地测试默认不发）
    if all(os.environ.get(k) for k in ENV_KEYS):
        try:
            send_email(out_path, date)
        except Exception as exc:  # noqa: BLE001
            print(f"[失败] 邮件发送失败: {exc}")
            print(f"[提示] txt 已生成于 {out_path}，可手动发送到 Kindle 邮箱。")
            return 1
    else:
        print("[跳过] 未检测到 SMTP 环境变量，仅生成本地 txt，不发送邮件。")

    return 0


if __name__ == "__main__":
    sys.exit(main())
