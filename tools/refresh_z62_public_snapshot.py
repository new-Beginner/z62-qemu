"""Update the existing public Git clone inside this workspace, without raw samples.

This maintainer export preserves runtime source bytes and public Git history.
It never stages, commits, pushes, removes files, or touches the research index.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

import export_z62_public as old

ROOT=Path(__file__).resolve().parents[1]
SNAPSHOT='2026.11.04-r91'
REMOTE='https://github.com/new-Beginner/z62-qemu.git'


def refresh(destination,source=ROOT):
    source=Path(source).resolve(); destination=Path(destination).resolve()
    if not destination.is_relative_to(source/'.runtime/publication') or not (destination/'.git').is_dir():
        raise ValueError('Use the isolated existing public clone inside workspace .runtime/publication')
    if any(old.linked(p) for p in (destination,*destination.parents)):
        raise ValueError('Linked publication paths are protected')
    remote=subprocess.run(['git','-C',str(destination),'remote','get-url','origin'],
                          capture_output=True,text=True,check=True).stdout.strip()
    if remote!=REMOTE: raise ValueError('Publication clone has another origin')
    mapping={path:relative for path,relative in old.selection(source).items()
             if path.relative_to(source).parts[0]!='analysis' or path.name=='scope.md'}
    mapping[source/'README.md']='README.md'
    mapping[source/'GOAL-Z62-QEMU.md']='docs/GOAL-Z62-QEMU.md'
    prepared={}; ledger=[]
    for path,relative in sorted(mapping.items(),key=lambda pair:pair[1]):
        if old.linked(path) or not path.resolve().is_relative_to(source):
            raise ValueError('Linked publication input: '+relative)
        original=path.read_bytes()
        if len(original)>2*1024**2 or any(pattern.search(original) for pattern in old.SECRET_PATTERNS):
            raise ValueError('Oversized or credential-shaped publication input: '+relative)
        data=original
        if path.suffix=='.md':
            text=old.rewrite_links(original.decode('utf-8-sig'),path,relative,source,mapping)
            data=old.scrub(text,source).replace('Q:/.runtime/','<WORKSPACE>/.runtime/').encode('utf-8')
        prepared[relative]=data
        ledger.append({'source':path.relative_to(source).as_posix(),'published':relative,
            'original_sha256':hashlib.sha256(original).hexdigest(),
            'published_sha256':hashlib.sha256(data).hexdigest(),'transformed':original!=data,'bytes':len(data)})
    navigation='\n## 公开仓库导航\n\n- [构建与父依赖](docs/BUILD.md)\n- [功能清单](docs/FEATURES.md)与[已知限制](docs/LIMITATIONS.md)\n- [开发时间线](docs/DEVELOPMENT.md)\n- [参考、作者与许可证](docs/REFERENCES.md)\n- [本次源码验证范围](docs/VALIDATION.md)\n- [历史内核事件验收摘要](docs/evidence/latest-kernel-events.json)（r83–r85，非完整原始轨迹）\n- [r86采集像素核验摘要](docs/evidence/capturework-pixels-r86.json)（独立数值阶段）\n- [r91原厂MAIN／DMA验收摘要](docs/evidence/capturework-original-r91.json)（统计／预览未贯通）\n'
    prepared['README.md']+=navigation.encode('utf-8')
    for row in ledger:
        if row['published']=='README.md':
            row.update(published_sha256=hashlib.sha256(prepared['README.md']).hexdigest(),
                       transformed=True,bytes=len(prepared['README.md']),publication_navigation_added=True)
    kernel=source/'analysis/z62-kernel-events-r83/verified-kernel-1.json'
    proof=json.loads(kernel.read_text(encoding='utf-8'))
    if proof.get('completed_evidence_check') is not True: raise ValueError('Latest kernel verification is incomplete')
    keys=('completed_evidence_check','observations','first_probe_incomplete_preserved',
          'same_vm_recovered_without_restart','actual_kernel_pattern_read',
          'original_setter_zero_result_proven','original_zero_to_00800000_publication_proven',
          'AND_wait_not_satisfied','target_rtos_product_or_version_proven','camera_accessed',
          'factory_capture_verified','functional_acceptance_eligible','AF_verified')
    summary={k:proof[k] for k in keys}
    summary.update(schema=1,snapshot=SNAPSHOT,original_record_sha256=old.digest(kernel),
        scope='Selected verification summary only; original traces, complete receipts and firmware are not distributed.')
    prepared['docs/evidence/latest-kernel-events.json']=(json.dumps(summary,ensure_ascii=False,indent=2)+'\n').encode()
    pixels=source/'analysis/z62-capturework-contract-r86/verified-pixels-1.json'
    pixel_proof=json.loads(pixels.read_text(encoding='utf-8'))
    if (pixel_proof.get('completed_evidence_check') is not True or
            pixel_proof.get('pixels_independently_decoded')!=1523084 or
            pixel_proof.get('sample_mismatches')!=0 or
            pixel_proof.get('QEMU_device_integrated') is not False or
            pixel_proof.get('MAIN_source_and_commit_provenance_verified') is not False):
        raise ValueError('Capturework numerical proof is incomplete or overclaims device integration')
    pixel_summary=dict(pixel_proof,snapshot=SNAPSHOT,original_record_sha256=old.digest(pixels),
        scope='Synthetic MAIN numerical fixture only; no QEMU DMA/IRQ or physical sampling equivalence.')
    prepared['docs/evidence/capturework-pixels-r86.json']=(json.dumps(pixel_summary,ensure_ascii=False,indent=2)+'\n').encode()
    stage_path=source/'analysis/z62-capturework-policy-r91/verified-stage-1.json'
    stage=json.loads(stage_path.read_text(encoding='utf-8'))
    bound={
        'original_window_result_sha256':'analysis/z62-capturework-original-r90/original-2/result.json',
        'original_verification_sha256':'analysis/z62-capturework-original-r90/verification-1/result.json',
    }
    for key,name in bound.items():
        if stage[key]!=old.digest(source/name): raise ValueError('r91 evidence binding changed: '+name)
    regression=source/'analysis/z62-capturework-policy-r91/regression-1.json'
    verified=json.loads((source/bound['original_verification_sha256']).read_text(encoding='utf-8'))
    if (stage['full_Python_regression']['result_sha256']!=old.digest(regression) or
            verified.get('completed_evidence_check') is not True or
            stage['actual_DMA_completed_counter']!=13 or stage['sample_mismatches']!=0 or
            stage['downstream_source_statistics_ISP_integration_complete'] is not False):
        raise ValueError('r91 stage proof is incomplete or overclaims downstream integration')
    stage_summary={key:value for key,value in stage.items() if key!='published'}
    stage_summary.update(snapshot=SNAPSHOT,original_record_sha256=old.digest(stage_path),
        scope='Selected historical r91 controlled-entry evidence; not a new firmware run or whole-camera acceptance.',
        publication_note='The local record predates publication; its published=false field is not a current cloud status.')
    prepared['docs/evidence/capturework-original-r91.json']=(json.dumps(stage_summary,ensure_ascii=False,indent=2)+'\n').encode()
    references=('analysis/z62-kernel-events-r83/verified-kernel-1.json',
        'analysis/z62-kernel-events-r83/events-1/result.json','analysis/z62-kernel-events-r83/events-2/result.json',
        'analysis/z62-kernel-events-r83/events-3/result.json','analysis/z62-kernel-events-r83/kernel-contract-1.json',
        'analysis/z62-prepare-control-r79/verified-control-3.json',
        'analysis/z62-capture-submit-r77/verified-traces-2.json',
        'analysis/z62-persistent-diagnostic-r74/verified-photo-and-faults-1.json',
        'analysis/z62-capturework-contract-r86/verified-pixels-1.json',
        'analysis/z62-capturework-contract-r86/state-1/result.json',
        'analysis/z62-capturework-contract-r86/state-1/source-archive.json',
        'analysis/z62-capturework-contract-r86/native-observed-2/result.json',
        'analysis/z62-capturework-contract-r86/native-observed-2/source-archive.json',
        'analysis/z62-capturework-contract-r86/session-archive-1/archive.json',
        'analysis/z62-capturework-policy-r91/verified-stage-1.json',
        'analysis/z62-capturework-policy-r91/regression-1.json',
        'analysis/z62-capturework-policy-r91/native-1/result.json',
        'analysis/z62-capturework-policy-r91/build-binding/source-archive.json',
        'analysis/z62-capturework-original-r90/original-1/result.json',
        'analysis/z62-capturework-original-r90/original-2/result.json',
        'analysis/z62-capturework-original-r90/verification-1/result.json')
    index={'schema':1,'snapshot':SNAPSHOT,'scope':'Hashes identify omitted local evidence; these are not downloadable traces.',
           'entries':[{'path':name,'bytes':(source/name).stat().st_size,'original_sha256':old.digest(source/name),
                       'original_contents_published':False} for name in references]}
    prepared['docs/evidence-index-20261104.json']=(json.dumps(index,ensure_ascii=False,indent=2)+'\n').encode()
    for relative in ('docs/evidence/latest-kernel-events.json','docs/evidence/capturework-pixels-r86.json',
                     'docs/evidence/capturework-original-r91.json',
                     'docs/evidence-index-20261104.json'):
        data=prepared[relative]
        ledger.append({'source':'selected local verification records','published':relative,
            'original_sha256':None,'published_sha256':hashlib.sha256(data).hexdigest(),
            'transformed':True,'generated_summary':True,'bytes':len(data)})
    result={'schema':1,'snapshot':SNAPSHOT,'file_count':len(prepared),'bytes':sum(map(len,prepared.values())),
        'source_bytes_preserved':True,'original_firmware_included':False,'compiled_runtimes_included':False,
        'raw_disassembly_included':False,'original_git_history_included':False,'files':ledger,
        'notes':['Public Git history and pre-existing curated documents are preserved.',
                 'Only scope notes and explicitly selected summaries are newly exported from analysis.',
                 'No raw firmware, cards, NKN originals, host toolchains, complete traces or full RAM dumps are copied.',
                 'Documentation is redacted and links to omitted evidence are marked as local-only.']}
    for relative,data in prepared.items():
        path=destination/relative
        if not path.resolve().is_relative_to(destination) or old.linked(path):
            raise ValueError('Publication target escaped clone')
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_bytes(data)
    # Preserve the existing public manifest's CRLF convention on any host.
    manifest=(json.dumps(result,ensure_ascii=False,indent=2)+'\n').replace('\n','\r\n')
    (destination/'publication-manifest.json').write_bytes(manifest.encode('utf-8'))
    print(json.dumps({k:v for k,v in result.items() if k!='files'},ensure_ascii=False))
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--destination',type=Path,required=True)
    args=parser.parse_args(); refresh(args.destination)
