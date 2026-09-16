# scrb2kindle

抓取《四川日报》电子版**头版**全部文章正文，合并为纯文本 `txt`（首页目录 + **遴选积累词汇 ★★ 标注**），并通过 SMTP 自动推送至 **Kindle**（txt 原生支持，无需转换）。

```
2026-09-11

目　录

01、十佳农文旅线路揭晓
02、“浙川同行·寻美乡村”

――――――――――――――――

【十佳农文旅线路揭晓】

　　本报讯（四川日报全媒体记者 兰楠）9月10日……
　　本次发布的十佳农文旅线路横贯川西高原，着力★提质增效★……

――――――――――――――――

★今日积累★

01、提质增效

（每个词仅在全文首次出现时标注一次，避免正文过密；文末集中汇总当天词汇。词表 `keywords.txt` 可自行增删）
```

## 项目结构

```
scrb2kindle/
├── scrb2kindle.py        # 主脚本，含 main()
├── .github/workflows/daily.yml     # 每日定时推送（名义北京 09:10，实测约 14:30 送达）
├── .github/workflows/watchdog.yml  # 看门狗：当天未成功自动补跑
├── bark_notify.py        # Bark 手机通知（免打扰时段自动跳过）
├── keywords.txt          # 遴选积累词汇表（命中即用 ★★ 标注，一行一词）
```

## 工作原理

1. 抓取头版索引页 `https://epaper.scdaily.cn/shtml/scrb/{YYYYMMDD}/v01.html`；
2. 删除版面整图（`<img>`、`<map>`）等非正文节点，解析出全部文章链接
   （匹配 `/shtml/scrb/{YYYYMMDD}/\d+\.html`，文章 ID 不连续，从页面解析，不递增遍历）；
3. 逐篇抓取正文，删除 `script/style/img/nav/header/footer/iframe/a` 等节点，
   提取 `h1`(主标题)/`h2`(引题·副题) 与所有 `<p>`（按 `<br>` 切分为段）；
4. 组装为 UTF-8 纯文本：首页目录、标题用 `【】` 包裹、每段段首两个全角空格，
   正文命中 `keywords.txt` 词汇的片段用 `★词汇★` 标注；
5. 用 `SMTP_SSL`（如 QQ 邮箱 `smtp.qq.com:465`）以**授权码**登录，将 `txt` 作为附件发到 Kindle 邮箱。

日期使用**北京时间当天**（UTC+8），非 UTC。所有请求带浏览器 `User-Agent`，超时 15 秒，失败重试 2 次（间隔 5 秒）。

## 一、配置 QQ 邮箱授权码

Kindle 推送需要用一个**普通邮箱**作为发件人（本项目用 QQ 邮箱示范）。需要开启 SMTP 并获取**授权码**（不是 QQ 登录密码）。

1. 登录网页版 [QQ 邮箱](https://mail.qq.com/)；
2. 顶部「设置」→「账户」；
3. 找到「POP3/IMAP/SMTP/Exchange/CardDAV/CalDAV 服务」，开启 **IMAP/SMTP 服务**；
4. 按提示用手机发短信验证，生成一串**授权码**（形如 `abcdwxyzefghijkl`）；
5. 记下你的 QQ 邮箱地址（如 `123456789@qq.com`）和这串授权码。

> 若用其他邮箱（163、Gmail 等），只需把 `SMTP_SERVER` 换成对应地址，并用其授权码。

## 二、把发件邮箱加入亚马逊“已认可的发件人”

亚马逊**仅接收“已认可的发件人”**发来的个人文档，否则会退信。务必先添加，否则推送失败。

1. 打开亚马逊「管理我的内容和设备」：
   - 中国用户：<https://www.amazon.cn/mn/dcw/myx#/home/settings/payment>
   - 海外用户：<https://www.amazon.com/mn/dcw/myx#/home/settings/payment>
2. 左侧「**偏好设置**」(Preferences) → 「**个人文档设置**」(Personal Document Settings)；
3. 在「**已认可的发件人**」(Approved Personal Document E-mail List) 中，点击「添加地址」，填入你的发件邮箱（如 `123456789@qq.com`）；
4. 记下你的 **Kindle 接收邮箱**，形如 `yourname@kindle.com`（在「发送至 Kindle 电子邮件地址」中查看）。

## 三、本地运行

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 配置环境变量（Linux / macOS）
export SMTP_SERVER=smtp.qq.com
export SMTP_USER=123456789@qq.com
export SMTP_PASS=你的授权码
export KINDLE_ADDR=yourname@kindle.com

# Windows PowerShell
$env:SMTP_SERVER="smtp.qq.com"
$env:SMTP_USER="123456789@qq.com"
$env:SMTP_PASS="你的授权码"
$env:KINDLE_ADDR="yourname@kindle.com"

# 3. 运行（默认抓取北京时间当天头版）
python scrb2kindle.py

# 也可指定历史日期测试（仅抓取，不依赖是否配置邮箱）
python scrb2kindle.py --date 20260911
```

### 一键运行（推荐，除授权码外全自动）

仓库内附带 `run_local.py`：自动装依赖、首次交互式询问四项配置并写入 `.env`（已被忽略、不会提交），之后直接调用主脚本抓取并发送。

```bash
# 回家后只需这一条；首次按提示粘贴授权码等三项，之后重跑免输入
python run_local.py

# 也可带参数，例如指定历史日期
python run_local.py --date 20260911
```

> 想先只测抓取不发邮件，仍可直接 `python scrb2kindle.py`（不设环境变量即跳过邮件）。

**本地测试建议（先只测抓取、不发邮件）：** 不设置任何 SMTP 环境变量直接运行，脚本会抓取到 `scrb_front_{YYYYMMDD}.txt` 并提示「[跳过] 未检测到 SMTP 环境变量，仅生成本地文件，不发送邮件」。确认内容无误后，再配置环境变量、启用邮件推送。

## 四、GitHub Actions 每日自动推送（私有仓库）

定时任务：UTC `10 1 * * *` = **名义上北京时间 09:10**。注意：本仓库的 scheduled 事件存在 **GitHub 平台侧约 5.4 小时的系统性延迟**（与配置无关），因此实际送达时间约为 **北京时间 14:30 前后**。另有看门狗工作流 `watchdog.yml` 定时检查，当天主任务未成功会自动补跑。

> 生效条件：工作流文件必须位于**默认分支**（`main`）；仓库连续 **60 天无任何提交**时，GitHub 会自动停用定时任务，需到 Actions 页面手动重新启用。
> 定时任务在高峰期可能被延迟几分钟到十几分钟，属正常现象。

### 1. 把项目推到仓库（建议 Private）

```bash
git init -b main
git add -A
git commit -m "scrb2kindle init"
git remote add origin git@github.com:你的用户名/scrb2kindle.git
git push -u origin main
```

> 建议设为 **Private**：`.gitignore` 已排除 `.env`，Secrets 也不会出现在日志中，但私有仓库更保险。
> 工作流文件必须落在**默认分支**上，GitHub 才会识别并定时触发。

### 2. 配置 Secrets（**关键，缺失则不会发邮件**）

仓库页面 → **Settings** → **Secrets and variables** → **Actions** → **New repository secret**，逐个添加：

| Name           | 示例值                  | 说明                     |
| -------------- | ----------------------- | ------------------------ |
| `SMTP_SERVER`  | `smtp.qq.com`           | SMTP 服务器              |
| `SMTP_USER`    | `123456789@qq.com`      | 发件邮箱                 |
| `SMTP_PASS`    | `abcdwxyzefghijkl`      | QQ 邮箱**授权码**        |
| `KINDLE_ADDR`  | `yourname@kindle.com`   | Kindle 接收邮箱          |
| `BARK_KEY`     | Bark App 里复制的密钥   | 可选；配置后运行结束发 Bark 通知 |

> 这些是**私有仓库 Secrets**，仅在工作流运行时注入，不会出现在代码或日志中。

> **Bark 通知（可选）**：配置 `BARK_KEY` 后，每次运行结束（成功或失败）都会向手机推一条 Bark 消息，正文含日期与抓取统计；北京时间 **13:00-14:30**、**22:30-次日 08:00** 两个免打扰时段内自动跳过、不发请求。密钥只放 Secrets，切勿写进代码或文档。自建 Bark 服务器时，另加 Secret `BARK_SERVER` 覆盖默认地址即可。

### 3. 触发运行

- 自动：每天 **UTC 01:10（名义北京 09:10）** 触发，受平台系统性延迟影响实际约北京 14:30 执行；
- 自动补跑：看门狗在北京时间 16:10 / 18:10 检查，当天主任务未成功则经 API 触发 `workflow_dispatch`；
- 手动：仓库 **Actions** → 左侧选择 `scrb2kindle daily` → 右侧 **Run workflow**；
  - 可在 `date` 输入框填 `20260911` 指定历史日期，留空则抓取北京时间当天，便于首次验证；
- 运行日志可直接查看抓取与发送结果（产物不上传，避免报纸全文公开可下载）。

## 健壮性说明

- 当日未出报或头版为空：打印提示并**正常退出（退出码 0）**，不发邮件、不抛堆栈；
- 单篇文章抓取失败：跳过该篇并打印警告，继续其余文章；仅当**全部失败**才退出码 1；
- 所有请求带浏览器 UA、超时 15 秒、失败重试 2 次（间隔 5 秒）；
- 敏感信息全部来自环境变量，不硬编码。

## 常见问题

- **收不到邮件**：先确认发件邮箱已加入亚马逊「已认可的发件人」，且 `KINDLE_ADDR` 与亚马逊后台显示的接收邮箱完全一致（区分 `@kindle.com` / `@kindle.cn`）。
- **推送被拒**：附件名已固定为 ASCII（`scrb_front_{YYYYMMDD}.txt`），正文为纯文本，符合亚马逊要求；若仍被拒，检查发件邮箱是否在认可列表。
- **提示未出报**：偶有当日报纸尚未发布（早于 06:00  UTC 触发时），可手动 `Run workflow` 重跑。
- **定时为什么不准**：GitHub 对本仓库的 scheduled 事件存在约 5.4 小时的系统性延迟（平台行为，换 cron 分钟无效）。当前 cron 已按「名义时刻 = 目标 − 5.4h」反推补偿；若某天突然恢复准点（北京 09:10 就跑），把 `daily.yml` 的 cron 改回目标时刻即可。
- **Actions 定时不准 / 漏跑**：平台固有限制（整点拥堵、偶发事故），已由看门狗自动补跑兜底；极端情况可手动 `Run workflow`，或用 API 触发（令牌需 Actions 读写权限）：
  ```
  curl -X POST -H "Authorization: Bearer <你的PAT>" \
    -H "Accept: application/vnd.github+json" \
    https://api.github.com/repos/<用户名>/scrb2kindle/actions/workflows/daily.yml/dispatches \
    -d '{"ref":"main"}'
  ```
- **Actions 里没有定时任务**：确认工作流已在默认分支；仓库超过 60 天无提交会被自动停用，需在 Actions 页面重新启用。
