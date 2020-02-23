import datetime
import hashlib
import ctypes
import base64
import io

from PIL import Image
from dateutil.tz import tzlocal

import pdfrw
import libxmp


class XMPGenerator:
    """This class spits out PDF/A-1B compliant XMP Metadata as a pdfrw PDFDict."""
    def __init__(self, pdf_metadata):
        self.pdf_metadata = pdf_metadata
        self.n_thumbnail = 0

        # some XMP set-up
        self.md = libxmp.XMPMeta()

        self.dc = libxmp.consts.XMP_NS_DC
        self.pdf = libxmp.consts.XMP_NS_PDF
        self.pdfaid = libxmp.consts.XMP_NS_PDFA_ID
        self.xmp = libxmp.consts.XMP_NS_XMP
        self.xmpGImg = "http://ns.adobe.com/xap/1.0/g/img/"

        self.md.register_namespace(self.pdf, "pdf")
        self.md.register_namespace(self.dc, "dc")
        self.md.register_namespace(self.pdfaid, "pdfaid")
        self.md.register_namespace(self.xmp, "xmp")
        self.md.register_namespace(self.xmpGImg, "xmpGImg")

    def generate_xmp(self):
        """Generate the appropriate XMP metadata and return as properly-formatted
string. See [1] for references."""
        self.make_xmp()
        return self.make_output()

    def make_xmp(self):
        # required PDF/A-1B XMP
        self.md.set_property(self.pdfaid, "conformance",
                             "B")  # basic conformance
        self.md.set_property_int(self.pdfaid, "part", 1)  # "1" for A-1

        # required metadata
        self.md.append_array_item(self.dc, "creator", self.pdf_metadata.author,
                                  {
                                      "prop_array_is_ordered": True,
                                      "prop_value_is_array": True,
                                  })
        self.md.set_localized_text(self.dc, "description", "en", "en-US",
                                   self.pdf_metadata.subject)
        self.md.set_localized_text(self.dc, "title", "en", "en-US",
                                   self.pdf_metadata.title)
        self.md.set_property(self.xmp, "CreatorTool",
                             self.pdf_metadata.creator)
        self.md.set_property(self.pdf, "Keywords", self.pdf_metadata.keywords)
        self.md.set_property(self.pdf, "Producer", self.pdf_metadata.producer)

        self.add_time("CreateDate", self.pdf_metadata.time)
        self.add_time("ModifyDate", self.pdf_metadata.time)

        # additional metadata
        self.md.set_property(self.pdf, "PDFVersion", "1.4")
        self.md.append_array_item(self.xmp, "Identifier",
                                  self.pdf_metadata.hash(), {
                                      "prop_array_is_ordered": False,
                                      "prop_value_is_array": True,
                                  })
        if self.pdf_metadata.has_thumbnail():
            self.add_thumbnail(self.pdf_metadata.thumbnail)

    def make_output(self):
        # generate the output string
        ostr = libxmp.core._remove_trailing_whitespace(
            self.md.serialize_to_str().replace("\ufeff", ""))

        # assemble the output dictionary
        output_dict = pdfrw.IndirectPdfDict(Type=pdfrw.PdfName("Metadata"),
                                            Subtype=pdfrw.PdfName("XML"))
        output_dict.stream = ostr.encode("utf-8").decode("latin-1")
        return output_dict

    def add_time(self, name, time):
        """Need to dig into the C library here because the Python wrapper does not save
the correct time zone offset."""

        # construct the internal XMP date object
        xmp_date = libxmp.exempi.XmpDateTime()
        xmp_date.year = time.year
        xmp_date.month = time.month
        xmp_date.day = time.day
        xmp_date.hour = time.hour
        xmp_date.minute = time.minute
        xmp_date.second = time.second
        xmp_date.nanosecond = 0

        # fix the time zone offset (this is just ignored by the
        # python-xmp-toolkit)
        ofst = time.strftime("%z")  # not the prettiest way to do it
        xmp_date.tzsign = 1 if ofst[0] == "+" else -1
        xmp_date.tzhour = int(ofst[1:3])
        xmp_date.tzminute = int(ofst[3:5])

        # ctypes call
        lib = libxmp.exempi.EXEMPI
        # FIXME: I think this can be zero
        options = libxmp.consts.options_mask(libxmp.consts.XMP_PROP_OPTIONS)
        lib.xmp_set_property_date.restype = libxmp.exempi.check_error
        lib.xmp_set_property_date.argtypes = [
            ctypes.c_void_p, ctypes.c_char_p, ctypes.c_char_p,
            ctypes.POINTER(libxmp.exempi.XmpDateTime), ctypes.c_uint32
        ]
        lib.xmp_set_property_date(self.md.xmpptr,
                                  ctypes.c_char_p(self.xmp.encode('utf-8')),
                                  ctypes.c_char_p(name.encode('utf-8')),
                                  ctypes.byref(xmp_date),
                                  ctypes.c_uint32(options))

    def add_thumbnail(self, thumbnail: Image):
        """add a thumbnail to the xmp metadata"""

        self.n_thumbnail = self.n_thumbnail + 1

        # generate the image data (base64-encoded JPEG)
        buf = io.BytesIO()
        thumbnail.save(buf, format="JPEG", optimize=True)
        img_data = base64.b64encode(buf.getvalue()).decode("latin-1")

        # prepare the xmp object
        self.md.append_array_item(self.xmp, "Thumbnails", None,
                                  {"prop_array_is_alt": True})
        self.md.set_array_item(self.xmp,
                               "Thumbnails",
                               self.n_thumbnail,
                               None,
                               prop_value_is_struct=True)
        path = "Thumbnails[{:d}]/{:s}{{:s}}".format(
            self.n_thumbnail, self.md.get_prefix_for_namespace(self.xmpGImg))

        # add the image data to the xmp object
        self.md.set_property(self.xmp, path.format("format"), "JPEG")
        self.md.set_property_int(self.xmp, path.format("height"),
                                 thumbnail.height)
        self.md.set_property_int(self.xmp, path.format("width"),
                                 thumbnail.width)
        self.md.set_property(self.xmp, path.format("image"), img_data)


class PDFMetadata:
    """I need to keep metadata synchronized between the /Info dict and the XMP
data. this class holds data for which this is true."""
    def __init__(self, **kwargs):
        for thing in ("title", "author", "subject", "keywords", "creator",
                      "producer", "time", "thumbnail"):
            if thing in kwargs:
                setattr(self, thing, kwargs[thing])
            else:
                setattr(self, thing, "")
        if not self.has_time():
            self.time = datetime.datetime.now(tzlocal())

    def has_time(self):
        return not self.time == ""

    def has_thumbnail(self):
        return not self.thumbnail == ""

    def pdftime(self):
        # pdf has a strange UTC offset formatting spec
        ofst = self.time.strftime("%z")
        uoff = ofst[0] + ofst[1:3] + "'" + ofst[3:5] + "'"
        # assemble the format string
        fmt = "D:%Y%m%d%H%M%S{:s}".format(uoff)
        return self.time.strftime(fmt)

    def hash(self):
        docid = hashlib.sha256()
        for thing in (self.title, self.author, self.subject, self.keywords,
                      self.creator, self.producer, self.pdftime()):
            docid.update(thing.encode("utf-8") if thing else b"")
        return docid.hexdigest()

    def pdfInfo(self):
        return pdfrw.IndirectPdfDict(
            Title=self.title,
            Author=self.author,
            Subject=self.subject,
            Keywords=self.keywords,
            Creator=self.creator,
            Producer=self.producer,
            CreationDate=self.pdftime(),
            ModDate=self.pdftime(),
        )

    def pdfID(self):
        return [self.hash()] * 2

    def pdfXMP(self):
        return XMPGenerator(self).generate_xmp()


def get_thumbnail(fp, size):
    """return a thumbnail for the image saved in 'fp'"""
    img = Image.open(fp)
    img.thumbnail(size)
    return img


# references
# [1] https://www.pdfa.org/resource/technical-note-tn0008-predefined-xmp-properties-in-pdfa-1/
