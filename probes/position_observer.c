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
typedef struct {
    uint32_t low,high,status,actor,vtable,flags,removed,body,interest;
    float xyz[3];
} PeerRow;
typedef struct {
    char magic[8],token[32];
    uint32_t pid,sequence,count;
    uint32_t hp_status,current,maximum,death_tag;
    PeerRow rows[4];
} PeerSample;
typedef struct {
    uint32_t low,high,status,actor,display_mask,visual,visual_vtable,secondary_gate,gates,nested;
    uint32_t model_wrapper,render_model,model_gate,loader_ready,loader_stage;
    uint32_t loader_done,loader_callbacks,loader_pending,loader_unreadable;
    uint32_t actor_resource,actor_resource_ready,runtime_resource,runtime_data,resource_unreadable;
    uint32_t actor_name_status,runtime_name_status;
    char actor_name[96],runtime_name[96];
} VisualRow;
typedef struct {
    char magic[8],token[32];
    uint32_t pid,sequence,count;
    VisualRow rows[5];
} VisualSample;
typedef struct {
    uint32_t slot,status,item,vtable,low,high,template_id,owner,model,loaded,capacity,dirty;
    uint32_t scope,scope_vtable,scope_template,scope_owner,normal_model,ads_model,ads_mode;
    uint32_t normal_flag,ads_flag;
} EquipmentRow;
typedef struct {
    char magic[8],token[32];
    uint32_t pid,sequence,count,inventory;
    EquipmentRow rows[2];
} EquipmentSample;
#pragma pack(pop)
_Static_assert(sizeof(void*)==4,"Build for x86");
_Static_assert(sizeof(Sample)==136,"Position sample layout changed");
_Static_assert(sizeof(PeerSample)==260,"Peer diagnostic layout changed");
_Static_assert(sizeof(VisualSample)==1532,"Visual diagnostic layout changed");
_Static_assert(sizeof(EquipmentSample)==224,"Equipment diagnostic layout changed");

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

/* Read-only copies of the own build's F074E0 scene and 1365120 interest
 * hash lookups. No game function is called, no scan outside four local bot
 * IDs is made. Return -1 on unavailable/malformed/changing data, 0 absent,
 * 1 present. Bounds also stop cycles and never divide by a zero count. */
static int hash_node(uintptr_t table,unsigned buckets_offset,unsigned count_offset,
                     unsigned next_offset,uint32_t low,uint32_t high,uint32_t *found) {
    uint32_t buckets=0,count=0,node=0,sentinel=0;
    *found=0;
    if(!self_read(table+buckets_offset,&buckets,4) ||
       !self_read(table+count_offset,&count,4) || !count || count>1048576u ||
       !self_read(buckets+count*4,&sentinel,4) ||
       !self_read(buckets+(low%count)*4,&node,4))return -1;
    for(unsigned step=0;node && node!=sentinel && step<128;step++) {
        uint32_t key[2],next=0;
        if(!self_read(node,key,8))return -1;
        if(key[0]==low && key[1]==high) {*found=node;return 1;}
        if(!self_read(node+next_offset,&next,4) || next==node)return -1;
        node=next;
    }
    return !node || node==sentinel?0:-1;
}

static int valid_xyz(float values[3]) {
    for(int i=0;i<3;i++)if((u32((unsigned char*)&values[i])&0x7f800000u)==0x7f800000u ||
        values[i]<=-2000000.f || values[i]>=2000000.f)return 0;
    return values[0]!=0.f || values[1]!=0.f;
}

static void peer_rows(uintptr_t manager,uintptr_t base,PeerSample *out) {
    uint32_t scene=0;
    self_read(manager+0x1c,&scene,4);
    for(unsigned i=0;i<4;i++) {
        PeerRow *row=out->rows+i;
        clear_bytes(row,sizeof(*row));
        row->low=0x1100+i;row->high=0x10000;row->status=1;
        uint32_t node=0,vt=0,getter=0;
        int present=hash_node(base+0x2aedc90,4,8,0x30,row->low,row->high,&node);
        row->interest=present<0?2:(uint32_t)present;
        if(!scene)continue;
        present=hash_node(scene,0x50,0x54,0x10,row->low,row->high,&node);
        row->status=present<0?4:2;
        if(present!=1 || !self_read(node+8,&row->actor,4) || !row->actor)continue;
        row->status=3;
        unsigned char removed=0;
        if(!self_read(row->actor,&row->vtable,4) ||
           !self_read(row->actor+0x2f8,&row->flags,4) ||
           !self_read(row->actor+0x40f,&removed,1)) {row->status=4;continue;}
        row->removed=removed;
        if(removed) {row->status=5;continue;}
        Sample diagnostic;clear_bytes(&diagnostic,sizeof(diagnostic));
        if(self_read(row->vtable+0xa4,&getter,4))
            row->body=(uint32_t)resolve_pointer(getter,row->actor,base,&diagnostic,0);
        if(self_read(row->actor+0x10,&vt,4) && self_read(vt+0x6c,&getter,4)) {
            uintptr_t pos=position_pointer(getter,row->actor+0x10,base,&diagnostic);
            float xyz[3];
            if(pos && self_read(pos,xyz,sizeof(xyz)) && valid_xyz(xyz)) {
                copy_bytes(row->xyz,xyz,sizeof(xyz));row->status=0;
            }
        }
    }
}

/* Original 108D720 -> 113E2C0 -> 113C6A0 property lookup and 139FA40
 * HP decoding, read only. A successful server send alone does not prove
 * the own actor consumed it. No object construction/initialization here. */
static void player_health(uintptr_t base,PeerSample *out) {
    uint32_t root=0,table=0,node=0,props=0,current=0,maximum=0;
    unsigned char guard=0,death=0;
    out->hp_status=1;out->current=out->maximum=out->death_tag=0;
    if(!self_read(base+0x2aedc7c,&root,4) || !self_read(root+4,&table,4))return;
    int found=hash_node(table,8,0xc,0x10,0x100,0x10000,&node);
    if(found!=1) {out->hp_status=found<0?1:2;return;}
    if(!self_read(node+8,&props,4) || !self_read(props+0x7ec,&guard,1) ||
       !self_read(props+0x17c,&current,4) || !self_read(props+0x184,&maximum,4) ||
       !self_read(props+0x178,&death,1))return;
    if(guard!=0xdb) {out->hp_status=3;return;}
    current^=0xa59cf5b6u;maximum^=0xa59cf5b6u;
    if(!maximum || maximum>1000000u || current>maximum) {out->hp_status=4;return;}
    out->hp_status=0;out->current=current;out->maximum=maximum;out->death_tag=death;
}

/* 10F3630 writes interface+330 == actor+340; 10F3690 consumes that
 * mask, actor+11A and the actor+104 appearance object. No virtual calls. */
/* 409390/D05280 use begin/end/capacity strings. Never follow unbounded
 * strings or truncate them into a plausible resource name. Status 0 means
 * complete, 1 unreadable, 2 invalid/too long. No engine functions called. */
static uint32_t resource_name(uintptr_t string,char out[96]) {
    uint32_t words[3];clear_bytes(out,96);
    if(!self_read(string,words,sizeof(words)))return 1;
    if(!words[0] && !words[1] && !words[2])return 0;
    if(words[0]<0x10000 || words[1]<words[0] || words[2]<words[1] ||
       words[1]-words[0]>=96)return 2;
    unsigned length=words[1]-words[0];
    if(length && !self_read(words[0],out,length)) {clear_bytes(out,96);return 1;}
    for(unsigned i=0;i<length;i++)if((unsigned char)out[i]<32 || (unsigned char)out[i]>126) {
        clear_bytes(out,96);return 2;
    }
    return 0;
}
static void visual_row(uint32_t actor,uintptr_t base,VisualRow *row) {
    row->actor=actor;row->status=1;
    if(!actor)return;
    unsigned char hidden=0;
    row->status=2;
    if(!self_read(actor+0x340,&row->display_mask,4) ||
       !self_read(actor+0x104,&row->visual,4) || !self_read(actor+0x11a,&hidden,1))return;
    row->secondary_gate=hidden;
    if(row->visual && !self_read(row->visual,&row->visual_vtable,4))return;
    if(row->visual) {
        uint32_t aggregate=0,has_nested=0;
        unsigned char flags[3];
        if(!self_read(row->visual_vtable+0xb0,&aggregate,4) || aggregate!=base+0x8f1330 ||
           !self_read(row->visual_vtable+0x1c4,&has_nested,4) || has_nested!=base+0x90d2b0 ||
           !self_read(row->visual+0xc,flags,3) || !self_read(row->visual+0x828,&row->nested,4))return;
        row->gates=(uint32_t)flags[0]|((uint32_t)flags[1]<<8)|((uint32_t)flags[2]<<16);
        /* D066B0 also requires the D01780 getter (+480), then uses the
         * wrapper at +A8 and its model at +F0. Read these fields only; a
         * nonzero pointer is still not evidence of visible pixels. */
        uint32_t getter=0;unsigned char enabled=0,ready=0;
        if(!self_read(row->visual_vtable+0x258,&getter,4) || getter!=base+0x901780 ||
           !self_read(row->visual+0x480,&enabled,1) ||
           !self_read(row->visual+0x8ff,&ready,1) ||
           !self_read(row->visual+0x48c,&row->loader_stage,4) ||
           !self_read(row->visual+0xa8,&row->model_wrapper,4))return;
        row->model_gate=enabled;
        row->loader_ready=ready;
        if(row->model_wrapper && !self_read(row->model_wrapper+0xf0,&row->render_model,4))return;
        /* Ten D00F80 entries: callback, completed byte, two dependencies.
         * Read bounded status bytes only; never call any pointer. */
        for(unsigned i=0;i<10;i++) {
            uint32_t entry=row->visual+0x3ec+16*i,callback=0,dep[2]={0,0};
            unsigned char done=0;
            if(!self_read(entry,&callback,4) || !self_read(entry+4,&done,1) ||
               !self_read(entry+8,dep,8))return;
            if(callback)row->loader_callbacks|=1u<<i;
            if(done)row->loader_done|=1u<<i;
            for(unsigned j=0;j<2;j++)if(dep[j]) {
                unsigned char complete=0;
                if(!self_read((uintptr_t)dep[j]+4,&complete,1))row->loader_unreadable|=1u<<i;
                else if(!complete)row->loader_pending|=1u<<i;
            }
        }
        row->actor_name_status=resource_name(row->visual+0x4e8,row->actor_name);
        row->runtime_name_status=resource_name(row->visual+0x4d8,row->runtime_name);
        unsigned char resource_ready=0;
        if(!self_read(row->visual+0x500,&row->actor_resource,4))row->resource_unreadable|=1;
        else if(row->actor_resource && !self_read(row->actor_resource+0x21,&resource_ready,1))
            row->resource_unreadable|=2;
        row->actor_resource_ready=resource_ready;
        if(!self_read(row->visual+0x50c,&row->runtime_resource,4))row->resource_unreadable|=4;
        else if(row->runtime_resource && !self_read(row->runtime_resource+0x18,&row->runtime_data,4))
            row->resource_unreadable|=8;
    }
    row->status=0;
}

/* F60AE0/793E90's primary-slot map, without its insertion-on-miss behavior.
 * Examine only slots 1 and 2, cap chain traversal and reject malformed data. */
static int equipment_object(uint32_t inventory,uint32_t slot,uint32_t *object) {
    uint32_t buckets=0,count=0,node=0,sentinel=0;
    *object=0;
    if(!inventory || !self_read(inventory+0x84,&buckets,4) ||
       !self_read(inventory+0x88,&count,4) || !count || count>1048576u ||
       !self_read(buckets+count*4,&sentinel,4) ||
       !self_read(buckets+(slot%count)*4,&node,4))return -1;
    for(unsigned i=0;node && node!=sentinel && i<128;i++) {
        uint32_t key=0,next=0;
        if(!self_read(node,&key,4))return -1;
        if(key==slot)return self_read(node+4,object,4)?(*object?1:0):-1;
        if(!self_read(node+8,&next,4) || next==node)return -1;
        node=next;
    }
    return !node || node==sentinel?0:-1;
}

/* Native inventory/weapon fields established by the offline attachment probe.
 * No function/RTTI calls, renderer calls, writes or equipment changes occur. */
static void equipment_rows(uint32_t actor,uintptr_t base,EquipmentSample *out) {
    out->inventory=0;
    self_read(actor+0x7c0,&out->inventory,4);
    for(unsigned i=0;i<2;i++) {
        EquipmentRow *row=out->rows+i;clear_bytes(row,sizeof(*row));row->slot=i+1;row->status=1;
        row->normal_flag=row->ads_flag=0xffffffffu;
        if(!out->inventory)continue;
        int found=equipment_object(out->inventory,row->slot,&row->item);
        row->status=found<0?3:2;
        if(found!=1)continue;
        row->status=3;
        uint32_t category=0,begin=0,end=0;unsigned char dirty=0;
        if(!self_read(row->item,&row->vtable,4) ||
           !self_read(row->item+0x18,&row->low,4) || !self_read(row->item+0x1c,&row->high,4) ||
           !self_read(row->item+0x20,&row->template_id,4) || !self_read(row->item+0x24,&category,4))continue;
        if(category!=1 && category!=2) {row->status=4;continue;}
        if(!self_read(row->item+0x66c,&row->owner,4) || !self_read(row->item+0x674,&row->model,4) ||
           !self_read(row->item+0x60,&row->loaded,4) || !self_read(row->item+0x39c,&row->capacity,4) ||
           !self_read(row->item+0x6c4,&dirty,1) ||
           !self_read(row->item+0x6b4,&begin,4) || !self_read(row->item+0x6b8,&end,4))continue;
        row->dirty=dirty;
        if(!begin || end<begin || end-begin!=28) {row->status=4;continue;}
        if(!self_read(begin+8,&row->scope,4))continue;
        if(row->scope) {
            uint32_t getter=0;unsigned char mode=0,visible=0;
            if(!self_read(row->scope,&row->scope_vtable,4) ||
               !self_read(row->scope_vtable+4,&getter,4) ||
               !self_read(row->scope+0x20,&row->scope_template,4))continue;
            if(getter!=base+0xc62840u) {row->status=4;continue;}
            if(!self_read(row->scope+0x4c,&row->scope_owner,4) ||
               !self_read(row->scope+0x48,&row->normal_model,4) ||
               !self_read(row->scope+0x58,&row->ads_model,4) ||
               !self_read(row->scope+0x5c,&mode,1))continue;
            row->ads_mode=mode;
            if(row->normal_model && self_read(row->normal_model+0xf4,&visible,1))row->normal_flag=visible;
            if(row->ads_model && self_read(row->ads_model+0xf4,&visible,1))row->ads_flag=visible;
        }
        uint32_t again=0;
        if(equipment_object(out->inventory,row->slot,&again)==1 && again==row->item)row->status=0;
    }
}

static void write_atomic(const wchar_t *output,const wchar_t *temporary,const void *data,DWORD size) {
    HANDLE file=CreateFileW(temporary,GENERIC_WRITE,0,NULL,CREATE_ALWAYS,FILE_ATTRIBUTE_NORMAL,NULL);
    if(file!=INVALID_HANDLE_VALUE) {
        DWORD written=0;BOOL ok=WriteFile(file,data,size,&written,NULL);
        CloseHandle(file);
        if(ok && written==size)MoveFileExW(temporary,output,MOVEFILE_REPLACE_EXISTING);
    }
}

typedef struct {char magic[8],token[32];wchar_t expected[1024],output[1024];} Configuration;

static DWORD WINAPI observe(void *module) {
    static wchar_t expected[1024],actual[1024],output[1024],temporary[1040];
    static wchar_t peer_output[1040],peer_temporary[1040];
    static wchar_t visual_output[1040],visual_temporary[1040];
    static wchar_t equipment_output[1040],equipment_temporary[1040];
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
    lstrcpyW(peer_output,output);lstrcatW(peer_output,L".peers");
    lstrcpyW(peer_temporary,peer_output);lstrcatW(peer_temporary,L".tmp");
    lstrcpyW(visual_output,output);lstrcatW(visual_output,L".visuals");
    lstrcpyW(visual_temporary,visual_output);lstrcatW(visual_temporary,L".tmp");
    lstrcpyW(equipment_output,output);lstrcatW(equipment_output,L".equipment");
    lstrcpyW(equipment_temporary,equipment_output);lstrcatW(equipment_temporary,L".tmp");
    uintptr_t base=(uintptr_t)GetModuleHandleW(NULL);
    unsigned char dos[2];
    if(base!=0x400000 || !self_read(base,dos,2) || dos[0]!='M' || dos[1]!='Z')return 0;
    Sleep(15000);
    Sample sample;clear_bytes(&sample,sizeof(sample));
    copy_bytes(sample.magic,"ROEPOS1",7);copy_bytes(sample.token,config.token,32);
    sample.pid=GetCurrentProcessId();
    PeerSample peers;clear_bytes(&peers,sizeof(peers));
    copy_bytes(peers.magic,"ROEPEER2",8);copy_bytes(peers.token,config.token,32);
    peers.pid=sample.pid;peers.count=4;
    VisualSample visuals;clear_bytes(&visuals,sizeof(visuals));
    copy_bytes(visuals.magic,"ROEVIS6",7);copy_bytes(visuals.token,config.token,32);
    visuals.pid=sample.pid;visuals.count=5;
    EquipmentSample equipment;clear_bytes(&equipment,sizeof(equipment));
    copy_bytes(equipment.magic,"ROEEQP1",7);copy_bytes(equipment.token,config.token,32);
    equipment.pid=sample.pid;equipment.count=2;
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
        write_atomic(output,temporary,&sample,sizeof(sample));
        if(sample.sequence%10==1) {
            peers.sequence=sample.sequence;peer_rows(manager,base,&peers);player_health(base,&peers);
            write_atomic(peer_output,peer_temporary,&peers,sizeof(peers));
            visuals.sequence=sample.sequence;
            for(unsigned i=0;i<5;i++) {
                VisualRow *row=visuals.rows+i;clear_bytes(row,sizeof(*row));
                row->low=i?0x10ff+i:0x100;row->high=0x10000;
                visual_row(i?peers.rows[i-1].actor:actor,base,row);
            }
            write_atomic(visual_output,visual_temporary,&visuals,sizeof(visuals));
            equipment.sequence=sample.sequence;equipment_rows(actor,base,&equipment);
            write_atomic(equipment_output,equipment_temporary,&equipment,sizeof(equipment));
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
