"""一次游戏运行的组合快照：ECS 与 agent 记忆两个平级子系统。"""

import datetime
from typing import Final, final

from pydantic import BaseModel

from .agent_memory_snapshot import AgentMemorySnapshot
from .context_snapshot import ContextSnapshot

#: 组合快照格式版本；子结构各自还有版本号。
GAME_SNAPSHOT_FORMAT_VERSION: Final[int] = 4


###############################################################################################################################################
@final
class GameSnapshot(BaseModel):
    """ECS 核心状态与 agent 记忆的成对快照。"""

    format_version: int = GAME_SNAPSHOT_FORMAT_VERSION
    ecs: ContextSnapshot
    memory: AgentMemorySnapshot

    ###########################################################################
    @property
    def game(self) -> str:
        """快照所属游戏名（取自 ECS 快照）。"""
        return self.ecs.game


###############################################################################
@final
class GameSnapshotInfo(BaseModel):
    """快照列表项：只含查看历史所需的元数据，不展开两个子系统。"""

    id: int
    game_name: str
    format_version: int
    created_at: datetime.datetime
    entity_count: int
    memory_count: int


###############################################################################
@final
class GameSummary(BaseModel):
    """一局的概览：最新快照 + 累计条数，用于列房间里的所有对局。"""

    game_name: str
    latest_snapshot_id: int
    snapshot_count: int
    updated_at: datetime.datetime
    entity_count: int


###############################################################################
__all__ = [
    "GameSnapshot",
    "GameSnapshotInfo",
    "GameSummary",
    "GAME_SNAPSHOT_FORMAT_VERSION",
]
