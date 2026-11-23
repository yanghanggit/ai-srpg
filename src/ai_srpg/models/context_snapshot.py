"""ECS 快照信封：整块导出 / 恢复 context 的 core 数据。

只包含实体与组件；agent 记忆等平级系统各自管理自己的快照。
``entities`` 的格式与 ``entitas.serialization.ContextData`` 一致。
"""

from typing import Final, final

from pydantic import BaseModel

from ..entitas import ContextData

#: 快照格式版本；改变 ``ContextData`` 结构（含组件类型名）时递增；旧快照会被明确拒绝。
SNAPSHOT_FORMAT_VERSION: Final[int] = 5


###############################################################################################################################################
@final
class ContextSnapshot(BaseModel):
    """一次 ECS 核心状态的不可变快照。

    - ``game``：快照所属游戏名，恢复时用于防串档；
    - ``entity_naming_counter``：实体创建顺序计数器（在 context 之外）；
    - ``entities``：按实体名索引的组件数据，顺序即创建顺序。
    """

    format_version: int = SNAPSHOT_FORMAT_VERSION
    game: str
    entity_naming_counter: int = 0
    entities: ContextData


###############################################################################
__all__ = ["ContextSnapshot", "SNAPSHOT_FORMAT_VERSION"]
