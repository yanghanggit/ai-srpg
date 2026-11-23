"""跑一轮角色计划：把上下文与工具表交给 agent loop，再把动作挂到角色身上。

计划是「想」而不是「做」：它只挂动作，不改世界。失败只让这个角色本轮轮空，不抛给
pipeline——思考失败不该让世界倒退。

记忆里写入的是 ``record_message``（压缩版上下文），与接管路径（``game.command``）写
的完全一致：事后看记忆，分不出这一轮是自己想的还是被接管的。
"""

import json
from typing import Awaitable, Callable, Dict, Final, List, Optional, Tuple, Type, Union
from uuid import uuid4

from loguru import logger

from ...deepseek import AgentLoopResult, agent_loop
from ...entitas import Entity
from ...entitas.components import Component
from ...llm import ToolDefinition
from ...models import AIMessage, ChatMessage, HumanMessage, ToolMessage
from ..entities.action_rules import action_tool_call
from ..memory import (
    get_agent_memory,
    insert_messages,
    sync_latest_context_usage_ratio,
)
from .system_mixin import SystemMixin

#: 最多往返几轮：够表达一个行动，又不给模型自己绕圈的空间
PLAN_ROUNDS: Final[int] = 3

#: 写进记忆的回执，与工具处理器返回同一个词
ACK: Final[str] = "（已记下）"


############################################################################################################
############################################################################################################
class PlanMixin(SystemMixin):
    """给某一层的计划 system 提供「跑一轮」与「挂动作」。"""

    ############################################################################################################
    def allowed_actions(self) -> Tuple[Type[Component], ...]:
        """这一层允许挂的动作类型；由各层自己声明。"""
        raise NotImplementedError

    ############################################################################################################
    async def run_plan(
        self,
        entity: Entity,
        *,
        input_message: str,
        record_message: str,
        tools: List[ToolDefinition],
        handlers: Dict[str, Callable[..., Union[str, Awaitable[str]]]],
    ) -> None:
        name = f"plan:{entity.name}"
        try:
            result = await agent_loop(
                name=name,
                input_message=input_message,
                messages=get_agent_memory(self._game, entity).messages,
                tools=tools,
                handlers=handlers,
                max_rounds=PLAN_ROUNDS,
                terminal_tools=tools,
                loop_id=name,
            )
        except Exception as e:
            logger.opt(exception=e).warning(
                f"[plan:{entity.name}] 计划失败，本轮轮空: {type(e).__name__}: {e}"
            )
            return

        # 记忆里留摘要而不是整段上下文：接管路径写的也是这一版，两条来源因此同形
        if result.start_message is not None:
            result.start_message.content = record_message

        # agent_loop 直接往记忆的消息列表里追加，不经 insert_messages，
        # 所以上下文占比要在这里手动接上，否则满度信号永远停在 0
        sync_latest_context_usage_ratio(self._game, entity)

        logger.info(
            " ".join(
                [
                    f"[plan:{entity.name}]",
                    f"success={result.success}",
                    f"rounds={len(result.rounds)}",
                    f"tools={_called_tools(result)}",
                ]
            )
        )

    ############################################################################################################
    def predecided_action(self, actor: Entity) -> Optional[Component]:
        """这一轮的行动是否已经由接管决定：是就返回那个动作。"""
        for action_type in self.allowed_actions():
            if actor.has(action_type):
                return actor.get(action_type)
        return None

    ############################################################################################################
    def record_decision(self, actor: Entity, *, action: Component, prompt: str) -> None:
        """把接管写进记忆：「输入 → 工具调用 → 回执」，与计划 loop 产出的三条一致。"""
        tool_name, arguments = action_tool_call(action)
        call_id = f"call_{uuid4().hex[:24]}"
        messages: List[ChatMessage] = [
            HumanMessage(content=prompt),
            AIMessage(
                content="",
                additional_kwargs={
                    "tool_calls": [
                        {
                            "id": call_id,
                            "type": "function",
                            "function": {
                                "name": tool_name,
                                "arguments": json.dumps(arguments, ensure_ascii=False),
                            },
                        }
                    ]
                },
            ),
            ToolMessage(content=ACK, tool_call_id=call_id),
        ]
        memory = get_agent_memory(self._game, actor)
        insert_messages(self._game, actor, len(memory.messages), messages)
        logger.info(f"[plan:{actor.name}] 接管决定: {tool_name}{arguments}")

    ############################################################################################################
    def mount_action(
        self, actor: Entity, action_type: Type[Component], *args: object
    ) -> str:
        """把动作挂到角色身上；本轮已经有行动时忽略后到的，并在回执里说明。"""
        allowed = self.allowed_actions()
        if action_type not in allowed:
            raise ValueError(f"{action_type.__name__} 不属于这一层可用的动作")
        if any(actor.has(item) for item in allowed):
            logger.warning(
                f"[plan:{actor.name}] 本轮已有行动，忽略 {action_type.__name__}"
            )
            return "（本轮已经有行动了，这次忽略）"
        actor.replace(action_type, *args)
        logger.info(f"[plan:{actor.name}] {action_type.__name__}{args}")
        return "（已记下）"


############################################################################################################
def _called_tools(result: AgentLoopResult) -> str:
    """本次计划实际调用了哪些工具；一个都没有时明说。"""
    names = [
        call.function.name
        for one_round in result.rounds
        for call in (one_round.completion.tool_calls or [])
    ]
    return ",".join(names) if names else "无"


###############################################################################
__all__ = ["ACK", "PlanMixin"]
