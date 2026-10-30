from pathlib import Path
import json,struct
from native_codec_probe import NativeCodec,ROOT
c=NativeCodec();p=0x10900000;c.invoke(0xd13840,p,[])
rows=[]
expected=[(0xd00ff0,()),(0xd07530,(0,)),(0xd0b270,(0,)),(0xd01000,(2,)),(0xd0b210,(1,)),(0xd10c80,(4,7)),(0xd13380,(3,5)),(0xd07790,(1,3)),(0xd01950,(6,)),(0xd010d0,(6,8))]
for i,(fn,deps) in enumerate(expected):
 callback,done,a,b=struct.unpack('<IB3xII',c.uc.mem_read(p+16*i,16))
 actual=tuple((q-p)//16 for q in (a,b) if q)
 if callback!=fn or done or actual!=deps:raise ValueError((i,callback,done,actual))
 rows.append(dict(index=i,callback=hex(callback),depends=list(actual)))
report=dict(constructor='0xd13840',entries=rows,passed=True,limitation='Synthetic constructor; no renderer or live assets')
(ROOT/'private/typed-gameplay/model-loader-graph-20261030.json').write_text(json.dumps(report,indent=2),encoding='utf8')
print(json.dumps(report))
