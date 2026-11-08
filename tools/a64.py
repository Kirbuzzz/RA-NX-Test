#!/usr/bin/env python3
"""Desensamblador minimo de AArch64 + utilidades ELF para analisis estatico (sin dependencias).
Cubre las instrucciones habituales de codigo generado por clang (mov/add/adrp/ldr/str/ldp/stp/b/bl/cbz...)."""
import struct, sys

class Elf:
    def __init__(self, path):
        self.d = open(path, 'rb').read()
        d = self.d
        assert d[:4] == b'\x7fELF' and d[4] == 2
        (self.entry,) = struct.unpack_from('<Q', d, 24)
        phoff, shoff = struct.unpack_from('<QQ', d, 32)
        phentsize, phnum, shentsize, shnum, shstrndx = struct.unpack_from('<HHHHH', d, 54)
        self.loads = []
        for i in range(phnum):
            t, fl, off, va, pa, fsz, msz, al = struct.unpack_from('<IIQQQQQQ', d, phoff + i * phentsize)
            if t == 1: self.loads.append((va, off, fsz, msz, fl))
        self.sections = {}
        if shoff:
            secs = [struct.unpack_from('<IIQQQQIIQQ', d, shoff + i * shentsize) for i in range(shnum)]
            stroff = secs[shstrndx][4]
            for s in secs:
                e = d.index(b'\0', stroff + s[0])
                self.sections[d[stroff + s[0]:e].decode()] = (s[3], s[4], s[5])   # va, off, size
    def read(self, va, n):
        for (v, off, fsz, msz, fl) in self.loads:
            if v <= va < v + msz:
                o = off + (va - v)
                return self.d[o:o + n]
        return b''
    def cstr(self, va):
        b = self.read(va, 400); i = b.find(b'\0')
        return b[:i].decode('latin1') if i >= 0 else b.decode('latin1')
    def find_bytes(self, needle):
        out = []; start = 0
        while True:
            i = self.d.find(needle, start)
            if i < 0: break
            for (v, off, fsz, msz, fl) in self.loads:
                if off <= i < off + fsz: out.append(v + i - off)
            start = i + 1
        return out

def sx(v, bits): return v - (1 << bits) if v & (1 << (bits - 1)) else v
def R(n, sf=1, sp=False):
    if n == 31: return 'sp' if sp else ('xzr' if sf else 'wzr')
    return ('x%d' if sf else 'w%d') % n

def dis(w, pc):
    sf = w >> 31
    rd, rn, rm = w & 31, (w >> 5) & 31, (w >> 16) & 31
    if w == 0xd503201f: return 'nop'
    if w == 0xd65f03c0: return 'ret'
    if (w & 0x9f000000) == 0x90000000:
        imm = sx((((w >> 5) & 0x7ffff) << 2) | ((w >> 29) & 3), 21) << 12
        return 'adrp x%d, 0x%x' % (rd, (pc & ~0xfff) + imm)
    if (w & 0x9f000000) == 0x10000000:
        imm = sx((((w >> 5) & 0x7ffff) << 2) | ((w >> 29) & 3), 21)
        return 'adr x%d, 0x%x' % (rd, pc + imm)
    if (w & 0x1f000000) == 0x11000000:
        op = ('add', 'adds', 'sub', 'subs')[((w >> 29) & 3)]
        imm = ((w >> 10) & 0xfff) << (12 if (w >> 22) & 1 else 0)
        if op == 'subs' and rd == 31: return 'cmp %s, #%d' % (R(rn, sf, True), imm)
        if op == 'add' and imm == 0 and (rn == 31 or rd == 31): return 'mov %s, %s' % (R(rd, sf, True), R(rn, sf, True))
        return '%s %s, %s, #0x%x' % (op, R(rd, sf, op in ('add', 'sub')), R(rn, sf, True), imm)
    if (w & 0x1f800000) == 0x12800000 or (w & 0x1f800000) == 0x12800000:
        pass
    opc = (w >> 29) & 3
    if (w & 0x1f800000) == 0x12800000:
        hw = (w >> 21) & 3; imm = (w >> 5) & 0xffff; nm = ('movn', None, 'movz', 'movk')[opc]
        if nm is None: return '.word 0x%08x' % w
        return '%s %s, #0x%x%s' % (nm, R(rd, sf), imm, (', lsl #%d' % (hw * 16)) if hw else '')
    if (w & 0x7c000000) == 0x14000000:
        t = pc + sx(w & 0x3ffffff, 26) * 4
        return '%s 0x%x' % ('bl' if sf else 'b', t)
    if (w & 0xfffffc1f) == 0xd61f0000: return 'br x%d' % rn
    if (w & 0xfffffc1f) == 0xd63f0000: return 'blr x%d' % rn
    if (w & 0x7e000000) == 0x34000000:
        return '%s %s, 0x%x' % ('cbnz' if (w >> 24) & 1 else 'cbz', R(rd, sf), pc + sx((w >> 5) & 0x7ffff, 19) * 4)
    if (w & 0x7e000000) == 0x36000000:
        return '%s %s, #%d, 0x%x' % ('tbnz' if (w >> 24) & 1 else 'tbz', R(rd, 1), ((sf << 5) | ((w >> 19) & 31)), pc + sx((w >> 5) & 0x3fff, 14) * 4)
    if (w & 0xff000010) == 0x54000000:
        cc = ('eq', 'ne', 'cs', 'cc', 'mi', 'pl', 'vs', 'vc', 'hi', 'ls', 'ge', 'lt', 'gt', 'le', 'al', 'nv')[w & 15]
        return 'b.%s 0x%x' % (cc, pc + sx((w >> 5) & 0x7ffff, 19) * 4)
    if (w & 0x3b000000) == 0x18000000:
        return 'ldr %s, [0x%x]' % (R(rd, 1 if (w >> 30) & 1 else 0), pc + sx((w >> 5) & 0x7ffff, 19) * 4)
    if (w & 0x3a000000) == 0x28000000:        # ldp/stp
        mode = (w >> 23) & 3; ld = (w >> 22) & 1; rt2 = (w >> 10) & 31
        s = 1 if (w >> 31) & 1 else 0
        imm = sx((w >> 15) & 0x7f, 7) * (8 if s else 4)
        base = R(rn, 1, True)
        mem = ('[%s, #%d]' % (base, imm)) if mode == 2 else (('[%s, #%d]!' % (base, imm)) if mode == 3 else '[%s], #%d' % (base, imm))
        return '%s %s, %s, %s' % ('ldp' if ld else 'stp', R(rd, s), R(rt2, s), mem)
    if (w & 0x3b000000) == 0x39000000:        # ldr/str imm unsigned
        size = (w >> 30) & 3; opc2 = (w >> 22) & 3; imm = ((w >> 10) & 0xfff) << size
        nm = {0: 'strb', 1: 'ldrb'}.get(opc2) if size == 0 else {0: 'str', 1: 'ldr'}.get(opc2) if size >= 2 else {0: 'strh', 1: 'ldrh'}.get(opc2)
        if size == 0 and opc2 in (2, 3): nm = 'ldrsb'
        if size == 1 and opc2 in (2, 3): nm = 'ldrsh'
        if size == 2 and opc2 == 2: nm = 'ldrsw'
        if nm is None: return '.word 0x%08x' % w
        return '%s %s, [%s, #%d]' % (nm, R(rd, 1 if size == 3 else 0), R(rn, 1, True), imm)
    if (w & 0x3b200c00) == 0x38000000:        # ldur/stur
        size = (w >> 30) & 3; opc2 = (w >> 22) & 3; imm = sx((w >> 12) & 0x1ff, 9)
        return '%s %s, [%s, #%d]' % (('stur' if opc2 == 0 else 'ldur'), R(rd, 1 if size == 3 else 0), R(rn, 1, True), imm)
    if (w & 0x3b200c00) == 0x38200800:        # reg offset
        size = (w >> 30) & 3
        return '%s %s, [%s, %s]' % (('str' if ((w >> 22) & 3) == 0 else 'ldr'), R(rd, 1 if size == 3 else 0), R(rn, 1, True), R(rm, 1))
    if (w & 0x7f2003e0) == 0x2a0003e0: return 'mov %s, %s' % (R(rd, sf), R(rm, sf))
    if (w & 0x7f200000) == 0x0a000000 or (w & 0x7f200000) == 0x2a000000 or (w & 0x7f200000) == 0x4a000000:
        nm = {0x0a: 'and', 0x2a: 'orr', 0x4a: 'eor'}[(w >> 24) & 0x7f & 0x7f] if ((w >> 24) & 0x7f) in (0x0a, 0x2a, 0x4a) else 'logic'
        return '%s %s, %s, %s' % (nm, R(rd, sf), R(rn, sf), R(rm, sf))
    if (w & 0x1f200000) == 0x0b000000:
        nm = ('add', 'adds', 'sub', 'subs')[(w >> 29) & 3]
        if nm == 'subs' and rd == 31: return 'cmp %s, %s' % (R(rn, sf), R(rm, sf))
        return '%s %s, %s, %s' % (nm, R(rd, sf), R(rn, sf), R(rm, sf))
    if (w & 0x7fe0ffe0) == 0x1a9f07e0: return 'cset %s, #%d' % (R(rd, sf), (w >> 12 & 15) ^ 1)
    return '.word 0x%08x' % w

def disasm_range(elf, va, n):
    b = elf.read(va, n * 4)
    out = []
    for i in range(len(b) // 4):
        w = struct.unpack_from('<I', b, i * 4)[0]
        out.append((va + 4 * i, w, dis(w, va + 4 * i)))
    return out

def xrefs_to(elf, target_vas, text_range=None):
    """Busca ADRP+ADD (y ADRP+LDR/ADD con desplazamiento) que formen cualquiera de target_vas. Devuelve {va: [pc,...]}."""
    ts = set(target_vas)
    if text_range is None:
        va, off, size = elf.sections['.text']; text_range = (va, size)
    b = elf.read(text_range[0], text_range[1])
    res = {}; pages = {}
    for i in range(len(b) // 4):
        pc = text_range[0] + 4 * i
        w = struct.unpack_from('<I', b, 4 * i)[0]
        if (w & 0x9f000000) == 0x90000000:
            imm = sx((((w >> 5) & 0x7ffff) << 2) | ((w >> 29) & 3), 21) << 12
            pages[w & 31] = ((pc & ~0xfff) + imm, pc)
        elif (w & 0xff000000) == 0x91000000:
            rn, rdd = (w >> 5) & 31, w & 31
            if rn in pages and pc - pages[rn][1] < 64:
                a = pages[rn][0] + (((w >> 10) & 0xfff) << (12 if (w >> 22) & 1 else 0))
                if a in ts: res.setdefault(a, []).append(pc)
                pages[rdd] = (a, pc) if rdd != rn else pages.get(rdd)
    return res

def func_start(elf, pc, limit=4096):
    """Retrocede hasta un prologo tipico (stp x29,x30,[sp,#-n]! / sub sp,sp,#n)."""
    for a in range(pc & ~3, pc - limit, -4):
        w = struct.unpack_from('<I', elf.read(a, 4), 0)[0]
        if (w & 0xffc003e0) == 0xa98003e0 and ((w >> 10) & 31) == 30 or (w & 0xff0003ff) == 0xd10003ff:
            return a
    return pc

if __name__ == '__main__':
    e = Elf(sys.argv[1])
    for a, w, t in disasm_range(e, int(sys.argv[2], 16), int(sys.argv[3])): print('%x: %08x  %s' % (a, w, t))
