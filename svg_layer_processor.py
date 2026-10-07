"""
svg_layer_processor.py
Post-processor for 2D vector SVG patterns exported by Blender's paper model engine.
Organizes elements into dedicated machine layers (Cut, Mountain Fold, Valley Fold, Annotations)
compatible with LightBurn, Glowforge, Cricut, CNC plasma, and laser cutters.
"""

import os
import re
import xml.etree.ElementTree as ET

# Standard Machine Presets
MACHINE_PRESETS = {
    "LightBurn (Laser)": {
        "cut_color": "#FF0000",        # Red: High-power cut
        "cut_width": "0.1mm",
        "mountain_color": "#0000FF",   # Blue: Medium-power score
        "mountain_dash": "4,2",
        "valley_color": "#00CC00",     # Green: Medium-power score
        "valley_dash": "2,2",
        "text_color": "#000000",       # Black: Engrave/Mark
    },
    "Glowforge (Laser)": {
        "cut_color": "#FF0000",        # Red: Vector Cut
        "cut_width": "0.1mm",
        "mountain_color": "#0000FF",   # Blue: Vector Score
        "mountain_dash": "5,3",
        "valley_color": "#800080",     # Purple: Vector Score
        "valley_dash": "3,3",
        "text_color": "#000000",       # Black: Engrave
    },
    "Cricut / Silhouette (Plotter)": {
        "cut_color": "#FF0000",        # Red: Cut Blade
        "cut_width": "0.2mm",
        "mountain_color": "#0000FF",   # Blue: Scoring Wheel / Stylus
        "mountain_dash": "none",
        "valley_color": "#FF8C00",     # Orange: Scoring Wheel
        "valley_dash": "none",
        "text_color": "#000000",       # Black: Pen tool
    },
    "CNC Plasma / Sheet Metal": {
        "cut_color": "#FF0000",        # Red: Plasma Torch Cut
        "cut_width": "0.5mm",
        "mountain_color": "#0066FF",   # Blue: Scribe / Center-punch / Marker
        "mountain_dash": "none",
        "valley_color": "#009900",     # Green: Scribe / Marker
        "valley_dash": "none",
        "text_color": "#000000",       # Black: Scribe / Stamp text
    },
    "Standard Papercraft (Generic)": {
        "cut_color": "#000000",        # Black solid
        "cut_width": "0.2mm",
        "mountain_color": "#000000",   # Dashed
        "mountain_dash": "5,2",
        "valley_color": "#000000",     # Dot-dashed
        "valley_dash": "2,2",
        "text_color": "#444444",
    }
}


def process_svg_layers(
    svg_filepath,
    preset_name="LightBurn (Laser)",
    material_mode="Sheet Metal",
    use_tabs=False,
    print_bend_angles=True,
    print_seam_numbers=True,
    kerf_offset_mm=0.0
):
    """
    Parses Blender's generated SVG and restructures it into clean, labeled
    vector layers with machine-specific color coding and annotations.
    """
    if not os.path.exists(svg_filepath):
        return False, f"File not found: {svg_filepath}"

    preset = MACHINE_PRESETS.get(preset_name, MACHINE_PRESETS["LightBurn (Laser)"])

    try:
        # Register namespaces to preserve Inkscape and SVG attributes cleanly
        ET.register_namespace("", "http://www.w3.org/2000/svg")
        ET.register_namespace("inkscape", "http://www.inkscape.org/namespaces/inkscape")
        ET.register_namespace("sodipodi", "http://sodipodi.sourceforge.net/DTD/sodipodi-0.dtd")

        tree = ET.parse(svg_filepath)
        root = tree.getroot()

        # Remove default namespace prefixes in tag matching
        def clean_tag(tag):
            return tag.split("}")[-1] if "}" in tag else tag

        # Create structured layer groups
        layer_cut = ET.Element("g", {
            "id": "benforge_cut_paths",
            "{http://www.inkscape.org/namespaces/inkscape}label": "Cut Paths (Outer Perimeter)",
            "{http://www.inkscape.org/namespaces/inkscape}groupmode": "layer",
            "stroke": preset["cut_color"],
            "fill": "none",
            "stroke-width": preset["cut_width"],
            "stroke-linecap": "round",
            "stroke-linejoin": "round"
        })

        layer_mountain = ET.Element("g", {
            "id": "benforge_mountain_folds",
            "{http://www.inkscape.org/namespaces/inkscape}label": "Mountain Folds / Up-Bends",
            "{http://www.inkscape.org/namespaces/inkscape}groupmode": "layer",
            "stroke": preset["mountain_color"],
            "fill": "none",
            "stroke-width": "0.15mm",
            "stroke-dasharray": preset["mountain_dash"]
        })

        layer_valley = ET.Element("g", {
            "id": "benforge_valley_folds",
            "{http://www.inkscape.org/namespaces/inkscape}label": "Valley Folds / Down-Bends",
            "{http://www.inkscape.org/namespaces/inkscape}groupmode": "layer",
            "stroke": preset["valley_color"],
            "fill": "none",
            "stroke-width": "0.15mm",
            "stroke-dasharray": preset["valley_dash"]
        })

        layer_text = ET.Element("g", {
            "id": "benforge_annotations_and_ids",
            "{http://www.inkscape.org/namespaces/inkscape}label": "Bend Angles & Seam IDs",
            "{http://www.inkscape.org/namespaces/inkscape}groupmode": "layer",
            "fill": preset["text_color"],
            "stroke": "none"
        })

        # Categorize existing elements
        elements_to_remove = []
        for elem in list(root):
            tag = clean_tag(elem.tag)
            if tag in ("defs", "style", "metadata"):
                continue

            elem_id = elem.attrib.get("id", "").lower()
            stroke = elem.attrib.get("stroke", "").lower()
            dash = elem.attrib.get("stroke-dasharray", "").lower()
            style = elem.attrib.get("style", "").lower()

            if tag == "text":
                if print_seam_numbers or print_bend_angles:
                    elem.attrib["fill"] = preset["text_color"]
                    layer_text.append(elem)
                elements_to_remove.append(elem)
            elif tag in ("path", "polyline", "polygon", "line", "g"):
                # Detect mountain vs valley vs cut line based on stroke/dash attributes
                is_dash = bool(dash and dash != "none") or "dasharray" in style
                is_tab = "tab" in elem_id or "flap" in elem_id

                if is_tab and not use_tabs and (material_mode in ("Sheet Metal", "EVA Foam")):
                    # In Sheet Metal or Foam mode without tabs, skip tab geometry
                    elements_to_remove.append(elem)
                    continue

                if is_dash or "mountain" in elem_id or "fold" in elem_id:
                    elem.attrib["stroke"] = preset["mountain_color"]
                    elem.attrib["stroke-dasharray"] = preset["mountain_dash"]
                    layer_mountain.append(elem)
                elif "valley" in elem_id:
                    elem.attrib["stroke"] = preset["valley_color"]
                    elem.attrib["stroke-dasharray"] = preset["valley_dash"]
                    layer_valley.append(elem)
                else:
                    elem.attrib["stroke"] = preset["cut_color"]
                    elem.attrib["fill"] = "none"
                    layer_cut.append(elem)
                elements_to_remove.append(elem)

        # Remove raw uncategorized elements from root
        for elem in elements_to_remove:
            try:
                root.remove(elem)
            except ValueError:
                pass

        # Append structured layers in standard CNC cutting order (Text first -> Score/Bend folds -> Outer Cut last)
        root.append(layer_text)
        root.append(layer_mountain)
        root.append(layer_valley)
        root.append(layer_cut)

        # Write formatted SVG back to file
        tree.write(svg_filepath, encoding="utf-8", xml_declaration=True)
        return True, "SVG post-processed into machine layers successfully."
    except Exception as e:
        return False, f"SVG layer processing error: {e}"
