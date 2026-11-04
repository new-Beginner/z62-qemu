"""Virtual-time MAIN producer with bounded mailboxes and lossless audit storage.

Payloads are retained once; per-publication headers reconstruct each accepted
packet exactly. Busy/paused clocks create no queued frame credits or fake DMA.
"""
import hashlib
import os
from pathlib import Path
import struct
import zlib
from PIL import Image
from z62_main_frame import make_packet,parse_packet
from record_z62_action_evidence import workspace,require


class FrameCadence:
    def __init__(self,fps=30):
        require(type(fps) is int and fps==30,'Current MAIN envelope uses the explicit 30 Hz timeline')
        self.fps=fps;self.last_frame=None;self.last_time=None;self.publication=0;self.skipped=0

    def suggest(self,now_ns,eligible=True):
        require(type(now_ns) is int and now_ns>=0,'Actual nonnegative virtual time required')
        if self.last_time is not None:require(now_ns>=self.last_time,'Source clock moved backwards; needs a new epoch')
        frame=now_ns*self.fps//1_000_000_000
        if not eligible or frame==self.last_frame:return None
        return {'publication':self.publication+1,'frame':frame,'time_ns':now_ns}

    def accept(self,proposal):
        require(self.suggest(proposal['time_ns'])==proposal,'Accepted source proposal is stale')
        if self.last_frame is not None:self.skipped+=proposal['frame']-self.last_frame-1
        self.publication=proposal['publication'];self.last_frame=proposal['frame'];self.last_time=proposal['time_ns']


class MainTemplate:
    def __init__(self,width,height,color):
        packet=make_packet(Image.new('RGB',(8,8),color),width=width,height=height,stride=2*width,
            epoch=1,publish_id=1,frame_id=0,virtual_time_ns=0)
        self.metadata,self.payload=parse_packet(packet);self.header=packet[:96]
        self.payload_sha256=hashlib.sha256(self.payload).hexdigest()

    def packet(self,epoch,publication,now_ns):
        require(type(epoch) is int and 0<epoch<1<<64,'Source epoch required')
        require(type(publication) is int and 0<publication<1<<64,'Source publication required')
        require(type(now_ns) is int and 0<=now_ns<1<<64,'Original virtual time required')
        header=bytearray(self.header)
        struct.pack_into('<4Q',header,32,epoch,publication,now_ns*30//1_000_000_000,now_ns)
        struct.pack_into('<I',header,88,zlib.crc32(header[:88]))
        return bytes(header)+self.payload


class AuditedMailbox:
    def __init__(self,directory,epoch=0x97):
        self.directory=workspace(directory);require(not self.directory.exists(),'Use a new MAIN mailbox directory')
        self.directory.mkdir(parents=True);self.epoch=epoch;self.templates={};self.template_records={}

    def prepare(self,proposal,width,height,color_index):
        require(color_index in (0,1),'Choose a declared diagnostic color')
        key=(width,height,color_index)
        if key not in self.templates:
            require(len(self.templates)<8,'Source geometry history limit')
            color=((40,80,160),(210,60,20))[color_index]
            template=MainTemplate(width,height,color);self.templates[key]=template
            path=self.directory/f'payload-{width}-{height}-{color_index}.linear16'
            with path.open('xb') as handle:handle.write(template.payload)
            self.template_records[key]={'path':path.name,'sha256':template.payload_sha256,
                'width':width,'height':height,'stride':width*2,'color':color,'bytes':len(template.payload)}
        template=self.templates[key]
        packet=template.packet(self.epoch,proposal['publication'],proposal['time_ns'])
        destination=self.directory/f'mailbox-{proposal["publication"]%2}.z62m'
        temporary=self.directory/'publication.new'
        require(not temporary.exists(),'An incomplete MAIN publication is preserved')
        with temporary.open('xb') as handle:handle.write(packet)
        require(destination.resolve().is_relative_to(self.directory.resolve()),'Mailbox target escaped directory')
        os.replace(temporary,destination)
        return destination,{'header_hex':packet[:96].hex(),'packet_sha256':hashlib.sha256(packet).hexdigest(),
            'payload':self.template_records[key],'geometry':[width,height],**proposal}


def reconstruct(directory,row):
    directory=workspace(directory);path=(directory/row['payload']['path']).resolve()
    require(path.is_relative_to(directory.resolve()),'Audit payload escaped source directory')
    payload=path.read_bytes();require(hashlib.sha256(payload).hexdigest()==row['payload']['sha256'],'Audit payload changed')
    packet=bytes.fromhex(row['header_hex'])+payload
    require(hashlib.sha256(packet).hexdigest()==row['packet_sha256'],'Reconstructed source packet differs')
    meta,_=parse_packet(packet)
    require((meta.publish_id,meta.frame_id,meta.virtual_time_ns)==(row['publication'],row['frame'],row['time_ns']),
        'Audit source tags differ')
    return packet
