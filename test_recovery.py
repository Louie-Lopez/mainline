"""Recovery uses the remembered address without changing project progress."""

import json
import os
import signal
import subprocess
import sys
from pathlib import Path
import unittest
from unittest.mock import patch

import mainline
import test_mainline


class RecoveryTests(unittest.TestCase):
    setUp = test_mainline.MainlineTests.setUp

    def remember(self, url):
        mainline.atomic_json(mainline.runtime_path(self.path), {
            "pid": 1, "state_path": str(self.path), "url": url,
        })

    def test_closed_service_recovers_its_address_without_changing_state(self):
        original = self.path.read_bytes()
        first = mainline.make_server(self.path)
        port = first.server_port
        self.remember(f"http://127.0.0.1:{port}")
        first.server_close()
        resumed = mainline.resume_server(self.path)
        try:
            self.assertEqual(resumed.server_port, port)
            self.assertEqual(self.path.read_bytes(), original)
        finally:
            resumed.server_close()

    def test_occupied_remembered_port_falls_back_but_explicit_port_is_strict(self):
        occupied = mainline.make_server(self.path)
        self.remember(f"http://127.0.0.1:{occupied.server_port}")
        try:
            resumed = mainline.resume_server(self.path)
            try:
                self.assertNotEqual(resumed.server_port, occupied.server_port)
            finally:
                resumed.server_close()
            with self.assertRaises(OSError):
                mainline.resume_server(self.path, occupied.server_port)
        finally:
            occupied.server_close()

    def test_untrusted_runtime_does_not_supply_an_address(self):
        for url in ('https://127.0.0.1:8090', 'http://example.com:8090',
                    'http://127.0.0.1:8090/other', 'http://user@127.0.0.1:8090',
                    'http://127.0.0.1:8090?query', 'http://127.0.0.1:99999'):
            self.remember(url)
            self.assertIsNone(mainline.recorded_runtime(self.path))
        self.remember('http://127.0.0.1:8090')
        record = mainline.recorded_runtime(self.path)
        record['state_path'] = str(self.path.parent / 'other.json')
        mainline.atomic_json(mainline.runtime_path(self.path), record)
        self.assertIsNone(mainline.recorded_runtime(self.path))

    def event(self, **changes):
        return {"hook_event_name": "SessionStart", "source": "resume",
                "session_id": "known", "cwd": str(self.directory), **changes}

    def test_binding_resumes_without_progress_changes_and_skips_other_events(self):
        original = self.path.read_bytes()
        mainline.bind_session(self.path, "known")
        with patch.object(mainline, "start", return_value={"url": "http://127.0.0.1:1234"}) as start:
            result = mainline.recover_session(self.event())
            self.assertIn("http://127.0.0.1:1234", result['hookSpecificOutput']['additionalContext'])
            self.assertEqual(start.call_count, 1)
            for changes in ({"session_id": "unknown"}, {"source": "compact"},
                            {"source": "fork"}, {"agent_id": "child"},
                            {"cwd": str(self.directory.parent)}, {"cwd": "relative"},
                            {"session_id": "../known"}, {"hook_event_name": "UserPromptSubmit"}):
                self.assertIsNone(mainline.recover_session(self.event(**changes)))
            self.assertEqual(start.call_count, 1)
        self.assertEqual(self.path.read_bytes(), original)

    def test_existing_standard_path_and_subdirectory_need_no_registration(self):
        state = self.directory / '.mainline' / 'known' / 'state.json'
        mainline.init_state(state, 'known', self.stages)
        nested = self.directory / 'src'
        nested.mkdir()
        self.assertEqual(mainline.session_state(self.event(cwd=str(nested))), state)
        self.assertIsNone(mainline.session_state(self.event(session_id='new-chat')))

    def test_each_conversation_selects_its_bound_project(self):
        other = self.directory / '.mainline' / 'second' / 'state.json'
        mainline.init_state(other, 'second-project', self.stages)
        mainline.bind_session(self.path, 'first-chat')
        mainline.bind_session(other, 'second-chat')
        mainline.bind_session(self.path, 'third-chat')
        self.assertEqual(mainline.session_state(self.event(session_id='first-chat')), self.path)
        self.assertEqual(mainline.session_state(self.event(session_id='second-chat')), other)
        self.assertEqual(mainline.session_state(self.event(session_id='third-chat')), self.path)

    def test_binding_outside_workspace_or_changed_identity_is_rejected(self):
        mainline.bind_session(self.path, 'known')
        binding = self.directory / '.mainline' / 'sessions' / 'known.json'
        data = json.loads(binding.read_text(encoding='utf-8'))
        data['task_id'] = 'wrong-project'
        mainline.atomic_json(binding, data)
        self.assertIsNone(mainline.session_state(self.event()))
        data['state_path'] = str(self.directory.parent / 'other.json')
        mainline.atomic_json(binding, data)
        self.assertIsNone(mainline.session_state(self.event()))

    def test_rebinding_is_idempotent_and_rejects_path_traversal(self):
        mainline.bind_session(self.path, 'known')
        binding = self.directory / '.mainline' / 'sessions' / 'known.json'
        before = binding.stat().st_mtime_ns
        mainline.bind_session(self.path, 'known')
        self.assertEqual(binding.stat().st_mtime_ns, before)
        with self.assertRaises(ValueError):
            mainline.bind_session(self.path, '../escape')

    def test_bad_hook_input_does_not_block_conversation(self):
        cli = [sys.executable, str(Path(mainline.__file__)), 'recover']
        for payload in ('invalid json', '{}', '[]', '{"hook_event_name":"SessionStart"}'):
            result = subprocess.run(cli, input=payload, text=True, capture_output=True)
            self.assertEqual(result.returncode, 0)
            self.assertEqual(result.stdout, '')

    def test_install_hook_preserves_other_hooks_encoding_and_is_idempotent(self):
        home = self.directory / 'codex-home'
        home.mkdir()
        path = home / 'hooks.json'
        other = {'matcher': 'startup', 'hooks': [{'type': 'command', 'command': 'echo unrelated'}]}
        original = {'description': '用户的设置', 'hooks': {'SessionStart': [other], 'Stop': []}}
        raw = (json.dumps(original, ensure_ascii=False, indent=2) + '\n').replace('\n', '\r\n').encode('utf-8-sig')
        path.write_bytes(raw)
        result = mainline.install_recovery_hook(str(home))
        self.assertTrue(result['changed'])
        self.assertTrue(path.read_bytes().startswith(b'\xef\xbb\xbf'))
        self.assertIn(b'\r\n', path.read_bytes())
        saved = json.loads(path.read_text(encoding='utf-8-sig'))
        self.assertEqual(saved['hooks']['SessionStart'][0], other)
        self.assertEqual(saved['hooks']['Stop'], [])
        self.assertEqual(len(saved['hooks']['SessionStart']), 2)
        self.assertEqual(next(home.glob('hooks.mainline-backup-*.json')).read_bytes(), raw)
        before = path.read_bytes()
        self.assertFalse(mainline.install_recovery_hook(str(home))['changed'])
        self.assertEqual(path.read_bytes(), before)

    def test_install_hook_rejects_invalid_existing_configuration(self):
        home = self.directory / 'codex-home'
        home.mkdir()
        path = home / 'hooks.json'
        path.write_text('[]', encoding='utf-8')
        with self.assertRaises(ValueError):
            mainline.install_recovery_hook(str(home))
        self.assertEqual(path.read_text(encoding='utf-8'), '[]')

    def test_concurrent_launches_share_one_service(self):
        cli = [sys.executable, str(Path(mainline.__file__)), 'start', '--state', str(self.path), '--session-id', 'parallel']
        children = [subprocess.Popen(cli, stdout=subprocess.PIPE, stderr=subprocess.PIPE) for _ in range(2)]
        runtime = None
        try:
            results = []
            for child in children:
                out, err = child.communicate(timeout=15)
                self.assertEqual(child.returncode, 0, err)
                results.append(json.loads(out))
            runtime = results[0]
            self.assertEqual(results[0]['pid'], results[1]['pid'])
            self.assertEqual(sum(x['reused'] for x in results), 1)
        finally:
            if runtime and mainline.discover(self.path, '测试任务')['pid'] == runtime['pid']:
                os.kill(runtime['pid'], signal.SIGTERM)


if __name__ == '__main__':
    unittest.main()
