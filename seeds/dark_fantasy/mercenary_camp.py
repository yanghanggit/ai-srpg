"""剧本「雇佣兵的营地」：一个世界、一棵舞台树、两个角色，作为开发与测试的起点。

舞台上是一个失忆的年轻人和捡到他的老雇佣兵。故事级设定（战役设定、全局规则、世界
职责）在 ``story`` 模块共用；这里只放本剧本专属的实体数据，状态一律写成组件数据。
"""

from typing import Dict, Final

from ai_srpg.game.prompt_composer import compose_actor, compose_stage, compose_world
from ai_srpg.models import (
    ActorBlueprint,
    ActorComponent,
    AppearanceComponent,
    Blueprint,
    EnvironmentComponent,
    GridComponent,
    MapPosition,
    NPCComponent,
    StageBlueprint,
    StageComponent,
    WorldBlueprint,
    WorldComponent,
)

from .story import CAMPAIGN_SETTING, GLOBAL_RULES, WORLD_ROLE_RULES

BATTLEFIELD_NAME: Final[str] = "舞台.战场"
STAGE_NAME: Final[str] = "舞台.营地"
BATTLEFIELD_GRID: Dict[str, int] = {"width": 5, "height": 5}

#######################################################################################################################################
# 无名的体型：既进 prompt 的「基础体型」段，也是角色的初始外观
NAMELESS_BODY: Final[str] = (
    "年近三十的男性，肩宽而骨架分明，身形偏瘦但不单薄。身穿一件洗得发白的旧斗篷，缝制方式少见、边角磨损起毛，肤色偏浅。面容轮廓分明，下颌线条硬朗，眼下有淡淡的暗沉，眼睑低垂，目光沉静。手指细长，关节明显。"
)

#: 两个舞台的环境底稿：进游戏时是它们的初始环境叙述，之后按状态更新
BATTLEFIELD_ENVIRONMENT: Final[str] = (
    "夜里分辨得出的只有几处轮廓：一段残墙、一片矮树林，再远处是没有灯火的平地。风从旧车辙的方向来，带着潮土味，除此以外没有别的声音。"
)
CAMP_ENVIRONMENT: Final[str] = (
    "碎石围出一圈浅坑，坑底是压实的灰土，北面几块石头挡着风。地面干燥，风从旧道方向进来时被石头切开，剩下的一股贴着坑壁低低地绕过去。"
)

#: 老雇佣兵的体型
OLD_DOG_BODY: Final[str] = (
    "五十上下的男性，肩背宽厚但已经垮下去。左脸一道从颊骨划到耳根的旧疤，右眼浑浊成一片灰白。右手的食指与中指各少了一节。身上是层层缝补的旧皮甲，甲片颜色深浅不一；脖子上一根皮绳，串着几枚磨得看不清纹路的旧币。"
)


def create_nameless() -> ActorBlueprint:
    """创建主角——无名：失忆、被老雇佣兵捡回来、被带进这一行。"""

    actor = compose_actor(
        name="角色.无名",
        profile="""**历史**: 你醒来时想不起自己是谁，也想不起自己从哪儿来。你身上穿着一件不属于此地样式的旧斗篷，脑海深处只残留着一些断裂的碎片——那里没有魔法，也没有刀剑横行的荒野。你说不清那是什么地方，却清楚一件事：你不是这里的人。把你从路边捡回来的，是个落魄的老雇佣兵，他给你起了名字，也没多问，就这样把你带进了这一行。
**性格**: 你沉默，观察多于开口。面对陌生的事物不会慌乱，而是停下来，仔细看，仔细想，再决定怎么做。你不排斥危险，但也不会轻易莽撞。
**禁忌**: 你对任何人追问你的来历、强行拿走你身上仅有的东西、或强迫你去某个地方，都有本能的抵触。
**最爱**: 你发现自己喜欢坐在炉火边，听火舌舔过木柴的轻响，那时候周围很安静。""",
        base_body=NAMELESS_BODY,
        campaign_setting=CAMPAIGN_SETTING,
        global_rules=GLOBAL_RULES,
    )
    actor.components = {
        ActorComponent.__name__: {"current_stage": STAGE_NAME},
        AppearanceComponent.__name__: {"base_body": NAMELESS_BODY},
    }
    return actor


#######################################################################################################################################
def create_old_dog() -> ActorBlueprint:
    """创建 NPC——老狗：捡到「无名」的老雇佣兵，本剧本的引路人。"""

    actor = compose_actor(
        name="角色.老狗",
        profile="""**历史**: 你说不清自己打过多少仗，只记得三场有名字的，那三场你的队伍都没赢到最后。佣兵团散了之后你在荒野上卖力气：押货、找人、替人把债讨回来，价钱合适就干。两年前你在通往荒野的旧道上捡到一个年轻人——身上没有伤，却什么都不记得。你给他取了名字叫「无名」，教他怎么握刀，也没多问。你留下的理由是：一个人干活，总得有个人替你看着背后。营地里的人都叫你老狗——不算骂，是说你像条赶不走的狗：给口吃的就跟着走，被打断了腿也还是回来。
**性格**: 你话少，只在该说的时候说。开口先讲价钱：要付什么、能拿到什么，说清了再动手。你对年轻人的蠢问题有耐心，对自己的一点没有。你笑的时候只有半边脸会动。
**禁忌**: 你不谈那三场仗。你不碰别人挂在腰上的东西——那是人家的命。你不许任何人在你面前鞭打牲口。
**最爱**: 你数钱，一枚一枚数完再收好；还有把弯曲的铁片敲平、磨亮、缝回自己的甲上——那是你唯一还信得过的手艺。""",
        base_body=OLD_DOG_BODY,
        campaign_setting=CAMPAIGN_SETTING,
        global_rules=GLOBAL_RULES,
    )
    actor.components = {
        ActorComponent.__name__: {"current_stage": STAGE_NAME},
        AppearanceComponent.__name__: {"base_body": OLD_DOG_BODY},
        NPCComponent.__name__: {},
    }
    return actor


#######################################################################################################################################
def create_camp_stage() -> StageBlueprint:
    """创建营地舞台：故事的起点，两个人暂时落脚的地方。"""

    stage = compose_stage(
        name=STAGE_NAME,
        profile="""荒野上来往的人偶尔在此落脚：背风、离水近、离旧道不远。这里没有可做的事，也没有人愿意多待，
它只是出发前与归来后短暂停留的地方。""",
        campaign_setting=CAMPAIGN_SETTING,
        global_rules=GLOBAL_RULES,
    )
    stage.components = {
        StageComponent.__name__: {},
        EnvironmentComponent.__name__: {"base_environment": CAMP_ENVIRONMENT},
    }
    stage.map_position = MapPosition(x=2, y=2)
    return stage


#######################################################################################################################################
def create_battlefield() -> StageBlueprint:
    """创建舞台树的根——大地图：自带网格，营地摆在中央一格。"""

    stage = compose_stage(
        name=BATTLEFIELD_NAME,
        profile="""一片没有名字的旷野，被雨水与旧车辙切成方格状的地界。这里没有路标，也没有人烟：
路是车轮压出来的，方向由地面记着，不由人指点。""",
        campaign_setting=CAMPAIGN_SETTING,
        global_rules=GLOBAL_RULES,
    )
    stage.components = {
        StageComponent.__name__: {},
        GridComponent.__name__: dict(BATTLEFIELD_GRID),
        EnvironmentComponent.__name__: {"base_environment": BATTLEFIELD_ENVIRONMENT},
    }
    stage.children = [create_camp_stage()]
    return stage


#######################################################################################################################################
def create_starless_world() -> WorldBlueprint:
    """创建世界实体——无星长夜：叙事者与规则仲裁者，高于所有舞台。"""

    world = compose_world(
        name="世界.无星长夜",
        campaign_setting=CAMPAIGN_SETTING,
        global_rules=GLOBAL_RULES,
        role_rules=WORLD_ROLE_RULES,
    )
    world.components = {WorldComponent.__name__: {}}
    return world


#######################################################################################################################################
def create_blueprint(game_name: str) -> Blueprint:
    """装配本剧本的蓝图；出厂闸门与提示词留痕由内容包统一处理。"""

    return Blueprint(
        name=game_name,
        campaign_setting=CAMPAIGN_SETTING,
        global_rules=GLOBAL_RULES,
        stage_tree=create_battlefield(),
        actors=[create_nameless(), create_old_dog()],
        worlds=[create_starless_world()],
    )


###############################################################################
__all__ = ["create_blueprint"]
