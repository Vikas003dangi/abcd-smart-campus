import os
import subprocess
from django.test import TestCase, SimpleTestCase
from django.template.loader import render_to_string
from django.conf import settings


class ThemeAndTWATest(TestCase):
    """
    Test suite for ABCD Web theme synchronization, flash prevention,
    and Android TWA long-press menu suppression.
    """

    ROOT_TEMPLATES = [
        "home_page.html",
        "users/teacher_dashboard.html",
        "users/student_dashboard.html",
        "users/admission_form.html",
        "users/register.html",
        "users/fee_calendar.html",
        "users/library_availability.html",
        "users/teacher_seat_status.html",
        "users/your_seat_status.html",
        "404.html",
        "500.html",
    ]

    def test_all_base_templates_have_early_head_theme_elements(self):
        """
        Verify that every base template defines the required:
        1. <meta name="color-scheme">
        2. <meta name="theme-color"> (with light/dark media queries)
        3. Inline <style id="abcd-early-theme-style"> for zero-flash paint
        4. Early blocking script reading localStorage.getItem('theme') before first CSS
        5. Inclusion of abcd-theme.js
        """
        for tpl_name in self.ROOT_TEMPLATES:
            # Locate file on disk
            found = False
            for tpl_dir in settings.TEMPLATES[0]["DIRS"]:
                full_path = os.path.join(tpl_dir, tpl_name)
                if os.path.exists(full_path):
                    with open(full_path, "r", encoding="utf-8") as f:
                        content = f.read()
                    found = True
                    break

            if not found:
                # Check app templates directory
                full_path = os.path.join(settings.BASE_DIR, "users", "templates", tpl_name)
                if os.path.exists(full_path):
                    with open(full_path, "r", encoding="utf-8") as f:
                        content = f.read()
                    found = True

            self.assertTrue(found, f"Template {tpl_name} could not be located on disk.")

            # Assertions
            self.assertIn(
                'name="color-scheme"',
                content,
                f"{tpl_name} missing <meta name=\"color-scheme\">"
            )
            self.assertIn(
                'name="theme-color"',
                content,
                f"{tpl_name} missing <meta name=\"theme-color\">"
            )
            self.assertIn(
                'id="abcd-early-theme-style"',
                content,
                f"{tpl_name} missing <style id=\"abcd-early-theme-style\">"
            )
            self.assertIn(
                "localStorage.getItem('theme')",
                content,
                f"{tpl_name} missing early script reading localStorage.getItem('theme')"
            )
            self.assertIn(
                "abcd-theme.js",
                content,
                f"{tpl_name} missing inclusion of abcd-theme.js"
            )

    def test_master_loader_supports_early_theme_classes_and_events(self):
        """Verify partials/_master_loader.html supports dark theme classes and listens to abcd-theme-change."""
        loader_path = os.path.join(settings.BASE_DIR, "users", "templates", "partials", "_master_loader.html")
        self.assertTrue(os.path.exists(loader_path))
        with open(loader_path, "r", encoding="utf-8") as f:
            content = f.read()

        self.assertIn("html.dark-theme .master-loader-overlay", content)
        self.assertIn("abcd-theme-change", content)

    def test_custom_popup_has_dark_mode_and_callout_suppression(self):
        """Verify custom-popup.css has html.dark-theme styles and -webkit-touch-callout: none."""
        popup_css_path = os.path.join(settings.BASE_DIR, "static", "css", "custom-popup.css")
        self.assertTrue(os.path.exists(popup_css_path))
        with open(popup_css_path, "r", encoding="utf-8") as f:
            content = f.read()

        self.assertIn("-webkit-touch-callout: none", content)
        self.assertIn("html.dark-theme .custom-popup", content)
        self.assertIn("[data-theme=\"dark\"] .custom-popup", content)

    def test_node_stub_tests_execution(self):
        """Run the Node.js stub test to verify abcdToggleTheme and contextmenu guard logic in a DOM environment."""
        node_script = os.path.join(settings.BASE_DIR, "static", "js", "tests_theme_stub.js")
        self.assertTrue(os.path.exists(node_script))

        res = subprocess.run(
            ["node", node_script],
            capture_output=True,
            text=True,
            cwd=settings.BASE_DIR
        )
        self.assertEqual(res.returncode, 0, f"Node tests failed: {res.stderr}\n{res.stdout}")
        self.assertIn("ALL NODE STUB TESTS PASSED SUCCESSFULLY!", res.stdout)
