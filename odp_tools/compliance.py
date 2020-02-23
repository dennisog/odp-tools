#!/usr/bin/env python3
#
# attempt to make a PDF file PDF/A compliant
#
# use at own risk. This does not do font embedding for example. If that is
# needed, use ghostscript.

import argparse
import os

import pdfrw

from metadata import PDFMetadata
from metadata import get_thumbnail
from colors import SRGBColorspace


class MakePDFCompliant:
    def __init__(self):
        self.options = None

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
        self.options = parser.parse_args()

    def run(self):
        print(self.options)


# Local Variables:
# mode: python
# End:
