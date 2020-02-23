import pathlib

from PIL import ImageCms
import pdfrw


class SRGBColorspace:
    """load and properly format the ICC sRGB2014 color profile for embedding in a
PDF file."""
    def __init__(self):
        # load the sRGB2014 ICC color profile
        iccpath = pathlib.Path(
            __file__).absolute().parent / "icc" / "sRGB2014.icc"
        srgb = ImageCms.getOpenProfile(str(iccpath))

        # construct the correct pdf dict. first the output profile
        # N=3 is required for RGB colorspaces
        op = pdfrw.IndirectPdfDict(N=3, Alternate=pdfrw.PdfName("DeviceRGB"))
        op.stream = srgb.tobytes().decode("latin-1")

        # then the outputintents array
        oi = pdfrw.IndirectPdfDict(
            Type=pdfrw.PdfName("OutputIntent"),
            S=pdfrw.PdfName("GTS_PDFA1"),
            OutputConditionIdentifier="sRGB",
            DestOutputProfile=op,
            Info=srgb.profile.profile_description,
            # I am not sure whether this is correct, but it doesn't fail
            RegistryName="http://color.org/srgbprofiles.xalter")
        self.output_intent = [oi]

    def pdfOutputIntent(self):
        return self.output_intent
