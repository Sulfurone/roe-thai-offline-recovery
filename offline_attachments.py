"""Small original-Thai part compatibility matrix; not a weapon-stat simulator.

ItemTable WeaponPartTypeCanUseArray and WeaponPartIndexCanUseArray are
independent constraints. Both must match, including the index on a request.
"""
from offline_items import EXTRA_ITEMS


PART_TYPES={
    10101:(5,14,13,12,20,23),10102:(5,20),10103:(5,14,13,12,20,23),
    10104:(5,14,13,12,20,23,8),10105:(14,13,12),
    10201:(2,8,14,13,12,16,18,22),10202:(2,14,13,12,18,22),
    10203:(2,8,14,13,12,18,22),10204:(2,8,14,13,12,16,18,22),
    10205:(13,12,18,2,22),10207:(2,8,14,13,12,18,22),
    10301:(3,6,8,13,12,19,7),10302:(3,7,6,8,12,16,19),
    10303:(3,7,8,13,12,19,6,16),10401:(13,12,4),10402:(4,17),
    10403:(2,8,13,12,18,4),20001:(),20002:(),20003:(),
}
PART_INDICES={
    10101:(0,2,3,6),10102:(3,),10103:(0,2,3,6),10104:(0,1,2,3,6),10105:(2,6),
    10201:(0,1,2,3,4,6),10202:(0,2,3,6),10203:(0,1,2,3,6),
    10204:(0,1,2,3,6),10205:(0,2,3,6),10207:(0,1,2,3,6),
    10301:(0,1,2,3,6),10302:(0,1,2,3,4,6),10303:(0,1,2,3,4,6),
    10401:(0,2,6),10402:(0,),10403:(0,1,2,3,6),20001:(),20002:(),20003:(),
}


def compatible(weapon,part,index):
    spec=EXTRA_ITEMS.get(part.template)
    return (weapon.kind==1 and spec is not None and part.kind==spec.kind==4
            and part.count==1 and index==spec.part_index
            and spec.part_type in PART_TYPES.get(weapon.template,())
            and index in PART_INDICES.get(weapon.template,()))
