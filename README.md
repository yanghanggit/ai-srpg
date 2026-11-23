# AI-SRPG

一个基于**多智能体架构**与 **ECS (Entity Component System)** 的 AI 驱动型 SRPG（Strategy RPG）框架：
以 ECS 承载可重建的世界状态与快照，以 LLM（DeepSeek）驱动叙事生成；玩法规则与 LLM 决策待重建。

> 本仓库是**引擎 + 常驻服务端 + 服务端真相**，自带一个面向 AI 代理的命令行工具与 LLM 调用留痕。

## 🛠️ 技术栈

- **Python 3.12+** / **FastAPI** / **Pydantic v2**
- **DeepSeek**（chat + reasoner）
- **PostgreSQL**（pgvector 为基建，当前业务未调用）
- **Sentence Transformers** / **Replicate**（嵌入与文生图基建，当前业务未调用）
- **uv** / **Black** / **Ruff** / **MyPy** / **Pytest**

## 🚀 快速开始

### 环境要求

- Python 3.12+
- PostgreSQL
- [uv](https://github.com/astral-sh/uv)

### 安装

```bash
git clone <repository-url>
cd ai-srpg

make install        # 等价 uv sync（含 dev 依赖组）
# 或
uv sync

source .venv/bin/activate        # macOS/Linux
# .\.venv\Scripts\activate       # Windows
```

### 配置

复制 `cp .env.example .env`，填好 `DEEPSEEK_API_KEY`、`GAME_SERVER_PORT` 等。PostgreSQL 连接全部来自 `AI_SRPG_DB_HOST` / `AI_SRPG_DB_PORT` / `AI_SRPG_DB_NAME` / `AI_SRPG_DB_USER` / `AI_SRPG_DB_PASSWORD`；缺少任一变量（密码可留空）会在导入配置时直接失败。JWT 同样全部来自环境变量：`AI_SRPG_JWT_SIGNING_KEY`（至少 32 字符，务必自己生成，仓库不提供默认密钥）、`AI_SRPG_JWT_REFRESH_TOKEN_EXPIRE_DAYS`、`AI_SRPG_JWT_ACCESS_TOKEN_EXPIRE_MINUTES`。

### 重置开发数据库

```bash
uv run python -m scripts.reset_dev_db     # 种子蓝图写入 .blueprints/，并重建空库（表结构 + Procrastinate + 测试用户）
```

> 会删除目标库中的全部数据，运行前请确认 `.env` 指向的是开发库。

同一次运行还会把蓝图里每个实体（演员/舞台/世界）的 system prompt 导出到
`logs/blueprints/<游戏名>/`：一实体一个 md，另有一份 `index.md` 概览。内容即该实体
进游戏后的 `memories[0]`，用于逐段核对提示词；`make clean-temp` 会一并清掉。

## ▶️ 启动与使用

### 启动游戏服务器

```bash
uv run ai-srpg-server                  # --port 缺省读 .env 的 GAME_SERVER_PORT
uv run ai-srpg-server --host 0.0.0.0 --port 8000

# 验证
curl http://127.0.0.1:8000/
```

### 客户端-服务端基本操作（无鉴权阶段）

当前是基建阶段：**没有鉴权**，路径里的 `user_name` 就是身份；**没有玩法规则**，
一次 `advance` 跑一遍 pass，并追加执行前/结果两条快照。舞台心跳
`StagePulseSystem` 保留为可插拔样例，默认管线不挂。用客户端 CLI 走完整条链路
（服务端另开终端）：

```bash
uv run ai-srpg-server --host 127.0.0.1 --port 8000

export AI_SRPG_SERVER_URL=http://127.0.0.1:8000     # 或每条命令传 --server

uv run ai-srpg-client info                         # 服务自描述与路由清单
uv run ai-srpg-client enter alice                  # 进入房间（=登录）
uv run ai-srpg-client open alice Game1             # 开局：最新快照或蓝图新建
uv run ai-srpg-client advance alice Game1          # 派发一次 pass 并等待终态
uv run ai-srpg-client snapshots alice Game1        # 执行前 + 成功后各一条快照
uv run ai-srpg-client messages alice               # 会话历史增量
uv run ai-srpg-client play alice Game1 --rounds 3  # 无人值守连跑 3 轮
uv run ai-srpg-client leave alice                  # 离开房间（快照保留）
```

前提：`.blueprints/Game1.json` 已存在（`uv run python -m scripts.reset_dev_db`
会一并生成蓝图与建表）。

约定与注意：

- 房间与游戏是两个生命周期：先 `enter` 再 `open`；`leave` 不影响已落库的快照。
- 一房 = 一局：状态响应里的 `room_id` / `owner` / `seats` 描述这一局本身；当前一人一房，
  `room_id` 就是房主用户名，多人席位的基础设施已就位但玩法仍按单人推进。
- `advance` 默认等 job 终态；`--no-wait` 只返回 job id，进度用 `job` 子命令看。
- 房间级 queueing_lock 只挡「排队中」的重复派发（409）；已出队执行时可再次派发，
  执行期由房间锁串行。
- 客户端与服务端共用同一份传输契约；原始 HTTP 与 OpenAPI 同样可用：
  `/openapi.json`、`/docs`、`/redoc`，路由按 `rooms` / `games` /
  `session-messages` / `components` / `entities` / `jobs` 分组。
- **不要**在不可信网络上用 `--host 0.0.0.0`：路由本身没有鉴权。

### 后台定时任务

服务器在 `lifespan` 内启动两个进程内定时循环（与 `RoomRegistry` 同进程 / 同事件循环）：

| 环境变量 | 默认 | 说明 |
| --- | --- | --- |
| `GAME_ROOM_REAP_INTERVAL_SECONDS` | `60` | 空闲房间回收的扫描间隔 |
| `GAME_ROOM_TTL_SECONDS` | `1800` | 房间空闲多久后被回收；`<=0` 关闭回收 |
| `GAME_TICK_INTERVAL_SECONDS` | `60` | 游戏玩法定时器（`gameplay/scheduler.py`）的间隔；`<=0` 关闭 |

游戏玩法定时器目前仅为骨架（`on_room_tick` 为空实现），用于后续添加“定时查看 ECS 状态并触发玩法”的逻辑。

### 面向 AI 代理的工具（非人工操作）

游戏的「操作」由 AI 代理驱动，日常无需人手动执行。此处仅列入口，
**用法、参数与环境变量见对应文档**：

| 命令 | 用途 | 文档 |
| --- | --- | --- |
| `ai-srpg-agent-game` | 离线、快照驱动推进（建局、查看、推进、压缩；含 LLM 调用观测） | [docs/wiki/run-agent-game.md](docs/wiki/run-agent-game.md) |
| `ai-srpg-client` | 进程内 HTTP 驱动服务端（进入房间、开局、推进、快照与会话读取） | [docs/wiki/run-game-client.md](docs/wiki/run-game-client.md) |

`uv run <命令> --help` 可列出全部子命令。

## 🔧 开发

```bash
make install        # uv sync（含 dev 依赖组）+ editable 安装
make test           # uv run pytest tests/ -v
make lint           # uv run mypy --strict + ruff check
make format         # black 格式化
```

### 测试约定

- 测试一律 `from ai_srpg... import ...`（**不要** `from src.ai_srpg...`）——测试、脚本、生产共用同一导入身份。
- `tests/` 不是包（无 `__init__.py`）；pytest 走 `--import-mode=importlib` + `pythonpath=["src"]`。
- 共享测试代码放包里（如 `src/ai_srpg/entitas/testing.py`）或 `tests/conftest.py` 的 fixture，不要 `from tests... import`。

> **Windows 用户**：需装 [Git Bash](https://git-scm.com/) 与 Make（`winget install ezwinports.make`）。

## 📚 文档

架构文档位于 `docs/`，以 [docs/README.md](docs/README.md) 为根节点。

## 🤝 贡献

欢迎提交 Issue 和 Pull Request！

## 📄 许可证

[许可证信息]
