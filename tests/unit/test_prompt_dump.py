"""蓝图 prompt 留痕：导出内容与实体 memories[0] 必须一致。"""

import pathlib

from ai_srpg.game.assembly import create_srpg_game
from ai_srpg.game.entities.queries import get_actor_entity, get_stage_entity
from ai_srpg.game.entities.world_builder import build_from_blueprint
from ai_srpg.game.memory import get_agent_memory
from ai_srpg.game.prompt_dump import dump_blueprint_prompts
from ai_srpg.models import (
    ActorBlueprint,
    ActorComponent,
    Blueprint,
    GridComponent,
    StageBlueprint,
    StageComponent,
    WorldBlueprint,
    WorldComponent,
)


###############################################################################
def _blueprint() -> Blueprint:
    return Blueprint(
        name="TestGame",
        campaign_setting="设定",
        global_rules="规则",
        stage_tree=StageBlueprint(
            name="舞台.营",
            system_message="# 舞台.营\n\n舞台 prompt",
            components={
                StageComponent.__name__: {},
                GridComponent.__name__: {"width": 5, "height": 5},
            },
        ),
        actors=[
            ActorBlueprint(
                name="角色.甲",
                system_message="# 角色.甲\n\n角色 prompt",
                components={ActorComponent.__name__: {"current_stage": "舞台.营"}},
            )
        ],
        worlds=[
            WorldBlueprint(
                name="世界.主",
                system_message="# 世界.主\n\n世界 prompt",
                components={WorldComponent.__name__: {}},
            )
        ],
    )


###############################################################################
def test_exports_one_markdown_per_entity(tmp_path: pathlib.Path) -> None:
    target = dump_blueprint_prompts(_blueprint(), directory=tmp_path / "bp")

    assert {p.name for p in target.glob("*.md")} == {
        "世界.主.md",
        "index.md",
        "角色.甲.md",
        "舞台.营.md",
    }
    assert (target / "角色.甲.md").read_text(
        encoding="utf-8"
    ) == "# 角色.甲\n\n角色 prompt\n"


def test_index_lists_every_entity_with_sections(tmp_path: pathlib.Path) -> None:
    target = dump_blueprint_prompts(_blueprint(), directory=tmp_path / "bp")

    index = (target / "index.md").read_text(encoding="utf-8")

    assert "| 世界 | 世界.主 |" in index
    assert "| 舞台 | 舞台.营 |" in index
    assert "| 角色 | 角色.甲 |" in index
    assert "角色.甲 /" not in index  # 段落列只有标题，不含正文


def test_removes_stale_files_from_previous_export(tmp_path: pathlib.Path) -> None:
    target = tmp_path / "bp"
    target.mkdir()
    stale = target / "已删除的实体.md"
    stale.write_text("old", encoding="utf-8")

    dump_blueprint_prompts(_blueprint(), directory=target)

    assert not stale.exists()


def test_entity_name_is_sanitized(tmp_path: pathlib.Path) -> None:
    blueprint = _blueprint()
    blueprint.worlds[0].name = "世界.主/副"

    target = dump_blueprint_prompts(blueprint, directory=tmp_path / "bp")

    assert (target / "世界.主_副.md").exists()


###############################################################################
def test_dumped_prompt_equals_first_memory(tmp_path: pathlib.Path) -> None:
    """导出的就是实体进 ECS 后的 memories[0]。"""
    blueprint = _blueprint()
    target = dump_blueprint_prompts(blueprint, directory=tmp_path / "bp")

    game = create_srpg_game(name=blueprint.name)
    build_from_blueprint(
        game,
        blueprint,
    )

    stage = get_stage_entity(game, "舞台.营")
    actor = get_actor_entity(game, "角色.甲")
    assert stage is not None and actor is not None

    for entity in (stage, actor):
        first_memory = get_agent_memory(game, entity).messages[0]
        dumped = (target / f"{entity.name}.md").read_text(encoding="utf-8")
        assert first_memory.content == dumped.rstrip()
