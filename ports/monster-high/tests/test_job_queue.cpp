/* Host-state/error contract only. Real SPU outputs are tested separately with
 * local captured inputs, which must never be committed with this fixture. */
#include "../monster_high_job_queue.cpp"
#include <cassert>
#include <vector>
#include <cstring>
#include <memory>
extern "C" { uint8_t* vm_base; }
static uint64_t test_fp;
static unsigned calls;
static bool runner_succeeds;
static uint32_t active_descriptor;
extern "C" void ps3_hle_register_ctx(unsigned,const char*,void(*)(ppu_context*)) {}
extern "C" uint64_t spu_workload_fingerprint(const void*,size_t) { return test_fp; }
extern "C" int spu_run_spurs_job(void(*entry)(spu_context*),int,uint32_t descriptor,uint32_t) {
    ++calls;if(!runner_succeeds)return -1;
    active_descriptor=descriptor;
    auto context=std::make_unique<spu_context>();
    context->ls=context->ls_store;
    context->gpr[3]._u32[0]=0x100;entry(context.get());return 0;
}
extern "C" uint32_t spu_interp_run_until(spu_context* c,uint32_t start,uint32_t stop) {
    assert(start==0x10 && stop==0 && c->ls[0x115]==3 && c->ls[0x116]==0xf8);
    uint32_t output=vm_read32(active_descriptor+0x38);
    vm_base[output+3]=1; // Synthetic backend result; not a geometric oracle.
    c->status=SPU_STATUS_STOPPED_BY_STOP;c->stop_code=0x3fff;c->pc=0x3ff04;return 0x3fff;
}
extern "C" uint8_t vm_read8(uint64_t a) { assert(a<0x100000);return vm_base[a]; }
extern "C" uint32_t vm_read32(uint64_t a) {
    return (uint32_t)vm_read8(a)<<24 | (uint32_t)vm_read8(a+1)<<16 |
           (uint32_t)vm_read8(a+2)<<8 | vm_read8(a+3);
}
static void put(uint32_t a,uint32_t v) {
    vm_base[a]=v>>24;vm_base[a+1]=v>>16;vm_base[a+2]=v>>8;vm_base[a+3]=v;
}
int main() {
    _set_error_mode(_OUT_TO_STDERR);
    _set_abort_behavior(0,_WRITE_ABORT_MSG|_CALL_REPORTFAULT);
    std::vector<uint8_t> memory(0x100000);vm_base=memory.data();
    ppu_context c{};
    auto reset=[&] {std::memset(&c,0,sizeof c);};
    auto value=[&] {return (uint32_t)c.gpr[3];};
    auto make_queue=[&] {
        reset();c.gpr[3]=2;c.gpr[5]=0x30000;c.gpr[6]=0x40000;
        c.gpr[7]=0x20000;c.gpr[9]=0x50000;c.gpr[10]=2048;create(&c);
    };
    auto make_port=[&] {
        reset();c.gpr[3]=0x60000;c.gpr[4]=0x40000;c.gpr[5]=0x70000;
        c.gpr[6]=64;c.gpr[7]=2048;port_init(&c);
    };
    auto push=[&] {reset();c.gpr[3]=0x60000;c.gpr[4]=0x80000;c.gpr[5]=64;submit(&c);};
    // Unknown port/queue and missing attribute are errors, not fake success.
    c.gpr[3]=0x60000;sync(&c);assert(value()==CELL_EINVAL);
    make_queue();assert(value()==CELL_EINVAL);
    reset();c.gpr[3]=0x20000;attribute_init(&c);assert(value()==0);
    reset();c.gpr[3]=0x20000;c.gpr[4]=0;attribute_max_grab(&c);assert(value()==CELL_EINVAL);
    make_queue();assert(value()==0);
    make_queue();assert(value()==CELL_EBUSY);
    make_port();assert(value()==0);
    make_port();assert(value()==CELL_EBUSY);
    // Unsupported content never reaches the job runner.
    put(0x80004,0x90000);put(0x80008,0x070a0000);
    put(0x80018,32);put(0x8001c,0x10000000);
    put(0x8002c,0x04000000);put(0x80030,0xa0000);put(0x80034,0xa1000);
    put(0x80038,0xa2000);put(0x8003c,0x00dc0038);
    test_fp=0;push();assert(value()==CELL_ENOSYS && calls==0);
    // A known job whose actual runner fails also cannot report completion.
    test_fp=0x27fa9d8b5746efd5ULL;push();assert(value()==CELL_ENOSYS && calls==1);
    reset();c.gpr[3]=0x60000;sync(&c);assert(value()==CELL_ENOSYS);
    reset();c.gpr[3]=0x40000;join(&c);assert(value()==CELL_EBUSY);
    reset();c.gpr[3]=0x40000;shutdown(&c);assert(value()==CELL_ENOSYS);
    push();assert(value()==CELL_EINVAL && calls==1);
    reset();c.gpr[3]=0x40000;join(&c);assert(value()==CELL_ENOSYS);
    reset();c.gpr[3]=0x60000;sync(&c);assert(value()==CELL_EINVAL);
    // The same guest addresses can be reused after a completed lifetime.
    make_queue();assert(value()==0);make_port();assert(value()==0);
    // Malformed staging must be rejected before the runner reads user data.
    put(0x80008,0x070a0080);push();assert(value()==CELL_ENOSYS && calls==1);
    put(0x80008,0x070a0000);
    runner_succeeds=true;push();
    assert(value()==0 && calls==2 && vm_read32(0xa2000)==1);
    reset();c.gpr[3]=0x60000;finalize(&c);assert(value()==0);
    reset();c.gpr[3]=0x60000;finalize(&c);assert(value()==CELL_EINVAL);
    std::puts("PASS: queue/port lifetime, rejected work, failed/completed output, sticky sync error");
}
