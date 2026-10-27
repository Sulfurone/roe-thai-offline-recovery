"""Read only the known local test entity in the verified Thai client.

No code injection, memory writes, input injection, privilege adjustment,
network access or general heap dump. All reads are bounded and output stays
under recovery/private. Exact process path and creation time are mandatory.
"""
import argparse
import ctypes as c
from ctypes import wintypes as w
import datetime
import hashlib
import json
from pathlib import Path
import struct

ROOT=Path(__file__).resolve().parents[1]
CLIENT=ROOT.parent/'32838/Europa_Client.exe'
EXPECTED='ff980bec18fe325d2cfb0b624f0a3b3c9911ccbb4cdbc16c5d40b3a47852619a'
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--pid',type=int,required=True)
p.add_argument('--created',required=True)
p.add_argument('--output',type=Path,required=True)
a=p.parse_args()
output=a.output.resolve()
if not output.is_relative_to((ROOT/'private').resolve()):
    raise ValueError('Inspection output must stay in recovery/private')
report={'pid':a.pid,'operation':'bounded read-only local ground entity',
        'time':datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).isoformat()}
k=c.WinDLL('kernel32',use_last_error=True)
k.OpenProcess.argtypes=[w.DWORD,w.BOOL,w.DWORD]
k.OpenProcess.restype=w.HANDLE
k.CloseHandle.argtypes=[w.HANDLE]
k.QueryFullProcessImageNameW.argtypes=[w.HANDLE,w.DWORD,w.LPWSTR,c.POINTER(w.DWORD)]
k.ReadProcessMemory.argtypes=[w.HANDLE,c.c_void_p,c.c_void_p,c.c_size_t,c.POINTER(c.c_size_t)]
k.GetProcessTimes.argtypes=[w.HANDLE,c.POINTER(w.FILETIME),c.POINTER(w.FILETIME),c.POINTER(w.FILETIME),c.POINTER(w.FILETIME)]
handle=None
try:
    if hashlib.sha256(CLIENT.read_bytes()).hexdigest()!=EXPECTED:
        raise ValueError('Original client file hash differs')
    handle=k.OpenProcess(0x410,False,a.pid)
    if not handle:raise c.WinError(c.get_last_error())
    path=c.create_unicode_buffer(32768)
    length=w.DWORD(len(path))
    if not k.QueryFullProcessImageNameW(handle,0,path,c.byref(length)):
        raise c.WinError(c.get_last_error())
    if Path(path.value).resolve()!=CLIENT.resolve():
        raise ValueError('Process executable is not the verified Thai client')
    created,exited,kernel,user=(w.FILETIME() for _ in range(4))
    if not k.GetProcessTimes(handle,c.byref(created),c.byref(exited),c.byref(kernel),c.byref(user)):
        raise c.WinError(c.get_last_error())
    ticks=(created.dwHighDateTime<<32)|created.dwLowDateTime
    actual=datetime.datetime(1601,1,1,tzinfo=datetime.timezone.utc)+datetime.timedelta(microseconds=ticks//10)
    wanted=datetime.datetime.fromisoformat(a.created).astimezone(datetime.timezone.utc)
    if abs((actual-wanted).total_seconds())>.001:
        raise ValueError('Process creation time changed')
    report['identity']={'path':str(CLIENT),'created':actual.isoformat(),'sha256':EXPECTED}
    read_total=0
    def read(address,size):
        global read_total
        if not 0x10000<=address<0x80000000 or not 0<size<=16384 or read_total+size>131072:
            raise ValueError('Read exceeds the bounded 32-bit entity inspection')
        buffer=c.create_string_buffer(size)
        received=c.c_size_t()
        if not k.ReadProcessMemory(handle,address,buffer,size,c.byref(received)) or received.value!=size:
            raise c.WinError(c.get_last_error())
        read_total+=size
        return buffer.raw
    def u32(address):return struct.unpack('<I',read(address,4))[0]
    def vector_string(address):
        start,end,capacity=struct.unpack('<3I',read(address,12))
        if not start<=end<=capacity or end-start>256:
            raise ValueError('Unexpected bounded config string')
        return read(start,end-start).decode('utf-8') if end>start else ''
    if read(0x400000,2)!=b'MZ':raise ValueError('Expected original image base')
    manager=u32(0x2eedb58)
    entities=u32(manager+0x74)
    table,buckets=struct.unpack('<2I',read(entities+0x14,8))
    if not 1<=buckets<=65536:raise ValueError('Unexpected entity hash bucket count')
    entity_uid=0x400001
    node=u32(table+(entity_uid%buckets)*4)
    seen=set()
    found=None
    while node:
        if node in seen or len(seen)>=32:raise ValueError('Entity chain outside bound')
        seen.add(node)
        low,high,pointer,unused,next_node=struct.unpack('<5I',read(node,20))
        if (low,high)==(entity_uid,0):
            found=pointer
            break
        node=next_node
    report['entity_hash']={'buckets':buckets,'chain_nodes_read':len(seen),'found':found is not None}
    if found:
        data=read(found,0x5d0)
        at=lambda offset:struct.unpack_from('<I',data,offset)[0]
        report['entity']={'uid':hex(entity_uid),'native_type':at(0x498),
            'template':at(0x34c),'count':at(0x350),'entity_id':at(0x4c8),
            'using_entity':at(0x340),'removed':data[0x48d],
            'has_model':bool(at(0x104)),'has_config':bool(at(0x500)),
            'slot_list_bytes':at(0x5bc)-at(0x5b8)}
        config=at(0x500)
        if config:
            row=read(config,0x134)
            report['config']={'id':struct.unpack_from('<I',row)[0],
                'name':vector_string(config+4),'model':vector_string(config+0x20),
                'kind':struct.unpack_from('<I',row,0x14)[0],
                'subtype':struct.unpack_from('<I',row,0x18)[0],
                'pickup_distance_cm':struct.unpack_from('<I',row,0x4c)[0]}
    report['bytes_read']=read_total
    report['status']='inspected'
except Exception as error:
    report.update(status='failed',error=str(error))
finally:
    if handle:k.CloseHandle(handle)
output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps(report,ensure_ascii=True,indent=2))
