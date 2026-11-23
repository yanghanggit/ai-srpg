"""测试动态组件类型创建与挂载功能。

覆盖范围：
- registry.create_component_type 动态创建组件类（含幂等与字段定义）
- registry.resolve_component_type 惰性重建动态组件（含按 data 推断字段）
- build_from_blueprint 挂载蓝图声明的动态组件
- RPGEntityManager.restore_context 跨进程重建动态组件
"""

import uuid
from typing import Any, Iterator, cast

import pytest
from pydantic import ValidationError

from ai_srpg.entitas import Context
from ai_srpg.entitas.components import Component
from ai_srpg.game.ecs_context import ECSContext
from ai_srpg.game.entities import build_from_blueprint, get_stage_entity
from ai_srpg.models import (
    COMPONENT_TYPES,
    AgentMemoryStore,
    Blueprint,
    GridComponent,
    IdentityComponent,
    MapPosition,
    StageBlueprint,
    StageComponent,
    create_component_type,
    resolve_component_type,
)


############################################################################################################
@pytest.fixture(autouse=True)
def _clean_dynamic_component_types() -> Iterator[None]:
    """测试结束后清理动态注册的组件类型，避免污染全局注册表。"""
    before = set(COMPONENT_TYPES.keys())
    yield
    for key in list(COMPONENT_TYPES.keys()):
        if key not in before:
            del COMPONENT_TYPES[key]


############################################################################################################
def _make_stage_model(name: str, component_name: str) -> StageBlueprint:
    """构造一个挂载了指定动态组件的舞台声明。"""
    return StageBlueprint(
        name=name,
        system_message=f"{name} 的系统消息",
        components={
            StageComponent.__name__: {},
            component_name: {"name": name},
        },
    )


############################################################################################################
def _build(game: Any, *stages: StageBlueprint) -> None:
    """把若干舞台声明挂到一棵 5x5 的大地图树下并构建。"""
    root = StageBlueprint(
        name="舞台.大地图",
        system_message="# 舞台.大地图",
        components={
            StageComponent.__name__: {},
            GridComponent.__name__: {"width": 5, "height": 5},
        },
        children=[
            stage.model_copy(update={"map_position": MapPosition(x=index, y=0)})
            for index, stage in enumerate(stages)
        ],
    )
    build_from_blueprint(
        game,
        Blueprint(
            name="DynamicComponentTest",
            campaign_setting="设定",
            global_rules="规则",
            stage_tree=root,
            actors=[],
            worlds=[],
        ),
    )


############################################################################################################
# create_component_type
############################################################################################################
class _GameImpl(ECSContext):
    """最小 SRPGGame 替身：直接复用 ECSContext 的实体与快照能力。"""

    def __init__(self) -> None:
        super().__init__()
        self.agent_memory_store = AgentMemoryStore()


def _new_game() -> Any:
    return _GameImpl()


class TestCreateComponentType:
    def test_creates_registered_component_subclass(self) -> None:
        cls = create_component_type("TestDynamicComponent")

        assert cls.__name__ == "TestDynamicComponent"
        assert issubclass(cls, Component)
        assert COMPONENT_TYPES["TestDynamicComponent"] is cls
        assert cls().model_dump() == {}

    def test_is_idempotent(self) -> None:
        cls1 = create_component_type("TestDynamicComponent")
        cls2 = create_component_type("TestDynamicComponent")

        assert cls1 is cls2

    def test_supports_field_definitions(self) -> None:
        cls = create_component_type("TestDynamicWithField", name=(str, ...))

        with pytest.raises(ValidationError):
            cls()
        inst = cls.model_validate({"name": "guard"})
        assert inst.model_dump() == {"name": "guard"}

    def test_rejects_empty_or_non_string_name(self) -> None:
        with pytest.raises(AssertionError):
            create_component_type("   ")
        with pytest.raises(AssertionError):
            create_component_type(cast(Any, 123))

    def test_usable_as_marker_on_entity(self) -> None:
        cls = create_component_type("TestDynamicOnEntity")

        entity = Context().create_entity()
        entity.add(cls)

        assert entity.has(cls)
        assert entity.get(cls) == cls()


############################################################################################################
# resolve_component_type
############################################################################################################
class TestResolveComponentType:
    def test_returns_registered_class(self) -> None:
        cls = create_component_type("TestResolveRegistered")

        assert resolve_component_type("TestResolveRegistered", {}) is cls

    def test_rebuilds_unknown_empty_data_component(self) -> None:
        cls = resolve_component_type("TestResolveRebuild", {})

        assert cls.__name__ == "TestResolveRebuild"
        assert COMPONENT_TYPES["TestResolveRebuild"] is cls

    def test_rebuilds_unknown_non_empty_data_with_inferred_fields(self) -> None:
        cls = resolve_component_type("TestResolveWithField", {"name": "舞台.测试"})

        assert cls.__name__ == "TestResolveWithField"
        assert COMPONENT_TYPES["TestResolveWithField"] is cls
        inst = cls.model_validate({"name": "舞台.测试"})
        assert inst.model_dump() == {"name": "舞台.测试"}


############################################################################################################
# 蓝图装配挂载动态组件
############################################################################################################
class TestBuildWithDynamicComponent:
    def test_attaches_dynamic_component(self, sample_game: Any) -> None:
        tag_cls = create_component_type("integration_001", name=(str, ...))
        _build(sample_game, _make_stage_model("舞台.测试房", "integration_001"))

        stage_entity = sample_game.get_entity_by_name("舞台.测试房")

        assert stage_entity is not None
        assert stage_entity.has(StageComponent)
        assert stage_entity.has(tag_cls)
        assert stage_entity.get(tag_cls).model_dump() == {"name": "舞台.测试房"}

    def test_each_stage_gets_its_own_unique_component(self, sample_game: Any) -> None:
        cls_a = create_component_type("integration_a", name=(str, ...))
        cls_b = create_component_type("integration_b", name=(str, ...))

        _build(
            sample_game,
            _make_stage_model("舞台.A", "integration_a"),
            _make_stage_model("舞台.B", "integration_b"),
        )
        stage_a = get_stage_entity(sample_game, "舞台.A")
        stage_b = get_stage_entity(sample_game, "舞台.B")
        assert stage_a is not None and stage_b is not None

        assert stage_a.has(cls_a)
        assert not stage_a.has(cls_b)
        assert stage_b.has(cls_b)
        assert not stage_b.has(cls_a)
        assert stage_a.get(cls_a).model_dump() == {"name": "舞台.A"}
        assert stage_b.get(cls_b).model_dump() == {"name": "舞台.B"}


############################################################################################################
# RPGEntityManager.restore_context 集成
############################################################################################################
class TestRestoreContextDynamicComponent:
    def test_rebuilds_dynamic_component_from_serialization(self) -> None:
        tag_name = "deser_001"
        tag_cls = create_component_type(tag_name, name=(str, ...))

        source = _new_game()
        entity = source.create_entity("舞台.序列化测试")
        entity.add(IdentityComponent, 1, str(uuid.uuid4()))
        entity.set(tag_cls, tag_cls.model_validate({"name": "舞台.序列化测试"}))

        serialized = source.serialize()

        # 模拟全新进程：动态类不在注册表中
        del COMPONENT_TYPES[tag_name]
        assert tag_name not in COMPONENT_TYPES

        target = _new_game()
        restored = target.restore(serialized, resolve_component_type)

        restored_entity = next(iter(restored.values()))
        assert tag_name in COMPONENT_TYPES  # 反序列化时已惰性重建
        rebuilt_cls = COMPONENT_TYPES[tag_name]
        assert restored_entity.name == "舞台.序列化测试"
        assert restored_entity.has(rebuilt_cls)
        assert restored_entity.get(rebuilt_cls).model_dump() == {
            "name": "舞台.序列化测试"
        }
