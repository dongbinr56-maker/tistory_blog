import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class WorkflowSecurityTest(unittest.TestCase):
    def test_dispatch_inputs_are_not_interpolated_into_shell_commands(self):
        workflow = (ROOT / ".github/workflows/daily-tistory-draft.yml").read_text(encoding="utf-8")
        self.assertIn("RUN_DATE: ${{ inputs.run_date }}", workflow)
        self.assertIn("REFRESH_FLAG: ${{ inputs.refresh }}", workflow)
        self.assertIn('args+=(--date "$RUN_DATE")', workflow)
        self.assertIn('python -m tistory_newsroom run "${args[@]}"', workflow)
        self.assertIn('if [ -d data/history ]; then', workflow)
        self.assertNotIn('"${{ inputs.run_date }}"', workflow)
        self.assertNotIn('"${{ inputs.refresh }}"', workflow)
