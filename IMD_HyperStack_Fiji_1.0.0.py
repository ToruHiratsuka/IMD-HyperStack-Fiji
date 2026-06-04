"""
IMD HyperStack for Fiji
Author: Toru Hiratsuka
Institution: Osaka International Cancer Institute
Version: 1.0.0

Description
--------
This Jython script can make a IMD FRET ratio image from donor and acceptor images.

Features
--------
- HyperStack support
- Multiple LUTs
    * 8colours
    * jet
    * White-Red
    * Red
- Numerator intensity mode
- Denominator intensity mode
- Average intensity mode

Requirements
------------
- Fiji/ImageJ
- Lut files: 8colours.lut; jet.lut; White-Red.lut

License
--------
MIT License
"""

from ij import IJ, ImagePlus, WindowManager, ImageStack
from ij.gui import GenericDialog
from ij.plugin import Duplicator, ImageCalculator, LutLoader
from ij.process import ColorProcessor
from java.awt import Color
from jarray import zeros


# -----------------------------
# Utility
# -----------------------------

def safe_close(imp):
    if imp is not None:
        imp.changes = False
        imp.close()


def copy_calibration(src, dst):
    try:
        dst.setCalibration(src.getCalibration().copy())
    except:
        pass


def get_open_image_titles():
    ids = WindowManager.getIDList()
    if ids is None:
        return []
    return [WindowManager.getImage(i).getTitle() for i in ids]


def make_ratio_name(low_val, high_val):
    low_s = str(low_val).replace(".", "")
    high_s = str(high_val).replace(".", "")
    return "Ratio" + low_s + high_s + "-"


def check_compatible(nu, de):
    if nu.getWidth() != de.getWidth():
        raise Exception("Width mismatch.")
    if nu.getHeight() != de.getHeight():
        raise Exception("Height mismatch.")
    if nu.getNChannels() != de.getNChannels():
        raise Exception("Channel number mismatch.")
    if nu.getNSlices() != de.getNSlices():
        raise Exception("Z-slice number mismatch.")
    if nu.getNFrames() != de.getNFrames():
        raise Exception("Frame number mismatch.")


def get_required_lut(lut_name):
    lut = None
    try:
        lut = LutLoader.getLut(lut_name)
    except:
        lut = None

    if lut is None:
        raise Exception(
            "LUT not found: " + lut_name +
            ". Please install/register this LUT in Fiji."
        )

    return lut


# -----------------------------
# Ratio image to RGB by LUT
# -----------------------------

def ratio_to_rgb_by_lut(ratio_imp, low_val, high_val, lut_name):

    ip = ratio_imp.getProcessor().convertToFloat()
    w = ip.getWidth()
    h = ip.getHeight()

    lut = get_required_lut(lut_name)

    out_pixels = zeros(w * h, 'i')

    for y in range(h):
        for x in range(w):
            idx = y * w + x
            v = ip.getf(x, y)

            if high_val > low_val:
                scaled = int(round(255.0 * (v - low_val) / (high_val - low_val)))
            else:
                scaled = 0

            if scaled < 0:
                scaled = 0
            elif scaled > 255:
                scaled = 255

            r = lut.getRed(scaled)
            g = lut.getGreen(scaled)
            b = lut.getBlue(scaled)

            # Do not include alpha to avoid signed int overflow in Jython
            rgb = (r << 16) | (g << 8) | b

            out_pixels[idx] = rgb

    out_ip = ColorProcessor(w, h)
    out_ip.setPixels(out_pixels)

    return ImagePlus("Ratio_RGB_tmp", out_ip)


# -----------------------------
# Replace brightness with intensity
# -----------------------------

def replace_brightness_with_intensity(rgb_imp, intensity_imp, title="IMD_frame"):

    rgb_ip = rgb_imp.getProcessor().convertToRGB()
    int_ip = intensity_imp.getProcessor().convertToFloat()

    w = rgb_ip.getWidth()
    h = rgb_ip.getHeight()

    if int_ip.getWidth() != w or int_ip.getHeight() != h:
        raise Exception("RGB and intensity image size mismatch.")

    stats = int_ip.getStatistics()
    min_val = stats.min
    max_val = stats.max

    out_pixels = zeros(w * h, 'i')

    for y in range(h):
        for x in range(w):
            idx = y * w + x

            rgb = rgb_ip.getPixel(x, y)

            r = (rgb >> 16) & 0xff
            g = (rgb >> 8) & 0xff
            b = rgb & 0xff

            hsb = Color.RGBtoHSB(r, g, b, None)

            val = int_ip.getf(x, y)

            if max_val > min_val:
                brightness = (val - min_val) / (max_val - min_val)
            else:
                brightness = 0.0

            if brightness < 0.0:
                brightness = 0.0
            elif brightness > 1.0:
                brightness = 1.0

            out_pixels[idx] = Color.HSBtoRGB(hsb[0], hsb[1], brightness)

    out_ip = ColorProcessor(w, h)
    out_ip.setPixels(out_pixels)

    return ImagePlus(title, out_ip)


# -----------------------------
# Single frame IMD
# -----------------------------

def SingleFrameIMD(nu_slice, de_slice,
                   low_val, high_val,
                   intensity_mode,
                   lut_name="8colours",
                   add_bar=False,
                   title="IMD_frame"):

    if add_bar:
        IJ.log("Warning: Colour scale / Calibration Bar is not supported in this API-only version.")

    if nu_slice.getWidth() != de_slice.getWidth():
        raise Exception("Width mismatch in SingleFrameIMD.")
    if nu_slice.getHeight() != de_slice.getHeight():
        raise Exception("Height mismatch in SingleFrameIMD.")

    temp_images = []

    try:
        ratio = ImageCalculator.run(nu_slice, de_slice, "Divide create 32-bit")
        ratio.setTitle("Ratio_tmp")
        temp_images.append(ratio)

        ratio_rgb = ratio_to_rgb_by_lut(
            ratio,
            low_val,
            high_val,
            lut_name
        )
        temp_images.append(ratio_rgb)

        if intensity_mode == "Numerator intensity":
            intensity = nu_slice.duplicate()
            intensity.setTitle("Intensity_Numerator_tmp")

        elif intensity_mode == "Denominator intensity":
            intensity = de_slice.duplicate()
            intensity.setTitle("Intensity_Denominator_tmp")

        elif intensity_mode == "Average intensity":
            intensity = ImageCalculator.run(nu_slice, de_slice, "Average create 32-bit")
            intensity.setTitle("Intensity_Average_tmp")

        else:
            raise Exception("Unknown intensity mode: " + intensity_mode)

        temp_images.append(intensity)

        out = replace_brightness_with_intensity(
            ratio_rgb,
            intensity,
            title
        )

        copy_calibration(nu_slice, out)

        return out

    finally:
        for imp in temp_images:
            safe_close(imp)


# -----------------------------
# Main
# -----------------------------

titles = get_open_image_titles()

if len(titles) < 2:
    IJ.error("Please open at least two images.")
    raise Exception("Please open at least two images.")

gd = GenericDialog("IMD ratio - Jython API version")

gd.addChoice("Numerator", titles, titles[0])
gd.addChoice("Denominator", titles, titles[1])
gd.addNumericField("Lower limit", 0.5, 2)
gd.addNumericField("Higher limit", 1.5, 2)

gd.addChoice(
    "Intensity",
    ["Numerator intensity", "Denominator intensity", "Average intensity"],
    "Average intensity"
)

gd.addChoice(
    "LUT",
    ["8colours", "jet", "White-Red", "Red"],
    "8colours"
)

gd.addCheckbox("Colour scale", False)

gd.showDialog()

if gd.wasCanceled():
    raise Exception("Canceled.")

nu_title = gd.getNextChoice()
de_title = gd.getNextChoice()
low_val = gd.getNextNumber()
high_val = gd.getNextNumber()
intensity_mode = gd.getNextChoice()
lut_name = gd.getNextChoice()
add_bar = gd.getNextBoolean()

if high_val <= low_val:
    raise Exception("Higher limit must be larger than lower limit.")

# Check LUT before long processing
get_required_lut(lut_name)

nu = WindowManager.getImage(nu_title)
de = WindowManager.getImage(de_title)

if nu is None:
    raise Exception("Numerator image not found: " + nu_title)
if de is None:
    raise Exception("Denominator image not found: " + de_title)

check_compatible(nu, de)

w = nu.getWidth()
h = nu.getHeight()
nC = nu.getNChannels()
nZ = nu.getNSlices()
nT = nu.getNFrames()

result_stack = ImageStack(w, h)
dup = Duplicator()

total = nC * nZ * nT
count = 0

for t in range(1, nT + 1):
    for z in range(1, nZ + 1):
        for c in range(1, nC + 1):

            count += 1
            IJ.showStatus("Processing IMD %d / %d" % (count, total))
            IJ.showProgress(count, total)

            nu_slice = dup.run(nu, c, c, z, z, t, t)
            de_slice = dup.run(de, c, c, z, z, t, t)

            nu_slice.setTitle("Nu_c%d_z%d_t%d" % (c, z, t))
            de_slice.setTitle("De_c%d_z%d_t%d" % (c, z, t))

            out = SingleFrameIMD(
                nu_slice,
                de_slice,
                low_val,
                high_val,
                intensity_mode,
                lut_name,
                add_bar,
                "IMD_c%d_z%d_t%d" % (c, z, t)
            )

            result_stack.addSlice(
                "c%d_z%d_t%d" % (c, z, t),
                out.getProcessor().duplicate()
            )

            safe_close(out)
            safe_close(nu_slice)
            safe_close(de_slice)

IJ.showProgress(1.0)
IJ.showStatus("IMD processing finished.")

result_title = make_ratio_name(low_val, high_val)
result = ImagePlus(result_title, result_stack)

copy_calibration(nu, result)

if nC > 1 or nZ > 1 or nT > 1:
    result.setDimensions(nC, nZ, nT)
    result.setOpenAsHyperStack(True)

result.show()

IJ.log("IMD image created: " + result_title)