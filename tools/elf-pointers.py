"""Resolve pointers in ARM ELF data, including Android APS2 and RELR.

For analysis only: this resolves locally defined symbols, without loading code.
An imported symbol is kept by name rather than assigned a guessed address.
Android formats follow bionic linker_reloc_iterators.h in the pinned AOSP 10.
"""
import io
import struct

from elftools.elf.elffile import ELFFile
from elftools.elf.relocation import RelocationSection


class ElfPointers:
    def __init__(self, data):
        self.data = data
        self.elf = ELFFile(io.BytesIO(data))
        if not self.elf.little_endian or self.elf.header.e_machine not in ('EM_AARCH64', 'EM_ARM'):
            raise ValueError('Expected little-endian ARM ELF')
        self.width = self.elf.elfclass // 8
        self.word_format = '<Q' if self.width == 8 else '<I'
        self.segments = [s for s in self.elf.iter_segments() if s.header.p_type == 'PT_LOAD']
        self.symbols = {s.name: s.entry for s in self.elf.get_section_by_name('.dynsym').iter_symbols()
                        if s.name and s.entry.st_shndx != 'SHN_UNDEF'}
        self.pointers = {}
        self.formats = set()
        self._decode()

    def file_offset(self, address, size=1):
        for s in self.segments:
            if s.header.p_vaddr <= address and address + size <= s.header.p_vaddr + s.header.p_filesz:
                return s.header.p_offset + address - s.header.p_vaddr
        raise ValueError('Unmapped ELF address: ' + hex(address))

    def word(self, address):
        return struct.unpack_from(self.word_format, self.data, self.file_offset(address, self.width))[0]

    def pointer(self, address):
        return self.pointers.get(address, {'address': self.word(address), 'symbol': None})

    def _save(self, slot, value):
        if slot in self.pointers and self.pointers[slot] != value:
            raise ValueError('Conflicting relocations at ' + hex(slot))
        self.pointers[slot] = value

    def _relocation(self, slot, info, addend):
        bits, mask = (32, 0xffffffff) if self.width == 8 else (8, 0xff)
        kind = info & mask
        relative = 1027 if self.width == 8 else 23
        absolute = (257, 1025) if self.width == 8 else (2, 21)
        if kind == relative:
            self._save(slot, {'address': addend, 'symbol': None})
        elif kind in absolute:
            symbol = self.elf.get_section_by_name('.dynsym').get_symbol(info >> bits)
            value = None if symbol.entry.st_shndx == 'SHN_UNDEF' else symbol.entry.st_value + addend
            self._save(slot, {'address': value, 'symbol': symbol.name})

    def _decode(self):
        for section in self.elf.iter_sections():
            if isinstance(section, RelocationSection):
                self.formats.add('RELA' if section.is_RELA() else 'REL')
                for r in section.iter_relocations():
                    slot = r.entry.r_offset
                    addend = r.entry.r_addend if section.is_RELA() else self.word(slot)
                    self._relocation(slot, r.entry.r_info, addend)
            elif section.name == '.relr.dyn':
                self.formats.add('Android RELR')
                base = 0
                for (entry,) in struct.iter_unpack(self.word_format, section.data()):
                    if not entry & 1:
                        self._save(entry, {'address': self.word(entry), 'symbol': None})
                        base = entry + self.width
                    else:
                        if not base:
                            raise ValueError('RELR bitmap without base')
                        for bit in range(self.width * 8 - 1):
                            if entry & (1 << (bit + 1)):
                                slot = base + bit * self.width
                                self._save(slot, {'address': self.word(slot), 'symbol': None})
                        base += (self.width * 8 - 1) * self.width
            elif section.data().startswith(b'APS2'):
                self.formats.add('Android APS2')
                packed, cursor = section.data(), 4

                def pop():
                    nonlocal cursor
                    value = shift = 0
                    while shift < 70 and cursor < len(packed):
                        byte = packed[cursor]
                        cursor += 1
                        value |= (byte & 127) << shift
                        shift += 7
                        if not byte & 128:
                            return value - (1 << shift) if byte & 64 else value
                    raise ValueError('Invalid packed SLEB128')

                count, slot = pop(), pop()
                if not 0 <= count <= 10000000:
                    raise ValueError('Invalid packed relocation count')
                decoded = info = addend = 0
                is_rela = section.name.startswith('.rela')
                while decoded < count:
                    size, flags = pop(), pop()
                    if not 0 < size <= count - decoded or flags & ~15:
                        raise ValueError('Invalid packed relocation group')
                    delta = pop() if flags & 2 else None
                    if flags & 1:
                        info = pop()
                    if flags & 8 and flags & 4:
                        addend += pop()
                    elif not flags & 8:
                        addend = 0
                    for _ in range(size):
                        slot += delta if delta is not None else pop()
                        if not flags & 1:
                            info = pop()
                        if flags & 8 and not flags & 4:
                            addend += pop()
                        self._relocation(slot, info, addend if is_rela else self.word(slot))
                        decoded += 1
                if cursor != len(packed):
                    raise ValueError('Trailing packed relocation bytes')

    def vtable(self, name):
        symbol = self.symbols[name]
        begin, size = symbol.st_value, symbol.st_size
        return [{'offset': offset, **self.pointer(begin + offset)}
                for offset in range(0, size, self.width)]
