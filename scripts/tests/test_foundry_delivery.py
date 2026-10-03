"""Preservation transport checks; not additional game/runtime qualification."""
from pathlib import Path
import hashlib
import importlib.util
import io
import json
import tempfile
import unittest
from unittest.mock import patch
import zipfile

SPEC = importlib.util.spec_from_file_location("preservation", Path(__file__).resolve().parents[1] / "preserve_foundry_delivery.py")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class DeliveryTests(unittest.TestCase):
    def test_safe_relative_path(self):
        self.assertEqual(MODULE.safe_name("evidence/native/qualification.json"), "evidence/native/qualification.json")

    def test_unsafe_paths(self):
        for name in ("", "/tmp/file", "../file", "a/../b", "a\\b", "C:file", "a//b", "a/./b"):
            with self.subTest(name=name), self.assertRaises(ValueError):
                MODULE.safe_name(name)

    def test_zip_roundtrip(self):
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, "w") as archive:
            archive.writestr("nested/file.txt", b"retained")
        self.assertEqual(MODULE.read_zip(stream.getvalue()), {"nested/file.txt": b"retained"})

    def test_zip_traversal(self):
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, "w") as archive:
            archive.writestr("../escape.txt", b"refused")
        with self.assertRaises(ValueError):
            MODULE.read_zip(stream.getvalue())

    def test_zip_symlink(self):
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, "w") as archive:
            item = zipfile.ZipInfo("link")
            item.external_attr = 0o120777 << 16
            archive.writestr(item, "target")
        with self.assertRaises(ValueError):
            MODULE.read_zip(stream.getvalue())

    def test_zip_transport_budget(self):
        with self.assertRaises(ValueError):
            MODULE.read_zip(b"x" * 8_000_001)

    def test_overlay_is_bound_before_decompression(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "overlay"
            path.write_bytes(b"changed")
            with patch.object(MODULE.lzma, "LZMADecompressor", side_effect=AssertionError("untrusted decompression")):
                with self.assertRaises(ValueError):
                    MODULE.read_overlay(path)

    def test_input_digest_before_zip_parse(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            first = next(iter(MODULE.ARTIFACTS.values()))[0]
            (root / f"{first}.zip").write_bytes(b"changed")
            with patch.object(MODULE, "read_zip", side_effect=AssertionError("unbound ZIP parsed")):
                with self.assertRaises(ValueError):
                    MODULE.recover(root, root / "overlay")

    def test_replacing_checksum_authority_fails(self):
        with self.assertRaises(ValueError):
            MODULE.verify_entries({"SHA256SUMS.txt": b"replacement inventory"})

    def test_original_fixture_overlay(self):
        overlay = Path(__file__).resolve().parents[2] / "delivery/foundry-v1/local-overlay.tar.xz"
        files = MODULE.read_overlay(overlay)
        self.assertEqual(len(files), 7)
        self.assertEqual(json.loads(files["bundle-manifest.json"])["qualification"]["native_attempts"], 8)

    def test_corrupt_entry_is_not_repaired(self):
        overlay = Path(__file__).resolve().parents[2] / "delivery/foundry-v1/local-overlay.tar.xz"
        files = MODULE.read_overlay(overlay)
        files["SHA256SUMS.txt"] = b"partial inventory"
        with self.assertRaises(ValueError):
            MODULE.verify_entries(files)


if __name__ == "__main__":
    unittest.main()
