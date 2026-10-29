"""Small Thai equipment/throwable/attachment catalogue, not a full ItemTable.

Fields are independently read with the row121 reflection parser and joined
to collectable EntityTable rows. Healing, armour damage and grenade physics
are separate from ground/bag support. Part installation is in inventory.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class ExtraSpec:
    kind:int
    name:str
    max_stack:int=1
    slot:int|None=None
    part_type:int=0
    part_index:int=0
    extra_weight:int=0
    durability:int=0
    defense:int=0
    head_defense:int=0


EXTRA_ITEMS={
    70001:ExtraSpec(7,'绷带',20),
    70002:ExtraSpec(7,'急救包',20),
    70003:ExtraSpec(7,'医疗箱',20),
    200101:ExtraSpec(20,'一级头盔',slot=10,durability=800,head_defense=30),
    200102:ExtraSpec(20,'二级头盔',slot=10,durability=1500,head_defense=40),
    200103:ExtraSpec(20,'三级头盔',slot=10,durability=2300,head_defense=55),
    201001:ExtraSpec(20,'一级防弹衣',slot=12,extra_weight=50,durability=2000,defense=30),
    201002:ExtraSpec(20,'二级防弹衣',slot=12,extra_weight=50,durability=2200,defense=40),
    201003:ExtraSpec(20,'三级防弹衣',slot=12,extra_weight=50,durability=2500,defense=55),
    200901:ExtraSpec(20,'一级背包',slot=11,extra_weight=150),
    200902:ExtraSpec(20,'二级背包',slot=11,extra_weight=200),
    200903:ExtraSpec(20,'三级背包',slot=11,extra_weight=250),
    50001:ExtraSpec(5,'手雷',100,5),
    50002:ExtraSpec(5,'烟雾弹',100,5),
    50003:ExtraSpec(5,'闪光弹',10,5),
    40101:ExtraSpec(4,'狙击枪消音器',part_type=5),
    40102:ExtraSpec(4,'手枪消音器',part_type=1),
    40201:ExtraSpec(4,'三角前握把',part_type=8,part_index=1),
    40301:ExtraSpec(4,'15倍瞄准镜',part_type=14,part_index=2),
    40302:ExtraSpec(4,'8倍瞄准镜',part_type=14,part_index=2),
    40303:ExtraSpec(4,'4倍瞄准镜',part_type=13,part_index=2),
    40304:ExtraSpec(4,'2倍瞄准镜',part_type=13,part_index=2),
    40305:ExtraSpec(4,'红点瞄准镜',part_type=12,part_index=2),
    40401:ExtraSpec(4,'狙击枪扩容弹匣',part_type=20,part_index=3),
    40403:ExtraSpec(4,'步枪扩容弹匣',part_type=18,part_index=3),
    40405:ExtraSpec(4,'冲锋枪扩容弹匣',part_type=19,part_index=3),
}


def is_extra(item):
    spec=EXTRA_ITEMS.get(item.template)
    return spec is not None and item.kind==spec.kind and 0<item.count<=spec.max_stack
