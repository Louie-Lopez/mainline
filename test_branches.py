"""Branch isolation and upgrade compatibility; fixtures stay under .test-runs."""

import copy
import json
from pathlib import Path
import subprocess
import sys
import unittest
import uuid
from unittest.mock import patch

import mainline


class BranchTests(unittest.TestCase):
    def setUp(self):
        self.path = Path(__file__).resolve().parent / '.test-runs' / ('branches-' + uuid.uuid4().hex[:8]) / 'state.json'
        self.original = mainline.init_state(self.path, 'branches-test', ['Define', 'Build', 'Try'], mainline='Deliver the agreed project.')
        mainline.status_state(self.path, done=['Define'], active=['Build', 'Try'])
        self.before = mainline.read_state(self.path)

    def create(self, identity='local'):
        return mainline.branch_state(self.path, identity, name=identity.title(), parent='Build',
                                     mainline='Keep the information local.', stages=['Plan', 'Build', 'Try'])

    def mainline_only(self, state):
        return {key: value for key, value in state.items() if key not in {'branches', 'revision', 'updated_at'}}

    def test_old_state_reads_without_rewrite_or_new_fields(self):
        original = self.path.read_bytes()
        mainline.read_state(self.path)
        self.assertEqual(self.path.read_bytes(), original)
        self.assertNotIn('branches', mainline.read_state(self.path))

    def test_branch_creation_and_updates_preserve_mainline_and_other_routes(self):
        self.create()
        both = self.create('cloud')
        result = mainline.status_state(self.path, branch='local', done=['Plan'], active=['Build'], label='Fixing')
        self.assertEqual(self.mainline_only(result), self.mainline_only(self.before))
        self.assertEqual(result['branches']['cloud'], both['branches']['cloud'])
        self.assertEqual(result['branches']['local']['stage_statuses'], ['done', 'active', 'pending'])
        mainline.status_state(self.path, done=['Build'])
        self.assertEqual(mainline.read_state(self.path)['branches'], result['branches'])

    def test_branch_stage_goals_and_substages_stay_inside_route(self):
        self.create()
        mainline.subdivide_state(self.path, 'Build', ['Data', 'View'], current=['View'], branch='local')
        mainline.describe_state(self.path, 'Make the view usable.', stage='View', parent='Build', details='One clear axis.', branch='local')
        result = mainline.status_state(self.path, parent='Build', done=['Data'], active=['View'], label='Fixing', branch='local')
        self.assertNotIn('substages', result)
        route = result['branches']['local']
        self.assertEqual(route['stage_labels']['Build'], 'Fixing')
        self.assertEqual(route['substages']['Build']['stage_mainlines']['View'], 'Make the view usable.')
        self.assertEqual(self.mainline_only(result), self.mainline_only(self.before))

    def test_finished_branch_does_not_complete_parent(self):
        self.create()
        mainline.status_state(self.path, branch='local', done=['Plan', 'Build'], active=['Try'])
        result = mainline.finish_state(self.path, branch='local')
        self.assertEqual(result['branches']['local']['stage_statuses'], ['done'] * 3)
        self.assertEqual(result['stage_statuses'], self.before['stage_statuses'])

    def test_archive_retains_progress_and_requires_restore_for_edits(self):
        created = self.create()
        archived = mainline.branch_state(self.path, 'local', archive=True)
        self.assertEqual({k: v for k, v in archived['branches']['local'].items() if k != 'archived'}, created['branches']['local'])
        before = self.path.read_bytes()
        with self.assertRaises(ValueError):
            mainline.status_state(self.path, branch='local', active=['Build'])
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(mainline.branch_state(self.path, 'local', archive=True), archived)
        restored = mainline.branch_state(self.path, 'local', restore=True)
        self.assertEqual(restored['branches']['local'], created['branches']['local'])

    def test_duplicate_creation_and_unknown_branch_cannot_overwrite(self):
        self.create()
        original = self.path.read_bytes()
        with self.assertRaises(ValueError):
            self.create()
        with self.assertRaises(ValueError):
            mainline.status_state(self.path, branch='missing', done=['Build'])
        self.assertEqual(self.path.read_bytes(), original)

    def test_replan_retains_routes_and_rejects_lost_anchor(self):
        created = self.create()
        mainline.branch_state(self.path, 'local', archive=True)
        original = self.path.read_bytes()
        with self.assertRaises(ValueError):
            mainline.replan_state(self.path, ['New', 'Done'], 'New', 'Scope changed')
        self.assertEqual(self.path.read_bytes(), original)
        result = mainline.replan_state(self.path, ['Define', 'Build', 'Launch'], 'Build', 'Scope changed')
        self.assertEqual(result['branches']['local']['stages'], created['branches']['local']['stages'])
        self.assertTrue(result['branches']['local']['archived'])

    def test_branch_replan_and_reanchor_preserve_other_work(self):
        self.create()
        both = self.create('cloud')
        result = mainline.replan_state(self.path, ['Research', 'Verify'], 'Research', 'Different local approach', branch='local')
        self.assertEqual(result['branches']['cloud'], both['branches']['cloud'])
        self.assertEqual(self.mainline_only(result), self.mainline_only(self.before))
        moved = mainline.branch_state(self.path, 'local', parent='Try', name='Offline route')
        self.assertEqual(moved['branches']['local']['stage_statuses'], ['active', 'pending'])
        self.assertEqual(moved['branches']['local']['parent'], 'Try')

    def test_scoped_noop_does_not_write_or_increment(self):
        self.create()
        original = self.path.read_bytes()
        mainline.position_state(self.path, 'Plan', branch='local')
        self.assertEqual(self.path.read_bytes(), original)

    def test_invalid_and_nested_routes_are_rejected(self):
        created = self.create()
        for patch_data in ({'parent': 'missing'}, {'branches': {}}, {'archived': 'yes'}, {'stage_statuses': ['done']}, {'mainline': 'two\nlines'}):
            state = copy.deepcopy(created)
            state['branches']['local'].update(patch_data)
            with self.subTest(patch=patch_data), self.assertRaises(ValueError):
                mainline.validate_state(state)
        for identity in ('main', '../bad', '', 'two words'):
            with self.assertRaises(ValueError):
                self.create(identity)

    def test_atomic_failure_preserves_all_progress(self):
        self.create()
        original = self.path.read_bytes()
        with patch.object(mainline.os, 'replace', side_effect=OSError('test failure')):
            with self.assertRaises(OSError):
                mainline.status_state(self.path, branch='local', active=['Build'])
        self.assertEqual(self.path.read_bytes(), original)

    def test_cli_reads_only_requested_route(self):
        self.create()
        self.create('cloud')
        result = subprocess.run([sys.executable, str(Path(mainline.__file__)), 'read', '--state', str(self.path), '--branch', 'local'], capture_output=True, encoding='utf-8', check=True)
        route = json.loads(result.stdout)
        self.assertEqual(route['branch'], 'local')
        self.assertNotIn('branches', route)
        self.assertNotIn('cloud', result.stdout)

    def test_overview_contains_index_without_branch_contents(self):
        root = self.create()
        overview = mainline.overview_state(root)
        self.assertNotIn('branches', overview)
        self.assertEqual(overview['branch_index'], {'local': {'name': 'Local', 'parent': 'Build'}})
        self.assertEqual(overview['stage_statuses'], root['stage_statuses'])
        self.assertNotIn('Keep the information local.', json.dumps(overview))


if __name__ == '__main__':
    unittest.main()
