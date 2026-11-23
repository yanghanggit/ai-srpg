"""大地图上的计划：这一刻站在哪一格、视野里的相邻格上有什么。

大地图不是场所：没有在场者、也没有环境，只有坐标、地点，以及站在格上的别人。
"""

from typing import Awaitable, Callable, Dict, Final, List, Tuple, Type, final, override

from ...entitas import Entity, GroupEvent, Matcher, ReactiveProcessor
from ...entitas.components import Component
from ...llm import ToolDefinition, ToolFunction
from ...models import (
    ActorComponent,
    ActorEnterSiteAction,
    ActorPlanAction,
    ActorTravelAction,
    ActorWaitAction,
)
from ...utils import prompt_builder
from ..context import SRPGGame
from ..entities.queries import (
    MapCell,
    get_map_position,
    get_site_at_cell,
    get_visible_cells,
    is_on_map,
)
from .actor_plan_mixin import ActorPlanMixin

############################################################################################################
# 大地图上能发起的行为
_TRAVEL_TOOL: Final[ToolDefinition] = ToolDefinition(
    function=ToolFunction(
        name="travel",
        description="在大地图上移动到相邻的一格。",
        parameters={
            "type": "object",
            "properties": {
                "x": {"type": "integer", "description": "目标格子的横坐标"},
                "y": {"type": "integer", "description": "目标格子的纵坐标"},
            },
            "required": ["x", "y"],
        },
    )
)

_ENTER_TOOL: Final[ToolDefinition] = ToolDefinition(
    function=ToolFunction(
        name="enter",
        description="走进脚下这个地点。只有站在地点所在的格子上才能进。",
        parameters={
            "type": "object",
            "properties": {"site": {"type": "string", "description": "要进的地点名字"}},
            "required": ["site"],
        },
    )
)

_WAIT_TOOL: Final[ToolDefinition] = ToolDefinition(
    function=ToolFunction(
        name="wait",
        description="这一轮什么都不做，留在原地。",
        parameters={"type": "object", "properties": {}},
    )
)

_MAP_TOOLS: Final[List[ToolDefinition]] = [_TRAVEL_TOOL, _ENTER_TOOL, _WAIT_TOOL]

_MAP_ACTIONS: Final[Tuple[Type[Component], ...]] = (
    ActorTravelAction,
    ActorEnterSiteAction,
    ActorWaitAction,
)


############################################################################################################
@prompt_builder
def map_plan_prompt(
    *,
    location: str,
    cells: List[str],
    same_cell: Tuple[str, ...] = (),
    compact: bool = False,
) -> str:
    """大地图上计划的任务说明：这一刻的位置、同格的人与视野内的相邻格。

    ``compact`` 给记忆用：视野压成一行，只留地点与别人——空地在记忆里没有信息量。
    """
    lines = [f"当前位置：{location}"]
    if same_cell:
        lines.append(f"与你同格：{'、'.join(same_cell)}")
    lines.extend(["", "视野："])
    if compact:
        lines.append("、".join(cells) if cells else "全是空地")
    else:
        lines.extend(f"- {cell}" for cell in cells)
    lines.extend(
        [
            "",
            "用工具表达你这一轮的行动：在大地图上移动到相邻一格、进入地点，或者原地不动。一次只做一件事。",
        ]
    )
    return "\n".join(lines)


############################################################################################################
@final
class MapPlanSystem(ReactiveProcessor, ActorPlanMixin):
    """消费 ``ActorPlanAction``：给站在大地图上的角色跑一轮计划。"""

    ##########################################################################################
    def __init__(self, game: SRPGGame) -> None:
        ReactiveProcessor.__init__(self, game)
        ActorPlanMixin.__init__(self, game)

    ##########################################################################################
    @override
    def get_trigger(self) -> Dict[Matcher, GroupEvent]:
        return {Matcher(all_of=[ActorPlanAction, ActorComponent]): GroupEvent.ADDED}

    ##########################################################################################
    @override
    def filter(self, entity: Entity) -> bool:
        """只处理站在大地图上、且挂着计划动作的角色。"""
        return entity.has(ActorComponent, ActorPlanAction) and is_on_map(
            self._game, entity
        )

    ##########################################################################################
    @override
    def allowed_actions(self) -> Tuple[Type[Component], ...]:
        return _MAP_ACTIONS

    ##########################################################################################
    @override
    async def react(self, entities: List[Entity]) -> None:
        for entity in sorted(entities, key=lambda item: item.index):
            # 「该想一次」在处理的同一刻被消费；行为动作留给后面的 system
            entity.remove(ActorPlanAction)
            record_message = map_plan_input(self._game, entity, compact=True)
            decided = self.predecided_action(entity)
            if decided is not None:
                self.record_decision(entity, action=decided, prompt=record_message)
                continue
            await self.run_plan(
                entity,
                input_message=map_plan_input(self._game, entity, compact=False),
                record_message=record_message,
                tools=_MAP_TOOLS,
                handlers=self._handlers(entity),
            )

    ##########################################################################################
    ##########################################################################################
    def _handlers(
        self, entity: Entity
    ) -> Dict[str, Callable[..., Awaitable[str] | str]]:
        return {
            "travel": lambda x, y: self.mount_action(entity, ActorTravelAction, x, y),
            "enter": lambda site: self.mount_action(entity, ActorEnterSiteAction, site),
            "wait": lambda: self.mount_action(entity, ActorWaitAction),
        }


############################################################################################################
def map_plan_input(srpg_game: SRPGGame, entity: Entity, *, compact: bool) -> str:
    """大地图层这一刻的输入；计划与接管共用，只有 compact 不同。

    脚下那一格不重复写「这里是什么」——位置行已经说了；但格上的人必须写出来，
    否则同一格上的两个人互相瞎。
    """
    map_entity, position = get_map_position(srpg_game, entity)
    x, y = position.x, position.y
    here = get_site_at_cell(srpg_game, map_entity, position)
    cells = get_visible_cells(srpg_game, entity)
    same_cell = [cell for cell in cells if (cell.x, cell.y) == (x, y)]
    around = [_describe_cell(cell) for cell in cells if (cell.x, cell.y) != (x, y)]
    if compact:
        around = [cell for cell in around if not cell.endswith(" 空地")]
    return map_plan_prompt(
        location=f"({x},{y}) {here.name if here is not None else '空地'}",
        same_cell=same_cell[0].actors if same_cell else (),
        cells=around,
        compact=compact,
    )


############################################################################################################
def _describe_cell(cell: MapCell) -> str:
    """一格一行：坐标、格上的地点（或空地），以及在格上的角色。"""
    where = cell.site if cell.site is not None else "空地"
    line = f"({cell.x},{cell.y}) {where}"
    if cell.actors:
        line = f"{line}，在场 {'、'.join(cell.actors)}"
    return line


###############################################################################
__all__ = ["MapPlanSystem", "map_plan_input", "map_plan_prompt"]
