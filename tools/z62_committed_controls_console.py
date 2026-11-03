"""UI-only state synchronization over the persistent diagnostic profile."""
from pathlib import Path

VERSION='2026.11.03-committed-controls-r75'


def apply_console(source):
    from reference_updates import replace_once
    source=Path(source)
    script=source/'web-z62/console.js'
    script.write_text(script.read_text(encoding='utf-8')+'\n'+
        (Path(__file__).with_name('assets')/'z62-committed-controls.js').read_text(encoding='utf-8'),
        encoding='utf-8',newline='\n')
    html=source/'web-z62/index.html'; content=html.read_text(encoding='utf-8')
    content=replace_once(content,'<form id="software-optics">',
        '<p id="software-optics-state" class="body-input-note" role="status">等待已应用的镜头参数</p>\n'
        '        <form id="software-optics">')
    content=replace_once(content,'<form id="software-exposure">',
        '<p id="software-exposure-state" class="body-input-note" role="status">等待已应用的曝光参数</p>\n'
        '        <form id="software-exposure">')
    html.write_text(content,encoding='utf-8',newline='\n')
