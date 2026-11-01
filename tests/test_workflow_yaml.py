import unittest
from pathlib import Path

import yaml

WORKFLOW_PATH = Path('.github/workflows/snake.yml')


def load_workflow():
    return yaml.safe_load(WORKFLOW_PATH.read_text())


class WorkflowYamlTest(unittest.TestCase):
    def test_workflow_file_is_named_descriptively(self):
        self.assertTrue(WORKFLOW_PATH.exists())
        self.assertFalse(Path('.github/workflows/blank.yml').exists())

    def test_on_trigger_is_string_key(self):
        workflow = load_workflow()

        self.assertIn('on', workflow)
        self.assertIsInstance(workflow['on'], dict)
        for trigger in ('schedule', 'workflow_dispatch', 'push'):
            self.assertIn(trigger, workflow['on'])

    def test_no_commented_out_legacy_workflow(self):
        commented_yaml = [
            line for line in WORKFLOW_PATH.read_text().splitlines()
            if line.startswith('# ') and ('uses:' in line or 'runs-on:' in line)
        ]

        self.assertEqual(commented_yaml, [])

    def test_check_job_sets_the_output_the_generate_job_reads(self):
        # Regression: the script used to `return` an object, which sets the
        # step output `result`, so `has_contributions` was never set and the
        # `generate` job was always skipped.
        workflow = load_workflow()
        check = workflow['jobs']['check-contributions']
        script = next(
            step['with']['script'] for step in check['steps'] if step.get('id') == 'check'
        )

        self.assertIn("core.setOutput('has_contributions'", script)
        self.assertNotIn('return {', script)
        self.assertEqual(
            check['outputs']['has_contributions'],
            '${{ steps.check.outputs.has_contributions }}',
        )
        self.assertIn('has_contributions', workflow['jobs']['generate']['if'])

    def test_contribution_query_is_retried(self):
        workflow = load_workflow()
        script = next(
            step['with']['script']
            for step in workflow['jobs']['check-contributions']['steps']
            if step.get('id') == 'check'
        )

        self.assertIn('maxAttempts', script)
        self.assertIn('catch', script)

    def test_permissions_are_least_privilege(self):
        workflow = load_workflow()

        self.assertEqual(workflow['permissions'], {'contents': 'read'})
        self.assertEqual(
            workflow['jobs']['generate']['permissions'], {'contents': 'write'}
        )

    def test_runs_do_not_overlap(self):
        workflow = load_workflow()

        self.assertIn('group', workflow['concurrency'])
        self.assertFalse(workflow['concurrency']['cancel-in-progress'])


if __name__ == '__main__':
    unittest.main()
