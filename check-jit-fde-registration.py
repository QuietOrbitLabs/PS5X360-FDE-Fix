#!/usr/bin/env python3
"""Reproduce the CIE/FDE API mismatch using macOS LLVM libunwind.

On Apple Silicon this compiles an x86_64 synthetic JIT test for Rosetta.
Only locally authored test code is executed; no game or emulator is run.
"""
from pathlib import Path
import platform
import resource
import signal
import subprocess
import tempfile


def main():
    if platform.system() != 'Darwin':
        raise SystemExit('This runner requires macOS LLVM libunwind (and Rosetta on Apple Silicon).')
    source = Path(__file__).with_suffix('.cpp')
    with tempfile.TemporaryDirectory(prefix='jit-fde-regression-') as folder:
        executable = Path(folder) / 'regression'
        subprocess.run(['clang++', '-arch', 'x86_64', '-std=c++20', '-O2',
                        str(source), '-o', str(executable)], check=True)
        # The CIE-pointer baseline deliberately aborts. Do not retain core files.
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
        baseline = subprocess.run([str(executable), '--cie'], capture_output=True,
                                  text=True, timeout=30)
        if baseline.returncode != -signal.SIGABRT or 'FiberReentry' not in baseline.stderr:
            raise SystemExit(f'Baseline did not reproduce the expected exception abort: {baseline}')
        fixed = subprocess.run([str(executable)], capture_output=True, text=True, timeout=30)
        if fixed.returncode or 'PASS: 100 fiber exceptions' not in fixed.stdout:
            raise SystemExit(f'FDE registration failed: {fixed}')
        print('PASS: CIE registration reproduces SIGABRT.')
        print(fixed.stdout.strip())


if __name__ == '__main__':
    main()
