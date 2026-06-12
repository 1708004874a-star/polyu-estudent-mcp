# PolyU eStudent MCP Server — 设计文档

日期：2026-06-10
状态：已与用户确认（历史版本——后续演进见下）

> **2026-06-12 注记**：本文档是 v1 原始设计，其中"7 个工具、不做抢课"已过时。
> 实际实现演进为 9 个工具（新增 start_course_sniper / sniper_status），抢课为
> 克制频率 + 下限保护 + 自愈重试（详见仓库根 CLAUDE.md 与 README.md，以
> CLAUDE.md 为当前事实来源）。其余架构（三层 + 可插拔后端 + 两步确认）与实现一致。

## 目标

构建一个本地 MCP server，让 Claude Code 能代替用户操作香港理工大学（PolyU）的
eStudent 学生门户，支持：查成绩/GPA、查课表、查考试安排、搜索科目、选课/退课。

## 关键约束与前提

- 登录方式：NetID + 密码，无 2FA（用户确认）。
- 凭据存放在项目根目录 `.env`（gitignore），仅存在用户本机。
- 技术路线：**方案 A（Playwright 浏览器自动化）起步，后续向方案 C（混合：
  Playwright 登录 + HTTP 取数）演进**。架构必须为此预留接口。
- 开发期无法凭空看到登录后的页面，selector/parser 需要联调阶段配合真实账号完成。
- 对学校服务器保持克制：操作间最小间隔，不做高频轮询/抢课；遵守学校可接受使用政策。

## 总体架构

项目目录：`~/Desktop/Entertain_Apps/estudent-mcp`，Python + FastMCP + Playwright。

三层结构：

1. **MCP 工具层**（`src/estudent_mcp/server.py`）
   定义 7 个工具、参数校验、选课二次确认机制。不直接接触浏览器。
2. **后端适配层**（`src/estudent_mcp/backend/`）
   抽象接口 `EStudentBackend`（login、get_grades、get_timetable、
   get_exam_schedule、search_subjects、preview_registration、
   confirm_registration、session_status）。
   - 现在实现：`PlaywrightBackend`。
   - 将来方案 C：新增 `HybridBackend`（Playwright 登录拿 cookie，httpx 取数），
     实现同一接口，工具层零改动。
3. **解析层**（`src/estudent_mcp/parsers/`）
   HTML → 结构化数据的纯函数，独立可单测。这是 A/C 两方案的共享资产。

## MCP 工具（7 个，单一 server）

| 工具 | 读/写 | 说明 |
|---|---|---|
| `session_status` | 读 | 是否已登录、会话是否过期 |
| `get_grades` | 读 | 各学期成绩与 GPA，可指定学期 |
| `get_timetable` | 读 | 上课时间表 |
| `get_exam_schedule` | 读 | 考试时间地点 |
| `search_subjects` | 读 | 按科目代码/关键词搜索科目及剩余名额 |
| `preview_registration` | 读 | 选课/退课预演：返回操作摘要（科目、班别、冲突），不提交 |
| `confirm_registration` | **写** | 必须携带 preview 返回的操作摘要才真正提交，返回系统回执 |

设计要点：

- 读写分离 + 两步确认：任何真实变更必须先 `preview_registration`，
  用户看到摘要后才能 `confirm_registration`。confirm 的参数必须与 preview
  返回的摘要匹配（携带 preview 生成的操作指纹），防止跳过预览直接提交。
- 7 个独立工具便于在 Claude Code 权限系统中区分粒度
  （如：查询类免确认，`confirm_registration` 每次人工批准）。

## 会话管理

- Playwright `storage_state` 持久化到本地文件，避免每次登录。
- 检测到会话过期时，自动用 `.env` 凭据重新登录。
- 默认 headless；环境变量 `ESTUDENT_HEADFUL=1` 切到有头模式便于调试。

## 错误处理

- 页面结构不匹配（学校改版）时，错误信息附带自动截图的本地路径。
- 登录失败区分：凭据错误（提示用户检查 `.env`）vs 网络/页面超时（可重试）。
- 所有工具返回结构化错误而非裸异常。

## 测试策略

- **parser 单测**：用联调阶段保存的真实 HTML fixture（脱敏后）测试解析逻辑。
- **端到端**：只读功能用真实账号验证；选课只验证到 preview 一步，
  confirm 的真实提交由用户在真正需要选课时验证。

## 开发流程（两阶段）

1. **骨架阶段**（可独立完成）：项目结构、7 个工具定义、`EStudentBackend` 接口、
   登录流程框架、两步确认机制、parser 单测框架。
2. **联调阶段**（需用户配合）：用户填好 `.env`，以有头浏览器实际走
   登录 → 成绩页 → 课表页 → 选课页，保存真实页面 HTML 为 fixture，
   据此实现 selector 与 parser。

## 不做的事（YAGNI）

- 不做抢课/定时轮询。
- 不做多账号支持。
- 不做 2FA 处理（当前登录无 2FA；若学校日后启用，届时再扩展）。
- 第一版不实现 HybridBackend，只保证接口可插拔。
