"""ActionCleanupSystem 单元测试。

动作组件用 ``@register_action_component_type`` 声明，系统清的是真实注册表
``ACTION_COMPONENT_TYPES``，因此这里同时覆盖「声明 → 注册 → 收集 → 清除」。
"""

from typing import Any, Iterator, Type, final
from unittest.mock import MagicMock

import pytest

from ai_srpg.entitas import CleanupProcessor, ExecuteProcessor
from ai_srpg.entitas.components import Component
from ai_srpg.game.ecs_context import ECSContext
from ai_srpg.game.systems.action_cleanup_system import ActionCleanupSystem
from ai_srpg.models import (
    ACTION_COMPONENT_TYPES,
    COMPONENT_TYPES,
    RefreshAppearanceAction,
    register_action_component_type,
    register_component_type,
)
from ecs_testing import Position


@final
@register_action_component_type
@register_component_type
class SpeakTestAction(Component):
    """测试用动作组件：只携带发起者名字。"""

    name: str


@final
@register_action_component_type
@register_component_type
class WhisperAction(Component):
    """测试用动作组件：只携带发起者名字。"""

    name: str


@final
@register_action_component_type
@register_component_type
class AnnounceAction(Component):
    """测试用动作组件：只携带发起者名字。"""

    name: str


_TEST_ACTIONS: tuple[Type[Component], ...] = (
    SpeakTestAction,
    WhisperAction,
    AnnounceAction,
)


@pytest.fixture(scope="module", autouse=True)
def clean_registries() -> Iterator[None]:
    """模块用例跑完后移除测试动作组件，避免污染全局注册表。"""
    yield
    for cls in _TEST_ACTIONS:
        ACTION_COMPONENT_TYPES.pop(cls.__name__, None)
        COMPONENT_TYPES.pop(cls.__name__, None)


@pytest.fixture()
def context() -> ECSContext:
    """提供真实 ECS Context，使 Group 自动更新行为生效。"""
    return ECSContext()


@pytest.fixture()
def mock_game(context: ECSContext) -> Any:
    """Mock SRPGGame，将 get_group() 代理到真实 Context，避免初始化重量级 SRPGGame。"""
    game = MagicMock()
    game.get_group.side_effect = context.get_group
    return game


@pytest.fixture()
def system(mock_game: Any) -> ActionCleanupSystem:
    return ActionCleanupSystem(mock_game, ACTION_COMPONENT_TYPES.values())


class TestActionCleanupSystem:
    """ActionCleanupSystem 的 execute/cleanup 双入口测试。"""

    def test_implements_execute_and_cleanup_phases(
        self, system: ActionCleanupSystem
    ) -> None:
        """正常路径走 execute，异常兜底走 cleanup，两个接口都要实现。"""
        assert isinstance(system, ExecuteProcessor)
        assert isinstance(system, CleanupProcessor)

    def test_clears_every_registered_action(
        self, context: ECSContext, system: ActionCleanupSystem
    ) -> None:
        """注册表里的每个动作组件都被清除，不遗漏。"""
        assert set(ACTION_COMPONENT_TYPES) >= {cls.__name__ for cls in _TEST_ACTIONS}

        placed = []
        for action_cls in _TEST_ACTIONS:
            entity = context.create_entity()
            entity.add(action_cls, "alice")
            placed.append((entity, action_cls))

        system.cleanup()

        for entity, action_cls in placed:
            assert not entity.has(action_cls)

    @pytest.mark.asyncio
    async def test_execute_clears_actions(
        self, context: ECSContext, system: ActionCleanupSystem
    ) -> None:
        """正常 execute 路径也应清理动作组件。"""
        entity = context.create_entity()
        entity.add(SpeakTestAction, "alice")

        await system.execute()

        assert not entity.has(SpeakTestAction)

    def test_cleanup_empty_world(self, system: ActionCleanupSystem) -> None:
        """无实体时 cleanup() 应正常完成，不抛出任何异常。"""
        system.cleanup()

    def test_cleanup_without_registered_actions_is_noop(
        self, mock_game: Any, context: ECSContext
    ) -> None:
        """动作表为空时清理是空操作：不抛错，也不动其他组件。"""
        entity = context.create_entity()
        entity.add(Position, 1.0, 2.0)

        ActionCleanupSystem(mock_game, ()).cleanup()

        assert entity.has(Position)

    def test_cleanup_removes_multiple_actions_from_same_entity(
        self, context: ECSContext, system: ActionCleanupSystem
    ) -> None:
        """单实体同时持有多个动作组件，执行后应全部被移除。"""
        entity = context.create_entity()
        entity.add(SpeakTestAction, "alice")
        entity.add(WhisperAction, "alice")
        entity.add(AnnounceAction, "alice")

        system.cleanup()

        assert not entity.has(SpeakTestAction)
        assert not entity.has(WhisperAction)
        assert not entity.has(AnnounceAction)

    def test_clears_production_action(
        self, context: ECSContext, system: ActionCleanupSystem
    ) -> None:
        """生产注册表里的动作组件同样在清理范围内。"""
        assert (
            ACTION_COMPONENT_TYPES["RefreshAppearanceAction"] is RefreshAppearanceAction
        )
        entity = context.create_entity()
        entity.add(RefreshAppearanceAction)

        system.cleanup()

        assert not entity.has(RefreshAppearanceAction)

    def test_cleanup_preserves_non_action_components(
        self, context: ECSContext, system: ActionCleanupSystem
    ) -> None:
        """实体同时持有动作组件与非动作组件，执行后非动作组件应保留。"""
        entity = context.create_entity()
        entity.add(SpeakTestAction, "alice")
        entity.add(Position, 1.0, 2.0)

        system.cleanup()

        assert not entity.has(SpeakTestAction)
        assert entity.has(Position)
