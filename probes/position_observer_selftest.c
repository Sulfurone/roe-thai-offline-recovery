/* Pure accessor recognition, using only a synthetic buffer in this process. */
#include "position_observer.c"
static unsigned char fixture[4096];
static unsigned char health_fixture[4096];
static void expect(int ok) {if(!ok)ExitProcess(1);}
void WINAPI TestEntry(void) {
    Sample sample;clear_bytes(&sample,sizeof(sample));
    uintptr_t fn=(uintptr_t)fixture,component=(uintptr_t)(fixture+128);
    fixture[0]=0x8d;fixture[1]=0x41;fixture[2]=64;fixture[3]=0xc3;
    expect(position_pointer(fn,component,fn,&sample)==component+64);
    fixture[0]=0x8b;fixture[1]=0x41;fixture[2]=16;fixture[3]=0xc3;
    uint32_t value=component+64;copy_bytes((void*)(component+16),&value,4);
    expect(position_pointer(fn,component,fn,&sample)==component+64);
    fixture[0]=0xcc;
    expect(position_pointer(fn,component,fn,&sample)==0);
    fixture[0]=0x8d;fixture[1]=0x81;
    value=0x5000;copy_bytes(fixture+2,&value,4);fixture[6]=0xc3;
    expect(position_pointer(fn,component,fn,&sample)==0);
    expect(position_pointer(1,component,fn,&sample)==0);
    fixture[0]=0xe9;value=27;copy_bytes(fixture+1,&value,4);
    fixture[32]=0x8d;fixture[33]=0x41;fixture[34]=32;fixture[35]=0xc3;
    expect(position_pointer(fn,component,fn,&sample)==component+32);
    uintptr_t actor=fn+512,body=fn+1024,actor_vt=fn+2048,body_vt=fn+3072;
    value=actor_vt;copy_bytes((void*)actor,&value,4);
    value=body_vt;copy_bytes((void*)body,&value,4);
    value=fn+64;copy_bytes((void*)(actor_vt+0xa4),&value,4);
    value=body;copy_bytes((void*)(actor+64),&value,4);
    fixture[64]=0x8b;fixture[65]=0x41;fixture[66]=64;fixture[67]=0xc3;
    value=fn+80;copy_bytes((void*)(body_vt+0xec),&value,4);
    fixture[80]=0x8d;fixture[81]=0x41;fixture[82]=32;fixture[83]=0xc3;
    expect(entity_position(actor,fn,&sample,0)==body+32);
    /* Own synthetic conditional getter with a virtual boolean query. This is
     * not an original-game byte fixture; test offsets/layout are invented. */
    const unsigned char gate[]={0x56,0x8b,0xf1,0x8b,0x4e,0x40,0x85,0xc9,0x74,25,
        0x8b,0x01,0x8b,0x90,0x90,0,0,0,0xff,0xd2,0x84,0xc0,0x8b,0x46,0x40,
        0x74,6,0x8b,0x80,0x80,0,0,0,0x5e,0xc3,0x33,0xc0,0x5e,0xc3};
    copy_bytes(fixture+96,gate,sizeof(gate));
    value=fn+160;copy_bytes((void*)(body_vt+0x90),&value,4);
    fixture[160]=0xb0;fixture[161]=0;fixture[162]=0xc3;
    value=body;copy_bytes((void*)(actor+64),&value,4);
    uint32_t answer=0;
    expect(readonly_getter(fn+96,actor,fn,&sample,0,&answer) && answer==body);
    fixture[161]=1;
    value=fn+1280;copy_bytes((void*)(body+128),&value,4);
    expect(readonly_getter(fn+96,actor,fn,&sample,0,&answer) && answer==fn+1280);
    fixture[192]=0xc7;fixture[193]=0x41;fixture[194]=64;
    value=0xdeadbeef;copy_bytes(fixture+195,&value,4);fixture[199]=0xc3;
    expect(!readonly_getter(fn+192,actor,fn,&sample,0,&answer));
    expect(u32((void*)(actor+64))==body);
    fixture[224]=0xeb;fixture[225]=0xfe;
    expect(!readonly_getter(fn+224,actor,fn,&sample,0,&answer));
    /* Compound pointer getter: load a member pointer, then add a field offset. */
    const unsigned char compound[]={0x8b,0x41,16,0x05,12,0,0,0,0xc3};
    copy_bytes(fixture+256,compound,sizeof(compound));
    value=body;copy_bytes((void*)(actor+16),&value,4);
    expect(position_pointer(fn+256,actor,fn,&sample)==body+12);
    /* Scene hash lookup: collision chains compare both UID halves, skip the
     * end sentinel and fail closed on a malformed table or a cyclic chain. */
    uint32_t *table=(uint32_t*)(fixture+2048),*buckets=(uint32_t*)(fixture+2304);
    uint32_t *first=(uint32_t*)(fixture+2400),*second=(uint32_t*)(fixture+2464);
    uint32_t node=0;
    table[0x50/4]=(uint32_t)buckets;table[0x54/4]=4;
    buckets[0]=(uint32_t)first;buckets[4]=(uint32_t)(fixture+2528);
    first[0]=0x1100;first[1]=0x20000;first[4]=(uint32_t)second;
    second[0]=0x1100;second[1]=0x10000;second[4]=0;
    expect(hash_node((uintptr_t)table,0x50,0x54,0x10,0x1100,0x10000,&node)==1 && node==(uint32_t)second);
    expect(hash_node((uintptr_t)table,0x50,0x54,0x10,0x1100,0x30000,&node)==0);
    second[4]=(uint32_t)first;
    expect(hash_node((uintptr_t)table,0x50,0x54,0x10,0x1100,0x30000,&node)==-1);
    second[4]=buckets[4];
    expect(hash_node((uintptr_t)table,0x50,0x54,0x10,0x1100,0x30000,&node)==0);
    table[0x54/4]=0;
    expect(hash_node((uintptr_t)table,0x50,0x54,0x10,0x1100,0x10000,&node)==-1);
    table[0x54/4]=1048577;
    expect(hash_node((uintptr_t)table,0x50,0x54,0x10,0x1100,0x10000,&node)==-1);
    table[0x54/4]=4;buckets[0]=1;
    expect(hash_node((uintptr_t)table,0x50,0x54,0x10,0x1100,0x10000,&node)==-1);
    /* The interest cache uses the same key hash with different member offsets. */
    table[1]=(uint32_t)buckets;table[2]=4;buckets[0]=(uint32_t)first;
    first[0]=0x1100;first[1]=0x10000;first[12]=0;
    expect(hash_node((uintptr_t)table,4,8,0x30,0x1100,0x10000,&node)==1 && node==(uint32_t)first);
    /* Native HP properties are a separate UID table, never the actor body. */
    uint32_t *health_root=(uint32_t*)(fixture+3200);
    value=(uint32_t)health_root;copy_bytes(fixture,&value,4);
    health_root[1]=(uint32_t)table;
    table[2]=(uint32_t)buckets;table[3]=4;
    buckets[0]=(uint32_t)first;
    first[0]=0x100;first[1]=0x10000;first[2]=(uint32_t)health_fixture;first[4]=0;
    value=730^0xa59cf5b6u;copy_bytes(health_fixture+0x17c,&value,4);
    value=1000^0xa59cf5b6u;copy_bytes(health_fixture+0x184,&value,4);
    health_fixture[0x7ec]=0xdb;health_fixture[0x178]=0xdd;
    PeerSample peers;clear_bytes(&peers,sizeof(peers));
    player_health(fn-0x2aedc7c,&peers);
    expect(peers.hp_status==0 && peers.current==730 && peers.maximum==1000 && peers.death_tag==0xdd);
    value=0xa59cf5b6u;copy_bytes(health_fixture+0x17c,&value,4);health_fixture[0x178]=0xdc;
    player_health(fn-0x2aedc7c,&peers);
    expect(peers.hp_status==0 && peers.current==0 && peers.death_tag==0xdc);
    health_fixture[0x7ec]=0;
    player_health(fn-0x2aedc7c,&peers);
    expect(peers.hp_status==3 && peers.current==0 && peers.maximum==0);
    DWORD written;
    const char text[]="SELF_POSITION_ACCESSOR_TESTS_PASS\n";
    WriteFile(GetStdHandle(STD_OUTPUT_HANDLE),text,sizeof(text)-1,&written,NULL);
    ExitProcess(0);
}
