# PS5X360 v0.5.6 ODST startup fix

Community correction for the JIT unwind registration abort, confirmed working by the console owner while playing Halo 3: ODST.

The [download package](https://github.com/QuietOrbitLabs/PS5X360-FDE-Fix/releases) contains the corrected emulator `eboot.bin`, source fix, regression and license notices. No game files are included. Fully close PS5X360 before installing, and back up the original emulator.

# PS5 JIT unwind registration fix

On PS5X360 v0.5.6, Halo 3: ODST (title ID `4D530877`) repeatedly aborted during
startup with an uncaught `xe::kernel::FiberReentryException`. This exception is
an intentional Xenia control-flow mechanism: it must unwind generated x86_64
frames back to the guest thread's execution loop.

The POSIX code cache passed the start of its CIE/FDE sequence to
`__register_frame`. That is the libgcc convention. The PS5 SDK instead links
LLVM libunwind, whose API registers one FDE. Passing a CIE leaves the JIT frame
unregistered, so exception propagation terminates.

The source correction is gated by `XE_PLATFORM_PS5`. It advances from the CIE
using its encoded length, registers the FDE, and retains that same pointer for
`__deregister_frame` during teardown. Other platforms keep their existing path.
It does not suppress exceptions or change any game code, saves, settings, or
telemetry. The pinned Canary source already includes `<cstring>`.

## Evidence and limits

- Released v0.5.6 code creates a CIE with a 24-byte payload, making the FDE offset
  28 bytes including the length field. Its registration call received the CIE.
- The abort stack's throw site identifies `xe::kernel::FiberReentryException`.
- A synthetic x86_64 JIT frame using the same layout and stack rule reproduces
  SIGABRT when registered with the CIE pointer under macOS LLVM libunwind.
- Registering the FDE passes 100 exception propagation and register/deregister
  cycles. This is a host regression, separate from console testing.
- An exact-version binary equivalent was deployed to a PS5. The console owner
  confirmed that the correction works and that they are playing ODST.
- A full PS5 source rebuild has not been performed for this change. Console
  validation used the binary equivalent described below. This is one game's
  successful test, not a claim of universal compatibility or full campaign
  completion.

Run the host regression on macOS (Rosetta is required on Apple Silicon):

```sh
python3 check-jit-fde-registration.py
```

## Optional offline repair of the existing v0.5.6 release

The source change is suitable for the next emulator build. For the existing
release, `patch-v0.5.6-jit-fde.py` reproduces the tested binary correction
using Python's standard library. It accepts only the exact official v0.5.6
`eboot.bin`, leaves it unchanged, and writes a separate output. It refuses
unknown versions, altered inputs, existing outputs, and digest mismatches.

Download the original release from the
[official v0.5.6 release page](https://github.com/BrinooTk/PS5X360/releases/tag/v0.5.6).
Then, using paths to your extracted original and a new output:

```sh
python3 patch-v0.5.6-jit-fde.py /path/to/original/eboot.bin /path/to/new/eboot.bin
```

Expected values:

| Item | Value |
| --- | --- |
| Original and corrected size | 32,495,909 bytes |
| Original SHA-256 | `31550197518edbd81a6663fa812cfc800a44c2dba4ff632d4020ab5ee7d708e0` |
| Corrected SHA-256 | `d1e80f7d98c10be80ee3b4b4edbc9f649cb722349bbae44f2e22758865b3e027` |
| Total changed bytes | 48 (16 code bytes and 32 SELF digest bytes) |

Only while PS5X360 is fully closed, back up the console's original `eboot.bin`
and replace it with the separate corrected output. Keep the existing game,
assets and saves. Do not replace files while the emulator or game is running.
To roll back, fully close PS5X360 and restore the original backup.

This is a locally tested correction, not an official upstream release. The
patcher never connects to a console and does not install anything automatically.

### Binary equivalence

The registration call at ELF virtual address `0x2d71ee` is redirected into
previously unused alignment space at `0x2d71b2`. The stub adds 28 to `r12`, moves
that pointer to `rdi`, and tail-jumps to `__register_frame` at `0xc809e0`.
The original return address remains unchanged. Updating `r12` also changes the
pointer retained in `registered_frames_` to the FDE for matching deregistration.
The SELF digest is regenerated from the exact reconstructed ELF. Container
geometry, all other segments, and unrelated code remain unchanged.

## Source references

- [Pinned Canary POSIX code cache](https://github.com/xenia-canary/xenia-canary/blob/b083312b8b18e07e6e410b82104191f126722794/src/xenia/cpu/backend/x64/x64_code_cache_posix.cc)
- [Pinned Canary fiber reentry and catch](https://github.com/xenia-canary/xenia-canary/blob/b083312b8b18e07e6e410b82104191f126722794/src/xenia/kernel/xthread.cc)
- [LLVM libunwind registration API](https://github.com/llvm/llvm-project/blob/release/18.x/libunwind/src/UnwindLevel1-gcc-ext.c)
- [Official PS5 payload SDK v0.43](https://github.com/ps5-payload-dev/sdk/releases/tag/v0.43)
