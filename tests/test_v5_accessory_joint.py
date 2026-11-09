import sys
import json
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from accessory_core import validated_config
from deformation_metrics import compare_region
from issue_triage import build_triage
from auto_workflow_core import gate_source_report
from game_qa_core import validate_test_config
from game_evidence_merge import merge


def part(mode='secondary_baked', approved=True):
    bones=[{'name':'acc_hair1','head':[0,0,0],'tail':[0,0,1]},
           {'name':'acc_hair2','head':[0,0,1],'tail':[0,0,2]}]
    return {'id':'hair','mode':mode,'anchor_bone':'head_0','mesh_objects':['Hair'],
            'rest_positions_approved':approved,'weight_mode':'manual','bones':bones}


class V5Tests(unittest.TestCase):
    def test_accessory_chain_passes_structure(self):
        a=validated_config({'accessories':[part()]})
        self.assertEqual(len(a['accessories'][0]['bones']),2)

    def test_unlisted_accessories_require_confirmation(self):
        with self.assertRaises(ValueError):validated_config({'accessories':[]})
        validated_config({'accessories':[],'no_accessories_confirmed':True})

    def test_no_rigid_two_bone_setup(self):
        with self.assertRaises(ValueError):validated_config({'accessories':[part(mode='rigid')]})

    def test_reject_guessed_auto_soft_weights(self):
        a=part();a['weight_mode']='rigid_auto';a['allow_replace_weights']=True
        with self.assertRaises(ValueError):validated_config({'accessories':[a]})

    def test_reject_unapproved_auto_rigid_replacement(self):
        a=part(mode='rigid');a['bones']=a['bones'][:1]
        a['weight_mode']='rigid_auto'
        with self.assertRaises(ValueError):validated_config({'accessories':[a]})

    def test_approved_auto_soft_skinning(self):
        a=part();a['weight_mode']='chain_linear_auto';a['allow_replace_weights']=True
        with self.assertRaises(ValueError):validated_config({'accessories':[a]})
        a['approved_chain_skinning']=True
        self.assertEqual(len(validated_config({'accessories':[a]})['accessories']),1)

    def test_reject_same_mesh_claimed_twice(self):
        b=part();b['id']='extra';b['bones'][0]['name']='acc_hair3';b['bones'][1]['name']='acc_hair4'
        with self.assertRaises(ValueError):validated_config({'accessories':[part(),b]})

    def test_no_deformation_shape_changed(self):
        xyz=[(0,0,0),(1,0,0),(0,1,0)]
        z=[(0,1,0),(1,1,0),(0,2,0)]
        res=compare_region(xyz,z,[(0,1),(1,2),(2,0)],[(0,1,2)])
        self.assertEqual(res['status'],'PASS_PRELIMINARY')

    def test_joint_edge_stretch_triggered(self):
        xyz=[(0,0,0),(1,0,0),(0,1,0)]
        deformed=[(0,0,0),(2,0,0),(0,1,0)]
        res=compare_region(xyz,deformed,[(0,1),(1,2),(2,0)],[(0,1,2)])
        self.assertEqual(res['status'],'FAIL')
        self.assertEqual(res['samples'][0]['vertices'],[0,1])

    def test_joint_area_collapse_triggered(self):
        xyz=[(0,0,0),(1,0,0),(0,1,0)]
        deformed=[(0,0,0),(1,0,0),(0,0.1,0)]
        res=compare_region(xyz,deformed,[],[(0,1,2)])
        self.assertEqual(res['status'],'FAIL')

    def test_topology_mismatch_does_not_pass(self):
        self.assertEqual(compare_region([(0,0,0)],[],[],[])['status'],'PENDING_TOPOLOGY_CHANGED')

    def test_gate_blocks_missing_joint_or_accessory(self):
        report={'status':'PASS_PRELIMINARY','checks':{
            'source_height':{'status':'PASS','selection_confirmed':True},
            'source_proportions':{'status':'PASS'},'reference_rest_pose':'USER_ATTESTED',
            'animation_suite':{'status':'PENDING_RUNTIME'},
            'bounding_boxes':{'static_comparison':{'status':'PASS'},'dynamic_comparison':{'status':'PASS'}},
            'joint_deformation':{'status':'PENDING'},'accessories':{'status':'PENDING'},
            'mesh_integrity':{'status':'PASS_PRELIMINARY'},'rig_stretch':{'status':'PASS_PRELIMINARY'}}}
        self.assertIn('装饰物',''.join(gate_source_report(report,'player_runtime')))
        report['checks']['accessories']['status']='PASS_PRELIMINARY'
        report['checks']['joint_deformation']['status']='PASS_PRELIMINARY'
        self.assertEqual(gate_source_report(report,'player_runtime'),[])

    def test_multiphase_capture_is_bounded(self):
        cfg={'enabled':True,'server_endpoint':'127.0.0.1:27015','model_name':'test_character',
             'readiness':{'strategy':'image_template','image_path':'ready.png'},
             'steps':[{'id':'running','action':'run','view':'thirdperson','seconds':1.2,'captures':3}]}
        self.assertEqual(validate_test_config(cfg)['steps'][0]['captures'],3)
        cfg['steps'][0]['captures']=4
        with self.assertRaises(ValueError):validate_test_config(cfg)

    def test_runtime_accessory_and_joint_images_stay_pending(self):
        report={'model_name':'test_character','test_results':[{'id':'run','action':'run','view':'thirdperson',
               'screenshot':'run.png','sequence_screenshots':['run-1.png','run-2.png','run.png']}]}
        merged=merge(report,{'target':'player_runtime','tests':{}})
        self.assertEqual(merged['tests']['accessory_motion_live']['status'],'PENDING')
        self.assertEqual(merged['tests']['joint_deformation_live']['status'],'PENDING')
        self.assertIn('run-1.png',merged['tests']['accessory_motion_live']['evidence'])

    def test_triage_identifies_joint_as_manual(self):
        audit={'checks':{'joint_deformation':{'status':'FAIL'},'accessories':{'status':'PASS_PRELIMINARY'}},
               'findings':{'errors':[{'code':'JOINT_DEFORMATION','message':'elbow collapse'}],
                           'warnings':[{'code':'WEIGHT_SUM','message':'normalization'}]}}
        r=build_triage(audit)
        self.assertEqual(r['status'],'FAIL')
        self.assertFalse(r['items'][0]['auto_fix_allowed'])
        self.assertTrue(any(x['auto_fix_allowed'] for x in r['items']))

if __name__=='__main__':unittest.main()
