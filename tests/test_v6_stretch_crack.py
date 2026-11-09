"""Pure math and gates, plus v6 safety checks with no Blender required."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from mesh_gap_math import seam_drift, scale_spread, relative_length
from auto_workflow_core import gate_source_report


class V6Tests(unittest.TestCase):
    def test_seam_closed_and_moving_together(self):
        result=seam_drift((0,0,0),(0.0001,0,0),(5,2,0),(5.0001,2,0),max_gap=.001,max_increase=.0003)
        self.assertFalse(result['failed'])

    def test_dynamic_seam_opens(self):
        result=seam_drift((0,0,0),(0.0001,0,0),(5,2,0),(5.03,2,0),max_gap=.001,max_increase=.0003)
        self.assertTrue(result['failed'])
        self.assertAlmostEqual(result['gap_increase'],0.0299)

    def test_intentional_open_gap_no_change(self):
        result=seam_drift((0,0,0),(0.03,0,0),(0,0,0),(0.03,0,0),max_gap=.001,max_increase=.001)
        self.assertFalse(result['failed'])

    def test_invalid_thresholds_rejected(self):
        with self.assertRaises(ValueError):
            seam_drift((0,0,0),(1,0,0),(0,0,0),(2,0,0),max_gap=0,max_increase=0)

    def test_uniform_global_scale_permitted(self):
        self.assertAlmostEqual(scale_spread((1.25,1.25,1.25)),0)
        self.assertGreater(scale_spread((1,1.5,1)),0.1)

    def test_bone_length_check(self):
        self.assertAlmostEqual(relative_length(1,1.2),.2)
        self.assertEqual(relative_length(0,1),float('inf'))

    def source(self):
        return {'status':'PASS_PRELIMINARY','findings':{'errors':[]},'checks':{
            'bounding_boxes':{'static_comparison':{'status':'PASS'},'dynamic_comparison':{'status':'PASS'}},
            'source_proportions':{'status':'PASS'},'accessories':{'status':'PASS_PRELIMINARY'},
            'joint_deformation':{'status':'PASS_PRELIMINARY'},
            'mesh_integrity':{'status':'PASS_PRELIMINARY'},'rig_stretch':{'status':'PASS_PRELIMINARY'},
            'reference_rest_pose':'USER_ATTESTED','animation_suite':{'status':'PENDING_RUNTIME'}}}

    def test_player_passes_when_both_v6_checks_pass(self):
        self.assertEqual(gate_source_report(self.source(),'player_runtime'),[])

    def test_dynamic_crack_blocks_deploy(self):
        r=self.source()
        r['checks']['mesh_integrity']['status']='FAIL'
        self.assertIn('网格',str(gate_source_report(r,'player_runtime')))

    def test_pose_stretch_pending_blocks_deploy(self):
        r=self.source()
        r['checks']['rig_stretch']['status']='PENDING_REVIEW'
        self.assertIn('骨骼',str(gate_source_report(r,'player_runtime')))

    def test_missing_mesh_integrity_blocks_player(self):
        r=self.source()
        del r['checks']['mesh_integrity']
        self.assertTrue(gate_source_report(r,'player_runtime'))

    def test_prop_preview_failure_still_blocks(self):
        r=self.source()
        r['checks']['mesh_integrity']['status']='FAIL'
        self.assertTrue(gate_source_report(r,'prop_preview'))

if __name__=='__main__':unittest.main()
