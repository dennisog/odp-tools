#!/usr/bin/env python3

import sys
import tempfile
import subprocess
import unittest
import shutil
from pathlib import Path
from argparse import Namespace

import pdfrw

DIR = Path(__file__).absolute().parent
sys.path.append(str(DIR.parent / "odp_tools"))

from pages import PageDropper


class TestPageDropper(unittest.TestCase):
    def test_find_verapdf(self):
        vera = shutil.which("verapdf")
        self.assertNotEqual(vera, None)

    def test_page_dropper(self):
        print("")
        sample_path = DIR / "samples" / "drop.pdf"
        with tempfile.TemporaryDirectory() as tempdir:
            pdf_path = Path(tempdir) / "sample.pdf"
            old_path = Path(tempdir) / "sample.pdf.orig"
            shutil.copyfile(sample_path, pdf_path)
            options = Namespace()
            options.filename = [str(pdf_path)]
            options.keep_original = True
            options.write_metadata = True
            options.pages = [2]
            pagedropper = PageDropper(options)
            pagedropper.run()
            self.check_page_count(pdf_path, 2)
            self.assertTrue(old_path.exists())
            cmd = [
                "verapdf", "-v", "-f", "1b", "--format", "text",
                str(pdf_path)
            ]
            cp = subprocess.run(cmd, check=True)
            self.assertEqual(cp.returncode, 0)

    def check_page_count(self, path, expected):
        reader = pdfrw.PdfReader(str(path))
        self.assertEqual(len(reader.pages), expected)


if __name__ == "__main__":
    unittest.main()
