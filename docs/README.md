# AI-SRPG 知识库根节点

> 这是 `docs/` 目录的唯一入口。每次新增文档领域时，请在此处更新索引。
> Agent 从此处出发，可定位到任何知识。
>
> **写作约束（AI 编写文档时必须遵守）**
>
> **写什么**
>
> - 写**设计意图与架构决策**：解释"为何这样设计"、"与哪些系统交互"，不描述实现步骤。代码已能自述的细节不再复述。
> - 写**跨系统关联**：本系统如何被其他系统驱动、产出被谁消费。单系统内部的步骤逻辑靠代码阅读。
> - 写**相对稳定的知识**：核心类名（如 `Job`、`PlayerSession`）可用行内代码引用；变量名、函数名、字段名随实现变化，引用它们等于复述代码，应规避。
> - 写**紧凑精要**：追求信息密度，避免铺陈。一段文字如果删掉后设计意图仍然完整，就该删。
> - 写**系统层面而非表现层**：只陈述引擎与系统的事实和关系，不写表现层的呈现、交互或实现归属。
>
> **怎么写**
>
> - 禁止代码块（` ``` `）。
> - 交叉引用格式：`→ 参见：[文档标题](相对路径)`，置于段落末或独立行。
> - 每篇聚焦一个系统；跨系统对比用交叉引用表达，不在同文档内做横向对比表。
> - 结论优先，比喻克制：先给结论性质的事实，再给支撑它的关系；过程性描述只做必要因果交代，比喻只在能一语点破时使用、不铺陈。
>
> **何时新建文档**
>
> - 新增文档的条件：出现了一个独立的设计概念，其意图和关联无法用现有文档的一两段话说清。
> - 否则更新已有文档。新建后立即更新本页索引。

---

## 知识领域索引

### wiki/ — 基建与工具

| 文档 | 简介 |
| ------ | ------ |
| [内容无关引擎（Content-Agnostic Engine）](wiki/content-agnostic-engine.md) | 蓝图是输入、引擎是机制执行器：结构词汇与题材词汇、机制与值、骨架与内容三条分界线；换故事的边界与防线 |
| [空间模型（Spatial Model）](wiki/spatial-model.md) | 空间词汇的唯一来源：舞台、大地图、地点、区域、大地图格；树存储、图移动、地点占一格 |
| [角色行为（Actor Actions）](wiki/actor-actions.md) | 大地图与地点内部两套动词：大地图不是场所、地点对外只占一格、一次位置变化说给三处听 |
| [角色计划（Actor Plan）](wiki/actor-plan.md) | 角色一轮里的「想」：大地图与地点各有一个计划系统、上下文取哪一层、行为如何以工具表达、失败即轮空；接管与自主只共享模型可见的决策形状 |
| [描述刷新（Description Refresh）](wiki/description-refresh.md) | 外观与环境两对「底稿/当前」：收集端的幂等守卫、主动强制重写、两种描述的尺度差异与失败出口 |
| [状态改动的边界（State Change Boundary）](wiki/state-change-boundary.md) | 读写在架构上不对等：基建模块只放原语，改记忆与 ECS 只在 systems 的 mixin 里；四类例外与回滚，守卫靠命名约定 + 类型入口 |
| [System 错误处理与回滚边界](wiki/system-error-handling.md) | system 何时可自行处理失败、何时必须上抛；整次 pass 的回滚粒度与 `StopPipeline` 的区别 |
| [Job 执行与事件日志（Job Execution）](wiki/job-execution.md) | 一次动作的异步执行单元：Procrastinate 队列状态 + `job_events` 过程日志、失败定位与事件记录 |
| [会话历史（Session History）](wiki/session-history.md) | 局级 append-only 事件流：一局一条流、每人一个游标、事件自带可见性；内存只留游标与上下文 |
| [上下文窗口管理（Context Window Management）](wiki/context-window-management.md) | agent 记忆膨胀的基础能力：上下文占比信号与手动压缩原语；自动触发待玩法规则落地 |
| [工具即上下文（Tools as Context）](wiki/tools-as-context.md) | 方法论：工具的 name/description/parameters 本身即上下文；据此把约束下沉到 schema / description / 对象说明，减少提示词重复与冗余 |
| [SRPG AI 操作 CLI（ai-srpg-agent-game）](wiki/run-agent-game.md) | 离线、快照驱动的游戏开发辅助入口；建局、查看、推进与记忆压缩，附 LLM 调用观测 |
| [服务端客户端（ai-srpg-client）](wiki/run-game-client.md) | 第二种运行方式：进程内经 HTTP 驱动常驻服务端；契约共用、房间与对局双生命周期、异步推进边界 |
| [图像生成模型（Replicate）](wiki/image-generation.md) | 显式选择模型的图像生成基建；Nano-Banana 支持的尺寸、宽高比与 Token 消耗 |
