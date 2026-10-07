"""
svg_preview.py
Lightweight, dependency-free preview of the 2D vector patterns produced by the
BenForge unfolding engine. Parses the exported SVG page(s) and renders their
cut/fold polylines onto a Tkinter canvas — no Pillow, cairosvg or external
rasterizer required (Blender's paper-model SVGs use only straight M/L/Z paths).
"""

import os
import re
import xml.etree.ElementTree as ET

import tkinter as tk
import customtkinter as ctk

# Canvas colors per logical layer (tuned for the dark UI).
LAYER_STYLE = {
    "cut":      {"color": "#FF5252", "width": 1.6, "dash": None},
    "mountain": {"color": "#4FC3F7", "width": 1.0, "dash": (5, 3)},
    "valley":   {"color": "#81C784", "width": 1.0, "dash": (2, 3)},
    "tab":      {"color": "#B0BEC5", "width": 1.0, "dash": None},
}

_NUM = re.compile(r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?")


def _clean_tag(tag):
    return tag.split("}")[-1] if "}" in tag else tag


def _classify(cls, hint, stroke):
    """Map an element's class / ancestor-group hint / stroke to a layer key."""
    cls = (cls or "").lower()
    hint = (hint or "").lower()
    if "sticker" in cls or "tab" in hint:
        return "tab"
    if "convex" in cls or "mountain" in hint:
        return "mountain"
    if "concave" in cls or "valley" in hint:
        return "valley"
    # outer perimeter, explicit cut layer, or anything unclassified -> cut
    return "cut"


def _parse_path_d(d):
    """Return a list of subpaths; each subpath is a list of (x, y) points.

    Only M/L/Z commands are emitted by the paper-model exporter, so a simple
    command tokenizer is sufficient. Z closes the current subpath back to its
    start point.
    """
    subpaths = []
    current = []
    start = None
    i = 0
    tokens = re.findall(r"[MLZmlz]|[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?", d or "")
    cmd = None
    while i < len(tokens):
        t = tokens[i]
        if t in "MLmlZz":
            cmd = t
            if cmd in "Zz":
                if current and start is not None:
                    current.append(start)
                if len(current) > 1:
                    subpaths.append(current)
                current = []
                start = None
            i += 1
            continue
        # coordinate pair under the active command
        if cmd in ("M", "m", "L", "l") and i + 1 < len(tokens):
            try:
                x = float(tokens[i]); y = float(tokens[i + 1])
            except ValueError:
                i += 1
                continue
            if cmd in ("M", "m"):
                if len(current) > 1:
                    subpaths.append(current)
                current = [(x, y)]
                start = (x, y)
                cmd = "L" if cmd == "M" else "l"  # subsequent pairs are line-to
            else:
                current.append((x, y))
            i += 2
        else:
            i += 1
    if len(current) > 1:
        subpaths.append(current)
    return subpaths


def parse_svg(path):
    """Parse one SVG file into a dict: {width, height, strokes, labels}.

    strokes: list of (layer_key, [(x, y), ...]) polylines in SVG user units (mm).
    labels:  list of (x, y, text).
    """
    tree = ET.parse(path)
    root = tree.getroot()

    # View box / document size (user units == millimeters for these exports).
    w = h = None
    vb = root.attrib.get("viewBox")
    if vb:
        nums = _NUM.findall(vb)
        if len(nums) == 4:
            w, h = float(nums[2]), float(nums[3])
    if w is None:
        wn = _NUM.findall(root.attrib.get("width", "") or "")
        hn = _NUM.findall(root.attrib.get("height", "") or "")
        w = float(wn[0]) if wn else 300.0
        h = float(hn[0]) if hn else 400.0

    strokes = []
    labels = []

    def walk(elem, hint):
        tag = _clean_tag(elem.tag)
        if tag in ("g", "svg", "a", "switch"):
            new_hint = " ".join(filter(None, [
                hint,
                elem.attrib.get("id", ""),
                elem.attrib.get("{http://www.inkscape.org/namespaces/inkscape}label", ""),
            ]))
            for child in list(elem):
                walk(child, new_hint)
            return
        if tag == "path":
            layer = _classify(elem.attrib.get("class"), hint, elem.attrib.get("stroke"))
            for sub in _parse_path_d(elem.attrib.get("d", "")):
                strokes.append((layer, sub))
        elif tag in ("polygon", "polyline"):
            layer = _classify(elem.attrib.get("class"), hint, elem.attrib.get("stroke"))
            nums = _NUM.findall(elem.attrib.get("points", ""))
            pts = [(float(nums[k]), float(nums[k + 1])) for k in range(0, len(nums) - 1, 2)]
            if tag == "polygon" and len(pts) > 1:
                pts.append(pts[0])
            if len(pts) > 1:
                strokes.append((layer, pts))
        elif tag == "line":
            layer = _classify(elem.attrib.get("class"), hint, elem.attrib.get("stroke"))
            try:
                p = [(float(elem.attrib["x1"]), float(elem.attrib["y1"])),
                     (float(elem.attrib["x2"]), float(elem.attrib["y2"]))]
                strokes.append((layer, p))
            except (KeyError, ValueError):
                pass
        elif tag == "text":
            try:
                x = float(_NUM.findall(elem.attrib.get("x", "0"))[0])
                y = float(_NUM.findall(elem.attrib.get("y", "0"))[0])
                txt = "".join(elem.itertext()).strip()
                if txt:
                    labels.append((x, y, txt))
            except (IndexError, ValueError):
                pass

    walk(root, "")
    return {"width": w, "height": h, "strokes": strokes, "labels": labels}


class PatternPreview(ctk.CTkToplevel):
    """A window that renders exported pattern page(s) onto a zoomable canvas."""

    def __init__(self, master, svg_files, title="Pattern Preview"):
        super().__init__(master)
        self.title(title)
        self.geometry("900x820")
        self.minsize(560, 520)

        self.svg_files = list(svg_files)
        self.pages = []           # parsed page dicts (lazy)
        self.page_index = 0
        self.show_labels = tk.BooleanVar(value=False)

        # --- Top control bar ---
        bar = ctk.CTkFrame(self)
        bar.pack(fill="x", padx=10, pady=(10, 4))

        self.btn_prev = ctk.CTkButton(bar, text="◀ Prev", width=80, command=self._prev)
        self.btn_prev.pack(side="left", padx=(8, 4), pady=8)
        self.lbl_page = ctk.CTkLabel(bar, text="Page 1 / 1", width=120)
        self.lbl_page.pack(side="left", padx=4)
        self.btn_next = ctk.CTkButton(bar, text="Next ▶", width=80, command=self._next)
        self.btn_next.pack(side="left", padx=(4, 12))

        ctk.CTkCheckBox(bar, text="Show IDs / angles", variable=self.show_labels,
                        command=self._render).pack(side="left", padx=8)

        # Legend
        legend = ctk.CTkFrame(bar, fg_color="transparent")
        legend.pack(side="right", padx=10)
        for key, label in (("cut", "Cut"), ("mountain", "Up / Mountain"), ("valley", "Down / Valley")):
            dot = ctk.CTkLabel(legend, text="  ", fg_color=LAYER_STYLE[key]["color"],
                               corner_radius=3, width=16)
            dot.pack(side="left", padx=(8, 3))
            ctk.CTkLabel(legend, text=label, font=ctk.CTkFont(size=11)).pack(side="left")

        # --- Canvas ---
        self.canvas = tk.Canvas(self, bg="#15151b", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True, padx=10, pady=(4, 4))
        self.canvas.bind("<Configure>", lambda e: self._render())

        self.status = ctk.CTkLabel(self, text="", text_color="gray70", font=ctk.CTkFont(size=11))
        self.status.pack(fill="x", padx=12, pady=(0, 8))

        self.after(60, self._first_render)

    # -- page management --
    def _get_page(self, idx):
        while len(self.pages) <= idx:
            self.pages.append(None)
        if self.pages[idx] is None:
            try:
                self.pages[idx] = parse_svg(self.svg_files[idx])
            except Exception as e:
                self.pages[idx] = {"width": 300, "height": 400, "strokes": [],
                                   "labels": [], "error": str(e)}
        return self.pages[idx]

    def _first_render(self):
        self.lift()
        self.focus_force()
        self._render()

    def _prev(self):
        if self.page_index > 0:
            self.page_index -= 1
            self._render()

    def _next(self):
        if self.page_index < len(self.svg_files) - 1:
            self.page_index += 1
            self._render()

    def _render(self):
        self.canvas.delete("all")
        n = len(self.svg_files)
        self.lbl_page.configure(text=f"Page {self.page_index + 1} / {n}")
        self.btn_prev.configure(state="normal" if self.page_index > 0 else "disabled")
        self.btn_next.configure(state="normal" if self.page_index < n - 1 else "disabled")

        page = self._get_page(self.page_index)
        cw = max(self.canvas.winfo_width(), 50)
        ch = max(self.canvas.winfo_height(), 50)
        pw, ph = page["width"] or 300, page["height"] or 400
        margin = 24
        scale = min((cw - 2 * margin) / pw, (ch - 2 * margin) / ph)
        if scale <= 0:
            scale = 1.0
        off_x = (cw - pw * scale) / 2
        off_y = (ch - ph * scale) / 2

        def tx(x, y):
            return (off_x + x * scale, off_y + y * scale)

        # Sheet background (white page under the dark canvas)
        x0, y0 = tx(0, 0)
        x1, y1 = tx(pw, ph)
        self.canvas.create_rectangle(x0, y0, x1, y1, fill="#fafafa", outline="#555555")

        if page.get("error"):
            self.canvas.create_text(cw / 2, ch / 2, fill="#E57373",
                                    text=f"Could not render page:\n{page['error']}",
                                    font=("TkDefaultFont", 12), justify="center")
            return

        # Draw folds first, cut lines last (so cuts sit on top).
        order = {"tab": 0, "valley": 1, "mountain": 2, "cut": 3}
        counts = {}
        for layer, pts in sorted(page["strokes"], key=lambda s: order.get(s[0], 3)):
            counts[layer] = counts.get(layer, 0) + 1
            style = LAYER_STYLE.get(layer, LAYER_STYLE["cut"])
            flat = []
            for (x, y) in pts:
                cx, cy = tx(x, y)
                flat.extend((cx, cy))
            if len(flat) >= 4:
                kwargs = {"fill": style["color"], "width": style["width"]}
                if style["dash"]:
                    kwargs["dash"] = style["dash"]
                self.canvas.create_line(*flat, **kwargs)

        if self.show_labels.get():
            for (x, y, txt) in page["labels"]:
                cx, cy = tx(x, y)
                self.canvas.create_text(cx, cy, text=txt, fill="#333333",
                                        font=("TkDefaultFont", max(6, int(3.0 * scale))))

        n_cut = counts.get("cut", 0)
        n_fold = counts.get("mountain", 0) + counts.get("valley", 0)
        self.status.configure(
            text=f"{os.path.basename(self.svg_files[self.page_index])}  •  "
                 f"{pw:.0f} × {ph:.0f} mm  •  {n_cut} cut, {n_fold} fold line(s)"
        )
