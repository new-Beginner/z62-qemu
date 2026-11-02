"""Presentation must use the backend photo receipt and captured-frame metadata."""
import json
from pathlib import Path
import shutil
import subprocess
import unittest


@unittest.skipUnless(shutil.which('node'), 'Node is needed for the status component test')
class NativeStatusJsTests(unittest.TestCase):
    def test_saved_failed_and_playback_information(self):
        source = Path(__file__).resolve().parents[1] / 'tools/assets/z62-native-scene-status.js'
        self.assertTrue(source.is_file(), 'The native status renderer is missing')
        harness = r'''
const fs = require('fs'), vm = require('vm');
const nodes = Object.fromEntries(['software-message','software-info'].map(id => [id,{textContent:''}]));
nodes['software-zoom'] = {value:'4',disabled:false};
const context = {document:{getElementById:id=>nodes[id]}};
vm.createContext(context);
vm.runInContext(fs.readFileSync(process.argv[1], 'utf8'), context);
context.renderNativeInputReceipt({shared_camera_input:{events:[{sequence:1,pin:25,level:0,
  software_applied:true,hardware_outcome:'issued',result:{name:'Z62_0001.JPG'}}]}});
const saved = nodes['software-message'].textContent;
context.renderNativeInputReceipt({shared_camera_input:{events:[{sequence:2,pin:25,level:0,
  software_applied:false,hardware_outcome:'issued',error:'CameraError: no_card'}]}});
const failed = nodes['software-message'].textContent;
context.renderNativeSoftwareInfo({view:'playback',zoom:4,selected_image:'Z62_0001.JPG',frame_id:999,
  virtual_time_ns:9000000000,lens:{focus_position:0,focus_target:0},card:{present:true,images:[{
    name:'Z62_0001.JPG',metadata:{frame_id:3,virtual_time_ns:100000000,
    exposure:{iso:200,shutter_seconds:0.008},lens:{aperture:4,focal_length_mm:35,focus_position:0.65}}}]}});
const playback = nodes['software-info'].textContent;
context.renderNativeSoftwareInfo({view:'live',zoom:1,lens:{focus_position:0.65,focus_target:0.65},card:{present:true,images:[]}});
console.log(JSON.stringify({saved,failed,playback,zoomAfterDelete:nodes['software-zoom']}));
'''
        result = subprocess.run([shutil.which('node'), '-e', harness, str(source)],
                                capture_output=True, text=True, encoding='utf-8', timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        values = json.loads(result.stdout)
        self.assertIn('已保存', values['saved'])
        self.assertIn('Z62_0001.JPG', values['saved'])
        self.assertIn('未保存', values['failed'])
        self.assertNotIn('已保存', values['failed'])
        self.assertIn('帧 3', values['playback'])
        self.assertIn('ISO 200', values['playback'])
        self.assertNotIn('999', values['playback'])
        self.assertEqual(values['zoomAfterDelete']['value'], '1')
        self.assertTrue(values['zoomAfterDelete']['disabled'])


if __name__ == '__main__':
    unittest.main()
