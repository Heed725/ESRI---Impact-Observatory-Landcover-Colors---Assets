"""ESRI Landcover Colorizer: choose Common or Bright.

Only supported class values present in raster band 1 enter the legend.
Install using Processing Toolbox > Scripts > Add Script to Toolbox.

Python Console (after importing this module):
    apply_esri_colors(iface.activeLayer(), palette="common")
    apply_esri_colors(iface.activeLayer(), palette="bright")

The right-hand Processing help panel displays both palettes and hex codes.
"""

from qgis.core import (
    QgsPalettedRasterRenderer,
    QgsProcessingAlgorithm,
    QgsProcessingException,
    QgsProcessingOutputRasterLayer,
    QgsProcessingParameterEnum,
    QgsProcessingParameterRasterLayer,
    QgsRasterBlockFeedback,
    QgsRasterLayer,
)
from qgis.PyQt.QtGui import QColor


ESRI_CLASS_NAMES = {
    0: "No data",
    1: "Water",
    2: "Trees",
    4: "Flooded Vegetation",
    5: "Crops",
    7: "Built Area",
    8: "Bare Ground",
    9: "Snow/Ice",
    10: "Clouds",
    11: "Rangeland",
}

ESRI_COLORS_COMMON = {
    0: "#FFFFFF",
    1: "#419BDF",
    2: "#397D49",
    4: "#7A87C6",
    5: "#E49635",
    7: "#C4281B",
    8: "#A59B8F",
    9: "#A8EBFF",
    10: "#616161",
    11: "#E3E2C3",
}

ESRI_COLORS_BRIGHT = {
    0: "#FFFFFF",
    1: "#1A5BAB",
    2: "#358221",
    4: "#87D19E",
    5: "#FFDB5C",
    7: "#ED022A",
    8: "#EDE9E4",
    9: "#F2FAFF",
    10: "#C8C8C8",
    11: "#EECFA8",
}

# Preserve the name used by the original script.
ESRI_COLORS = ESRI_COLORS_BRIGHT
PALETTE_KEYS = ("common", "bright")
ESRI_PALETTES = {
    "common": ESRI_COLORS_COMMON,
    "bright": ESRI_COLORS_BRIGHT,
}


def help_colour_cell(hex_colour):
    """Build a coloured HTML table cell with readable hex text."""
    colour = QColor(hex_colour)
    brightness = (
        colour.red() * 299 + colour.green() * 587 + colour.blue() * 114
    ) / 1000
    text_colour = "#000000" if brightness >= 140 else "#FFFFFF"
    return (
        '<td align="center" valign="middle" bgcolor="{background}" '
        'style="background-color:{background};color:{foreground};'
        'white-space:nowrap;">'
        '<font color="{foreground}" face="monospace">{background}</font>'
        '</td>'
    ).format(background=hex_colour, foreground=text_colour)


def build_palette_help():
    """Create the colour reference shown in the right-hand panel."""
    rows = []
    for value, name in ESRI_CLASS_NAMES.items():
        rows.append(
            '<tr><td valign="middle"><b>{value}</b> {name}</td>'
            '{common}{bright}</tr>'.format(
                value=value,
                name=name,
                common=help_colour_cell(ESRI_COLORS_COMMON[value]),
                bright=help_colour_cell(ESRI_COLORS_BRIGHT[value]),
            )
        )
    return (
        '<html><body>'
        '<p>Select an ESRI landcover raster, then choose '
        '<b>Common</b> or <b>Bright</b>.</p>'
        '<p><b>Bright</b> matches the supplied bright QML '
        'and is selected by default.</p>'
        '<h3>Colour reference</h3>'
        '<table width="100%" border="0" cellspacing="3" cellpadding="5">'
        '<tr><th align="left">Class</th><th align="center">Common</th>'
        '<th align="center">Bright</th></tr>'
        + ''.join(rows)
        + '</table>'
        '<p>Both palettes are shown here for comparison. '
        'The dropdown determines which palette is applied.</p>'
        '<h3>Classes and legend</h3><ul>'
        '<li>Only supported values present in band 1 enter the legend.</li>'
        '<li>Undefined values, including 3 and 6, are skipped.</li>'
        '<li>Provider-defined NoData remains excluded.</li></ul>'
        '<h3>Result</h3><p>Updates the selected raster layer\'s style. '
        'Raster pixel values are unchanged.</p>'
        '<p><b>Save your QGIS project</b> to retain the selected style.</p>'
        '</body></html>'
    )


def apply_esri_colors(layer, palette="bright", feedback=None):
    """Style an existing QgsRasterLayer; return the number of applied classes.

    palette: "common" or "bright" (case insensitive).
    No raster pixels are changed. Provider-defined NoData remains NoData.
    Returns 0 on cancellation, leaving the current renderer unchanged.
    """
    if not isinstance(layer, QgsRasterLayer) or not layer.isValid():
        raise QgsProcessingException("Select a valid raster layer.")
    if layer.bandCount() < 1:
        raise QgsProcessingException("The raster has no bands.")

    key = str(palette).strip().lower()
    if key not in ESRI_PALETTES:
        raise QgsProcessingException("Palette must be 'common' or 'bright'.")
    colors = ESRI_PALETTES[key]
    log = feedback.pushInfo if feedback is not None else print
    if feedback is not None and feedback.isCanceled():
        return 0

    log("Selected palette: {}".format(key.title()))
    log("Scanning raster band 1 for unique values...")
    scan_feedback = QgsRasterBlockFeedback()
    if feedback is not None:
        scan_feedback.progressChanged.connect(feedback.setProgress)
        feedback.canceled.connect(scan_feedback.cancel)
    try:
        raster_classes = QgsPalettedRasterRenderer.classDataFromRaster(
            layer.dataProvider(), 1, None, scan_feedback
        )
    finally:
        if feedback is not None:
            feedback.canceled.disconnect(scan_feedback.cancel)
            scan_feedback.progressChanged.disconnect(feedback.setProgress)

    if feedback is not None and feedback.isCanceled():
        return 0

    # Do not round fractional values into valid class codes.
    unique_values = sorted({c.value for c in raster_classes})
    log("Found {} unique values: {}".format(len(unique_values), unique_values))
    classes = []
    for value in unique_values:
        if value not in ESRI_CLASS_NAMES:
            log("  {}: skipped (not an ESRI class)".format(value))
            continue
        class_id = int(value)
        name = ESRI_CLASS_NAMES[class_id]
        hex_color = colors[class_id]
        classes.append(
            QgsPalettedRasterRenderer.Class(class_id, QColor(hex_color), name)
        )
        log("  {}: {} ({})".format(class_id, name, hex_color))

    if not classes:
        raise QgsProcessingException(
            "No supported ESRI classes were found in band 1. "
            "The existing style has been kept."
        )
    if feedback is not None and feedback.isCanceled():
        return 0

    renderer = QgsPalettedRasterRenderer(layer.dataProvider(), 1, classes)
    layer.setRenderer(renderer)
    layer.triggerRepaint()
    log("Applied {} {} classes to '{}'".format(len(classes), key, layer.name()))
    return len(classes)


class ESRILandcoverColorizer(QgsProcessingAlgorithm):
    INPUT = "INPUT"
    PALETTE = "PALETTE"
    OUTPUT = "OUTPUT"

    def initAlgorithm(self, config=None):
        self.addParameter(
            QgsProcessingParameterRasterLayer(self.INPUT, "Input ESRI landcover raster")
        )
        self.addParameter(
            QgsProcessingParameterEnum(
                self.PALETTE,
                "Colour palette",
                options=["Common", "Bright"],
                defaultValue=1,
            )
        )
        self.addOutput(QgsProcessingOutputRasterLayer(self.OUTPUT, "Styled raster"))

    def flags(self):
        # This algorithm changes the selected layer's renderer in place.
        return super().flags() | QgsProcessingAlgorithm.FlagNoThreading

    def processAlgorithm(self, parameters, context, feedback):
        layer = self.parameterAsRasterLayer(parameters, self.INPUT, context)
        palette_index = self.parameterAsEnum(parameters, self.PALETTE, context)
        if palette_index not in (0, 1):
            raise QgsProcessingException("Select either the Common or Bright palette.")
        count = apply_esri_colors(layer, PALETTE_KEYS[palette_index], feedback)
        if count == 0:
            return {}
        return {self.OUTPUT: layer.id(), self.INPUT: layer.id()}

    def name(self):
        return "esrilandcovercolorizer"

    def displayName(self):
        return "ESRI Landcover Colorizer"

    def group(self):
        return "Raster Analysis"

    def groupId(self):
        return "rasteranalysis"

    def shortHelpString(self):
        return build_palette_help()

    def createInstance(self):
        return ESRILandcoverColorizer()
