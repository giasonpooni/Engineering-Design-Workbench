"""Bounded RGB/RGBA PNG decoding for build evidence, not aesthetic scoring.

Only 640x360, 8-bit, non-interlaced PNGs are admitted by this first recipe.
No native image decoder, generated executable or external dependency is loaded.
"""
from __future__ import annotations
import struct
import zlib


def decode(raw: bytes) -> tuple[int, int, list[bytes]]:
    if type(raw) is not bytes or not 45 <= len(raw) <= 512*1024 or raw[:8] != b'\x89PNG\r\n\x1a\n':
        raise ValueError('Invalid bounded preview PNG')
    offset=8; header=None; parts=[]; ended=False; data_ended=False
    while offset<len(raw):
        if offset+12>len(raw):raise ValueError('Truncated PNG chunk')
        length=struct.unpack_from('>I',raw,offset)[0];kind=raw[offset+4:offset+8]
        if length>512*1024 or offset+12+length>len(raw):raise ValueError('PNG chunk exceeds bounds')
        payload=raw[offset+8:offset+8+length]
        crc=struct.unpack_from('>I',raw,offset+8+length)[0]
        if zlib.crc32(kind+payload)&0xffffffff!=crc:raise ValueError('PNG CRC mismatch')
        if header is None and kind!=b'IHDR':raise ValueError('Missing first PNG header')
        if kind==b'IHDR':
            if header is not None or length!=13:raise ValueError('Duplicate/invalid PNG header')
            w,h,depth,color,compression,filtering,interlace=struct.unpack('>IIBBBBB',payload)
            if (w,h)!=(640,360) or depth!=8 or color not in (2,6) or any((compression,filtering,interlace)):
                raise ValueError('Unsupported PNG pixel profile')
            header=(w,h,3 if color==2 else 4)
        elif kind==b'IDAT':
            if data_ended:raise ValueError('Non-contiguous PNG data')
            parts.append(payload)
        elif kind==b'IEND':
            if length or not parts or offset+12!=len(raw):raise ValueError('Invalid PNG end/trailing bytes')
            ended=True;offset+=12;break
        else:
            if not (kind[0]&32):raise ValueError('Unsupported critical PNG chunk')
            if parts:data_ended=True
        offset+=12+length
    if not ended or header is None:raise ValueError('Incomplete PNG')
    w,h,channels=header; expected=h*(w*channels+1)
    inflater=zlib.decompressobj()
    pixels=inflater.decompress(b''.join(parts),expected+1)
    if len(pixels)!=expected or not inflater.eof or inflater.unused_data or inflater.unconsumed_tail:
        raise ValueError('PNG decompressed extent mismatch')
    previous=bytearray(w*channels);rows=[];stride=w*channels
    for y in range(h):
        code=pixels[y*(stride+1)];row=bytearray(pixels[y*(stride+1)+1:(y+1)*(stride+1)])
        if code>4:raise ValueError('Unsupported PNG row filter')
        for x in range(stride):
            left=row[x-channels] if x>=channels else 0
            up=previous[x];upper_left=previous[x-channels] if x>=channels else 0
            if code==1:prediction=left
            elif code==2:prediction=up
            elif code==3:prediction=(left+up)//2
            elif code==4:
                p=left+up-upper_left;a=abs(p-left);b=abs(p-up);c=abs(p-upper_left)
                prediction=left if a<=b and a<=c else up if b<=c else upper_left
            else:prediction=0
            row[x]=(row[x]+prediction)&255
        if channels==4 and any(row[x]!=255 for x in range(3,stride,4)):
            raise ValueError('Preview must be fully opaque')
        rows.append(bytes(v for x in range(0,stride,channels) for v in row[x:x+3]));previous=row
    return w,h,rows


def inspect(raw: bytes) -> dict:
    w,h,rows=decode(raw)
    # Exclude the caption region. This checks nonblank evidence, NOT good art.
    colors=set();lo=255;hi=0
    for row in rows[150:]:
        for x in range(0,len(row),3):
            r,g,b=row[x:x+3];lum=(54*r+183*g+19*b)//256
            lo=min(lo,lum);hi=max(hi,lum);colors.add((r//16,g//16,b//16))
    return {'width':w,'height':h,'scene_luma_range':hi-lo,'scene_color_bins':len(colors),
            'nonblank':hi-lo>=24 and len(colors)>=12,'aesthetic_acceptance':False}
