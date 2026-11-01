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

    def test_two_year_snake_runs_before_one_year_and_cannot_break_it(self):
        steps = load_workflow()['jobs']['generate']['steps']
        names = [step.get('name', '') for step in steps]
        two_year = next(s for s in steps if 'two-year-snake' in s.get('run', ''))

        # A failure in the extra 2-year step must not stop the 1-year deploy.
        self.assertTrue(two_year.get('continue-on-error'))
        # Runs first so `dist/` is created by the runner user, not the
        # root-owned docker action that generates the 1-year snake.
        self.assertLess(
            steps.index(two_year),
            names.index('Generate GitHub Contributions Snake Animations'),
        )
        self.assertIn('Deploy to Output Branch', names)
        self.assertEqual(two_year['env']['GITHUB_TOKEN'], '${{ secrets.GITHUB_TOKEN }}')

    def test_two_year_snake_uses_pinned_snk_checkout_and_bun(self):
        steps = load_workflow()['jobs']['generate']['steps']
        snk = next(
            s for s in steps
            if s.get('with', {}).get('repository') == 'Platane/snk'
        )
        bun = next(s for s in steps if s.get('uses', '').startswith('oven-sh/setup-bun@'))

        self.assertRegex(snk['with']['ref'], r'^v\d+\.\d+\.\d+$')
        self.assertRegex(bun['with']['bun-version'], r'^\d+\.\d+\.\d+$')

    def test_two_year_script_fetches_two_windows_of_at_most_a_year(self):
        script = Path('scripts/two-year-snake.ts').read_text()

        # GitHub rejects contributionsCollection ranges longer than one year.
        self.assertIn('contributionsCollection(from: $from, to: $to)', script)
        self.assertIn('WINDOW_DAYS = 365', script)
        self.assertIn('windows', script)
        for output in ('github-snake-2y.svg', 'github-snake-2y-dark.svg'):
            self.assertIn(output, script)

    def test_runs_do_not_overlap(self):
        workflow = load_workflow()

        self.assertIn('group', workflow['concurrency'])
        self.assertFalse(workflow['concurrency']['cancel-in-progress'])


if __name__ == '__main__':
    unittest.main()
