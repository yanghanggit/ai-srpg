"""动作组件注册装饰器的单元测试。"""

from typing import Iterator

import pytest

from ai_srpg.entitas.components import Component
from ai_srpg.models import (
    ACTION_COMPONENT_TYPES,
    COMPONENT_TYPES,
    CompactAction,
    EnterSiteAction,
    ExitSiteAction,
    MoveWithinSiteAction,
    PlanAction,
    RefreshAppearanceAction,
    RefreshEnvironmentAction,
    SpeakAction,
    TravelAction,
    WaitAction,
    register_action_component_type,
    register_component_type,
)


@pytest.fixture(autouse=True)
def isolated_registries() -> Iterator[None]:
    """用例结束后清掉本次新注册的组件与动作，避免污染全局注册表。"""
    components_before = set(COMPONENT_TYPES)
    actions_before = set(ACTION_COMPONENT_TYPES)
    yield
    for name in list(COMPONENT_TYPES):
        if name not in components_before:
            del COMPONENT_TYPES[name]
    for name in list(ACTION_COMPONENT_TYPES):
        if name not in actions_before:
            del ACTION_COMPONENT_TYPES[name]


#: 全部动作；新增动作只改这一处
PRODUCTION_ACTIONS = [
    PlanAction,
    SpeakAction,
    TravelAction,
    EnterSiteAction,
    ExitSiteAction,
    MoveWithinSiteAction,
    WaitAction,
    RefreshAppearanceAction,
    RefreshEnvironmentAction,
    CompactAction,
]

#: 不带参数的动作：只声明「这轮做这件事」
FIELDLESS_ACTIONS = [
    PlanAction,
    WaitAction,
    ExitSiteAction,
    RefreshAppearanceAction,
    RefreshEnvironmentAction,
]


class JumpAction(Component):
    """测试用动作组件：只带高度。"""

    height: int


class TestProductionActions:
    """``actions.py`` 里真实登记的动作组件。"""

    @pytest.mark.parametrize("action", PRODUCTION_ACTIONS)
    def test_is_registered_in_both_tables(self, action: type) -> None:
        """动作同时是组件与动作组件——装饰器叠放的产物。"""
        assert COMPONENT_TYPES[action.__name__] is action
        assert ACTION_COMPONENT_TYPES[action.__name__] is action

    @pytest.mark.parametrize("action", FIELDLESS_ACTIONS)
    def test_is_a_fieldless_component(self, action: type) -> None:
        """动作本身不带状态：它只说「这轮要做这件事」。"""
        assert issubclass(action, Component)
        assert action().model_dump() == {}


class TestRegisterActionComponentType:
    def test_registers_into_action_table(self) -> None:
        """注册后出现在动作组件表里，且原样返回类。"""
        register_component_type(JumpAction)

        assert register_action_component_type(JumpAction) is JumpAction
        assert ACTION_COMPONENT_TYPES["JumpAction"] is JumpAction

    def test_decorator_stack_registers_both(self) -> None:
        """文档约定的装饰器叠放顺序可用：一行声明同时进两张表。"""

        @register_action_component_type
        @register_component_type
        class DanceAction(Component):
            """测试用动作组件：只带回合数。"""

            rounds: int

        assert COMPONENT_TYPES["DanceAction"] is DanceAction
        assert ACTION_COMPONENT_TYPES["DanceAction"] is DanceAction

    def test_requires_component_registration_first(self) -> None:
        """装饰器顺序反了要明确报错，而不是留下只在动作表里的类。"""

        class UnregisteredAction(Component):
            """只用于本断言、故意不先注册为组件。"""

        with pytest.raises(ValueError, match="register_component_type"):
            register_action_component_type(UnregisteredAction)

    def test_rejects_non_component(self) -> None:
        """不是 Component 子类的类直接拒绝。"""
        with pytest.raises(TypeError):
            register_action_component_type(int)  # type: ignore[type-var]

    def test_rejects_duplicate_action(self) -> None:
        """同一类重复声明为动作组件会报错。"""
        register_component_type(JumpAction)
        register_action_component_type(JumpAction)

        with pytest.raises(ValueError, match="already registered"):
            register_action_component_type(JumpAction)

    def test_action_table_is_subset_of_component_table(self) -> None:
        """动作组件一定是组件：动作表是组件表的子集。"""
        assert set(ACTION_COMPONENT_TYPES) <= set(COMPONENT_TYPES)
