/* Local offline position observer. Reads only its own process, calls no game
 * functions, installs no hooks and changes no page protection or game data.
 * The two DataEngine exports forward to the hash-verified original DLL. */
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <stdint.h>

#pragma pack(push,1)
typedef struct {
    char magic[8],token[32];
    uint32_t pid,sequence,status,actor,getter;
    float xyz[3];
    unsigned char code[64];
} Sample;
#pragma pack(pop)
_Static_assert(sizeof(void*)==4,"Build for x86");
_Static_assert(sizeof(Sample)==136,"Position sample layout changed");

static int self_read(uintptr_t address,void *out,SIZE_T size) {
    SIZE_T read=0;
    return address>=0x10000 && size<=4096 &&
        ReadProcessMemory(GetCurrentProcess(),(void*)address,out,size,&read) && read==size;
}
static void copy_bytes(void *out,const void *in,unsigned n) {
    volatile unsigned char *d=out;const volatile unsigned char *s=in;
    while(n--)*d++=*s++;
}
static void clear_bytes(void *out,unsigned n) {
    volatile unsigned char *d=out;while(n--)*d++=0;
}
static int equal_bytes(const void *a,const void *b,unsigned n) {
    const unsigned char *x=a,*y=b;while(n--)if(*x++!=*y++)return 0;return 1;
}
static uint32_t u32(const unsigned char *b) {uint32_t v;copy_bytes(&v,b,4);return v;}

typedef struct {uint32_t r[8],stack[32];int top,zf;} ReadVM;
static int read_operand(ReadVM *vm,const unsigned char *b,unsigned width,uint32_t *value,
                        uintptr_t *address,int *used,int lea) {
    unsigned mod=b[0]>>6,reg=b[0]&7;*used=1;*address=0;
    if(mod==3) {
        if(lea)return 0;
        *value=width==1?(vm->r[reg&3]>>((reg&4)?8:0))&255:
               width==2?vm->r[reg]&65535:vm->r[reg];return 1;
    }
    uintptr_t addr=0;
    if(reg==4) {
        unsigned sib=b[1],index=(sib>>3)&7,base_reg=sib&7;*used=2;
        if(index!=4)addr=vm->r[index]<<(sib>>6);
        if(mod==0 && base_reg==5) {addr+=u32(b+2);*used=6;}
        else addr+=vm->r[base_reg];
    } else if(mod==0 && reg==5) {addr=u32(b+1);*used=5;}
    else addr=vm->r[reg];
    if(mod==1) {addr+=(int8_t)b[*used];(*used)++;}
    else if(mod==2) {addr+=(int32_t)u32(b+*used);*used+=4;}
    *address=addr;
    if(lea) {*value=addr;return 1;}
    *value=0;return self_read(addr,value,width);
}
static int read_reg_operand(ReadVM *vm,unsigned char modrm,uint32_t value,unsigned width) {
    if((modrm>>6)!=3)return 0; /* writes to game memory are never allowed */
    unsigned reg=modrm&7;
    if(width==1) {
        unsigned shift=(reg&4)?8:0;reg&=3;
        vm->r[reg]=(vm->r[reg]&~(255u<<shift))|((value&255)<<shift);
    } else vm->r[reg]=value;
    return 1;
}
/* A bounded read-only instruction interpreter, not a call into the engine.
 * Only register changes/local push-pop, reads, comparisons and branches are
 * recognized. Every store, unsupported instruction and over-budget loop fails.
 * This handles conditional pointer getters such as the observed E52170. */
static int readonly_getter(uintptr_t pc,uintptr_t self,uintptr_t base,Sample *sample,int depth,uint32_t *out) {
    if(depth>8)return 0;
    ReadVM vm;clear_bytes(&vm,sizeof(vm));vm.r[1]=self;
    if(pc>=base && pc<base+50941952u)self_read(pc,sample->code,sizeof(sample->code));
    for(unsigned step=0;step<128;step++) {
        unsigned char b[16];
        if(pc<base || pc>base+50941952u-sizeof(b) || !self_read(pc,b,sizeof(b)))return 0;
        unsigned op=b[0],n=1,reg;uint32_t v=0,other=0;uintptr_t addr=0;int used=0;
        if(op>=0x50 && op<=0x57) {
            if(vm.top>=32)return 0;vm.stack[vm.top++]=vm.r[op-0x50];
        } else if(op>=0x58 && op<=0x5f) {
            if(!vm.top)return 0;vm.r[op-0x58]=vm.stack[--vm.top];
        } else if(op>=0xb8 && op<=0xbf) {vm.r[op-0xb8]=u32(b+1);n=5;}
        else if(op>=0xb0 && op<=0xb3) {vm.r[op-0xb0]=(vm.r[op-0xb0]&~255u)|b[1];n=2;}
        else if(op==0xc3 || (op==0xc2 && b[1]==0 && b[2]==0)) {
            if(vm.top)return 0;*out=vm.r[0];return 1;
        } else if(op==0x90) {}
        else if(op==0xe9 || op==0xeb) {pc+=(op==0xe9?5+(int32_t)u32(b+1):2+(int8_t)b[1]);continue;}
        else if(op==0x74 || op==0x75) {
            pc+=2+((op==0x74?vm.zf:!vm.zf)?(int8_t)b[1]:0);continue;
        } else if(op==0xe8) {
            if(!readonly_getter(pc+5+(int32_t)u32(b+1),vm.r[1],base,sample,depth+1,&v))return 0;
            vm.r[0]=v;n=5;
        } else if(op==0xff) {
            reg=(b[1]>>3)&7;
            if((reg!=2 && reg!=4) || !read_operand(&vm,b+1,4,&v,&addr,&used,0))return 0;
            sample->getter=v;
            if(!readonly_getter(v,vm.r[1],base,sample,depth+1,&other))return 0;
            if(reg==4) {if(vm.top)return 0;*out=other;return 1;}
            vm.r[0]=other;n+=used;
        } else if(op==0x8b || op==0x8a || op==0x8d || op==0x33 || op==0x32 || op==0x85 || op==0x84 || op==0x3b || op==0x39) {
            unsigned width=(op==0x8a || op==0x32 || op==0x84)?1:4;reg=(b[1]>>3)&7;
            if(!read_operand(&vm,b+1,width,&v,&addr,&used,op==0x8d))return 0;
            other=width==1?(vm.r[reg&3]>>((reg&4)?8:0))&255:vm.r[reg];
            if(op==0x85 || op==0x84)vm.zf=(other&v)==0;
            else if(op==0x3b || op==0x39)vm.zf=other==v;
            else {
                if(op==0x33 || op==0x32) {v^=other;vm.zf=v==0;}
                if(width==1)read_reg_operand(&vm,(unsigned char)(0xc0|reg),v,1);
                else vm.r[reg]=v;
            }
            n+=used;
        } else if(op==0x83 || op==0x81 || op==0xf6 || op==0xf7) {
            unsigned width=op==0xf6?1:4;reg=(b[1]>>3)&7;
            if(!read_operand(&vm,b+1,width,&v,&addr,&used,0))return 0;
            other=(op==0x83)?(uint32_t)(int32_t)(int8_t)b[1+used]:
                  op==0xf6?b[1+used]:u32(b+1+used);
            if((op==0xf6 || op==0xf7) && reg==0)vm.zf=(v&other)==0;
            else if((op==0x83 || op==0x81) && reg==7)vm.zf=v==other;
            else {
                if(op!=0x83 && op!=0x81)return 0;
                if(reg==0)v+=other;else if(reg==5)v-=other;else if(reg==4)v&=other;else return 0;
                if(!read_reg_operand(&vm,b[1],v,width))return 0;vm.zf=v==0;
            }
            n+=used+((op==0x83 || op==0xf6)?1:4);
        } else if(op==0x0f && (b[1]==0xb6 || b[1]==0xb7)) {
            reg=(b[2]>>3)&7;
            if(!read_operand(&vm,b+2,b[1]==0xb6?1:2,&v,&addr,&used,0))return 0;
            vm.r[reg]=v;n=2+used;
        } else if(op==0x0f && (b[1]==0x84 || b[1]==0x85)) {
            pc+=6+((b[1]==0x84?vm.zf:!vm.zf)?(int32_t)u32(b+2):0);continue;
        } else if(op==0x0f && (b[1]==0x94 || b[1]==0x95)) {
            if(!read_reg_operand(&vm,b[2],b[1]==0x94?vm.zf:!vm.zf,1))return 0;n=3;
        } else if(op==0xa1) {
            if(!self_read(u32(b+1),&vm.r[0],4))return 0;n=5;
        } else if(op==0x05 || op==0x2d) {
            if(op==0x05)vm.r[0]+=u32(b+1);else vm.r[0]-=u32(b+1);
            vm.zf=vm.r[0]==0;n=5;
        } else if(op==0x24 || op==0x25 || op==0x3c || op==0x3d) {
            unsigned small=op==0x24 || op==0x3c;other=small?b[1]:u32(b+1);
            v=small?vm.r[0]&255:vm.r[0];
            if(op==0x3c || op==0x3d)vm.zf=v==other;
            else {v&=other;vm.zf=v==0;if(small)vm.r[0]=(vm.r[0]&~255u)|v;else vm.r[0]=v;}
            n=small?2:5;
        } else return 0;
        pc+=n;
    }
    return 0;
}

/* Resolve only a small, inspected family of pointer-returning accessors.
 * Unknown code is reported, never executed. Displacements stay in the actor's
 * bounded component region. Jump following stays within the main image. */
static uintptr_t resolve_pointer(uintptr_t fn,uintptr_t component,uintptr_t base,Sample *sample,int depth);
static uintptr_t entity_position(uintptr_t actor,uintptr_t base,Sample *sample,int depth) {
    uint32_t vt=0,getter=0,body_vt=0,position_getter=0;
    if(depth>4 || !self_read(actor,&vt,4) || !self_read(vt+0xa4,&getter,4))return 0;
    sample->getter=getter;
    uintptr_t body=resolve_pointer(getter,actor,base,sample,depth+1);
    if(!body || !self_read(body,&body_vt,4) || !self_read(body_vt+0xec,&position_getter,4))return 0;
    sample->getter=position_getter;
    return resolve_pointer(position_getter,body,base,sample,depth+1);
}
static uintptr_t resolve_pointer(uintptr_t fn,uintptr_t component,uintptr_t base,Sample *sample,int depth) {
    unsigned char b[64];
    if(depth>4)return 0;
    for(int i=0;i<4;i++) {
        if(fn<base || fn>=base+50941952u || !self_read(fn,b,sizeof(b)))return 0;
        copy_bytes(sample->code,b,sizeof(b));
        /* Original 10F2140: interface -10 -> actor virtual A4 -> body
         * virtual EC. Resolve the two accessors; never call either. */
        const unsigned char thunk[]={0x8b,0x41,0xf0,0x8b,0x90,0xa4,0,0,0};
        if(fn==base+0xcf2140u && equal_bytes(b,thunk,sizeof(thunk)))
            return entity_position(component-0x10,base,sample,depth+1);
        if(b[0]==0xe9) {fn+=5+(int32_t)u32(b+1);continue;}
        unsigned char *p=b;
        if(p[0]==0x55 && p[1]==0x8b && p[2]==0xec)p+=3;
        if(p[0]==0x8b && p[1]==0xc1 && p[2]==0xc3)return component;
        int indirect=0,bytes=0;int32_t offset=0;
        if((p[0]==0x8d || p[0]==0x8b) && p[1]==0x41) {
            indirect=p[0]==0x8b;offset=(int8_t)p[2];bytes=3;
        } else if((p[0]==0x8d || p[0]==0x8b) && p[1]==0x81) {
            indirect=p[0]==0x8b;offset=(int32_t)u32(p+2);bytes=6;
        } else {
            uint32_t result=0;
            return readonly_getter(fn,component,base,sample,0,&result)?result:0;
        }
        unsigned char *end=p+bytes;
        if(*end==0x5d)end++;
        if(offset<0 || offset>0x4000)return 0;
        if(*end!=0xc3) {
            uint32_t result=0;
            return readonly_getter(fn,component,base,sample,0,&result)?result:0;
        }
        uintptr_t address=component+offset;
        if(indirect) {uint32_t ptr;if(!self_read(address,&ptr,4))return 0;address=ptr;}
        return address;
    }
    return 0;
}
static uintptr_t position_pointer(uintptr_t fn,uintptr_t component,uintptr_t base,Sample *sample) {
    return resolve_pointer(fn,component,base,sample,0);
}

typedef struct {char magic[8],token[32];wchar_t expected[1024],output[1024];} Configuration;

static DWORD WINAPI observe(void *module) {
    static wchar_t expected[1024],actual[1024],output[1024],temporary[1040];
    static wchar_t config_path[1024],original_path[1024];
    DWORD module_len=GetModuleFileNameW((HMODULE)module,config_path,1024);
    if(!module_len || module_len>=980)return 0;
    wchar_t *slash=NULL;
    for(wchar_t *p=config_path;*p;p++)if(*p==L'\\')slash=p;
    if(!slash)return 0;
    slash[1]=0;lstrcpyW(original_path,config_path);
    lstrcatW(original_path,L"_ROE_Original_DataEngine.dll");
    lstrcatW(config_path,L"DataEngine.roe-position.bin");
    HANDLE config_file=CreateFileW(config_path,GENERIC_READ,FILE_SHARE_READ,NULL,OPEN_EXISTING,FILE_ATTRIBUTE_NORMAL,NULL);
    if(config_file==INVALID_HANDLE_VALUE)return 0;
    static Configuration config;DWORD got=0;
    BOOL loaded=ReadFile(config_file,&config,sizeof(config),&got,NULL);
    CloseHandle(config_file);
    if(!loaded || got!=sizeof(config) || !equal_bytes(config.magic,"ROECFG1",8) ||
       config.expected[1023] || config.output[1023])return 0;
    copy_bytes(expected,config.expected,sizeof(expected));copy_bytes(output,config.output,sizeof(output));
    DWORD actual_len=GetModuleFileNameW(NULL,actual,1024);
    if(!expected[0] || !output[0] || !actual_len || actual_len>=1024 || lstrcmpiW(expected,actual))return 0;
    if(!LoadLibraryW(original_path))return 0;
    lstrcpyW(temporary,output);lstrcatW(temporary,L".tmp");
    uintptr_t base=(uintptr_t)GetModuleHandleW(NULL);
    unsigned char dos[2];
    if(base!=0x400000 || !self_read(base,dos,2) || dos[0]!='M' || dos[1]!='Z')return 0;
    Sleep(15000);
    Sample sample;clear_bytes(&sample,sizeof(sample));
    copy_bytes(sample.magic,"ROEPOS1",7);copy_bytes(sample.token,config.token,32);
    sample.pid=GetCurrentProcessId();
    for(;;) {
        uint32_t manager=0,actor=0,vt=0,getter=0;
        sample.sequence++;sample.status=1;sample.actor=sample.getter=0;
        clear_bytes(sample.xyz,sizeof(sample.xyz));clear_bytes(sample.code,sizeof(sample.code));
        if(self_read(0x2eedb58,&manager,4) && self_read(manager+0x7c,&actor,4) &&
            self_read(actor+0x10,&vt,4) && self_read(vt+0x6c,&getter,4)) {
            sample.actor=actor;sample.getter=getter;sample.status=2;
            uintptr_t pos=position_pointer(getter,actor+0x10,base,&sample);
            float values[3];
            if(pos && self_read(pos,values,sizeof(values))) {
                int valid=1;
                for(int i=0;i<3;i++)if((u32((unsigned char*)&values[i])&0x7f800000u)==0x7f800000u ||
                        values[i]<=-2000000.f || values[i]>=2000000.f)valid=0;
                if(valid && (values[0]!=0.f || values[1]!=0.f)) {
                    copy_bytes(sample.xyz,values,sizeof(values));sample.status=0;
                }
            }
        }
        HANDLE file=CreateFileW(temporary,GENERIC_WRITE,0,NULL,CREATE_ALWAYS,FILE_ATTRIBUTE_NORMAL,NULL);
        if(file!=INVALID_HANDLE_VALUE) {
            DWORD written=0;BOOL ok=WriteFile(file,&sample,sizeof(sample),&written,NULL);
            CloseHandle(file);
            if(ok && written==sizeof(sample))MoveFileExW(temporary,output,MOVEFILE_REPLACE_EXISTING);
        }
        Sleep(100);
    }
}

BOOL WINAPI DllMain(HINSTANCE module,DWORD reason,LPVOID reserved) {
    (void)reserved;
    if(reason==DLL_PROCESS_ATTACH) {
        DisableThreadLibraryCalls(module);
        HANDLE thread=CreateThread(NULL,0,observe,module,0,NULL);
        if(thread)CloseHandle(thread);
    }
    return TRUE;
}
