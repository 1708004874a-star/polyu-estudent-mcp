# eStudent MCP

> A local [MCP](https://modelcontextprotocol.io) server that lets Claude Code
> operate the PolyU **eStudent** portal — check grades, timetable and exams,
> search subjects, and (work in progress) add/drop & snipe courses.
>
> 一个本地 [MCP](https://modelcontextprotocol.io) 服务器，让 Claude Code 帮你操作
> 香港理工大学 **eStudent** 门户：查成绩、课表、考试，搜课，以及（开发中）选课/退课
> 与抢课。

**Everything runs on your own machine. Your NetID and password never leave it.**
**所有操作都在你本机运行，账号密码绝不外传。**

> ⚠️ This is an unofficial personal tool, not affiliated with PolyU. Use it on
> your own account and at your own risk, and respect the university's
> acceptable-use policy.
> 本项目为非官方个人工具，与理大无关。仅用于你自己的账号，风险自负，并请遵守学校的
> 网络使用规定。

---

## ✨ Features & Status / 功能与完成度

| Tool / 工具 | What it does / 功能 | Status / 状态 |
|---|---|---|
| `session_status` | Is there a live logged-in session? / 是否有有效登录会话 | ✅ Live-verified / 已实测 |
| `get_grades` | Grades & GPA, optional `term` filter / 成绩与 GPA，可按学期过滤 | ✅ Live-verified / 已实测 |
| `get_timetable` | Class timetable / 上课时间表 | ✅ Live-verified / 已实测 |
| `get_exam_schedule` | Exam dates / venues / seats / 考试日期、地点、座位 | ✅ Live-verified / 已实测 |
| `search_subjects` | Search by code/keyword **or** by programme; auto term, pagination, per-group vacancy on a single match / 按代码或关键词、或按专业搜课；自动选学期、自动翻页、单科目下钻名额 | ✅ Live-verified / 已实测 |
| `preview_registration` | Preview add/drop — **never submits** / 预演选退课，**不提交** | ⏳ Logic done; live calibration pending / 逻辑完成，待联调 |
| `confirm_registration` | Submit add/drop (needs preview `fingerprint`) / 提交选退课（需预演指纹） | ⏳ Pending registration window / 待选课窗口开放 |
| `start_course_sniper` | Automated grab (open-time / vacancy-watch) / 定时抢课（开放瞬间 / 满员捡漏） | ⏳ Scheduler done; real submit pending / 调度完成，真实提交待接通 |
| `sniper_status` | List / inspect / stop sniper jobs / 查看、检查、停止抢课任务 | ✅ Works / 可用 |

### Done & verified / 已完成并验证

- **Login** via PolyU ADFS SSO (NetID + password, no 2FA for the tested account);
  session is persisted and reused. / **登录**走理大 ADFS 单点登录（账号密码，测试账号无
  2FA），会话持久化复用。
- **Read tools** (`get_grades` / `get_timetable` / `get_exam_schedule`) calibrated
  against the live portal. / **读取类工具**已对真实门户校准。
- **`search_subjects`** — both **by subject** (code/title) and **by programme**
  (department → programme cascade); tries each term automatically when none is
  given; walks the result pagination to collect all subjects; when the query
  resolves to exactly one subject it drills into the detail page to return each
  teaching group's **vacancy** (handles `5` open / `(4)` reserved / `W=.. Top-up
  vac=..` waitlist). / **搜课**支持按科目和按专业两种模式；无学期时自动逐学期尝试；
  自动翻页收齐全部科目；命中单个科目时下钻详情页返回每个教学组的**名额**（识别
  `5` 开放 / `(4)` 保留 / `W=.. Top-up vac=..` 候补）。
- **Two-step registration invariant**, **sniper frequency floors**, and all
  **parsers** are unit-tested (19 tests). / **两步选课确认**、**抢课频率下限**、所有
  **解析器**均有单测（19 个）。

### Not finished yet / 尚未完成

- `preview_registration` / `confirm_registration` real submission, and the
  sniper's real grab path, can only be calibrated when the **subject
  registration window is open** (it was closed during development). The
  scheduling, frequency safety, and preview→confirm fingerprint logic are
  already built and tested. / 选课/退课的真实提交、抢课真实下单，必须等**选课窗口
  开放**才能联调（开发期间未开放）。调度、频率保护、预演→确认指纹逻辑已写好并测试。
- `search_subjects` keyword results across many pages are de-duplicated but
  large title searches return the offered subjects only (no extra filters yet).
  / 关键词大范围搜索已去重，但暂未加更多筛选条件。

---

## 🚀 Installation / 安装

**Prerequisites / 前置要求**: macOS, Python 3.12, [`uv`](https://docs.astral.sh/uv/),
and [Claude Code](https://claude.com/claude-code). / macOS、Python 3.12、`uv`、
Claude Code。

```bash
# 1. Clone / 克隆
git clone https://github.com/<your-account>/estudent-mcp.git
cd estudent-mcp

# 2. Create the venv and install deps / 创建虚拟环境并装依赖
uv sync --extra dev

# 3. Install the headless browser Playwright drives / 安装 Playwright 用的浏览器
.venv/bin/python -m playwright install chromium

# 4. Configure your credentials / 配置凭据
cp .env.example .env
#    then edit .env — see the next section
#    然后编辑 .env —— 见下一节
```

### Configure `.env` / 配置 `.env`

`.env` is **git-ignored** and must contain your real credentials. It never gets
committed or pushed. / `.env` **已被 git 忽略**，填你的真实凭据，绝不会被提交或推送。

```ini
ESTUDENT_NETID=your_netid          # e.g. 12345678d  你的 NetID
ESTUDENT_PASSWORD=your_password    # your portal password  门户密码
ESTUDENT_BASE_URL=https://www.polyu.edu.hk/student
ESTUDENT_HEADFUL=0                 # 1 = show the browser (debugging) 显示浏览器调试
```

```bash
chmod 600 .env   # restrict to your user / 仅本人可读写
```

### Verify / 验证

```bash
uv run pytest -q          # 19 tests should pass / 应有 19 个测试通过
```

---

## 🔌 Register with Claude Code / 注册到 Claude Code

```bash
claude mcp add estudent -s user -- \
  "$(pwd)/.venv/bin/python" -m estudent_mcp.server
```

`-s user` registers it globally (available in every project). Drop it for the
current project only. Confirm it connected: / `-s user` 是全局注册（所有项目可用），
去掉则只对当前项目生效。确认连接：

```bash
claude mcp get estudent     # should show ✔ Connected / 应显示 ✔ Connected
```

---

## 💬 Usage / 使用

Just talk to Claude Code in natural language — it picks the right tool. /
直接用自然语言跟 Claude Code 说，它会自动选用合适的工具。

| You say / 你说 | Tool used / 用到的工具 |
|---|---|
| "查一下我的成绩和 GPA" / "What's my GPA?" | `get_grades` |
| "这学期课表" / "Show my timetable" | `get_timetable` |
| "考试安排" / "When are my exams?" | `get_exam_schedule` |
| "搜一下 COMP1011 还有没有名额" / "Find COMP1011 and its vacancy" | `search_subjects` |
| "按专业搜 COMP 系 BA(HONS) COMPUTING 的课" | `search_subjects` (by programme) |
| "帮我盯着 COMP2012 有没有人退课" / "Watch COMP2012 for a vacancy" | `start_course_sniper` (⏳) |

### Two-step registration / 两步选课确认

`confirm_registration` only submits if you pass the `fingerprint` returned by a
`preview_registration` of the **same** actions — so you can never add/drop a
subject without first seeing exactly what will change. / `confirm_registration`
只有在你回传**同一组操作**的 `preview_registration` 指纹时才会真正提交——确保你在
提交前一定先看清会发生什么。

### The sniper is deliberately restrained / 抢课刻意克制

High-frequency "bombing" polling is **not supported**, by design — it's the
fastest way to get rate-limited/banned (so you'd miss the course anyway), may
violate the acceptable-use policy, and is unfair to others. /
高频"轰炸式"轮询**不支持**：那是被限速/封号最快的方式（反而抢不到），可能违反学校
规定，也对他人不公平。

Frequency floors are enforced (sub-floor configs are rejected): /
强制频率下限（低于下限直接拒绝）：

- **open_time** mode: retry ≥ 3s, total window ≤ 2 min. / 重试间隔 ≥ 3 秒，总时长 ≤ 2 分钟。
- **watch_vacancy** mode: poll ≥ 60s. / 轮询间隔 ≥ 60 秒。

Keep your Mac awake while a job runs. Set `ESTUDENT_HEADFUL=1` to watch the
browser. / 任务运行时让 Mac 保持唤醒。设 `ESTUDENT_HEADFUL=1` 可看到浏览器。

---

## 🔒 Security / 安全

- `.env` (your credentials), `.runtime/` (saved session + any captured page
  HTML, which may contain personal data), and screenshots are **all git-ignored**
  and were **never committed** to history. / `.env`（凭据）、`.runtime/`（会话与抓取的
  页面 HTML，可能含个人数据）、截图**全部被 git 忽略**，且**从未进入提交历史**。
- Only `.env.example` (a placeholder template) is tracked. / 仓库里只跟踪
  `.env.example`（占位模板）。
- Credentials are read locally by `config.py` and used solely to log into
  eStudent from your machine. / 凭据由 `config.py` 在本地读取，只用于从你本机登录
  eStudent。

If you fork/clone, never commit your `.env`. / 如果你 fork/clone，切勿提交你的 `.env`。

---

## 🏗 Architecture / 架构

```
src/estudent_mcp/
  server.py                  # MCP tool layer (no browser code) / 工具层，不碰浏览器
  backend/
    base.py                  # EStudentBackend interface (stable) / 稳定接口
    playwright_backend.py    # scheme A: headless browser (current) / 方案A：无头浏览器
    # future: hybrid_backend.py — scheme C: Playwright login + httpx fetch / 方案C预留
  parsers/                   # HTML -> dataclasses (pure, unit-tested) / 纯函数解析，可单测
  registration.py            # fingerprint + summary (two-step invariant) / 两步确认
  sniper.py                  # scheduler + frequency floors / 调度 + 频率下限
  models.py  config.py  errors.py
tests/                       # parser / registration / sniper unit tests / 单元测试
scripts/                     # joint-debug probes (no PII committed) / 联调探测脚本
```

The `EStudentBackend` interface lets a faster HTTP backend (scheme C) be swapped
in later without touching the tools or parsers. / `EStudentBackend` 接口让以后可
无痛换成更快的 HTTP 后端（方案 C），不动工具层和解析层。

---

## 🛠 Why a browser instead of an API? / 为什么用浏览器而非 API？

eStudent exposes **no public API**, so the backend drives a real headless
Chromium (via Playwright) that logs in and reads pages exactly like a human
would, then parses the HTML tables into structured data. / eStudent **没有公开
API**，所以后端用 Playwright 驱动一个真实的无头 Chromium，像人一样登录、读页面，再把
HTML 表格解析成结构化数据。

It passes login because PolyU's ADFS presented no CAPTCHA/2FA for the tested
account and a real browser is used — **not** by defeating any verification. If
the school adds a CAPTCHA/2FA, the right move is headful mode (`ESTUDENT_HEADFUL=1`)
to solve it once and reuse the session. / 它能登录，是因为测试账号的 ADFS 没有验证码/
2FA、且用的是真实浏览器——**不是**靠破解验证。若学校加了验证码/2FA，正确做法是用有头
模式手动过一次、复用会话。

---

## 📄 License / 许可

Personal use. No warranty. / 个人使用，不提供任何担保。
