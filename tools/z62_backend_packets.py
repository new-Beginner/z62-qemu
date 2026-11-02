"""Bounded decoder for captured Z62 backend parameter-load packets.

The decoded register values are observations, not recovered image algorithms.
Packet lengths include the header word; bit28 selects another packet.
"""
import argparse
from dataclasses import dataclass
import json
from pathlib import Path
import struct


@dataclass(frozen=True)
class Packet:
    offset: int
    values: tuple[int, ...]
    final: bool


def decode(data, *, max_packets=64, max_words=4096):
    if len(data)%4 or not 1 <= max_packets <= 256 or not 2 <= max_words <= 16384:
        raise ValueError('Invalid aligned packet buffer or budget')
    words=struct.unpack('<'+'I'*(len(data)//4),data)
    cursor=0
    packets=[]
    for _ in range(max_packets):
        if cursor>=len(words) or cursor>=max_words:
            raise ValueError('Missing packet terminator/header')
        header=words[cursor]
        kind=header>>24
        count=(header>>16)&255
        offset=header&65535
        if kind not in (1,17) or count<2 or offset%4 or offset+4*(count-1)>65536:
            raise ValueError(f'Unsupported packet header {header:#x}')
        end=cursor+count
        if end>len(words) or end>max_words:
            raise ValueError('Truncated packet or exceeded word budget')
        packets.append(Packet(offset,tuple(words[cursor+1:end]),kind==1))
        cursor=end
        if kind==1:
            return packets,cursor*4
    raise ValueError('Exceeded packet budget')


def registers(packets):
    result={}
    for packet in packets:
        result.update({packet.offset+4*i:value for i,value in enumerate(packet.values)})
    return result


def captured_graphs(trace):
    graphs={}
    for hit in trace['hits']:
        graph=hit.get('extra_observation',{}).get('native_graph')
        if graph is not None:
            graphs.setdefault(graph['container'],graph)
    result=[]
    for graph in graphs.values():
        nodes=[]
        for node in graph['nodes']:
            entry={k:node[k] for k in ('index','type_byte','physical_unit','payload_pointer')}
            if node['type_byte'] in (0,1,2,3):
                entry['encoding']='descriptor-or-routing; not parameter-load packets'
            else:
                data=bytes.fromhex(node.get('payload_512',''))
                packets,consumed=decode(data)
                entry.update(encoding='parameter-load packets',consumed_bytes=consumed,
                    packets=[{'offset':hex(p.offset),'values':[hex(v) for v in p.values],
                              'final':p.final} for p in packets],
                    registers={hex(k):hex(v) for k,v in registers(packets).items()})
            nodes.append(entry)
        result.append({'container':graph['container'],'count':graph['count'],'nodes':nodes})
    return {'schema':1,'graphs':result,'pixel_algorithms_verified':False}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--input',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    args=p.parse_args()
    result=captured_graphs(json.loads(args.input.read_text(encoding='utf-8')))
    with args.output.open('x',encoding='utf-8') as handle: json.dump(result,handle,indent=2)
    print([(g['container'],g['count'],sum(n.get('consumed_bytes',0) for n in g['nodes'])) for g in result['graphs']])
