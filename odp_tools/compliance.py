# attempt to make a PDF file PDF/A compliant
#
# use at own risk. This does not do font embedding for example. If that is
# needed, use ghostscript.
#
# this really just takes pages from the input file, and re-assembles the
# metadata with some very light parsing.

import argparse
import pathlib

import pdfrw

from metadata import PDFMetadata
from colors import SRGBColorspace


class MakePDFCompliant:
    def __init__(self):
        self.options = None
        self.srgb = SRGBColorspace()

    def parse_args(self):
        parser = argparse.ArgumentParser(
            description="Modify a PDF file to become PDF/A-1B")
        parser.add_argument("filenames",
                            metavar="FILENAME",
                            nargs="+",
                            help="files to modify")
        parser.add_argument("-d",
                            "--dont-keep",
                            action="store_false",
                            dest="keep_original",
                            default=True,
                            help="don't keep original file")
        parser.add_argument("-t",
                            "--thumbnail",
                            action="store_true",
                            dest="thumbnail",
                            default=False,
                            help="embed a thumbnail")
        parser.add_argument("-k",
                            "--keep-date",
                            action="store_true",
                            dest="keep_date",
                            default=False,
                            help="keep the CreationDate")
        self.options = parser.parse_args()
        if self.options.keep_date is True:
            # need to parse the pdf date from the string. possible, but I don't
            # need it. I just overwrite with current date.
            raise NotImplementedError()
        if self.options.thumbnail is True:
            # need to extract a thumbnail from the pdf. not super easily done
            # in PIL (PIL only writes to pdfs. implement when really needed)
            raise NotImplementedError()

    def run(self):
        for fn in self.options.filenames:
            path = pathlib.Path(fn).absolute()
            print("* {:s}".format(str(path)))
            self.convert_file(path)

    def convert_file(self, filepath):
        # (1) load the pdf, move all pages to the new file
        origpath = filepath.rename(filepath.with_suffix(".pdf.orig"))
        print(origpath)
        reader = pdfrw.PdfReader(str(origpath))
        writer = pdfrw.PdfWriter(filepath, version="1.4")
        for page in reader.pages:
            writer.addpage(page)

        # (2) extract the Metadata from the /Info dict
        metadata = PDFMetadata(pdfInfo=reader.Info)

        # (3) add new metadata to the output file and write
        writer.trailer.Info = metadata.pdfInfo()
        writer.trailer.ID = metadata.pdfID()
        writer.trailer.Root.Metadata = metadata.pdfXMP()
        writer.trailer.Root.OutputIntents = self.srgb.pdfOutputIntent()
        writer.write()

        # optionally remove the input
        if not self.options.keep_original:
            origpath.unlink()
