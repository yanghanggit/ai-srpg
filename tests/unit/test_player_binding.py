"""``bind_player_actor`` 的单元测试。

绑定是 ``PlayerComponent`` 的唯一写入路径，因此这里锁死三条规则：
一人一个角色、一个角色一人、重复绑同一对幂等。
"""

from typing import Any

import pytest

from ai_srpg.game.assembly import create_srpg_game
from ai_srpg.game.ecs_context import ECSContext
from ai_srpg.game.entities import (
    bind_player_actor,
    build_from_blueprint,
    get_player_actor_name,
    get_player_entity,
)
from ai_srpg.models import (
    ActorBlueprint,
    ActorComponent,
    Blueprint,
    GridComponent,
    PlayerComponent,
    StageBlueprint,
    StageComponent,
)


@pytest.fixture()
def game(context: ECSContext) -> Any:
    """ECSContext 已提供名称索引与 get_group，可直接当 SRPGGame 的替身。"""
    return context


@pytest.fixture()
def context() -> ECSContext:
    return ECSContext()


def _make_actor(context: ECSContext, name: str) -> Any:
    entity = context.create_entity(name)
    entity.add(ActorComponent, "")
    return entity


def _make_stage(context: ECSContext, name: str) -> Any:
    entity = context.create_entity(name)
    return entity


############################################################################################################
class TestBindPlayerActor:
    def test_binds_actor_to_player(self, context: ECSContext, game: Any) -> None:
        """绑定后 ``PlayerComponent`` 记录玩家身份，按身份能查回来。"""
        actor = _make_actor(context, "角色.甲")

        bound = bind_player_actor(game, "alice", "角色.甲")

        assert bound is actor
        assert actor.get(PlayerComponent).user_name == "alice"
        assert get_player_actor_name(game, "alice") == "角色.甲"

    def test_two_players_get_different_actors(
        self, context: ECSContext, game: Any
    ) -> None:
        """多席位各自绑一个角色，互不覆盖。"""
        _make_actor(context, "角色.甲")
        _make_actor(context, "角色.乙")

        bind_player_actor(game, "alice", "角色.甲")
        bind_player_actor(game, "bob", "角色.乙")

        assert get_player_actor_name(game, "alice") == "角色.甲"
        assert get_player_actor_name(game, "bob") == "角色.乙"

    def test_rebinding_same_pair_is_idempotent(
        self, context: ECSContext, game: Any
    ) -> None:
        """重复调同一个绑定不报错、不改变结果（席位重进房间会重放）。"""
        actor = _make_actor(context, "角色.甲")
        bind_player_actor(game, "alice", "角色.甲")

        assert bind_player_actor(game, "alice", "角色.甲") is actor
        assert actor.get(PlayerComponent).user_name == "alice"

    def test_rejects_actor_owned_by_someone_else(
        self, context: ECSContext, game: Any
    ) -> None:
        """抢别人已控制的角色要报错，并指出当前控制者。"""
        _make_actor(context, "角色.甲")
        bind_player_actor(game, "alice", "角色.甲")

        with pytest.raises(ValueError, match="alice"):
            bind_player_actor(game, "bob", "角色.甲")

    def test_rejects_second_actor_for_same_player(
        self, context: ECSContext, game: Any
    ) -> None:
        """一个玩家只能控制一个角色：换角色必须先解绑。"""
        _make_actor(context, "角色.甲")
        _make_actor(context, "角色.乙")
        bind_player_actor(game, "alice", "角色.甲")

        with pytest.raises(ValueError, match="角色.甲"):
            bind_player_actor(game, "alice", "角色.乙")

    def test_rejects_unknown_actor(self, context: ECSContext, game: Any) -> None:
        """角色名不存在时报错。"""
        with pytest.raises(ValueError, match="找不到角色实体"):
            bind_player_actor(game, "alice", "角色.无")

    def test_rejects_non_actor_entity(self, context: ECSContext, game: Any) -> None:
        """舞台等非角色实体不能被绑成玩家角色。"""
        _make_stage(context, "舞台.甲")

        with pytest.raises(ValueError, match="找不到角色实体"):
            bind_player_actor(game, "alice", "舞台.甲")

    @pytest.mark.parametrize(
        "user_name, actor_name", [("", "角色.甲"), ("  ", "角色.甲")]
    )
    def test_rejects_blank_player(
        self, context: ECSContext, game: Any, user_name: str, actor_name: str
    ) -> None:
        """玩家名为空白时报错（席位身份不能是空串）。"""
        _make_actor(context, "角色.甲")

        with pytest.raises(ValueError, match="玩家名不能为空"):
            bind_player_actor(game, user_name, actor_name)

    def test_rejects_blank_actor(self, context: ECSContext, game: Any) -> None:
        """角色名为空白时报错。"""
        with pytest.raises(ValueError, match="角色名不能为空"):
            bind_player_actor(game, "alice", "  ")


############################################################################################################
def _blueprint() -> Blueprint:
    """单舞台单角色的最小蓝图：谁会玩不写在蓝图里。"""
    actor = ActorBlueprint(
        name="角色.甲",
        system_message="# 角色.甲",
        components={ActorComponent.__name__: {"current_stage": "舞台.甲"}},
    )
    stage = StageBlueprint(
        name="舞台.甲",
        system_message="# 舞台.甲",
        components={
            StageComponent.__name__: {},
            GridComponent.__name__: {"width": 5, "height": 5},
        },
    )
    return Blueprint(
        name="TestGame",
        campaign_setting="设定",
        global_rules="规则",
        stage_tree=stage,
        actors=[actor],
        worlds=[],
    )


############################################################################################################
class TestBuildingBindsNobody:
    def test_blueprint_assembly_leaves_every_actor_unclaimed(self) -> None:
        """装配世界不涉及玩家：绑定是入场时的一次独立动作。"""
        game = create_srpg_game(name="TestGame")

        build_from_blueprint(game, _blueprint())

        assert get_player_entity(game, "alice") is None
