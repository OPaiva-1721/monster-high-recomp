/* Monster High's synchronous JobQueue subset.
 *
 * The generic JQ shim accepts jobs without executing them. This title consumes
 * their 32-byte geometric-query results. Keep its supported ABI separate from
 * that shim: queue/port lifetimes are real host state, a successful submit has
 * actually completed guest SPU code, and unsupported work returns an error.
 * Only the two verified binaries and 64-byte descriptors are supported here.
 */
#define PPU_NO_INLINE_LOADS
#include "ppu_recomp.h"
#include "spu_context.h"
#include "spu_interp.h"
#include "spu_workload.h"
#include "ps3emu/error_codes.h"
#include <array>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <mutex>
#include <windows.h>

extern "C" void ps3_hle_register_ctx(unsigned,const char*,void(*)(ppu_context*));
extern "C" int spu_run_spurs_job(void(*)(spu_context*),int,uint32_t,uint32_t);
extern "C" uint8_t* vm_base;

namespace {
struct Queue { uint32_t ea=0; bool closed=false; uint32_t error=0; };
struct Port { uint32_t ea=0, queue=0, descriptors=0, count=0; };
struct Attribute { uint32_t ea=0, max_grab=1; };
struct State {
    std::mutex mutex;
    std::array<Queue,16> queues;
    std::array<Port,32> ports;
    std::array<Attribute,32> attributes;
    uint64_t completed=0;
};
State& state() { static State s; return s; }
thread_local bool job_completed;
bool valid_ea(uint32_t ea,uint32_t bytes,bool writable=false) {
    if(!vm_base || ea<0x10000 || !bytes || bytes>0xefffffff || ea>0xefffffff-bytes)return false;
    uintptr_t cursor=(uintptr_t)(vm_base+ea),end=cursor+bytes;
    while(cursor<end) {
        MEMORY_BASIC_INFORMATION info{};
        if(!VirtualQuery((void*)cursor,&info,sizeof info) || info.State!=MEM_COMMIT ||
           (info.Protect&(PAGE_NOACCESS|PAGE_GUARD)))return false;
        if(!(info.Protect&(PAGE_READONLY|PAGE_READWRITE|PAGE_WRITECOPY|
                           PAGE_EXECUTE_READ|PAGE_EXECUTE_READWRITE|PAGE_EXECUTE_WRITECOPY)))return false;
        if(writable && !(info.Protect&(PAGE_READWRITE|PAGE_WRITECOPY|PAGE_EXECUTE_READWRITE|PAGE_EXECUTE_WRITECOPY)))return false;
        uintptr_t next=(uintptr_t)info.BaseAddress+info.RegionSize;
        if(next<=cursor)return false;
        cursor=next;
    }
    return true;
}
void result(ppu_context* c,uint32_t value) {
    static unsigned errors=0;
    if(value && errors++<16)
        std::fprintf(stderr,"[monster-high-jq] error=%08X lr=%08X\n",value,(uint32_t)c->lr);
    c->gpr[3]=(uint64_t)(int64_t)(int32_t)value;
}
Queue* find_queue(State& s,uint32_t ea) {
    for(auto& q:s.queues)if(q.ea==ea && ea)return &q;
    return nullptr;
}
Port* find_port(State& s,uint32_t ea) {
    for(auto& p:s.ports)if(p.ea==ea && ea)return &p;
    return nullptr;
}
void attribute_init(ppu_context* c) {
    auto& s=state();std::lock_guard<std::mutex> lock(s.mutex);
    uint32_t ea=(uint32_t)c->gpr[3];
    if(!valid_ea(ea,512) || (ea&15)){result(c,CELL_EINVAL);return;}
    for(auto& a:s.attributes)if(a.ea==ea || !a.ea){a={ea,1};result(c,0);return;}
    result(c,CELL_ENOMEM);
}
void attribute_max_grab(ppu_context* c) {
    auto& s=state();std::lock_guard<std::mutex> lock(s.mutex);
    uint32_t ea=(uint32_t)c->gpr[3],count=(uint32_t)c->gpr[4];
    for(auto& a:s.attributes)if(a.ea==ea && ea && count && count<=16){a.max_grab=count;result(c,0);return;}
    result(c,CELL_EINVAL);
}
void create(ppu_context* c) {
    // revision, SDK version, Spurs EA, queue EA, attribute EA, name,
    // command buffer EA/count, followed by contention/priorities on the stack.
    auto& s=state();std::lock_guard<std::mutex> lock(s.mutex);
    uint32_t ea=(uint32_t)c->gpr[6],buffer=(uint32_t)c->gpr[9],count=(uint32_t)c->gpr[10];
    bool attr=false;
    for(const auto& a:s.attributes)if(a.ea==(uint32_t)c->gpr[7] && a.ea)attr=true;
    if(c->gpr[3]!=2 || !valid_ea((uint32_t)c->gpr[5],128) || !valid_ea(ea,4096) ||
       (ea&127) || !attr || !count || count>65536 || !valid_ea(buffer,count*8) || (buffer&127)) {
        result(c,CELL_EINVAL);return;
    }
    if(find_queue(s,ea)){result(c,CELL_EBUSY);return;}
    for(auto& q:s.queues)if(!q.ea){q={ea,false,0};result(c,0);return;}
    result(c,CELL_ENOMEM);
}
void port_init(ppu_context* c) {
    auto& s=state();std::lock_guard<std::mutex> lock(s.mutex);
    uint32_t ea=(uint32_t)c->gpr[3],q=(uint32_t)c->gpr[4],buffer=(uint32_t)c->gpr[5];
    uint32_t size=(uint32_t)c->gpr[6],count=(uint32_t)c->gpr[7];
    Queue* queue=find_queue(s,q);
    if(!queue || queue->closed || !valid_ea(ea,128) || (ea&127) || size!=64 ||
       !count || count>65536 || !valid_ea(buffer,size*count) || (buffer&127)) {
        result(c,CELL_EINVAL);return;
    }
    if(find_port(s,ea)){result(c,CELL_EBUSY);return;}
    for(auto& p:s.ports)if(!p.ea){p={ea,q,buffer,count};result(c,0);return;}
    result(c,CELL_ENOMEM);
}
void interpret(spu_context* c) {
    // JOBCRT Ver14 reads the manager LS pointer in context+0x14's low bits.
    // The current generic job stager supplies descriptor size only. Give this
    // isolated manager its own record above the working set and below context.
    uint32_t a=c->gpr[3]._u32[0]+0x14;
    c->ls[a]=0;c->ls[a+1]=3;c->ls[a+2]=0xf8;c->ls[a+3]=0;
    // A real manager owns the return target; terminate cleanly at ours.
    c->ls[0x3ff00]=0;c->ls[0x3ff01]=0;c->ls[0x3ff02]=0x3f;c->ls[0x3ff03]=0xff;
    spu_interp_run_until(c,0x10,0);
    job_completed=c->status==SPU_STATUS_STOPPED_BY_STOP &&
                  c->stop_code==0x3fff && c->pc==0x3ff04;
}
void submit(ppu_context* c) {
    auto& s=state();std::lock_guard<std::mutex> lock(s.mutex);
    Port* port=find_port(s,(uint32_t)c->gpr[3]);
    Queue* queue=port?find_queue(s,port->queue):nullptr;
    uint32_t desc=(uint32_t)c->gpr[4];
    if(!queue || queue->closed || c->gpr[5]!=64 || !valid_ea(desc,64)) {
        result(c,CELL_EINVAL);return;
    }
    uint32_t binary=vm_read32(desc+4);
    uint32_t size=((uint32_t)vm_read8(desc+8)<<8 | vm_read8(desc+9))*16;
    if(!valid_ea(binary,size) || (size!=28832 && size!=12288)) {
        queue->error=CELL_ENOSYS;result(c,CELL_ENOSYS);return;
    }
    uint64_t fp=spu_workload_fingerprint(vm_base+binary,size);
    if(fp!=0x27fa9d8b5746efd5ULL && fp!=0xe4568290fc78c32fULL) {
        std::fprintf(stderr,"[monster-high-jq] unsupported job fp=%016llX\n",(unsigned long long)fp);
        queue->error=CELL_ENOSYS;result(c,CELL_ENOSYS);return;
    }
    // Both supported binaries declare this exact working set. Reject layouts
    // that could overlap our manager rather than silently clobbering context.
    uint32_t expected_output=fp==0x27fa9d8b5746efd5ULL?32u:4u;
    if((vm_read32(desc+8)&0xffffu)!=0 || vm_read32(desc+0xc)!=0 ||
       vm_read32(desc+0x10)!=0 || vm_read32(desc+0x14)!=0 ||
       vm_read32(desc+0x18)!=expected_output || vm_read32(desc+0x1c)!=0x10000000 ||
       vm_read32(desc+0x20)!=0 || vm_read32(desc+0x24)!=0 ||
       vm_read32(desc+0x28)!=0 || vm_read32(desc+0x2c)!=0x04000000) {
        queue->error=CELL_ENOSYS;result(c,CELL_ENOSYS);return;
    }
    uint32_t lengths=vm_read32(desc+0x3c),a_size=lengths>>16,b_size=lengths&0xffff;
    uint32_t output=vm_read32(desc+0x38);
    if(a_size>4096 || b_size>4096 || !valid_ea(vm_read32(desc+0x30),a_size) ||
       !valid_ea(vm_read32(desc+0x34),b_size) || !valid_ea(output,expected_output,true)) {
        queue->error=CELL_EINVAL;result(c,CELL_EINVAL);return;
    }
    job_completed=false;
    int rc=spu_run_spurs_job(interpret,-1,desc,64);
    if(rc || !job_completed) {
        queue->error=CELL_ENOSYS;
        std::fprintf(stderr,"[monster-high-jq] job did not complete; rc=%d\n",rc);
        result(c,CELL_ENOSYS);return;
    }
    if(++s.completed<=4)std::fprintf(stderr,"[monster-high-jq] completed job %llu\n",(unsigned long long)s.completed);
    result(c,0);
}
void sync(ppu_context* c) {
    // Submissions complete while holding this same lock: acquiring it waits
    // for earlier work, and its result includes any execution error.
    auto& s=state();std::lock_guard<std::mutex> lock(s.mutex);
    Port* p=find_port(s,(uint32_t)c->gpr[3]);
    Queue* q=p?find_queue(s,p->queue):nullptr;
    result(c,q?q->error:CELL_EINVAL);
}
void finalize(ppu_context* c) {
    auto& s=state();std::lock_guard<std::mutex> lock(s.mutex);
    Port* p=find_port(s,(uint32_t)c->gpr[3]);
    if(!p){result(c,CELL_EINVAL);return;}
    *p={};result(c,0);
}
void shutdown(ppu_context* c) {
    auto& s=state();std::lock_guard<std::mutex> lock(s.mutex);
    Queue* q=find_queue(s,(uint32_t)c->gpr[3]);
    if(!q){result(c,CELL_EINVAL);return;}
    q->closed=true;result(c,q->error);
}
void join(ppu_context* c) {
    auto& s=state();std::lock_guard<std::mutex> lock(s.mutex);
    Queue* q=find_queue(s,(uint32_t)c->gpr[3]);
    if(!q){result(c,CELL_EINVAL);return;}
    if(!q->closed){result(c,CELL_EBUSY);return;}
    uint32_t error=q->error;
    for(auto& p:s.ports)if(p.queue==q->ea)p={};
    *q={};result(c,error);
}
__attribute__((constructor)) void install() {
    const char* e=std::getenv("MONSTER_HIGH_JOB_QUEUE");
    if(!e || e[0]!='1')return;
    ps3_hle_register_ctx(0x43ddab4f,"Monster High JobQueue attribute init",attribute_init);
    ps3_hle_register_ctx(0x5fb9b05d,"Monster High JobQueue max grab",attribute_max_grab);
    ps3_hle_register_ctx(0xf244e799,"Monster High JobQueue create v2",create);
    ps3_hle_register_ctx(0xf5de6363,"Monster High JobQueue port init",port_init);
    ps3_hle_register_ctx(0xef66c4b7,"Monster High JobQueue real submit",submit);
    ps3_hle_register_ctx(0x634b1502,"Monster High JobQueue sync",sync);
    ps3_hle_register_ctx(0x26fa81b4,"Monster High JobQueue port finalize",finalize);
    ps3_hle_register_ctx(0x8c97a96c,"Monster High JobQueue shutdown",shutdown);
    ps3_hle_register_ctx(0x8ce4cffa,"Monster High JobQueue join",join);
    std::fprintf(stderr,"[monster-high-jq] synchronous verified-job subset enabled\n");
}
}
