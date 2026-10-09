import unittest
from pathlib import Path

import yaml


class WorkflowYamlTest(unittest.TestCase):
    def test_on_trigger_is_string_key(self):
        workflow = yaml.safe_load(Path('.github/workflows/blank.yml').read_text())

        self.assertIn('on', workflow)
        self.assertIsInstance(workflow['on'], dict)


if __name__ == '__main__':
    unittest.main()
