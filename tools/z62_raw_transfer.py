"""Immutable C-model RAW transfer descriptor, independent of mutable MMIO.

Z62T is a host contract, not a recovered Nikon format. LUT8 discards eight input
bits. Reconstruction therefore names an interval and a midpoint, not an exact
physical inverse or the original sample.
"""
from dataclasses import dataclass
import struct
import zlib

BODY=struct.Struct('<4sIII256H')
CODECS={'shift':0,'lookup8-high-byte':1}


@dataclass(frozen=True)
class RawTransfer:
    bits: int
    codec: str
    lookup: tuple=()

    def __post_init__(self):
        if type(self.bits) is not int or self.bits not in (12,14,16) or self.codec not in CODECS:
            raise ValueError('Unsupported RAW transfer domain')
        values=tuple(self.lookup)
        if self.codec=='shift':
            if values: raise ValueError('Shift domain must not carry a LUT')
        elif (len(values)!=256 or any(type(v) is not int or not 0<=v<1<<self.bits for v in values) or
              any(b<=a for a,b in zip(values,values[1:]))):
            raise ValueError('LUT requires 256 strictly increasing in-range codes')
        object.__setattr__(self,'lookup',values)

    @property
    def input_quantum(self): return 256 if self.codec=='lookup8-high-byte' else 1<<(16-self.bits)

    def to_bytes(self):
        body=BODY.pack(b'Z62T',1,self.bits,CODECS[self.codec],*(self.lookup or (0,)*256))
        return body+struct.pack('<I',zlib.crc32(body))

    @classmethod
    def from_bytes(cls,blob):
        if not isinstance(blob,(bytes,bytearray,memoryview)) or len(blob)!=532:
            raise ValueError('RAW transfer descriptor must contain 532 bytes')
        blob=bytes(blob); magic,version,bits,codec,*lookup=BODY.unpack_from(blob)
        if magic!=b'Z62T' or version!=1 or codec not in (0,1) or zlib.crc32(blob[:528])!=struct.unpack_from('<I',blob,528)[0]:
            raise ValueError('Invalid RAW transfer identity/checksum')
        if codec==0 and any(lookup): raise ValueError('Nonzero unused LUT')
        return cls(bits,'shift' if codec==0 else 'lookup8-high-byte',lookup if codec else ())
