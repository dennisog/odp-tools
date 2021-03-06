#!/usr/bin/env python3

import sys
import tempfile
import subprocess
import unittest
import shutil
from pathlib import Path
from argparse import Namespace

DIR = Path(__file__).absolute().parent
sys.path.append(str(DIR.parent / "odp_tools"))

from compliance import MakePDFCompliant


class TestMakeComply(unittest.TestCase):
    def test_find_verapdf(self):
        vera = shutil.which("verapdf")
        self.assertNotEqual(vera, None)

    def test_make_comply(self):
        print("")
        sample_path = DIR / "samples" / "non_compliant.pdf"
        with tempfile.TemporaryDirectory() as tempdir:
            pdf_path = Path(tempdir) / "sample.pdf"
            old_path = Path(tempdir) / "sample.pdf.orig"
            shutil.copyfile(sample_path, pdf_path)
            options = Namespace()
            options.filenames = [str(pdf_path)]
            options.keep_original = True
            options.thumbnail = False
            options.keep_date = False
            make_comply = MakePDFCompliant(options)
            make_comply.run()
            self.assertTrue(old_path.exists())
            cmd = ["verapdf", "-f", "1b", "--format", "text", str(pdf_path)]
            cp = subprocess.run(cmd, check=True)
            self.assertEqual(cp.returncode, 0)


if __name__ == "__main__":
    unittest.main()
