/* Pure accessor recognition, using only a synthetic buffer in this process. */
#include "position_observer.c"
static unsigned char fixture[4096];
static unsigned char health_fixture[4096];
static unsigned char equipment_fixture[8192];
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
    VisualRow visual;clear_bytes(&visual,sizeof(visual));
    visual_row(0,fn,&visual);expect(visual.status==1);
    value=0xfffffffd;copy_bytes(health_fixture+0x340,&value,4);
    value=(uint32_t)fixture;copy_bytes(health_fixture+0x104,&value,4);
    value=(uint32_t)(fixture+256);copy_bytes(fixture,&value,4);health_fixture[0x11a]=1;
    uint32_t target=fn+0x8f1330;copy_bytes(fixture+256+0xb0,&target,4);
    target=fn+0x90d2b0;copy_bytes(fixture+256+0x1c4,&target,4);
    target=fn+0x901780;copy_bytes(fixture+256+0x258,&target,4);
    fixture[0x480]=1;fixture[0x8ff]=1;
    target=1;copy_bytes(fixture+0x48c,&target,4);
    target=(uint32_t)health_fixture;copy_bytes(fixture+0xa8,&target,4);
    target=0x12345678;copy_bytes(health_fixture+0xf0,&target,4);
    fixture[0xc]=1;fixture[0xd]=1;fixture[0xe]=1;
    target=(uint32_t)health_fixture;copy_bytes(fixture+0x828,&target,4);
    visual_row((uint32_t)health_fixture,fn,&visual);
    expect(visual.status==0 && visual.display_mask==0xfffffffd &&
           visual.visual==(uint32_t)fixture && visual.visual_vtable==value && visual.secondary_gate==1 &&
           visual.gates==0x010101 && visual.nested==(uint32_t)health_fixture &&
           visual.model_gate==1 && visual.loader_ready==1 && visual.loader_stage==1 &&
           visual.model_wrapper==(uint32_t)health_fixture && visual.render_model==0x12345678);
    target=0;copy_bytes(fixture+0xa8,&target,4);fixture[0x480]=0;
    clear_bytes(&visual,sizeof(visual));visual_row((uint32_t)health_fixture,fn,&visual);
    expect(visual.status==0 && !visual.model_wrapper && !visual.render_model && !visual.model_gate);
    target=1;copy_bytes(fixture+0xa8,&target,4);
    clear_bytes(&visual,sizeof(visual));visual_row((uint32_t)health_fixture,fn,&visual);expect(visual.status==2);
    visual_row(1,fn,&visual);expect(visual.status==2);
    /* Slot lookup never inserts an empty native map entry. Exercise hash
     * collisions, missing/invalid nodes, telescope type and model presence. */
    uint32_t *inventory=(uint32_t*)equipment_fixture;
    uint32_t *eqb=(uint32_t*)(equipment_fixture+512),*eqnode=(uint32_t*)(equipment_fixture+544);
    uint32_t *gun=(uint32_t*)(equipment_fixture+1024),*slots=(uint32_t*)(equipment_fixture+3072);
    uint32_t *scope=(uint32_t*)(equipment_fixture+3200),*scopevt=(uint32_t*)(equipment_fixture+3328);
    uint32_t *normal=(uint32_t*)(equipment_fixture+4096),*zoom=(uint32_t*)(equipment_fixture+4608);
    value=(uint32_t)inventory;copy_bytes(health_fixture+0x7c0,&value,4);
    inventory[0x84/4]=(uint32_t)eqb;inventory[0x88/4]=1;eqb[0]=(uint32_t)eqnode;
    eqnode[0]=1;eqnode[1]=(uint32_t)gun;
    gun[0]=(uint32_t)scopevt;gun[0x18/4]=0x100101;gun[0x20/4]=10201;gun[0x24/4]=1;
    gun[0x60/4]=19;gun[0x39c/4]=30;
    gun[0x66c/4]=(uint32_t)health_fixture;gun[0x674/4]=(uint32_t)normal;
    gun[0x6b4/4]=(uint32_t)slots;gun[0x6b8/4]=(uint32_t)(slots+7);
    slots[2]=(uint32_t)scope;scope[0]=(uint32_t)scopevt;scopevt[1]=fn+0xc62840u;
    scope[0x20/4]=40303;scope[0x4c/4]=(uint32_t)health_fixture;
    scope[0x48/4]=(uint32_t)normal;scope[0x58/4]=(uint32_t)zoom;
    scope[0x5c/4]=1;normal[0xf4/4]=0;zoom[0xf4/4]=1;
    EquipmentSample equipment;clear_bytes(&equipment,sizeof(equipment));
    equipment_rows((uint32_t)health_fixture,fn,&equipment);
    expect(equipment.inventory==(uint32_t)inventory && equipment.rows[0].status==0 &&
           equipment.rows[1].status==2 && equipment.rows[0].loaded==19 &&
           equipment.rows[0].scope_template==40303 && equipment.rows[0].ads_mode==1 &&
           equipment.rows[0].normal_flag==0 && equipment.rows[0].ads_flag==1);
    expect(equipment_object((uint32_t)inventory,2,&value)==0 && value==0 && !eqnode[2]);
    scopevt[1]=fn+0xc62730u;equipment_rows((uint32_t)health_fixture,fn,&equipment);
    expect(equipment.rows[0].status==4);scopevt[1]=fn+0xc62840u;
    gun[0x6b8/4]=(uint32_t)(slots+8);equipment_rows((uint32_t)health_fixture,fn,&equipment);
    expect(equipment.rows[0].status==4);gun[0x6b8/4]=(uint32_t)(slots+7);
    slots[2]=0;equipment_rows((uint32_t)health_fixture,fn,&equipment);
    expect(equipment.rows[0].status==0 && !equipment.rows[0].scope &&
           !equipment.rows[0].ads_model && equipment.rows[0].ads_flag==0xffffffffu);
    eqnode[2]=(uint32_t)eqnode;
    expect(equipment_object((uint32_t)inventory,2,&value)==-1);
    eqnode[2]=0;inventory[0x88/4]=0;
    expect(equipment_object((uint32_t)inventory,1,&value)==-1);
    equipment_rows(0,fn,&equipment);expect(equipment.rows[0].status==1);
    DWORD written;
    const char text[]="SELF_POSITION_ACCESSOR_TESTS_PASS\n";
    WriteFile(GetStdHandle(STD_OUTPUT_HANDLE),text,sizeof(text)-1,&written,NULL);
    ExitProcess(0);
}
