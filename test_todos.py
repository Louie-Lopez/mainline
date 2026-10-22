"""Explicit reminders stay separate from lifecycle progress and concurrent edits."""
import copy
import json
import subprocess
import sys
import unittest
from urllib.error import HTTPError
from urllib.request import Request

import mainline
import test_mainline
from test_mainline import running, get, urlopen


class TodoTests(unittest.TestCase):
    setUp = test_mainline.MainlineTests.setUp

    def add(self, **kwargs):
        return mainline.todo_state(self.path, '实现', add=['检查另一个项目'], **kwargs)

    def item(self, state):
        return state['stage_todos']['实现']['items'][0]

    def test_opt_in_and_completion_never_changes_lifecycle(self):
        before = self.path.read_bytes()
        self.assertNotIn('stage_todos', mainline.read_state(self.path))
        with self.assertRaises(ValueError):
            mainline.todo_state(self.path, '实现')
        self.assertEqual(self.path.read_bytes(), before)
        saved = self.add()
        for key in ('stages', 'stage_statuses'):
            self.assertEqual(saved[key], self.state[key])
        done = mainline.todo_state(self.path, '实现', done=[self.item(saved)['id']])
        self.assertTrue(self.item(done)['done'])
        self.assertEqual(done['stage_statuses'], self.state['stage_statuses'])
        reopened = mainline.todo_state(self.path, '实现', pending=[self.item(saved)['id']])
        self.assertFalse(self.item(reopened)['done'])
        self.assertEqual(mainline.todo_state(self.path, '实现', pending=[self.item(saved)['id']]), reopened)
        finished = mainline.status_state(self.path, done=self.stages)
        self.assertFalse(self.item(finished)['done'])

    def test_branches_and_substages_have_independent_reminders(self):
        self.add()
        mainline.subdivide_state(self.path, '实现', ['接口', '页面'])
        mainline.todo_state(self.path, '页面', parent='实现', add=['核对小窗口'], ordered=True)
        mainline.branch_state(self.path, 'local', name='本地', parent='实现', mainline='本地处理', stages=['实现'])
        state = self.add(branch='local')
        branch_id = state['branches']['local']['stage_todos']['实现']['items'][0]['id']
        changed = mainline.todo_state(self.path, '实现', branch='local', done=[branch_id])
        self.assertFalse(self.item(changed)['done'])
        self.assertTrue(changed['substages']['实现']['stage_todos']['页面']['ordered'])
        self.assertEqual(changed['stage_statuses'], state['stage_statuses'])
        self.assertEqual(changed['branches']['local']['stage_statuses'], state['branches']['local']['stage_statuses'])

    def test_validation_and_replanning_preserve_reminders(self):
        saved = self.add()
        original = self.path.read_bytes()
        for kwargs in ({'done': ['unknown']}, {'add': ['a\nb']}, {'add': ['x'*501]}):
            with self.assertRaises(ValueError):
                mainline.todo_state(self.path, '实现', **kwargs)
            self.assertEqual(self.path.read_bytes(), original)
        with self.assertRaises(ValueError):
            mainline.replan_state(self.path, ['新阶段'], ['新阶段'], 'New scope')
        state = mainline.replan_state(self.path, ['实现', '交付'], ['实现'], 'New scope')
        self.assertEqual(state['stage_todos'], saved['stage_todos'])
        mainline.subdivide_state(self.path, '实现', ['接口', '页面'])
        mainline.todo_state(self.path, '页面', parent='实现', add=['保留提醒'])
        original = self.path.read_bytes()
        with self.assertRaises(ValueError):
            mainline.subdivide_state(self.path, '实现', ['接口'], reason='Change scope')
        self.assertEqual(self.path.read_bytes(), original)

    def test_stale_writers_cannot_overwrite_progress(self):
        saved = self.add()
        latest = mainline.status_state(self.path, done=['确定方案'], active=['实现'])
        with self.assertRaises(mainline.StateConflict):
            mainline.todo_state(self.path, '实现', done=[self.item(saved)['id']], revision=saved['revision'])
        changed = copy.deepcopy(saved)
        changed['stage_statuses'][0] = 'done'
        with self.assertRaises(mainline.StateConflict):
            mainline.commit_state(self.path, saved, changed)
        self.assertEqual(mainline.read_state(self.path), latest)

    def test_cli_supports_explicit_ordered_addition_and_reopening(self):
        script = str(mainline.Path(mainline.__file__))
        command = [sys.executable, script, 'todo', '--state', str(self.path), '--stage', '实现']
        result = subprocess.run(command + ['--ordered', '--add', '先核对', '--add', '再验证'], capture_output=True, encoding='utf-8')
        self.assertEqual(result.returncode, 0, result.stderr)
        saved = json.loads(result.stdout)
        self.assertTrue(saved['stage_todos']['实现']['ordered'])
        self.assertEqual([i['text'] for i in saved['stage_todos']['实现']['items']], ['先核对', '再验证'])

    def test_http_allows_only_authenticated_existing_item_toggles(self):
        saved = self.add()
        with running(self.path) as url:
            token = get(url + '/todo-token')[0]['token']
            payload = {'stage': '实现', 'parent': None, 'branch': None, 'id': self.item(saved)['id'], 'done': True, 'revision': saved['revision']}
            headers = {'Origin': url, 'Content-Type': 'application/json', 'X-Mainline-Token': token}
            def post(body, supplied=None, method='POST'):
                request = Request(url + '/todo', data=json.dumps(body).encode(), headers=headers if supplied is None else supplied, method=method)
                with urlopen(request, timeout=3) as response:
                    return json.load(response)
            changed = post(payload)['state']
            self.assertTrue(self.item(changed)['done'])
            self.assertEqual(changed['stage_statuses'], saved['stage_statuses'])
            with self.assertRaises(HTTPError) as caught:
                post(payload)
            self.assertEqual(caught.exception.code, 409)
            for altered in ({**headers, 'X-Mainline-Token': 'invalid'}, {**headers, 'Origin': 'https://other.test'}):
                with self.assertRaises(HTTPError) as caught:
                    post(payload, altered)
                self.assertEqual(caught.exception.code, 403)
            with self.assertRaises(HTTPError) as caught:
                post({**payload, 'add': 'unrequested item'})
            self.assertEqual(caught.exception.code, 400)
            with self.assertRaises(HTTPError) as caught:
                post(payload, method='PUT')
            self.assertEqual(caught.exception.code, 405)
            self.assertEqual(mainline.read_state(self.path), changed)


if __name__ == '__main__':
    unittest.main()
