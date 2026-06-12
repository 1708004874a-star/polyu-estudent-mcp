# estudent-mcp

本地 MCP server：让 Claude Code 操作 PolyU eStudent 门户（查成绩/课表/考试、搜课、
选退课、定时抢课）。门户无公开 API，全部经 Playwright 无头 Chromium 模拟操作；
登录走 ADFS SSO（NetID+密码，无 2FA）。

## 常用命令

```bash
uv sync --extra dev                          # 装依赖（必须带 --extra dev，否则
                                             # uv run pytest 会落到 anaconda 的 pytest）
uv run pytest -q                             # 必须在本项目目录下跑（27 个测试）
.venv/bin/python -m playwright install chromium
claude mcp get estudent                      # MCP 已以 user scope 注册，应显示 ✔ Connected
```

联调探针（需要 .env 凭据，输出存到 .runtime/probe/，已 gitignore）：
`scripts/probe_subject_search.py`、`probe_by_program.py`、`analyze_search.py`、`analyze_detail.py`。

## 架构（三层 + 调度）

- `src/estudent_mcp/server.py` — MCP 工具层（9 个工具），不碰浏览器。
- `src/estudent_mcp/backend/base.py` — `EStudentBackend` 抽象接口；
  `playwright_backend.py` 是当前唯一实现（方案 A）。接口保持与浏览器无关,
  为将来 HybridBackend（方案 C：登录拿 cookie + httpx 取数）留位。
- `src/estudent_mcp/parsers/` — HTML→dataclass 纯函数，BeautifulSoup，全部可单测。
- `src/estudent_mcp/sniper.py` — 抢课调度：频率下限、错误分类自愈、open_time→捡漏回退。

## 关键不变量（改代码前必读）

- **两步确认**：`confirm_registration` 必须携带 `preview_registration` 返回的
  SHA256 指纹，抢课的自动提交也走同一路径，不得绕过。
- **频率下限是硬约束**：open_time 重试 ≥3s、密集窗口 ≤30min；watch_vacancy ≥30s。
  低于下限抛 `FrequencyError`。不做秒级以下轰炸（封号风险 + 学校 AUP）。
- **错误分类**（sniper）：门户不可达（超时/连接错）按持续时长判定，连续宕机
  30min 才放弃；`PageStructureError` 连续 5 次终止；`CredentialsError` 立即终止。
- **fast-fail**：开抢窗口内 `set_fast_fail(True)` 把登录链路超时从 45s 压到 12s，
  窗口结束必须恢复（sniper 的 finally 已保证）。
- **会话自愈**：每次尝试先 `login()`——会话失效自动重登；浏览器崩溃由
  `backend.close()` 重置，下次 `_ensure_browser()` 全新拉起。

## 安全红线

- `.env`（真实 NetID/密码）、`.runtime/`（会话 state + 抓取的真实页面 HTML，含个人
  数据）、截图全部 gitignore，**绝不能进 git**。仓库是公开的
  （github.com/1708004874a-star/polyu-estudent-mcp），推送前自查敏感内容。
- 文档/示例里 NetID 只能用占位符 `12345678d`，不要写真实学号。
- tests/fixtures/ 里的 HTML 是手工编造的假数据，不是真实抓取页。

## 联调状态（截至 2026-06-12）

- ✅ 已对真实门户校准：login、get_grades、get_timetable、get_exam_schedule、
  search_subjects（按科目 + 按专业、自动选学期、翻页、单科下钻组级名额）。
- ⏳ 待选课窗口开放才能联调：`preview_registration`/`confirm_registration` 的真实
  提交（现在 confirm 直接抛 NEEDS_CALIBRATION 性质的 PageStructureError）、抢课
  真实下单。调度/自愈/通知层已完成并有单测。
- 页面是 JSF+RichFaces：元素 id 前缀 `mainForm:`，结果表 `table[id$=searchTable]`，
  翻页是 datascroller AJAX（点 `td[onclick*="next"]`），下拉级联（按专业模式
  dept→prog）要等 ~2500ms。

## 其他约定

- 通知用 macOS `osascript display notification`（server.py `_notify_macos`）。
- 长时间抢课任务建议用户另开终端跑 `caffeinate -dims` 防休眠。
- README.md 是双语（先全英后全中），改功能时两段都要同步,测试数量也别忘了改。
