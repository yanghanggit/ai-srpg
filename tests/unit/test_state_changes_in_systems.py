"""状态改动的位置守卫：改记忆 / 改 ECS 只能发生在 systems 的 mixin 里。

``game/entities`` / ``events`` / ``memory`` / ``tools`` 只有基建原语，谁都能读；一旦要改
状态，就必须走 systems 里的 mixin——mixin 本身就是提示：这段代码在某个 system 的执行
链上，知道自己在哪一轮、因为什么发生。散在各处直接改，就再也说不清「谁在什么时候改的」。

只有四类例外，它们不进 pipeline：创建（装配世界）、销毁、发动动作（接管与点名计划）、
绑定（入场前的席位配置），外加回滚（生命周期把世界拨回某个快照）。这张表就是全部例外，
新加一处会被这个测试拦下来，逼着先想清楚它属于哪一类。
"""

import ast
from pathlib import Path
from typing import Dict, List, Tuple

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_SRC = _PROJECT_ROOT / "src" / "ai_srpg"

#: 允许在 systems 之外直接改状态的模块，值必须是下面四类之一
_ALLOWED: Dict[str, str] = {
    "game/command.py": "发动动作",
    "gameplay/offline.py": "发动动作",
    "srpg_game_agent/compact.py": "发动动作",
    "game/entities/player_binding.py": "绑定",
    "game/entities/world_builder.py": "创建",
    "game/context.py": "销毁与回滚",
}

#: 这些前缀下的代码是原语或引擎本身，不在此规则的范围内
_SKIPPED_PREFIXES: Tuple[str, ...] = (
    "game/systems/",
    "entitas/",
    "models/",
    "pgsql/",
    "services/",
    "cli/",
    "llm/",
    "session/",
    "srpg_game_client/",
)
_SKIPPED_FILES = {
    "game/events/publish.py",
    "game/memory/access.py",
    "game/memory/compact.py",
}

#: 实体变量的常见名字：按约定识别「这是在改实体」，避免把 set/dict 的 add 当成状态改动
_ENTITY_NAMES = frozenset(
    {
        "entity",
        "actor",
        "stage_entity",
        "site",
        "site_entity",
        "map_stage",
        "region_entity",
        "target",
        "location",
        "node",
        "found",
        "parent",
        "child",
        "world",
        "owner",
        "holder",
        "item",
    }
)
_ECS_MUTATORS = frozenset({"replace", "add", "remove", "set"})
_MEMORY_MUTATORS = frozenset({"get_or_create", "restore", "remove"})

#: 模块级的记忆写原语：名字即契约，出现在例外模块之外就是越界
_MEMORY_WRITE_FUNCTIONS = frozenset(
    {
        "add_ai_message",
        "add_human_message",
        "add_system_message",
        "compact_agent_memory",
        "insert_messages",
        "remove_agent_memory",
        "remove_message_range",
        "remove_messages",
        "replace_span",
        "reset_agent_memory",
    }
)


def _relative(path: Path) -> str:
    return path.relative_to(_SRC).as_posix()


def _mutation_sites() -> List[str]:
    """收集 systems 之外的状态改动点，返回 ``文件:行 说明``。"""
    sites: List[str] = []
    for path in sorted(_SRC.rglob("*.py")):
        relative = _relative(path)
        if relative.startswith(_SKIPPED_PREFIXES) or relative in _SKIPPED_FILES:
            continue
        for line in _offending_lines(path.read_text(encoding="utf-8")):
            sites.append(f"{relative}:{line}")
    return sites


def _offending_lines(source: str) -> List[int]:
    lines: List[int] = []
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Name) and func.id in _MEMORY_WRITE_FUNCTIONS:
            lines.append(node.lineno)
            continue
        if not isinstance(func, ast.Attribute):
            continue
        receiver = func.value
        if func.attr in _ECS_MUTATORS and _is_entity(receiver):
            lines.append(node.lineno)
        elif func.attr in _MEMORY_MUTATORS and _is_memory_store(receiver):
            lines.append(node.lineno)
        elif func.attr == "append" and _is_message_list(receiver):
            lines.append(node.lineno)
    return lines


def _is_entity(receiver: ast.expr) -> bool:
    return isinstance(receiver, ast.Name) and receiver.id in _ENTITY_NAMES


def _is_message_list(receiver: ast.expr) -> bool:
    """绕开 ``insert_messages`` 直接往 ``memory.messages`` 里追加，同样算改记忆。"""
    return isinstance(receiver, ast.Attribute) and receiver.attr == "messages"


def _is_memory_store(receiver: ast.expr) -> bool:
    """``game.agent_memory_store.remove(...)`` 这类：属性名就是记忆容器。"""
    return isinstance(receiver, ast.Attribute) and receiver.attr == "agent_memory_store"


###############################################################################
def test_state_changes_only_happen_in_systems_or_the_listed_exceptions() -> None:
    sites = _mutation_sites()

    unexpected = [site for site in sites if site.split(":")[0] not in _ALLOWED]

    assert not unexpected, "\n".join(
        [
            "检测到 systems 之外直接改状态（记忆 / ECS）：",
            *[f"  {site}" for site in unexpected],
            "改状态的业务逻辑应当在 game/systems 里，通过 mixin 完成；",
            "若确属创建 / 销毁 / 发动动作 / 绑定 / 回滚，把它加进本文件的 _ALLOWED 并写明理由。",
        ]
    )


def test_every_exception_names_its_category() -> None:
    """例外表必须说明它属于哪一类：说不出类别的，就不该是例外。"""
    for module, reason in _ALLOWED.items():
        assert reason in {
            "创建",
            "销毁与回滚",
            "发动动作",
            "绑定",
        }, f"{module} 的理由 {reason!r} 不在约定的例外类别里"


def test_exception_modules_still_exist() -> None:
    """例外表不会悄悄过期：模块改名或删除后，这里要一起改。"""
    for module in _ALLOWED:
        assert (_SRC / module).is_file(), f"例外表里的模块不存在: {module}"
