"""Visible controls track applied state while preserving unsubmitted drafts."""
import json
from pathlib import Path
import shutil
import subprocess
import unittest

ROOT=Path(__file__).resolve().parents[1]


class CommittedControlsJsTests(unittest.TestCase):
    def test_ready_transition_drafts_and_busy_gates(self):
        node=shutil.which('node')
        self.assertIsNotNone(node,'Node is required for actual UI state transition checks')
        script=r'''
const fs=require('fs'),vm=require('vm'),assert=require('assert');
const field=(value,select=false)=>({value:String(value),tagName:select?'SELECT':'INPUT',
 options:[{value:String(value)}],appendChild(option){this.options.push(option);}});
const optics={focal_length_mm:field(50),aperture:field(4,true),focus_target:field(0)};
const exposure={shutter_seconds:field(.008,true),iso:field(100,true)};
const form=fields=>({fields,listeners:{},addEventListener(name,fn){this.listeners[name]=fn;},
 querySelector(selector){return this.fields[selector.match(/name="([^"]+)"/)[1]];}});
const forms={optics:form(optics),exposure:form(exposure)};
const elements={'software-optics':forms.optics,'software-exposure':forms.exposure,
 'software-optics-state':{textContent:''},'software-exposure-state':{textContent:''},
 'software-shutter':{disabled:true}};
const document={activeElement:null,getElementById:id=>elements[id],createElement:()=>({})};
const context={document,renderVideoControls(){}};
vm.createContext(context);vm.runInContext(fs.readFileSync(process.argv[1],'utf8'),context);
const state={powered:true,card:{present:true},pipeline_mode:{ready:true,confirmed_mode:'photo'},
 lens:{focal_length_mm:50,aperture:4,focus_target:.65},
 exposure:{shutter_seconds:.008,iso:200},video:{recording:false}};
context.renderVideoControls(state,false);
assert.strictEqual(elements['software-shutter'].disabled,false,'startup disabled attribute must be released');
assert.strictEqual(Number(optics.focus_target.value),.65);
assert.strictEqual(Number(exposure.iso.value),200);
exposure.iso.value='400';forms.exposure.listeners.input();
context.renderVideoControls(state,false);
assert.strictEqual(Number(exposure.iso.value),400,'an unsent draft must survive polling');
assert.strictEqual(state.exposure.iso,200,'drafts must not alter backend state');
assert.ok(elements['software-exposure-state'].textContent.includes('未应用'));
state.exposure.iso=400;context.renderVideoControls(state,false);
assert.ok(elements['software-exposure-state'].textContent.startsWith('已应用'));
context.renderVideoControls(state,true);assert.strictEqual(elements['software-shutter'].disabled,true);
context.renderVideoControls(state,false);assert.strictEqual(elements['software-shutter'].disabled,false);
state.video={async:true,job_id:'test',terminal:false};context.renderVideoControls(state,false);
assert.strictEqual(elements['software-shutter'].disabled,true);
state.video.terminal=true;context.renderVideoControls(state,false);
assert.strictEqual(elements['software-shutter'].disabled,false);
state.pipeline_mode.ready=false;context.renderVideoControls(state,false);
assert.strictEqual(elements['software-shutter'].disabled,true);
console.log('ready, draft acknowledgement and operation gates passed');
'''
        result=subprocess.run([node,'-e',script,str(ROOT/'tools/assets/z62-committed-controls.js')],
                              capture_output=True,text=True,encoding='utf-8',timeout=20)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)


if __name__=='__main__':
    unittest.main()
