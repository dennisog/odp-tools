#!/usr/bin/env python3

import sys
import io
import unittest
import tempfile
import subprocess
import shutil
from pathlib import Path

import pdfrw
import img2pdf

DIR = Path(__file__).absolute().parent
sys.path.append(str(DIR.parent / "odp_tools"))

from metadata import PDFMetadata
from metadata import get_thumbnail
from colors import SRGBColorspace


def editable_pdf_from_img(path: Path):
    buf = io.BytesIO()
    img2pdf.convert(str(path), outputstream=buf)
    page = pdfrw.PdfReader(fdata=buf.getvalue(), verbose=False).pages[0]
    pdf = pdfrw.PdfWriter(version="1.4")
    pdf.addpage(page)
    return pdf


class TestPDFACompliance(unittest.TestCase):
    def test_find_verapdf(self):
        vera = shutil.which("verapdf")
        self.assertNotEqual(vera, None)

    def test_compliance(self):
        print("Testing PDF/A-1B compliance...")
        pdf = editable_pdf_from_img(DIR / "samples" / "sample.jpg")
        metadata = PDFMetadata(title="Test title",
                               author="Test Author",
                               subject="Test Subject",
                               keywords="Test Keywords",
                               creator="Test Creator")
        pdf.trailer.Info = metadata.pdfInfo()
        pdf.trailer.ID = metadata.pdfID()
        pdf.trailer.Root.Metadata = metadata.pdfXMP()
        pdf.trailer.Root.OutputIntents = SRGBColorspace().pdfOutputIntent()
        with tempfile.TemporaryDirectory() as tempdir:
            pdfpath = Path(tempdir) / "in.pdf"
            pdf.write(str(pdfpath))
            cmd = ["verapdf", "-f", "1b", "--format", "text", str(pdfpath)]
            cp = subprocess.run(cmd, check=True)
            self.assertEqual(cp.returncode, 0)


if __name__ == "__main__":
    unittest.main()
