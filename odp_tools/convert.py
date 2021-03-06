# convert pnm scans to reasonably-sized PDFs.

import multiprocessing
import argparse
import io
import datetime
import subprocess
import tempfile
import os
from dateutil.tz import tzlocal

import noteshrink
import yaml
import img2pdf
import pdfrw
import tqdm
import numpy as np
from PIL import Image
from sklearn.cluster import MiniBatchKMeans

from metadata import PDFMetadata
from metadata import get_thumbnail
from colors import SRGBColorspace


class NumberedThing:
    """we need to keep track of the page numbers while processing the pages. this
is a very simple mechanism to to so."""
    def __init__(self, number, thing):
        self.number = number
        self.thing = thing


class HackedNoteShrink:
    """a slightly modfied version of Matt Zucker's noteshrink tool."""
    """
MIT License

Copyright (c) 2016, Matt Zucker

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
    """
    def run(self, img):
        samples = noteshrink.sample_pixels(img, self.options)
        palette = self.get_palette(samples)
        labels = noteshrink.apply_palette(img, palette, self.options)

        if self.options.saturate:
            palette = palette.astype(np.float32)
            pmin = palette.min()
            pmax = palette.max()
            palette = 255 * (palette - pmin) / (pmax - pmin)
            palette = palette.astype(np.uint8)

        if self.options.white_bg:
            palette = palette.copy()
            palette[0] = (255, 255, 255)

        output_img = Image.fromarray(labels, 'P')
        output_img.putpalette(palette.flatten())
        return output_img

    def get_palette(self, samples):
        """this allows some customization for the kmeans algo"""
        bg_color = noteshrink.get_bg_color(samples, 6)

        fg_mask = noteshrink.get_fg_mask(bg_color, samples, self.options)

        # use mini-batch k means from sklearn instead of scipy kmeans
        mbk = MiniBatchKMeans(init="k-means++",
                              n_clusters=self.options.num_colors - 1,
                              max_iter=self.options.kmeans_iter,
                              batch_size=self.options.kmeans_batch_size,
                              compute_labels=False)
        mbk.fit(samples[fg_mask].astype(np.float32))
        centers = mbk.cluster_centers_

        palette = np.vstack((bg_color, centers)).astype(np.uint8)
        return palette

    def __init__(self, options):
        self.options = options

    def shrink(self, imbuf, dpi):
        # load image using pillow and run noteshrink. noteshrink returns a
        # pillow image
        image, _ = noteshrink.load(imbuf)
        out_image = self.run(image)

        # write the image as optimzed PNG to output buffer
        pngopts = {"optimize": True, "dpi": (dpi, dpi)}
        obuf = io.BytesIO()
        out_image.save(obuf, format="PNG", **pngopts)
        obuf.seek(0)
        return obuf


class PDFWorker:
    """take a filename from the queue, process that file, put a bytes array of a
pdf version of that file on the results queue."""
    def __init__(self, work_queue, results_queue, options):
        # work until there is no more work
        self.options = options
        self.results_queue = results_queue
        while not work_queue.empty():
            self.do_work(work_queue.get())

    def do_work(self, work_item):
        # execute the processing pipeline
        raw_imbuf = self.load_image(work_item.thing)
        shrunk_imbuf = self.run_noteshrink(raw_imbuf)
        quant_imbuf = self.run_pngquant(shrunk_imbuf)
        opt_imbuf = self.run_optipng(quant_imbuf)

        pdfbuf = self.run_img2pdf(opt_imbuf)

        # check the processed file into the results queue
        output = NumberedThing(work_item.number, pdfbuf.getvalue())
        self.results_queue.put(output)

    def load_image(self, filename):
        with open(filename, "rb") as ifl:
            return io.BytesIO(ifl.read())

    # the work functions below all take a BytesIO as an input and return a
    # BytesIO as output. that way I can chain them and disable a step in the
    # pipeline if needed

    def run_noteshrink(self, imbuf):
        if not self.options.noteshrink.enable:
            return imbuf
        noteshrink = HackedNoteShrink(self.options.noteshrink)
        return noteshrink.shrink(imbuf, self.options.general.dpi)

    def run_pngquant(self, imbuf):
        if not self.options.pngquant.enable:
            return imbuf
        cmd = [
            self.options.pngquant.path,
            "--speed={:d}".format(self.options.pngquant.speed),
            "--quality=0-{:d}".format(self.options.pngquant.max_quality), "-"
        ]
        cp = subprocess.run(cmd,
                            input=imbuf.getbuffer(),
                            capture_output=True,
                            check=True)
        return io.BytesIO(cp.stdout)

    def run_optipng(self, imbuf):
        if not self.options.optipng.enable:
            return imbuf
        with tempfile.TemporaryDirectory() as tempdir:
            inpath = os.path.join(tempdir, "in")
            opath = os.path.join(tempdir, "out")
            # dump image to disk
            with open(inpath, "wb") as inf:
                inf.write(imbuf.read())

            # run optipng
            opts = ["-out={:s}".format(opath), "--"]
            cmd = [self.options.optipng.path] + opts + [inpath]
            subprocess.run(cmd, check=True, capture_output=True)
            with open(opath, "rb") as of:
                return io.BytesIO(of.read())

    def run_img2pdf(self, imbuf):
        """embed the image in a PDF file."""
        # first need to convert the png to RGB, otherwise pdfrw will complain
        rgb_imbuf = io.BytesIO()
        pngopts = {
            "format": "PNG",
            "optimize": True,
            "dpi": (self.options.general.dpi, self.options.general.dpi)
        }
        Image.open(imbuf).convert("RGB").save(rgb_imbuf, **pngopts)
        rgb_imbuf.seek(0)
        obuf = io.BytesIO()
        img2pdf.convert(rgb_imbuf, outputstream=obuf)
        return obuf


class PDFBuilder:
    """wait for the processing of all pages and construct the output pdf."""
    def __init__(self, options):
        self.options = options
        self.metadata = PDFMetadata(
            title=self.options.metadata.title,
            author=self.options.metadata.author,
            subject=self.options.metadata.subject,
            keywords=self.options.metadata.keywords,
            creator=self.options.metadata.creator,
        )
        if self.options.metadata.thumbnail:
            self.metadata.thumbnail = get_thumbnail(self.options.filenames[0],
                                                    (300, 300))
        self.colorspace = SRGBColorspace()

    def run(self, results_queue, remaining):
        self.remaining = remaining
        self.results_buffer = []
        self.last_written = -1
        self.pdf = None
        with tqdm.tqdm(total=self.remaining,
                       desc="processing images...") as pbar:
            while self.remaining > 0:
                result = results_queue.get()
                self.process_result(result)
                self.remaining = self.remaining - 1
                pbar.update()

    def process_result(self, numbered_work_output):
        self.rbuffer_add(numbered_work_output)
        if self.rbuffer_in_sequence():
            self.append_pdf()

    def rbuffer_add(self, numbered_work_output):
        self.results_buffer.append(numbered_work_output)
        self.results_buffer.sort(key=lambda x: x.number)

    def rbuffer_in_sequence(self):
        tlist = [self.last_written] + [x.number for x in self.results_buffer]
        return sorted(tlist) == list(range(min(tlist), max(tlist) + 1))

    def append_pdf(self):
        for item in self.results_buffer:
            # pull the new page out of the work item
            newpage = pdfrw.PdfReader(fdata=item.thing, verbose=False).pages[0]

            # if necessary, create the output pdf
            if self.pdf is None:
                self.pdf = pdfrw.PdfWriter(self.options.general.pdfname,
                                           version="1.4")

            # add the page to the output pdf
            self.pdf.addpage(newpage)
            self.write_pdf()

            # increase internal counter
            self.last_written = item.number
        self.results_buffer = []

    def write_pdf(self):
        # this needs to be set on every write, otherwise subsequent writes
        # overwrite these values.
        self.pdf.trailer.Info = self.metadata.pdfInfo()
        self.pdf.trailer.ID = self.metadata.pdfID()
        self.pdf.trailer.Root.Metadata = self.metadata.pdfXMP()
        self.pdf.trailer.Root.OutputIntents = self.colorspace.pdfOutputIntent()

        self.pdf.write()

    def get_pdf_time(self):
        """produce a valid pdf time string for the current time."""
        dt = datetime.datetime.now(tzlocal())
        ofst = dt.strftime("%z")
        uoff = ofst[0] + ofst[1:3] + "'" + ofst[3:5] + "'"
        fmt = "D:%Y%m%d%H%M%S{:s}".format(uoff)
        return dt.strftime(fmt)


class PDFWorkQueue:
    def __init__(self, options):
        # use the options in this object later
        self.options = options

        # create a work queue and a results queue
        self.work_queue = multiprocessing.Queue()
        for number, filename in enumerate(options.filenames):
            self.work_queue.put(NumberedThing(number, filename))
        self.results_queue = multiprocessing.Queue()

    def run(self):
        if self.options.general.nworkers < 1:
            raise RuntimeError("Need workers")
        # start the workers
        self.procs = []
        for _ in range(self.options.general.nworkers):
            proc = multiprocessing.Process(target=PDFWorker,
                                           args=(self.work_queue,
                                                 self.results_queue,
                                                 self.options))
            self.procs.append(proc)
            proc.start()

        # run the consumer
        builder = PDFBuilder(self.options)
        builder.run(self.results_queue, len(self.options.filenames))

        # end the workers after the work is done
        for proc in self.procs:
            proc.join()


class Options:
    """we hold options in this strange object."""
    @staticmethod
    def get_argument_parser():
        parser = argparse.ArgumentParser(
            description="Convert some images to PDF. Be opinionated.")
        parser.add_argument("infile",
                            metavar="FILE",
                            nargs=1,
                            help="input yaml")
        parser.add_argument("filenames",
                            metavar="IMAGE",
                            nargs="+",
                            help="files to convert")
        return parser

    def __init__(self, ns):
        # these are the members we want to fill
        self.filenames = None
        self.general = None
        self.metadata = None
        self.noteshrink = None
        self.pngquant = None
        self.optipng = None

        # properly load all filenames
        self.get_filenames(ns.filenames)

        # load all options from input file
        infile = ns.infile[0]
        self.load_options_from_file(infile, "general")
        self.load_options_from_file(infile, "metadata")
        self.load_options_from_file(infile, "noteshrink")
        self.load_options_from_file(infile, "pngquant")
        self.load_options_from_file(infile, "optipng")

    def load_options_from_file(self, filename, optname):
        # some default options
        defaults = {
            "general": {
                "pdfname": "out.pdf",
                "dpi": 300,
                "nworkers": 2,
            },
            "metadata": {
                "title": "A Scanned Document",
                "author": "Example Person",
                "subject": "Interesting Stuff",
                "keywords": "word1, word2",
                "thumbnail": False,
            },
            "noteshrink": {
                "enable": True,
                "value_threshold": 0.4,
                "sat_threshold": 0.2,
                "num_colors": 8,
                "sample_fraction": 5,
                "saturate": True,
                "white_bg": False,
                "quiet": True,
                "kmeans_iter": 5,
                "kmeans_batch_size": 100,
            },
            "pngquant": {
                "enable": True,
                "speed": 3,
                "max_quality": 100,
                "path": "pngquant"
            },
            "optipng": {
                "enable": True,
                "path": "optipng"
            }
        }
        # load from the yaml input
        ns = argparse.Namespace()
        with open(filename) as ifl:
            d = yaml.load(ifl, Loader=yaml.FullLoader)
            # add defaults
            for k, v in defaults[optname].items():
                if k not in d:
                    setattr(ns, k, v)
            # load from file
            for k, v in d[optname].items():
                setattr(ns, k, v)
        # save ns to options object
        setattr(self, optname, ns)

    def get_filenames(self, filenames):
        o = argparse.Namespace()
        o.sort_numerically = True
        o.filenames = filenames
        self.filenames = noteshrink.get_filenames(o)

    def __str__(self):
        return """Options:
 nfiles: {:d}
 general: {:s}
 metadata: {:s}
 noteshrink: {:s}
 pngquant: {:s}
 optipng: {:s}""".format(len(self.filenames), str(self.general),
                         str(self.metadata), str(self.noteshrink),
                         str(self.pngquant), str(self.optipng))
