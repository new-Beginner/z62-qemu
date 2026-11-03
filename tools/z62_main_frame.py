"""Explicit C-model MAIN producer, separate from the frozen auxiliary Z62S path.

This is a host envelope, not a Nikon protocol. CRC detects transport corruption,
not authenticity. Input is approximate sRGB8 scene data linearized into RGGB16.
"""
from dataclasses import dataclass
import struct
import zlib

import numpy as np
from PIL import Image

from z62_scene_packet import tags

HEADER=struct.Struct('<4s7I4Q8I')
MAX_BYTES=64*1024*1024
BLACK,WHITE=1024,65520


@dataclass(frozen=True)
class MainMetadata:
    width: int
    height: int
    stride: int
    epoch: int
    publish_id: int
    frame_id: int
    virtual_time_ns: int
    black: int
    white: int
    payload_crc32: int


def geometry(width,height,stride):
    if any(type(v) is not int for v in (width,height,stride)):
        raise ValueError('MAIN geometry requires integers')
    if (not 0<width<=4096 or not 0<height<=4096 or (width|height)&1 or
            width*height>4*1024*1024 or stride<width*2 or stride&1 or
            stride*height>MAX_BYTES):
        raise ValueError('Unsupported bounded even RGGB16 MAIN geometry')


def make_packet(image,*,width=2020,height=1342,stride=4040,epoch,publish_id,frame_id,virtual_time_ns):
    geometry(width,height,stride)
    tags(epoch,publish_id,frame_id,virtual_time_ns)
    if not isinstance(image,Image.Image) or not image.width or not image.height:
        raise ValueError('Nonempty scene image required')
    rgb=np.asarray(image.convert('RGB').resize((width,height),Image.Resampling.BILINEAR),dtype=np.float64)/255
    linear=np.where(rgb<=.04045,rgb/12.92,((rgb+.055)/1.055)**2.4)
    values=np.rint(BLACK+linear*(WHITE-BLACK)).astype('<u2')
    samples=np.empty((height,width),dtype='<u2')
    samples[0::2,0::2]=values[0::2,0::2,0]
    samples[0::2,1::2]=values[0::2,1::2,1]
    samples[1::2,0::2]=values[1::2,0::2,1]
    samples[1::2,1::2]=values[1::2,1::2,2]
    rows=np.zeros((height,stride),dtype=np.uint8)
    rows[:,:width*2]=samples.view(np.uint8).reshape(height,width*2)
    raw=rows.tobytes()
    header=bytearray(HEADER.pack(b'Z62M',1,HEADER.size,1,width,height,stride,len(raw),
        epoch,publish_id,frame_id,virtual_time_ns,1,1,BLACK,WHITE,0,zlib.crc32(raw),0,0))
    struct.pack_into('<I',header,88,zlib.crc32(header[:88]))
    return bytes(header)+raw


def parse_packet(packet):
    if not isinstance(packet,(bytes,bytearray,memoryview)) or not HEADER.size<=len(packet)<=MAX_BYTES+HEADER.size:
        raise ValueError('Invalid MAIN packet extent')
    packet=bytes(packet)
    (magic,version,header_size,role,width,height,stride,size,epoch,publication,frame,time_ns,
     domain,cfa,black,white,reserved,crc,header_crc,tail)=HEADER.unpack_from(packet)
    if (magic,version,header_size,role,domain,cfa,reserved,tail)!=(b'Z62M',1,96,1,1,1,0,0):
        raise ValueError('Expected explicit linear16 RGGB MAIN envelope')
    geometry(width,height,stride); tags(epoch,publication,frame,time_ns)
    if size!=height*stride or len(packet)!=96+size or not 0<=black<white<=65535:
        raise ValueError('MAIN extent or transfer levels differ')
    raw=packet[96:]
    if zlib.crc32(packet[:88])!=header_crc or zlib.crc32(raw)!=crc:
        raise ValueError('MAIN header or payload checksum mismatch')
    rows=np.frombuffer(raw,dtype=np.uint8).reshape(height,stride)
    if np.any(rows[:,width*2:]):
        raise ValueError('MAIN row padding must be zero')
    return MainMetadata(width,height,stride,epoch,publication,frame,time_ns,black,white,crc),raw
