# eStudent MCP

**English** | [中文](#中文文档)

A local [MCP](https://modelcontextprotocol.io) server that lets Claude Code
operate the PolyU **eStudent** portal — check grades, timetable and exams,
search subjects, and (work in progress) add/drop & snipe courses.

**Everything runs on your own machine. Your NetID and password never leave it.**

> ⚠️ This is an unofficial personal tool, not affiliated with PolyU. Use it on
> your own account and at your own risk, and respect the university's
> acceptable-use policy.

---

## ✨ Features & Status

| Tool | What it does | Status |
|---|---|---|
| `session_status` | Is there a live logged-in session? | ✅ Live-verified |
| `get_grades` | Grades & GPA, optional `term` filter | ✅ Live-verified |
| `get_timetable` | Class timetable | ✅ Live-verified |
| `get_exam_schedule` | Exam dates / venues / seats | ✅ Live-verified |
| `search_subjects` | Search by code/keyword **or** by programme; auto term, pagination, per-group vacancy on a single match | ✅ Live-verified |
| `preview_registration` | Preview add/drop — **never submits** | ⏳ Logic done; live calibration pending |
| `confirm_registration` | Submit add/drop (needs preview `fingerprint`) | ⏳ Pending registration window |
| `start_course_sniper` | Automated grab (open-time / vacancy-watch) | ⏳ Scheduler done; real submit pending |
| `sniper_status` | List / inspect / stop sniper jobs | ✅ Works |

### Done & verified

- **Login** via PolyU ADFS SSO (NetID + password, no 2FA for the tested account);
  session is persisted and reused.
- **Read tools** (`get_grades` / `get_timetable` / `get_exam_schedule`) calibrated
  against the live portal.
- **`search_subjects`** — both **by subject** (code/title) and **by programme**
  (department → programme cascade); tries each term automatically when none is
  given; walks the result pagination to collect all subjects; when the query
  resolves to exactly one subject it drills into the detail page to return each
  teaching group's **vacancy** (handles `5` open / `(4)` reserved / `W=.. Top-up
  vac=..` waitlist).
- **Two-step registration invariant**, **sniper frequency floors**, the
  sniper's **self-healing retry logic** (auto re-login, browser relaunch,
  open-time → vacancy-watch fallback), and all **parsers** are unit-tested
  (24 tests).

### Not finished yet

- `preview_registration` / `confirm_registration` real submission, and the
  sniper's real grab path, can only be calibrated when the **subject
  registration window is open** (it was closed during development). The
  scheduling, frequency safety, and preview→confirm fingerprint logic are
  already built and tested.
- `search_subjects` keyword results across many pages are de-duplicated but
  large title searches return the offered subjects only (no extra filters yet).

---

## 🚀 Installation

**Prerequisites**: macOS, Python 3.12, [`uv`](https://docs.astral.sh/uv/),
and [Claude Code](https://claude.com/claude-code).

```bash
# 1. Clone
git clone https://github.com/<your-account>/polyu-estudent-mcp.git
cd polyu-estudent-mcp

# 2. Create the venv and install deps
uv sync --extra dev

# 3. Install the headless browser Playwright drives
.venv/bin/python -m playwright install chromium

# 4. Configure your credentials
cp .env.example .env
#    then edit .env — see the next section
```

### Configure `.env`

`.env` is **git-ignored** and must contain your real credentials. It never gets
committed or pushed.

```ini
ESTUDENT_NETID=your_netid          # e.g. 12345678d
ESTUDENT_PASSWORD=your_password    # your portal password
ESTUDENT_BASE_URL=https://www.polyu.edu.hk/student
ESTUDENT_HEADFUL=0                 # 1 = show the browser (debugging)
```

```bash
chmod 600 .env   # restrict to your user
```

### Verify

```bash
uv run pytest -q          # 19 tests should pass
```

---

## 🔌 Register with Claude Code

```bash
claude mcp add estudent -s user -- \
  "$(pwd)/.venv/bin/python" -m estudent_mcp.server
```

`-s user` registers it globally (available in every project). Drop it for the
current project only. Confirm it connected:

```bash
claude mcp get estudent     # should show ✔ Connected
```

---

## 💬 Usage

Just talk to Claude Code in natural language — it picks the right tool.

| You say | Tool used |
|---|---|
| "What's my GPA?" | `get_grades` |
| "Show my timetable" | `get_timetable` |
| "When are my exams?" | `get_exam_schedule` |
| "Find COMP1011 and its vacancy" | `search_subjects` |
| "Search programmes in COMP for BA(HONS) COMPUTING" | `search_subjects` (by programme) |
| "Watch COMP2012 for a vacancy" | `start_course_sniper` (⏳) |

### Two-step registration

`confirm_registration` only submits if you pass the `fingerprint` returned by a
`preview_registration` of the **same** actions — so you can never add/drop a
subject without first seeing exactly what will change.

### The sniper is deliberately restrained

High-frequency "bombing" polling is **not supported**, by design — it's the
fastest way to get rate-limited/banned (so you'd miss the course anyway), may
violate the acceptable-use policy, and is unfair to others.

Frequency floors are enforced (sub-floor configs are rejected):

- **open_time** mode: retry ≥ 3s, total window ≤ 2 min.
- **watch_vacancy** mode: poll ≥ 60s.

Within those floors, jobs are **self-healing**: every attempt re-checks the
session (an expired login re-authenticates automatically with your `.env`
credentials), a crashed browser is closed and relaunched, and transient errors
(network blips, page hiccups) just count as a missed attempt. Only rejected
credentials or 5 identical errors in a row end a job early. Pass
`then_watch=true` to *open_time* so an unsuccessful open window falls through
to vacancy watching instead of giving up. Terminal events (grabbed / fallback /
failed) raise a native macOS notification.

Keep your Mac awake while a job runs — e.g. `caffeinate -dims` in a spare
terminal. Set `ESTUDENT_HEADFUL=1` to watch the browser.

---

## 🔒 Security

- `.env` (your credentials), `.runtime/` (saved session + any captured page
  HTML, which may contain personal data), and screenshots are **all git-ignored**
  and were **never committed** to history.
- Only `.env.example` (a placeholder template) is tracked.
- Credentials are read locally by `config.py` and used solely to log into
  eStudent from your machine.

If you fork/clone, never commit your `.env`.

---

## 🏗 Architecture

```
src/estudent_mcp/
  server.py                  # MCP tool layer (no browser code)
  backend/
    base.py                  # EStudentBackend interface (stable)
    playwright_backend.py    # scheme A: headless browser (current)
    # future: hybrid_backend.py — scheme C: Playwright login + httpx fetch
  parsers/                   # HTML -> dataclasses (pure, unit-tested)
  registration.py            # fingerprint + summary (two-step invariant)
  sniper.py                  # scheduler + frequency floors
  models.py  config.py  errors.py
tests/                       # parser / registration / sniper unit tests
scripts/                     # joint-debug probes (no PII committed)
```

The `EStudentBackend` interface lets a faster HTTP backend (scheme C) be swapped
in later without touching the tools or parsers.

---

## 🛠 Why a browser instead of an API?

eStudent exposes **no public API**, so the backend drives a real headless
Chromium (via Playwright) that logs in and reads pages exactly like a human
would, then parses the HTML tables into structured data.

It passes login because PolyU's ADFS presented no CAPTCHA/2FA for the tested
account and a real browser is used — **not** by defeating any verification. If
the school adds a CAPTCHA/2FA, the right move is headful mode (`ESTUDENT_HEADFUL=1`)
to solve it once and reuse the session.

---

## 📄 License

Personal use. No warranty.

<br>

---
---

<br>

# 中文文档

[English](#estudent-mcp) | **中文**

一个本地 [MCP](https://modelcontextprotocol.io) 服务器，让 Claude Code 帮你操作
香港理工大学 **eStudent** 门户：查成绩、课表、考试，搜课，以及（开发中）选课/退课
与抢课。

**所有操作都在你本机运行，账号密码绝不外传。**

> ⚠️ 本项目为非官方个人工具，与理大无关。仅用于你自己的账号，风险自负，并请遵守学校的
> 网络使用规定。

---

## ✨ 功能与完成度

| 工具 | 功能 | 状态 |
|---|---|---|
| `session_status` | 是否有有效登录会话 | ✅ 已实测 |
| `get_grades` | 成绩与 GPA，可按学期过滤 | ✅ 已实测 |
| `get_timetable` | 上课时间表 | ✅ 已实测 |
| `get_exam_schedule` | 考试日期、地点、座位 | ✅ 已实测 |
| `search_subjects` | 按代码/关键词、或按专业搜课；自动选学期、自动翻页、单科目下钻名额 | ✅ 已实测 |
| `preview_registration` | 预演选退课，**不提交** | ⏳ 逻辑完成，待联调 |
| `confirm_registration` | 提交选退课（需预演指纹） | ⏳ 待选课窗口开放 |
| `start_course_sniper` | 定时抢课（开放瞬间 / 满员捡漏） | ⏳ 调度完成，真实提交待接通 |
| `sniper_status` | 查看、检查、停止抢课任务 | ✅ 可用 |

### 已完成并验证

- **登录**走理大 ADFS 单点登录（账号密码，测试账号无 2FA），会话持久化复用。
- **读取类工具**（`get_grades` / `get_timetable` / `get_exam_schedule`）已对真实门户校准。
- **`search_subjects`** 支持**按科目**（代码/标题）和**按专业**（院系 → 专业级联）两种
  模式；无学期时自动逐学期尝试；自动翻页收齐全部科目；命中单个科目时下钻详情页返回每个
  教学组的**名额**（识别 `5` 开放 / `(4)` 保留 / `W=.. Top-up vac=..` 候补）。
- **两步选课确认**、**抢课频率下限**、抢课**自愈重试逻辑**（自动重登、浏览器重启、
  开抢失败转捡漏）、所有**解析器**均有单测（24 个）。

### 尚未完成

- 选课/退课的真实提交（`preview_registration` / `confirm_registration`）、抢课真实下单，
  必须等**选课窗口开放**才能联调（开发期间未开放）。调度、频率保护、预演→确认指纹逻辑
  已写好并测试。
- 关键词大范围搜索已去重，但暂未加更多筛选条件。

---

## 🚀 安装

**前置要求**：macOS、Python 3.12、[`uv`](https://docs.astral.sh/uv/)、
[Claude Code](https://claude.com/claude-code)。

```bash
# 1. 克隆
git clone https://github.com/<your-account>/polyu-estudent-mcp.git
cd polyu-estudent-mcp

# 2. 创建虚拟环境并装依赖
uv sync --extra dev

# 3. 安装 Playwright 用的浏览器
.venv/bin/python -m playwright install chromium

# 4. 配置凭据
cp .env.example .env
#    然后编辑 .env —— 见下一节
```

### 配置 `.env`

`.env` **已被 git 忽略**，填你的真实凭据，绝不会被提交或推送。

```ini
ESTUDENT_NETID=your_netid          # 例如 12345678d
ESTUDENT_PASSWORD=your_password    # 门户密码
ESTUDENT_BASE_URL=https://www.polyu.edu.hk/student
ESTUDENT_HEADFUL=0                 # 1 = 显示浏览器（调试用）
```

```bash
chmod 600 .env   # 仅本人可读写
```

### 验证

```bash
uv run pytest -q          # 应有 19 个测试通过
```

---

## 🔌 注册到 Claude Code

```bash
claude mcp add estudent -s user -- \
  "$(pwd)/.venv/bin/python" -m estudent_mcp.server
```

`-s user` 是全局注册（所有项目可用），去掉则只对当前项目生效。确认连接：

```bash
claude mcp get estudent     # 应显示 ✔ Connected
```

---

## 💬 使用

直接用自然语言跟 Claude Code 说，它会自动选用合适的工具。

| 你说 | 用到的工具 |
|---|---|
| "查一下我的成绩和 GPA" | `get_grades` |
| "这学期课表" | `get_timetable` |
| "考试安排" | `get_exam_schedule` |
| "搜一下 COMP1011 还有没有名额" | `search_subjects` |
| "按专业搜 COMP 系 BA(HONS) COMPUTING 的课" | `search_subjects`（按专业） |
| "帮我盯着 COMP2012 有没有人退课" | `start_course_sniper`（⏳） |

### 两步选课确认

`confirm_registration` 只有在你回传**同一组操作**的 `preview_registration` 指纹时才会
真正提交——确保你在提交前一定先看清会发生什么。

### 抢课刻意克制

高频"轰炸式"轮询**不支持**：那是被限速/封号最快的方式（反而抢不到），可能违反学校规定，
也对他人不公平。

强制频率下限（低于下限直接拒绝）：

- **open_time** 模式：重试间隔 ≥ 3 秒，总时长 ≤ 2 分钟。
- **watch_vacancy** 模式：轮询间隔 ≥ 60 秒。

在下限之内，任务具备**自愈能力**：每次尝试都会重新校验会话（登录过期会自动用
`.env` 凭据重新登录）；浏览器崩溃会关闭重启；网络抖动、页面异常等瞬时错误只算
一次未抢到。只有密码被拒、或同类错误连续 5 次才会提前终止任务。*open_time*
模式可传 `then_watch=true`：开抢窗口没抢到时自动转入捡漏轮询而不是放弃。
抢到 / 转捡漏 / 失败等终态会弹出 macOS 系统通知。

任务运行时让 Mac 保持唤醒——可在另一个终端跑 `caffeinate -dims`。
设 `ESTUDENT_HEADFUL=1` 可看到浏览器。

---

## 🔒 安全

- `.env`（凭据）、`.runtime/`（会话与抓取的页面 HTML，可能含个人数据）、截图**全部被
  git 忽略**，且**从未进入提交历史**。
- 仓库里只跟踪 `.env.example`（占位模板）。
- 凭据由 `config.py` 在本地读取，只用于从你本机登录 eStudent。

如果你 fork/clone，切勿提交你的 `.env`。

---

## 🏗 架构

```
src/estudent_mcp/
  server.py                  # 工具层，不碰浏览器
  backend/
    base.py                  # EStudentBackend 稳定接口
    playwright_backend.py    # 方案A：无头浏览器（当前）
    # future: hybrid_backend.py — 方案C：Playwright 登录 + httpx 取数（预留）
  parsers/                   # HTML -> dataclasses，纯函数可单测
  registration.py            # 指纹 + 摘要（两步确认）
  sniper.py                  # 调度 + 频率下限
  models.py  config.py  errors.py
tests/                       # 解析/选课/抢课单元测试
scripts/                     # 联调探测脚本（不含个人数据）
```

`EStudentBackend` 接口让以后可无痛换成更快的 HTTP 后端（方案 C），不动工具层和解析层。

---

## 🛠 为什么用浏览器而非 API？

eStudent **没有公开 API**，所以后端用 Playwright 驱动一个真实的无头 Chromium，像人一样
登录、读页面，再把 HTML 表格解析成结构化数据。

它能登录，是因为测试账号的 ADFS 没有验证码/2FA、且用的是真实浏览器——**不是**靠破解
验证。若学校加了验证码/2FA，正确做法是用有头模式（`ESTUDENT_HEADFUL=1`）手动过一次、
复用会话。

---

## 📄 许可

个人使用，不提供任何担保。
