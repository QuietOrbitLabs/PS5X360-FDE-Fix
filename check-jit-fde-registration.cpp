#include <cstdint>
#include <cstdio>
#include <cstring>
#include <sys/mman.h>
#include <unistd.h>

extern "C" void __register_frame(const void*);
extern "C" void __deregister_frame(const void*);
struct FiberReentry { uint32_t address; };
__attribute__((noinline)) static void reenter() { throw FiberReentry{0x12345678}; }

// Same CIE/FDE geometry and RSP unwind rule as Canary's POSIX code cache.
int main(int argc, char**) {
  auto* memory = static_cast<uint8_t*>(mmap(nullptr, 4096,
      PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANON, -1, 0));
  if (memory == MAP_FAILED) return 2;
  uint8_t code[] = {0x48,0x83,0xec,0x28, 0x48,0xb8,
      0,0,0,0,0,0,0,0, 0xff,0xd0,
      0x48,0x83,0xc4,0x28, 0xc3};
  const uintptr_t target = reinterpret_cast<uintptr_t>(&reenter);
  std::memcpy(code + 6, &target, sizeof(target));
  std::memcpy(memory, code, sizeof(code));
  auto* cie = memory + 256;
  const uint8_t cie_data[] = {24,0,0,0, 0,0,0,0, 1,'z','R',0,
      1,0x78,16,1,0x1b,0x0c,7,8,0x90,1,0,0,0,0,0,0};
  std::memcpy(cie, cie_data, sizeof(cie_data));
  auto* fde = cie + sizeof(cie_data);
  const uint32_t length = 24, cie_back = 32, range = sizeof(code);
  const int32_t pc = static_cast<int32_t>(memory - (fde + 8));
  std::memcpy(fde, &length, 4);
  std::memcpy(fde + 4, &cie_back, 4);
  std::memcpy(fde + 8, &pc, 4);
  std::memcpy(fde + 12, &range, 4);
  fde[16] = 0; fde[17] = 0x44; fde[18] = 0x0e; fde[19] = 48;
  if (mprotect(memory, 4096, PROT_READ | PROT_EXEC)) return 3;
  const void* registration = argc > 1 ? static_cast<void*>(cie) : static_cast<void*>(fde);
  for (unsigned i = 0; i < 100; ++i) {
    __register_frame(registration);
    try {
      reinterpret_cast<void(*)()>(memory)();
      return 4;
    } catch (const FiberReentry& e) {
      if (e.address != 0x12345678) return 5;
    }
    __deregister_frame(registration);
  }
  munmap(memory, 4096);
  std::puts("PASS: 100 fiber exceptions unwound through a JIT frame; register/deregister cycles passed");
}
