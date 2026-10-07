#!/usr/bin/env python3
"""Offline, exact-version JIT FDE repair for the official PS5X360 v0.5.6 SELF.

Reads an existing release eboot; writes a separate corrected eboot exclusively.
Never downloads, installs, connects to a console, or modifies the input file.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct

BASE_SHA256 = '31550197518edbd81a6663fa812cfc800a44c2dba4ff632d4020ab5ee7d708e0'
FIXED_SHA256 = 'd1e80f7d98c10be80ee3b4b4edbc9f649cb722349bbae44f2e22758865b3e027'
BASE_SIZE = 32495909


def require(condition, message):
    if not condition:
        raise ValueError(message)


def extract_elf(data):
    count = struct.unpack_from('<H', data, 24)[0]
    start = 32 + count * 32
    ph_count = struct.unpack_from('<H', data, start + 56)[0]
    headers = [struct.unpack_from('<IIQQQQQQ', data, start + 64 + i * 56)
               for i in range(ph_count)]
    segments = [struct.unpack_from('<QQQQ', data, 32 + i * 32)
                for i in range(count)]
    elf = bytearray(max(h[2] + h[5] for h in headers))
    for flags, offset, size, memory in segments:
        if flags & 0x800:
            require(size == memory, 'Unsupported compressed SELF segment')
            header = headers[flags >> 20]
            elf[header[2]:header[2] + size] = data[offset:offset + size]
    tail = max(offset + size for flags, offset, size, memory in segments)
    for header in headers:
        if header[0] == 0x6fffff01:
            elf[header[2]:header[2] + header[5]] = data[tail:tail + header[5]]
    elf[:64 + ph_count * 56] = data[start:start + 64 + ph_count * 56]
    extended = (start + 64 + ph_count * 56 + 15) & ~15
    require(len(elf) == 33335168, 'Unexpected ELF geometry')
    return elf, segments, extended


def repair(original):
    require(len(original) == BASE_SIZE, 'Not the exact official v0.5.6 eboot size')
    require(hashlib.sha256(original).hexdigest() == BASE_SHA256,
            'Not the exact official v0.5.6 eboot SHA-256; refusing to patch')
    elf, segments, extended = extract_elf(original)
    require(hashlib.sha256(elf).digest() == original[extended + 32:extended + 64],
            'Original SELF digest mismatch')
    require(elf[0x4000 + 0x2d7417:0x4000 + 0x2d741e].hex() == '48c70618000000',
            'Unexpected CIE size instruction')
    call, cave, register = 0x2d71ee, 0x2d71b2, 0xc809e0
    old_call = bytes.fromhex('67e8ec979a00')
    require(elf[0x4000 + call:0x4000 + call + 6] == old_call,
            'Unexpected registration call')
    require(elf[0x4000 + cave:0x4000 + cave + 14] == b'\xcc' * 14,
            'Expected alignment space is not unused')
    # Keep the original return address. R12 is the retained unwind pointer.
    new_call = b'\x67\xe8' + struct.pack('<i', cave - (call + 6))
    # Advance CIE to FDE, set the argument, then tail-call LLVM libunwind.
    stub = bytes.fromhex('4983c41c4c89e7e9') + struct.pack('<i', register - (cave + 12))
    changes = [(call, old_call, new_call), (cave, b'\xcc' * 12, stub)]
    result = bytearray(original)
    allowed = set(range(extended + 32, extended + 64))
    for address, before, after in changes:
        offset = segments[1][1] + address
        require(result[offset:offset + len(before)] == before,
                'Unexpected original SELF code bytes')
        result[offset:offset + len(after)] = after
        elf[0x4000 + address:0x4000 + address + len(after)] = after
        allowed.update(range(offset, offset + len(after)))
    result[extended + 32:extended + 64] = hashlib.sha256(elf).digest()
    rebuilt, _, _ = extract_elf(result)
    require(rebuilt == elf, 'Rebuilt ELF differs from intended correction')
    require(hashlib.sha256(rebuilt).digest() == result[extended + 32:extended + 64],
            'Corrected SELF digest mismatch')
    changed = [i for i, (a, b) in enumerate(zip(original, result)) if a != b]
    require(len(result) == len(original) and all(i in allowed for i in changed),
            'Unexpected bytes changed')
    require(hashlib.sha256(result).hexdigest() == FIXED_SHA256,
            'Corrected output SHA-256 mismatch')
    return bytes(result), len(changed)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('original', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    try:
        require(not args.output.exists(), 'Output already exists; refusing to overwrite')
        require(args.original.resolve() != args.output.resolve(), 'Input and output must differ')
        require(args.original.stat().st_size == BASE_SIZE, 'Unexpected input size')
        result, count = repair(args.original.read_bytes())
        with args.output.open('xb') as stream:
            stream.write(result)
        print(json.dumps({'version': 'v0.5.6', 'output_size': len(result),
                          'output_sha256': FIXED_SHA256, 'changed_bytes': count,
                          'container_digest_valid': True}, indent=2))
    except (ValueError, OSError) as exc:
        parser.exit(1, f'Refused: {exc}\n')


if __name__ == '__main__':
    main()
