"""r104b real LCD color challenges and MENU/half-press lifecycle observation."""
import argparse
import json
from pathlib import Path
from unittest.mock import patch
import probe_z62_capturework_preview_original as parent
from record_z62_action_evidence import workspace,digest,require


def run(qemu,card,group23,fixture,output,duration=24,wall_limit=600):
    output=workspace(output);stream=parent.parent.parent.parent.finite.parent
    previous=stream.original.snapshot;events=[];captures=[];sent=set();saved=set()
    sources={str(Path(p)):digest(Path(p)) for p in (__file__,parent.__file__)}
    schedule=((12,9,'menu-1'),(14,24,'half-return-1'),(18,9,'menu-2'),(20,24,'half-return-2'))
    pictures=((10.4,'color-blue'),(11.4,'color-orange'),(13,'menu-1'),(16.4,'photo-return-1'),
        (19,'menu-2'),(22.4,'photo-return-2'))
    def snapshot(machine,layout):
        row=previous(machine,layout);now=row['virtual_time_ns']/1e9
        words=machine._words(0xc1811e50,5)
        row['application']={'ready_word':words[0],'index':words[4]&255,'queued_keys':sorted(machine.key_events),
            'held':sorted(machine.held),'switch_words':machine._words(0xc25d6fc0,3)}
        for due,pin,label in schedule:
            if now>=due and label not in sent:
                machine._set_key_locked(pin,0);machine._set_key_locked(pin,1)
                entry={'virtual_time_ns':row['virtual_time_ns'],'pin':pin,'action':label,
                    'electrical_press_release_queued':True,'application_before':row['application']}
                events.append(entry);sent.add(label);print('LIFECYCLE_INPUT',json.dumps(entry),flush=True)
        for due,label in pictures:
            if now>=due and label not in saved:
                ppm=output/(label+'.ppm');png=output/(label+'.png')
                machine.qmp.command('screendump',{'filename':str(stream.paths.WorkspacePath(ppm))})
                encoded=machine.frame_png.__func__.__globals__['ppm_to_png'](ppm.read_bytes())
                with png.open('xb') as handle:handle.write(encoded)
                captures.append({'virtual_time_ns':row['virtual_time_ns'],'label':label,'path':png.name,
                    'sha256':digest(png),'application':row['application']})
                saved.add(label)
        return row
    with patch.object(stream.original,'snapshot',snapshot):
        result,prior=parent.run(qemu,card,group23,fixture,output,duration,wall_limit)
    require(all(digest(Path(p))==sha for p,sha in sources.items()),'Lifecycle observer changed')
    receipt={'schema':1,'version':'2026.11.04-CW-preview-lifecycle-r104b',
        'result_sha256':digest(output/'result.json'),'source_sha256':sources,'events':events,'LCD_captures':captures,
        'camera_accessed':False,'firmware_software_or_ready_modified':False,'GDB_attached':False,
        'menu_resume_acceptance_passed':False,'acceptance_note':'Inspect actual application indices, pixels and fresh sources; this flag is not an acceptance oracle.'}
    with (output/'preview-lifecycle.json').open('x',encoding='utf-8') as handle:
        json.dump(receipt,handle,ensure_ascii=False,indent=2)
    print(json.dumps({'input_sequences':len(events),'LCD_captures':len(captures),'completed_observation':result['completed_observation']}),flush=True)
    return result,receipt


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--qemu',type=Path,default=parent.hardware.DEFAULT_QEMU)
    parser.add_argument('--card',type=Path,required=True);parser.add_argument('--group23',type=Path,required=True)
    parser.add_argument('--fixture',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--duration',type=float,default=24);parser.add_argument('--wall-limit',type=float,default=600)
    args=parser.parse_args();result,receipt=run(args.qemu,args.card,args.group23,args.fixture,args.output,args.duration,args.wall_limit)
    raise SystemExit(0 if result['completed_observation'] and not result.get('failure') and result.get('process_exit_code')==0 else 1)
