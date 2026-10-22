# ruff: noqa: INP001
import importlib.util
import pathlib
import unittest

spec = importlib.util.spec_from_file_location(
    "publish",
    pathlib.Path(__file__).with_name("publish_lavida.py"),
)
publish = importlib.util.module_from_spec(spec)
spec.loader.exec_module(publish)


class StableVersionTests(unittest.TestCase):
    def test_numeric_order(self):
        self.assertGreater(
            publish.version("3.3.3-lavida.1"),
            publish.version("2.20.15-lavida.1"),
        )
        self.assertGreater(
            publish.version("2.20.15-lavida.1"),
            publish.version("2.7.2-lavida.1"),
        )
        self.assertGreater(
            publish.version("v3.3.3-lavida.10"),
            publish.version("3.3.3-lavida.2"),
        )

    def test_only_stable_versions(self):
        for value in [
            "main",
            "latest",
            "3.3.3",
            "3.3.3-lavida.1-rc.1",
            "3.3.3-lavida-asn-candidate-123",
            "v3.3.3-lavida.1\n",
        ]:
            with self.assertRaises(ValueError):
                publish.version(value)


if __name__ == "__main__":
    unittest.main()
