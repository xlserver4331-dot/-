"""Tests workflow plumbing using fake executables, NOT Blender/CS2 engine tests."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/auto_workflow.py"

FAKE_BLENDER = r'''#!/usr/bin/env python3
import sys,json,pathlib
p=sys.argv
script=p[p.index('--python')+1]
arguments=p[p.index('--')+1:]
def v(s): return arguments[arguments.index(s)+1]
if script.endswith('blender_auto_fix.py'):
    if '--apply' in arguments:
        pathlib.Path(v('--out')).write_text('new-blend',encoding='utf8')
    if '--export-fbx' in arguments:
        pathlib.Path(v('--export-fbx')).write_text('corrected-fbx',encoding='utf8')
    result={'status':'APPLIED_NEW_COPY' if '--apply' in arguments else 'DRY_RUN',
            'actions':[{'vertex':0}], 'output_blend':v('--out') if '--apply' in arguments else None,
            'exported_fbx':v('--export-fbx') if '--export-fbx' in arguments else None}
    pathlib.Path(v('--report')).write_text(json.dumps(result),encoding='utf8')
elif script.endswith('blender_seam_repair.py'):
    if '--apply' in arguments:
        pathlib.Path(v('--out')).write_text('new-seam-blend',encoding='utf8')
    result={'status':'APPLIED_REQUIRES_REAUDIT' if '--apply' in arguments else 'DRY_RUN_REVIEWED',
            'repairs':[{'mesh':'BodyMesh','keep_vertex':12,'merge_vertex':13}],
            'output_blend':v('--out') if '--apply' in arguments else None}
    pathlib.Path(v('--report')).write_text(json.dumps(result),encoding='utf8')
elif script.endswith('blender_accessory_setup.py'):
    if '--apply' in arguments:
        pathlib.Path(v('--out')).write_text('new-accessory-blend',encoding='utf8')
    result={'status':'PREPARED_REAUDIT_REQUIRED' if '--apply' in arguments else 'DRY_RUN',
            'output_blend':v('--out') if '--apply' in arguments else None,
            'manual_weights_pending':[], 'created_bones':['acc_test']}
    pathlib.Path(v('--report')).write_text(json.dumps(result),encoding='utf8')
elif script.endswith('blender_extract_firstperson.py'):
    if '--apply' in arguments:
        pathlib.Path(v('--out')).write_text('new-firstperson-cut-preview',encoding='utf8')
    result={'status':'EXTRACTED_REQUIRES_RIGGING' if '--apply' in arguments else 'DRY_RUN',
            'source_sha256_before':'mock', 'parts':[{'selected_faces':40}]}
    pathlib.Path(v('--report')).write_text(json.dumps(result),encoding='utf8')
elif script.endswith('blender_audit.py'):
    result={'status':'WARN', 'findings':{'errors':[], 'warnings':[{'code':'BBOX_REFERENCE_MISSING'}]},
            'checks':{'reference_rest_pose':'USER_ATTESTED',
                      'bounding_boxes':{'static_comparison':{'status':'PASS'},'dynamic_comparison':{'status':'PASS'}},
                      'source_proportions':{'status':'PASS'}, 'animation_suite':{'status':'PENDING_RUNTIME'},
                      'accessories':{'status':'PASS_PRELIMINARY'},'joint_deformation':{'status':'PASS_PRELIMINARY'},
                      'rig_stretch':{'status':'PASS_PRELIMINARY'},'mesh_integrity':{'status':'PASS_PRELIMINARY'}}}
    if '--height-profile' in arguments:
        hp=json.loads(pathlib.Path(v('--height-profile')).read_text())
        result['checks']['source_height']={'status':'PASS','selection_confirmed':True,
            'height_choice_mode':hp['height_choice']['mode'],
            'target_body_height':hp['agent_reference_body_height']}
    pathlib.Path(v('--out')).write_text(json.dumps(result),encoding='utf8')
else: sys.exit(3)
'''
FAKE_COMPILER = r'''#!/usr/bin/env python3
import pathlib,sys
src=pathlib.Path(sys.argv[sys.argv.index('-i')+1]); parts=list(src.parts)
i=parts.index('content')
root=pathlib.Path(*parts[:i])
relative=pathlib.Path(*parts[i+1:])
dst=root/'game'/relative
dst=dst.with_name(dst.name+'_c')
dst.parent.mkdir(parents=True,exist_ok=True)
dst.write_text('compiled',encoding='utf8')
'''


class IntegrationSimulated(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        base = Path(self.tmp.name)
        self.root = base / 'cs2'
        (self.root / 'game/csgo').mkdir(parents=True)
        (self.root / 'game/csgo/gameinfo.gi').write_text('mock')
        (self.root / 'content/csgo_addons/my_addon').mkdir(parents=True)
        (self.root / 'game/csgo_addons/my_addon').mkdir(parents=True)
        binpath = self.root / 'game/bin/win64'
        binpath.mkdir(parents=True)
        self.fake_blender = base / 'fake_blender'
        self.fake_blender.write_text(FAKE_BLENDER, encoding='utf8')
        self.fake_blender.chmod(0o755)
        (binpath / 'resourcecompiler.exe').write_text(FAKE_COMPILER, encoding='utf8')
        (binpath / 'resourcecompiler.exe').chmod(0o755)
        (binpath / 'csgocfg.exe').write_text('#!/bin/sh\nsleep 2\n', encoding='utf8')
        (binpath / 'csgocfg.exe').chmod(0o755)
        self.blend = base / 'original.blend'
        self.blend.write_text('original',encoding='utf8')
        self.fbx = base / 'old.fbx'
        self.fbx.write_text('stale-export',encoding='utf8')
        self.vmdl = base / 'model.vmdl'
        self.vmdl.write_text('modeldoc',encoding='utf8')
        self.profile = base / 'profile.json'
        self.profile.write_text('{}')
        self.bbox = base / 'bbox.json'
        self.bbox.write_text('{}')
        self.height_profile = base / 'height_profile.local.json'
        self.height_profile.write_text(json.dumps({'model_type': 'humanoid',
            'exclude_accessories_from_height': True,
            'agent_reference_body_height': 100,
            'height_choice': {'mode': 'match_agent', 'confirmed_by_user': True}}))
        self.settings = base / 'config.json'
        self.cfg = {
            'target':'prop_preview','cs2_root':str(self.root), 'addon_name':'my_addon',
            'blender_executable':str(self.fake_blender),'blend_file':str(self.blend),
            'ag2_profile':str(self.profile),'bbox_rules':str(self.bbox),
            'auto_export_fbx':{'enabled':True,'modeldoc_fbx_reference_verified':True,
                               'relative_path':'models/custom/model.fbx'},
            'deploy_files':[{'source':str(self.fbx),'area':'content','relative_path':'models/custom/model.fbx'},
                            {'source':str(self.vmdl),'area':'content','relative_path':'models/custom/model.vmdl'}],
            'compile_sources':['models/custom/model.vmdl'],
            'required_compiled_files':['models/custom/model.vmdl_c'],
            'launch_mode':'tools'
        }
        self.settings.write_text(json.dumps(self.cfg))

    def call(self,*args):
        out=Path(self.tmp.name)/('out_'+str(len(list(Path(self.tmp.name).glob('out_*')))))
        cmd=[sys.executable,str(SCRIPT),'run','--config',str(self.settings), '--out-dir',str(out), *args]
        res=subprocess.run(cmd,text=True,capture_output=True)
        return res,json.loads((out/'workflow_result.json').read_text()),out

    def test_simulated_dry_run_leaves_source_untouched(self):
        res,r,out=self.call('--fix','--deploy','--compile','--launch')
        self.assertEqual(res.returncode,0, res.stdout+res.stderr)
        self.assertEqual(r['status'],'DRY_RUN_COMPLETE')
        self.assertFalse((self.root/'content/csgo_addons/my_addon/models/custom/model.fbx').exists())
        self.assertEqual(self.blend.read_text(),'original')

    def test_simulated_run_exports_corrected_fbx(self):
        res,r,out=self.call('--fix','--deploy','--compile','--execute')
        self.assertEqual(res.returncode,0,res.stdout+res.stderr)
        self.assertEqual(r['status'],'STEPS_EXECUTED_RUNTIME_PENDING')
        self.assertEqual((self.root/'content/csgo_addons/my_addon/models/custom/model.fbx').read_text(), 'corrected-fbx')
        self.assertEqual((self.root/'game/csgo_addons/my_addon/models/custom/model.vmdl_c').read_text(), 'compiled')
        self.assertEqual(self.blend.read_text(),'original')
        self.assertTrue((out/'auto_fixed.blend').exists())
        self.assertTrue((out/'blender_audit_after.json').exists())

    def test_v5_accessory_setup_is_copy_then_audit_then_export(self):
        self.cfg['accessories']=str(self.profile)
        self.settings.write_text(json.dumps(self.cfg))
        res, meta, out=self.call('--rig-accessories','--fix','--deploy','--compile','--execute')
        self.assertEqual(res.returncode,0,res.stdout+res.stderr)
        self.assertTrue((out/'accessories_prepared.blend').exists())
        self.assertEqual(self.blend.read_text(encoding='utf8'),'original')
        self.assertEqual(meta['steps']['accessory_setup']['status'],'PREPARED_REAUDIT_REQUIRED')
        self.assertEqual((self.root/'content/csgo_addons/my_addon/models/custom/model.fbx').read_text(),'corrected-fbx')

    def test_game_qa_dry_run_pipeline(self):
        game_cfg = Path(self.tmp.name) / "game_test.json"
        game_cfg.write_text(json.dumps({
            "enabled": True, "allow_desktop_control": False,
            "server_endpoint": "127.0.0.1:27015", "model_name": "char_a",
            "readiness": {"strategy": "image_template", "image_path": "C:/not-yet-calibrated.png"},
            "steps": [{"id": "idle", "action": "idle", "seconds": 0.5}]
        }), encoding="utf-8")
        self.cfg["target"] = "player_runtime"
        self.cfg["height_profile"] = str(self.height_profile)
        for opt in ("proportion_profile", "original_proportions", "animation_suite", "accessories", "joint_deformation", "mesh_integrity", "rig_stretch"):
            self.cfg[opt] = str(self.profile)
        self.cfg["game_test_config"] = str(game_cfg)
        self.settings.write_text(json.dumps(self.cfg))
        res, result, out = self.call("--game-test")
        self.assertEqual(res.returncode, 2, res.stdout+res.stderr)
        self.assertEqual(result["status"], "BLOCKED")
        self.assertIn("双视角部署门禁", result["error"])
        self.assertFalse((out / "game_qa/screenshots").exists())

    def test_v7_firstperson_extraction_is_distinct_staged_operation(self):
        self.cfg['target']='player_runtime'
        self.cfg['height_profile']=str(self.height_profile)
        for opt in ('proportion_profile','original_proportions','animation_suite','accessories','joint_deformation','mesh_integrity','rig_stretch'):
            self.cfg[opt]=str(self.profile)
        self.cfg['firstperson_extraction']=str(self.profile)
        self.cfg['firstperson_source_blend_file']=str(self.blend)
        self.settings.write_text(json.dumps(self.cfg))
        res,r,out=self.call('--extract-viewmodel','--execute')
        self.assertEqual(res.returncode,0,res.stdout+res.stderr)
        self.assertEqual(r['status'],'VIEWMODEL_EXTRACTION_PENDING_RIGGING')
        self.assertTrue((out/'firstperson_cut_preview.blend').is_file())
        self.assertEqual(self.blend.read_text(),'original')
        res,r,out=self.call('--extract-viewmodel','--deploy','--execute')
        self.assertEqual(res.returncode,2)
        self.assertIn('单独成轮',r['error'])

    def test_v6_seam_repair_dry_run_and_execute_reaudits(self):
        self.cfg['seam_repair']=str(self.profile)
        self.settings.write_text(json.dumps(self.cfg))
        res, meta, out=self.call('--repair-seams')
        self.assertEqual(res.returncode,0, res.stdout+res.stderr)
        self.assertEqual(meta['steps']['seam_repair']['status'],'DRY_RUN_REVIEWED')
        self.assertFalse((out/'seam_repaired.blend').exists())
        res,meta,out=self.call('--repair-seams','--execute')
        self.assertEqual(res.returncode,0,res.stdout+res.stderr)
        self.assertTrue((out/'seam_repaired.blend').is_file())
        self.assertTrue((out/'blender_audit_after.json').is_file())
        self.assertEqual(self.blend.read_text(),'original')

    def test_v6_cannot_deploy_seam_repair_without_fresh_export(self):
        self.cfg['seam_repair']=str(self.profile)
        self.settings.write_text(json.dumps(self.cfg))
        res,meta,out=self.call('--repair-seams','--deploy','--execute')
        self.assertEqual(res.returncode,2)
        self.assertIn('重新导出',meta['error'])

    def test_blocks_without_modeldoc_reference_ack(self):
        self.cfg['auto_export_fbx']['modeldoc_fbx_reference_verified']=False
        self.settings.write_text(json.dumps(self.cfg))
        res,r,out=self.call('--fix','--deploy','--execute')
        self.assertEqual(res.returncode,2)
        self.assertEqual(r['status'],'BLOCKED')
        self.assertFalse((self.root/'content/csgo_addons/my_addon/models/custom/model.fbx').exists())


if __name__=='__main__': unittest.main()
