# drop some pages from a pdf file

import argparse
import pathlib

import pdfrw

from metadata import PDFMetadata
from colors import SRGBColorspace


class PageDropper:
    @staticmethod
    def get_argument_parser():
        parser = argparse.ArgumentParser(
            description="Drop pages from a PDF file")
        parser.add_argument("filename",
                            metavar="FILE",
                            nargs=1,
                            help="PDF file to modify")
        parser.add_argument("pages",
                            metavar="PAGE",
                            nargs="+",
                            type=int,
                            help="files to modify")
        parser.add_argument("-d",
                            "--dont-keep",
                            action="store_false",
                            dest="keep_original",
                            default=True,
                            help="don't keep original file")
        parser.add_argument("-",
                            "--no-metadata",
                            action="store_false",
                            dest="write_metadata",
                            default=True,
                            help="don't write out metadata")
        return parser

    def __init__(self, options):
        self.options = options

    def run(self):
        filepath = pathlib.Path(self.options.filename[0])
        origpath = filepath.rename(filepath.with_suffix(".pdf.orig"))
        reader = pdfrw.PdfReader(str(origpath))
        writer = pdfrw.PdfWriter(filepath, version="1.4")

        # not necessarily the most efficient algorithm here...
        for i, page in enumerate(reader.pages):
            if i + 1 in self.options.pages:
                continue
            writer.addpage(page)

        if self.options.write_metadata:
            metadata = PDFMetadata(pdfInfo=reader.Info)
            writer.trailer.Info = metadata.pdfInfo()
            writer.trailer.ID = metadata.pdfID()
            writer.trailer.Root.Metadata = metadata.pdfXMP()
            writer.trailer.Root.OutputIntents = SRGBColorspace(
            ).pdfOutputIntent()

        writer.write()

        # optionally remove the input
        if not self.options.keep_original:
            origpath.unlink()
