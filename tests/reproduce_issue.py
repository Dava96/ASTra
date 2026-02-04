import unittest

from astra.core.template_manager import TemplateManager


class TestTemplateContext(unittest.TestCase):
    def test_planning_template_includes_context(self):
        tm = TemplateManager()
        context_data = "CRITICAL_CONTEXT_DATA_FOR_PLANNING"
        rendered = tm.render("planning_feature", request="Test Task", context=context_data)

        print(f"\nRendered Template:\n{rendered}\n")

        self.assertIn(context_data, rendered, "The 'context' variable was not rendered in the template!")

if __name__ == "__main__":
    unittest.main()
