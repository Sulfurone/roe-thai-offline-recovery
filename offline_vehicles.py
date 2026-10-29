"""Bounded land-vehicle facts from the original Thai EuVehicleTable.

Generated assets stay private. These IDs select native models, not renamed
Jeep entities. Client rendering/driving still require individual acceptance.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class VehicleSpec:
    name:str
    hp:int
    seats:int
    geton_distance:int=500


LAND_VEHICLES={
    101:VehicleSpec('四座吉普车',24000,4),
    102:VehicleSpec('双座吉普车',18000,2),
    103:VehicleSpec('四座轿车',16000,4),
    104:VehicleSpec('双座轿车',14000,2),
    105:VehicleSpec('皮卡',24000,4),
    106:VehicleSpec('Tuk-tuk',10000,4),
    107:VehicleSpec('四座轿车（107）',14000,4),
    108:VehicleSpec('摩托车',10000,4),
}

# Keep original table facts separate from the spawn policy. The Thai renderer
# has reported a fatal VE_Motor_001a_Wheel archetype load error for the motorbike;
# successful wire decoding or an earlier driving test cannot certify its assets.
UNAVAILABLE_LAND_VEHICLES={
    108:'摩托车车轮配置载入报错，暂不可刷新；请选择其他车型',
}
SPAWNABLE_LAND_VEHICLES={key:spec for key,spec in LAND_VEHICLES.items()
                         if key not in UNAVAILABLE_LAND_VEHICLES}
