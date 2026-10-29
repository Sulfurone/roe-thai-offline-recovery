"""Local bullet armour rule using original Thai defense/durability facts.

Interpreting nDEF/nDEFHead as percentages and spending absorbed damage as
condition are explicit local rules, not recovered original server formulas.
Hit regions are supplied by the local geometric body approximation, not by
guessing the opaque native character-hit part enum.
"""
from dataclasses import dataclass,replace
from offline_items import EXTRA_ITEMS


@dataclass(frozen=True)
class ArmourHit:
    damage:int
    absorbed:int=0
    slot:int|None=None
    uid:int|None=None
    before:int|None=None
    after:int|None=None


def absorb_bullet(inventory,amount,region):
    if type(amount) is not int or not 0<=amount<=100000 or region not in ('head','torso','limb'):
        raise ValueError('Invalid local armour hit')
    plain=ArmourHit(amount)
    if inventory is None or not amount or region=='limb':return plain
    slot=10 if region=='head' else 12
    item=inventory.items.get((1,slot))
    spec=EXTRA_ITEMS.get(item.template) if item is not None else None
    if item is None or item.kind!=20 or spec is None or spec.slot!=slot or not spec.durability:return plain
    before=spec.durability if item.durability is None else item.durability
    if type(before) is not int or not 0<=before<=spec.durability:return plain
    rating=spec.head_defense if region=='head' else spec.defense
    absorbed=min(before,amount*rating//100)
    if not absorbed:return plain
    after=before-absorbed
    inventory.items[1,slot]=replace(item,durability=after)
    return ArmourHit(amount-absorbed,absorbed,slot,item.uid,before,after)


def local_region(impact,feet):
    """Coarse standing body only; no claim about original bone/pose mapping."""
    height=impact[2]-feet[2]
    return 'head' if height>=145 else 'torso' if height>=55 else 'limb'
