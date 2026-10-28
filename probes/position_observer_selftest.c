/* Pure accessor recognition, using only a synthetic buffer in this process. */
#include "position_observer.c"
static unsigned char fixture[4096];
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
    DWORD written;
    const char text[]="SELF_POSITION_ACCESSOR_TESTS_PASS\n";
    WriteFile(GetStdHandle(STD_OUTPUT_HANDLE),text,sizeof(text)-1,&written,NULL);
    ExitProcess(0);
}
