"""Follow the original single-item spawn through EVENT_ENTITY_ADD.

Runs original factory branches, DTO setters, item lookup, event callback and
nearby-list insertion. Resource construction, hash registration, model/UI
accessors and the event bus are isolated dependencies, not live-game proof.
"""
import contextlib
import io
import json
from pathlib import Path
import runpy
import struct

# Reuse the validated synthetic entity manager and original RTTI/vtable.
HERE=Path(__file__).resolve().parent
with contextlib.redirect_stdout(io.StringIO()):
    h=runpy.run_path(str(HERE/'validate_native_ground_pickup.py'))
c=h['c']
c.uc.mem_map(0,4096)  # Isolated x86 TIB/SEH head; no exception path is simulated.
manager,entities,entity=h['manager'],h['entities'],h['entity']
buckets,node,nearby=h['buckets'],h['node'],h['nearby']
configuration,entity_table=h['configuration'],h['entity_table']
component_vt=h['component_vt']
ROOT=h['ROOT']
from unicorn import UC_HOOK_CODE
from unicorn.x86_const import UC_X86_REG_EAX,UC_X86_REG_EDX,UC_X86_REG_ECX,UC_X86_REG_ESP,UC_X86_REG_EIP
from offline_inventory import Item
from offline_ground_loot import GroundStack
from extract_original_item_defaults import extract as extract_items

item_table,item_row,item_name=0x10810000,0x10811000,0x10811800
event_vector,event_wrapper,event_data,event_vt=0x10812000,0x10812100,0x10812200,0x10812300
virtuals,shim,model_getter,uid_setter,title_setter=0x10814000,0x109f0100,0x109f0120,0x109f0140,0x109f0160
image_vt=bytes(c.uc.mem_read(0x25b35f8,0x160))
c.uc.mem_write(virtuals,image_vt)
for offset,fn in ((0xb0,uid_setter),(0x110,title_setter),(0x114,title_setter)):
    c.uc.mem_write(virtuals+offset,struct.pack('<I',fn))
c.uc.mem_write(component_vt+0x10c,struct.pack('<I',model_getter))

# Decode the entire original row vector; the native lookup below needs only
# the queried row's ID/name, not its remaining UI/trade/attachment fields.
source=ROOT/'extracted/tablebin/08e66a956e5d5647.bin'
original_items=extract_items(source)
original_ammo=next(row for row in original_items['rows'] if row['dwStringID']==30001)
name=original_ammo['szName'].encode('utf-8')
c.uc.mem_write(item_name,name+b'\0')
c.uc.mem_write(item_row,struct.pack('<II',30001,item_name))
for address,value in ((manager+0xe4,item_table),(manager+0x114,0),(manager+0x120,0),
        (item_table+0x40,item_row),(item_table+0x44,item_row+0x2d0),
        (entities+0x68,nearby+4*0x28),(event_vector,event_wrapper),
        (event_wrapper+4,event_data),(event_data,event_vt),(event_data+4,entity),
        (event_vt+4,0x10f9450),(0x2984364,1)):
    c.uc.mem_write(address,struct.pack('<I',value))

matcher=c.read32(0x1cc1570)
page=matcher&~4095
c.uc.mem_map(page,4096)
c.uc.mem_write(matcher,b'\xc3')
external=(shim,model_getter,uid_setter,title_setter,matcher)
for address in external:
    c.external_hooks.add(address)
    if address!=matcher:c.uc.mem_write(address,b'\xc3')
events=[]
models=[]
pending=[]

def hook(uc,address,size,user):
    stack=uc.reg_read(UC_X86_REG_ESP)
    ret=c.read32(stack)
    ecx=uc.reg_read(UC_X86_REG_ECX)
    consumed,result,high=0,0,0
    if address==0x68ac70:pass
    elif address==0x65b7c0:
        consumed=4
        # This constructor is used here only for the reflection class token.
        uc.mem_write(ecx,struct.pack('<I',c.read32(stack+4)))
        result=ecx
    elif address==0x6825f0:
        consumed=8
        result=entity
    elif address==uid_setter:
        consumed=8
        actual=struct.unpack('<Q',uc.mem_read(stack+4,8))[0]
        if actual!=0x400001:raise ValueError('Original UID assignment differs')
    elif address==0x1097e70:
        consumed=8
        models.append({'template':c.read32(configuration),'entity':c.read32(stack+4)})
    elif address==0x10fb4f0:
        consumed=4
        if c.read32(stack+4)!=entity:raise ValueError('Different native entity registered')
        uc.mem_write(buckets+4,struct.pack('<I',node))
    elif address==0x401330:
        consumed=4
        pointer=c.read32(stack+4)
        raw=bytes(uc.mem_read(pointer,256)).split(b'\0',1)[0]
        if len(raw)==256:raise ValueError('Unbounded synthetic string dependency')
        uc.mem_write(ecx,struct.pack('<III',pointer,pointer+len(raw),pointer+len(raw)+1))
        result=ecx
    elif address==0x40a9e0:
        consumed=4
        result=ecx
    elif address==title_setter:consumed=4
    elif address==0x65ae90:pass
    elif address==0x1130780:pass
    elif address==model_getter:pass
    elif address==0x108ebe0:pass
    elif address==matcher:
        consumed=4
        result=int(ecx==0x28fbb74 and c.read32(stack+4)==0x28fbb74)
    elif address==0x10fcfd0:
        string=c.read32(c.read32(stack+4))
        label=bytes(uc.mem_read(string,80)).split(b'\0',1)[0]
        actual=c.read32(c.read32(stack+8))
        if label!=b'EVENT_ENTITY_ADD' or actual!=entity:
            raise ValueError(f'Unexpected native event dispatch {label!r}/{actual:#x}')
        events.append(label.decode())
        pending.append((ret,stack))
        # Redirect only the event bus to the original registered callback.
        uc.mem_write(stack-4,struct.pack('<II',shim,event_vector))
        uc.reg_write(UC_X86_REG_ECX,entities)
        uc.reg_write(UC_X86_REG_ESP,stack-4)
        uc.reg_write(UC_X86_REG_EIP,0x10fb840)
        return
    elif address==shim:
        actual_ret,actual_stack=pending.pop()
        uc.reg_write(UC_X86_REG_ESP,actual_stack+4)
        uc.reg_write(UC_X86_REG_EIP,actual_ret)
        return
    else:raise ValueError(f'Unexpected stub {address:#x}')
    uc.reg_write(UC_X86_REG_EAX,result)
    uc.reg_write(UC_X86_REG_EDX,high)
    uc.reg_write(UC_X86_REG_ESP,stack+4+consumed)
    uc.reg_write(UC_X86_REG_EIP,ret)

for address in external+(0x68ac70,0x65b7c0,0x6825f0,0x1097e70,0x10fb4f0,
        0x401330,0x40a9e0,0x65ae90,0x1130780,0x108ebe0,0x10fcfd0):
    c.uc.hook_add(UC_HOOK_CODE,hook,begin=address,end=address)

message,body=GroundStack(0x400001,(325950,271700,6501),Item(3,30001,1048835,60)).spawn()
check=c.decode_server(message,body)
if check['code'] or check['consumed']!=len(body)+10:raise ValueError('Production spawn does not decode')
dto=c.ROOT_OBJECT+10
report={'original_spawn':'0x1283140','original_factory':'0x1097250',
        'original_item_lookup':'0x1130E30 -> 0x7ADC10',
        'original_add_callback':'0x10FB840 -> 0x10FB740','cases':[]}
for item_available in (False,True):
    c.uc.mem_write(entity,bytes(0x600))
    for address,value in ((entity,virtuals),(entity+0x10,component_vt),(entity+0x340,0xffffffff),
            (buckets+4,0),(entities+0x64,nearby),(entities+0x120,0),(entities+0xa0,0),
            (item_table+0x44,item_row+(0x2d0 if item_available else 0))):
        c.uc.mem_write(address,struct.pack('<I',value))
    before=len(events)
    c.invoke(0x1283140,0,[dto,0])
    entries=(c.read32(entities+0x64)-nearby)//0x28
    if entries!=int(item_available) or len(events)-before!=int(item_available):
        raise ValueError('Original item lookup/event/nearby insertion differs')
    fields={name:c.read32(entity+offset) for name,offset in
            (('kind',0x4b0),('type',0x498),('template',0x34c),('count',0x350),('entity_id',0x4c8))}
    if fields!={'kind':1,'type':1,'template':30001,'count':60,'entity_id':0x400001}:
        raise ValueError(f'Original spawn fields differ: {fields}')
    if item_available:
        row=bytes(c.uc.mem_read(nearby,0x28))
        if struct.unpack_from('<Q',row)[0]!=0x400001 or struct.unpack_from('<I',row,0xc)[0]!=1:
            raise ValueError('Original nearby entry has different UID/type')
        # Repeated original callback must not duplicate the nearby entry.
        c.invoke(0x10fb840,entities,[event_vector])
        if c.read32(entities+0x64)!=nearby+0x28:raise ValueError('Duplicate nearby entity')
    report['cases'].append(dict(item_available=item_available,nearby_entries=entries,
        entity_add_events=len(events)-before,**fields))
report['source_item_table']=source.name
report['source_item_name']=name.decode()
report['source_item_rows_verified']=original_items['row_count']
report['limitation']='Synthetic resource factory, model/UI dependencies, hash registration and event bus; no rendering/live pickup proof'
destination=ROOT/'private/native-roster/native-ground-spawn-validation.json'
destination.write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps(report,indent=2))
