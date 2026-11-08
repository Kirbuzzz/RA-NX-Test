#!/usr/bin/env python3
"""Lista los simbolos (nombres mangled) de una .so de Android cuyo nombre contiene un texto.
uso: python3 tools/find_sym.py libuaf.so updateConnecting [otro_texto ...]
Sirve para escribir lineas de patches.txt:   ret 0 _ZN6online...   |   void ~texto"""
import struct, sys
sys.path.insert(0, __file__.rsplit('/', 1)[0] if '/' in __file__ else '.')
from a64 import Elf

e = Elf(sys.argv[1]); d = e.d
dsv, dso, dss = e.sections['.dynsym']; strv, stro, strs = e.sections['.dynstr']
names = []
for i in range(dss // 24):
    nm, info, oth, shn, val, sz = struct.unpack_from('<IBBHQQ', d, dso + 24 * i)
    if shn and val and (info & 15) == 2:
        end = d.index(b'\0', stro + nm); names.append((d[stro + nm:end].decode(), val))
for pat in sys.argv[2:]:
    hits = [(n, v) for n, v in names if pat in n]
    print('== "%s": %d funciones' % (pat, len(hits)))
    for n, v in hits[:60]: print('  0x%08x  %s' % (v, n))
