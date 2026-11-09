"""Dependency-free checks for strict extraction and player dual-view safeguards."""
import tempfile
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / 'scripts'))
from viewmodel_core import selected_face_indices, face_boundary_edges, extraction_preflight, viewmodel_release_gate
from dual_viewmodel_gate import inspect_pair
from auto_workflow_core import sha256

class TestViewmodelSplit(unittest.TestCase):
    def test_face_selection_strict_manual_masks(self):
        faces = [[0,1,2],[2,3,4],[5,6,7]]
        self.assertEqual(selected_face_indices(faces, {0,1,2,3}), [0])
        self.assertEqual(selected_face_indices(faces, {0,1,2,3}, minimum_fraction=2/3), [0,1])

    def test_face_selection_rejects_unsafe_fraction(self):
        with self.assertRaises(ValueError):
            selected_face_indices([[0,1,2]], {0,1,2}, minimum_fraction=0)

    def test_cut_boundary(self):
        f = [[0,1,2],[2,1,3]]
        self.assertEqual(len(face_boundary_edges(f,[0,1])), 4)
        self.assertIn((1,2), face_boundary_edges(f,[0]))
        self.assertNotIn((1,2), face_boundary_edges(f,[0,1]))

    def test_default_never_autocuts(self):
        c = {'target':'firstperson_from_fullbody','source_armature':'rig',
             'parts':[{'source_object':'body','output_object':'fp','min_face_fraction':1}]}
        self.assertGreater(len(extraction_preflight(c, {'body':{}})),0)

    def test_manual_approved_cut(self):
        c = {'target':'firstperson_from_fullbody','source_armature':'rig',
             'parts':[{'source_object':'body','output_object':'fp','min_face_fraction':1,
                       'mask_vertex_groups':['FP_KEEP'], 'approved_shoulder_cut':True}]}
        self.assertEqual(extraction_preflight(c, {'body':{}}), [])

    def test_no_stretch_or_blind_fill(self):
        c = {'target':'firstperson_from_fullbody','source_armature':'rig','auto_rescale_limbs':True,
             'parts':[{'source_object':'body','output_object':'fp','mask_vertex_groups':['x'],
                       'approved_shoulder_cut':True}]}
        self.assertIn('禁止自动拉长四肢或盲目 Fill Holes',extraction_preflight(c,{'body':{}}))

    def test_rigging_must_be_independent(self):
        errors = viewmodel_release_gate({'required':True},extraction={'status':'EXTRACTED_REQUIRES_RIGGING'},
                   audit={'status':'PASS_PRELIMINARY','rig_independent_from_world':False},
                   packaging={'modeldoc_viewmodel_fbx_reference_verified':True,'compiled_viewmodel_present':True})
        self.assertTrue(any('independent' in x or '独立' in x for x in errors))

    def test_player_missing_dual_blocks(self):
        with tempfile.TemporaryDirectory() as temp:
            cfg = Path(temp)/'workflow.json';cfg.write_text('{}',encoding='utf-8')
            errors = inspect_pair(cfg, {'target':'player_runtime','dual_viewmodel':''},{'status':'PASS_PRELIMINARY'})
            self.assertTrue(errors)

    def test_prop_not_required(self):
        with tempfile.TemporaryDirectory() as temp:
            cfg = Path(temp)/'workflow.json'; cfg.write_text('{}',encoding='utf-8')
            self.assertEqual(inspect_pair(cfg, {'target':'prop_preview'},None),[])

    def test_shared_pair_passes_when_fully_pinned(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); (root/'original.blend').write_bytes(b'blend')
            (root/'fp.fbx').write_bytes(b'fbx')
            (root/'agent.vmdl').write_text('vmdl')
            (root/'source.json').write_text(json.dumps({'status':'EXTRACTED_REQUIRES_RIGGING','source_sha256_before':'abc'}))
            (root/'map.json').write_text('{}')
            cfg={'required':True,'source_extraction_report':'source.json','firstperson_blend':'original.blend',
                 'firstperson_bone_map':'map.json','firstperson_blend_sha256':sha256(root/'original.blend'),
                 'firstperson_fbx_sha256':sha256(root/'fp.fbx'),
                 'modeldoc_viewmodel_fbx_reference_verified':True,'packaging_mode':'shared_bodygroup',
                 'bodygroup_verified':True,'ag2_viewmodel_skeleton_verified':True,
                 'firstperson_fbx_relative_path':'models/fp.fbx',
                 'shared_modeldoc_vmdl':'models/agent.vmdl','compiled_shared_model':'models/agent.vmdl_c'}
            (root/'dual.json').write_text(json.dumps(cfg))
            workflow={'target':'player_runtime','dual_viewmodel':'dual.json',
                      'deploy_files':[{'area':'content','relative_path':'models/fp.fbx','source':'fp.fbx'},
                                      {'area':'content','relative_path':'models/agent.vmdl','source':'agent.vmdl'}],
                      'compile_sources':['models/agent.vmdl'],
                      'required_compiled_files':['models/agent.vmdl_c']}
            self.assertEqual(inspect_pair(root/'workflow.json',workflow,{'status':'PASS_PRELIMINARY'}),[])
            (root/'fp.fbx').write_bytes(b'old-fbx')
            self.assertTrue(any('哈希' in msg for msg in inspect_pair(root/'workflow.json',workflow,{'status':'PASS_PRELIMINARY'})))

if __name__ == '__main__':
    unittest.main()
