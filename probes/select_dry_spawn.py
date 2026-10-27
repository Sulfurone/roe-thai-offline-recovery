"""Choose nearby, locally flat land from the Thai map's own PhysX height field."""
import array
import json
from pathlib import Path
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
folder = ROOT/'private/terrain-collision'
root = ET.parse(folder/'RigidTerrain.repx').getroot()
hf = root.find('PxHeightField')
rows,cols = int(hf.findtext('NbRows')),int(hf.findtext('NbColumns'))
actor = root.find('PxRigidStatic')
pose = list(map(float,actor.findtext('GlobalPose').split()))
geo = actor.find('Shapes/PxShape/Geometry/PxHeightFieldGeometry')
height_scale = float(geo.findtext('HeightScale'))
row_scale,col_scale = float(geo.findtext('RowScale')),float(geo.findtext('ColumnScale'))
if pose[:4] != [0.5]*4 or pose[4:6] != [0,0] or (row_scale,col_scale)!=(200,200):
    raise ValueError('Unexpected terrain transform; do not guess world axes')
# Quaternion(.5,.5,.5,.5) maps local X->world Y, Y->world Z, Z->world X.
samples = array.array('I',map(int,hf.findtext('samples').split()))
if len(samples)!=rows*cols:
    raise ValueError('Height field sample count changed')
def height(row,col):
    n = samples[row*cols+col]&0xffff
    if n>=32768:n-=65536
    return pose[6]+n*height_scale

old_x,old_y = 325800,271700
origin_r,origin_c = round(old_y/row_scale),round(old_x/col_scale)
candidates = []
for r in range(max(4,origin_r-400),min(rows-4,origin_r+401),2):
    for c in range(max(4,origin_c-400),min(cols-4,origin_c+401),2):
        z = height(r,c)
        if not 7000 < z < 30000:continue
        near = [height(r+dr,c+dc) for dr in (-3,0,3) for dc in (-3,0,3)]
        if max(near)-min(near)>100:continue
        distance2 = (c*col_scale-old_x)**2+(r*row_scale-old_y)**2
        candidates.append((distance2,r,c,z,max(near)-min(near)))
if not candidates:
    raise ValueError('No nearby flat land above water margin')
d2,r,c,z,spread = min(candidates)
old_r,old_c = int(old_y/row_scale),int(old_x/col_scale)
old_cell = [height(old_r+dr,old_c+dc) for dr in (0,1) for dc in (0,1)]
spawn = [round(c*col_scale),round(r*row_scale),round(z+250)]
selection = 'nearby_flat_land'
if min(old_cell)>6500:
    # Prefer changing only Z: spawning below a one-sided terrain surface can
    # leave the actor under land despite otherwise valid XY coordinates.
    spawn = [old_x,old_y,round(max(old_cell)+250)]
    z,spread,d2 = max(old_cell),max(old_cell)-min(old_cell),0
    selection = 'original_xy_above_terrain_cell'
report = {'map_id':16006,'terrain_size_cm':[cols*col_scale,rows*row_scale],
          'old_xy_cm':[old_x,old_y],
          'old_nearest_terrain_height_cm':height(origin_r,origin_c),
          'spawn_cm':spawn,'selection':selection,
          'terrain_height_cm':z,'selected_sample_height_spread_cm':spread,
          'distance_from_old_spawn_m':d2**0.5/100,
          'note':'Terrain-only dry-land candidate; client movement remains unverified'}
(folder/'dry-spawn.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps(report,indent=2))
