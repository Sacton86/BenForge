"""
app.py
BenForge — 3D Pattern Unfolder & Metal/Armor Fabrication Suite
GUI frontend for converting 3D meshes into flattened 2D vector cut & bend patterns.
"""

import os
import sys
import json
import glob
import math
import shutil
import tempfile
import platform
import subprocess
import threading
import tkinter as tk
from tkinter import filedialog, messagebox
import customtkinter as ctk

from tooltip import ToolTip, attach_tooltip

try:
    from svg_preview import PatternPreview
except Exception:
    PatternPreview = None

# Polygon-budget tuning for the decimation slider. The slider selects a TARGET
# face count (not a fixed ratio), mapped logarithmically so it works whether a
# model has 5k or 5M faces. The actual decimate ratio is target / poly_count.
TARGET_FACES_MIN = 200       # slider far-left: coarsest usable net
TARGET_FACES_MAX = 100000    # slider far-right: very detailed (slow to unfold)
RECOMMENDED_FACES = 2500     # auto-selected budget on model load
HEAVY_FACES_WARN = 8000      # warn/confirm above this many faces
MIN_DECIMATE_RATIO = 0.0002  # smallest ratio we will ask Blender to apply

# Application Metadata
APP_NAME = "BenForge"
VERSION = "v1.0.0-dev"
version_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "VERSION.txt")
if os.path.exists(version_file):
    try:
        with open(version_file, "r", encoding="utf-8") as f:
            v_content = f.read().strip()
            if v_content:
                VERSION = v_content
    except Exception:
        pass


class BenForgeApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title(f"{APP_NAME} — 3D Fabrication & Pattern Suite ({VERSION})")
        self.geometry("820x920")
        self.minsize(760, 700)
        ctk.set_appearance_mode("Dark")
        ctk.set_default_color_theme("blue")

        self.input_file = None
        self.last_output_file = None
        self.last_output_files = []   # all pages produced by the last export
        self.preview_files = []       # pages produced by the last preview run
        self.is_processing = False
        self.mesh_info = None  # Holds original bounding box and polycount
        self.blender_bin = self._resolve_blender_binary()

        # Build UI and Menus
        self._build_menu_bar()
        self._build_ui()
        self._update_engine_status()
        self._apply_material_preset("Sheet Metal (Press Brake / Weld)")

    def _resolve_blender_binary(self):
        """Finds Blender executable across development, portable, and system locations."""
        base_dir = os.path.dirname(os.path.abspath(__file__))
        is_windows = platform.system() == "Windows"

        # 1. PyInstaller extracted bundle (_MEIPASS)
        if hasattr(sys, "_MEIPASS"):
            if is_windows:
                p = os.path.join(sys._MEIPASS, "engine", "blender_portable", "blender.exe")
                if os.path.exists(p):
                    return p
            else:
                p = os.path.join(sys._MEIPASS, "engine", "blender_linux", "blender")
                if os.path.exists(p):
                    return p

        # 2. Local bundled portable engine (search base_dir, parent dir, cwd, and project dir)
        engine_dirs = [
            os.path.join(base_dir, "engine"),
            os.path.join(base_dir, "..", "engine"),
            os.path.join(os.getcwd(), "engine"),
            "/home/sacton3/Desktop/BenForge/engine",
            "/home/sacton3/Desktop/BenFold/engine"
        ]
        for ed in engine_dirs:
            if is_windows:
                p = os.path.join(ed, "blender_portable", "blender.exe")
                if os.path.exists(p):
                    return p
            else:
                p = os.path.join(ed, "blender_linux", "blender")
                if os.path.exists(p) and os.access(p, os.X_OK):
                    return p

        # 3. System PATH detection
        system_blender = shutil.which("blender.exe" if is_windows else "blender")
        if system_blender:
            return system_blender

        # 4. Standard Linux locations
        if not is_windows:
            candidates = [
                "/usr/bin/blender",
                "/usr/local/bin/blender",
                "/snap/bin/blender",
                "/var/lib/flatpak/exports/bin/org.blender.Blender",
                os.path.expanduser("~/.local/bin/blender"),
                os.path.expanduser("~/blender/blender"),
                os.path.expanduser("~/.local/share/flatpak/exports/bin/org.blender.Blender")
            ]
            for c in candidates:
                if os.path.exists(c) and os.access(c, os.X_OK):
                    return c
                    return c
        else:
            win_candidates = [
                r"C:\Program Files\Blender Foundation\Blender 4.2\blender.exe",
                r"C:\Program Files\Blender Foundation\Blender 4.1\blender.exe",
                r"C:\Program Files\Blender Foundation\Blender 4.0\blender.exe",
                r"C:\Program Files\Blender Foundation\Blender 3.6\blender.exe",
            ]
            for c in win_candidates:
                if os.path.exists(c):
                    return c

        return None

    def _build_menu_bar(self):
        """Builds native top menu bar with File, Presets, Settings, and Help."""
        menubar = tk.Menu(self)

        # File Menu
        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(label="Open 3D Mesh... (Ctrl+O)", command=self.select_file)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.quit)
        menubar.add_cascade(label="File", menu=file_menu)

        # Presets Menu
        presets_menu = tk.Menu(menubar, tearoff=0)
        presets_menu.add_command(
            label="Sheet Metal (Plasma / Laser / Brake)",
            command=lambda: self._apply_material_preset("Sheet Metal (Press Brake / Weld)")
        )
        presets_menu.add_command(
            label="EVA Foam Armor (Bevels, No Tabs)",
            command=lambda: self._apply_material_preset("EVA Foam (Bevel Glue)")
        )
        presets_menu.add_command(
            label="LightBurn Laser Cutter",
            command=lambda: self._apply_machine_preset("LightBurn (Laser)")
        )
        presets_menu.add_command(
            label="Glowforge Laser Cutter",
            command=lambda: self._apply_machine_preset("Glowforge (Laser)")
        )
        presets_menu.add_command(
            label="Cricut / Plotter Cutter",
            command=lambda: self._apply_machine_preset("Cricut / Silhouette (Plotter)")
        )
        presets_menu.add_command(
            label="Papercraft / Cardboard (Tabs & Seams)",
            command=lambda: self._apply_material_preset("Papercraft / Cardboard")
        )
        menubar.add_cascade(label="Presets", menu=presets_menu)

        # Settings / Preferences Menu
        self.pref_tooltips_var = tk.BooleanVar(value=True)
        pref_menu = tk.Menu(menubar, tearoff=0)
        pref_menu.add_checkbutton(
            label="Show Helpful Tooltips",
            variable=self.pref_tooltips_var,
            command=self._on_toggle_tooltips_menu
        )
        pref_menu.add_separator()
        pref_menu.add_command(label="Locate Blender Binary...", command=self._manual_locate_blender)
        menubar.add_cascade(label="Settings", menu=pref_menu)

        # Help Menu
        help_menu = tk.Menu(menubar, tearoff=0)
        help_menu.add_command(label=f"About {APP_NAME}", command=self._show_about)
        menubar.add_cascade(label="Help", menu=help_menu)

        self.config(menu=menubar)
        self.bind("<Control-o>", lambda e: self.select_file())

    def _show_about(self):
        messagebox.showinfo(
            f"About {APP_NAME}",
            f"{APP_NAME} — 3D Pattern Unfolder & Metal/Armor Suite\n"
            f"Version: {VERSION}\n\n"
            "Converts 3D STL & OBJ meshes into flattened 2D vector patterns for:\n"
            "• CNC Sheet Metal & Press Brake Bending\n"
            "• Laser Cutters (LightBurn, Glowforge)\n"
            "• EVA Foam Armor & Cosplay\n"
            "• Papercraft & Cardboard Prototyping\n\n"
            "Powered by CustomTkinter & Headless Blender Engine."
        )

    def _on_toggle_tooltips_menu(self):
        enabled = self.pref_tooltips_var.get()
        ToolTip.enabled = enabled
        self.switch_tooltips_header.set(enabled)

    def _on_toggle_tooltips_switch(self):
        enabled = bool(self.switch_tooltips_header.get())
        ToolTip.enabled = enabled
        self.pref_tooltips_var.set(enabled)

    def _build_ui(self):
        # Top Scrollable Container to fit all controls comfortably
        self.scroll_canvas = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self.scroll_canvas.pack(fill="both", expand=True, padx=10, pady=5)

        # 1. Header Banner
        self.header_frame = ctk.CTkFrame(self.scroll_canvas, fg_color="transparent")
        self.header_frame.pack(fill="x", padx=15, pady=(10, 5))

        self.lbl_title = ctk.CTkLabel(
            self.header_frame, 
            text=f"{APP_NAME} — 3D Pattern Unfolder & Fabrication Suite", 
            font=ctk.CTkFont(size=22, weight="bold")
        )
        self.lbl_title.pack(side="left", anchor="w")

        # Quick Tooltip Switch on Header
        self.switch_tooltips_header = ctk.CTkSwitch(
            self.header_frame,
            text="Tooltips",
            command=self._on_toggle_tooltips_switch,
            width=70,
            font=ctk.CTkFont(size=12)
        )
        self.switch_tooltips_header.select()
        self.switch_tooltips_header.pack(side="right", padx=5)
        attach_tooltip(self.switch_tooltips_header, "Toggle hover tooltips across the entire application on or off.")

        self.sub_header = ctk.CTkLabel(
            self.scroll_canvas, 
            text="Unfold 3D models into 2D cut sheets with bend angles, weld seams, and machine-coded vector layers.", 
            text_color="gray70",
            font=ctk.CTkFont(size=12)
        )
        self.sub_header.pack(anchor="w", padx=15, pady=(0, 6))

        # 2. Engine Status Bar
        self.engine_card = ctk.CTkFrame(self.scroll_canvas, height=36)
        self.engine_card.pack(fill="x", padx=15, pady=(2, 8))

        self.lbl_engine = ctk.CTkLabel(
            self.engine_card,
            text="Locating Blender unfolding engine...",
            font=ctk.CTkFont(size=12)
        )
        self.lbl_engine.pack(side="left", padx=12, pady=5)

        self.btn_browse_blender = ctk.CTkButton(
            self.engine_card,
            text="Locate Blender...",
            width=110,
            height=26,
            font=ctk.CTkFont(size=11),
            command=self._manual_locate_blender
        )
        self.btn_browse_blender.pack(side="right", padx=10, pady=5)
        attach_tooltip(self.btn_browse_blender, "Manually choose your local Blender executable if not auto-detected.")

        # 3. Card: File Selection & Mesh Inspector
        self.file_card = ctk.CTkFrame(self.scroll_canvas)
        self.file_card.pack(fill="x", padx=15, pady=6)

        file_top = ctk.CTkFrame(self.file_card, fg_color="transparent")
        file_top.pack(fill="x", padx=12, pady=(10, 4))

        self.btn_select = ctk.CTkButton(
            file_top, 
            text="1. Select 3D Mesh (.stl / .obj)", 
            command=self.select_file,
            width=230,
            height=36,
            font=ctk.CTkFont(weight="bold")
        )
        self.btn_select.pack(side="left")
        attach_tooltip(self.btn_select, "Select a 3D model (.stl or .obj) representing armor, helmet, or sheet metal part.")

        self.lbl_filename = ctk.CTkLabel(
            file_top, 
            text="No model loaded", 
            text_color="gray60",
            font=ctk.CTkFont(size=13, weight="bold")
        )
        self.lbl_filename.pack(side="left", padx=12)

        # Mesh Inspector details subframe
        self.inspect_frame = ctk.CTkFrame(self.file_card, fg_color="#181820", corner_radius=6)
        self.inspect_frame.pack(fill="x", padx=12, pady=(4, 10))

        self.lbl_inspect_dims = ctk.CTkLabel(
            self.inspect_frame,
            text="Model Dimensions: — | Polygons: —",
            text_color="gray75",
            font=ctk.CTkFont(size=12)
        )
        self.lbl_inspect_dims.pack(anchor="w", padx=10, pady=6)
        attach_tooltip(self.inspect_frame, "Displays live 3D bounding box dimensions (Width × Depth × Height) and polygon complexity.")

        # 4. Card: Anatomical Fitment & Scaling System (Full Body / Any Part)
        self.fit_card = ctk.CTkFrame(self.scroll_canvas)
        self.fit_card.pack(fill="x", padx=15, pady=6)

        lbl_fit_header = ctk.CTkLabel(
            self.fit_card,
            text="Anatomical Fitment & Real-World Sizing:",
            font=ctk.CTkFont(size=13, weight="bold")
        )
        lbl_fit_header.pack(anchor="w", padx=12, pady=(10, 4))

        row_fit1 = ctk.CTkFrame(self.fit_card, fg_color="transparent")
        row_fit1.pack(fill="x", padx=12, pady=4)

        ctk.CTkLabel(row_fit1, text="Body / Part Type:").pack(side="left", padx=(0, 6))
        self.opt_part_type = ctk.CTkOptionMenu(
            row_fit1,
            values=[
                "Head / Helmet",
                "Torso / Breastplate / Cuirass",
                "Shoulder / Pauldron",
                "Arm / Gauntlet / Vambrace",
                "Waist / Faulds / Tassets",
                "Leg / Greave / Cuisses",
                "Foot / Sabaton / Boot",
                "Custom Part / Free Dimension"
            ],
            command=self._on_part_type_changed,
            width=220
        )
        self.opt_part_type.set("Head / Helmet")
        self.opt_part_type.pack(side="left", padx=(0, 20))
        attach_tooltip(self.opt_part_type, "Select anatomical body location to configure dimension and clearance guidelines.")

        ctk.CTkLabel(row_fit1, text="Units:").pack(side="left", padx=(0, 6))
        self.opt_unit = ctk.CTkOptionMenu(
            row_fit1,
            values=["Millimeters (mm)", "Centimeters (cm)", "Inches (in)"],
            command=self._on_unit_changed,
            width=150
        )
        self.opt_unit.set("Millimeters (mm)")
        self.opt_unit.pack(side="left")
        attach_tooltip(self.opt_unit, "Select measurement unit used for sizing inputs and sheet stock.")

        # Row Fit 2: Target Sizing & Padding Clearance
        row_fit2 = ctk.CTkFrame(self.fit_card, fg_color="transparent")
        row_fit2.pack(fill="x", padx=12, pady=(4, 10))

        self.switch_autofit = ctk.CTkSwitch(
            row_fit2,
            text="Scale to Target Fit",
            command=self._update_scale_calculation,
            font=ctk.CTkFont(weight="bold")
        )
        self.switch_autofit.select()
        self.switch_autofit.pack(side="left", padx=(0, 15))
        attach_tooltip(self.switch_autofit, "Enable to automatically scale the 3D model to your specified target dimension. Leave off for 1:1 original CAD scale.")

        self.lbl_target_dim = ctk.CTkLabel(row_fit2, text="Target Height (mm):")
        self.lbl_target_dim.pack(side="left", padx=(0, 5))

        self.entry_target_dim = ctk.CTkEntry(row_fit2, width=80)
        self.entry_target_dim.insert(0, "290.0")
        self.entry_target_dim.pack(side="left", padx=(0, 15))
        self.entry_target_dim.bind("<KeyRelease>", lambda e: self._update_scale_calculation())
        attach_tooltip(self.entry_target_dim, "Desired final dimension of the assembled piece in chosen units (e.g., 290 mm for adult helmet height).")

        ctk.CTkLabel(row_fit2, text="Padding / Allowance:").pack(side="left", padx=(0, 5))
        self.entry_padding = ctk.CTkEntry(row_fit2, width=65)
        self.entry_padding.insert(0, "+10mm")
        self.entry_padding.pack(side="left", padx=(0, 15))
        self.entry_padding.bind("<KeyRelease>", lambda e: self._update_scale_calculation())
        attach_tooltip(self.entry_padding, "Extra clearance allowance for gambeson, foam liner, or clothing (e.g., '+10mm' or '+5%').")

        self.lbl_calculated_scale = ctk.CTkLabel(
            row_fit2,
            text="Scale: 1.000x (100%)",
            text_color="#64B5F6",
            font=ctk.CTkFont(weight="bold")
        )
        self.lbl_calculated_scale.pack(side="left")
        attach_tooltip(self.lbl_calculated_scale, "Resulting uniform scale multiplier applied to the mesh before unfolding.")

        # 5. Card: Mesh Optimization (Decimation)
        self.decimate_card = ctk.CTkFrame(self.scroll_canvas)
        self.decimate_card.pack(fill="x", padx=15, pady=6)

        dec_header = ctk.CTkFrame(self.decimate_card, fg_color="transparent")
        dec_header.pack(fill="x", padx=12, pady=(10, 2))

        self.lbl_decimate = ctk.CTkLabel(
            dec_header,
            text="Target Pattern Complexity (polygon budget):",
            font=ctk.CTkFont(size=13, weight="bold")
        )
        self.lbl_decimate.pack(side="left")

        self.btn_auto_poly = ctk.CTkButton(
            dec_header,
            text="Auto",
            width=60,
            height=24,
            font=ctk.CTkFont(size=11),
            command=self._auto_set_decimation
        )
        self.btn_auto_poly.pack(side="right")
        attach_tooltip(self.btn_auto_poly, f"Automatically pick a sensible polygon budget (~{RECOMMENDED_FACES:,} faces) for a cleanly cuttable pattern.")

        # Slider position is 0..1, mapped logarithmically to a target face count.
        self.slider_poly = ctk.CTkSlider(
            self.decimate_card,
            from_=0.0,
            to=1.0,
            number_of_steps=200,
            command=self._update_slider_label
        )
        self.slider_poly.set(self._target_to_pos(RECOMMENDED_FACES))
        self.slider_poly.pack(fill="x", padx=12, pady=5)
        attach_tooltip(self.slider_poly, "Fewer polygons (left) = simpler, faster, more practical to cut/fold. More (right) = finer detail but slower to unfold.")

        self.lbl_slider_val = ctk.CTkLabel(
            self.decimate_card,
            text=f"Target ≈ {RECOMMENDED_FACES:,} faces (load a model to calibrate)",
            text_color="gray70",
            font=ctk.CTkFont(size=12)
        )
        self.lbl_slider_val.pack(anchor="w", padx=12, pady=(0, 10))

        # 6. Card: Material & Fabrication Settings
        self.mat_card = ctk.CTkFrame(self.scroll_canvas)
        self.mat_card.pack(fill="x", padx=15, pady=6)

        lbl_mat_header = ctk.CTkLabel(
            self.mat_card,
            text="Material Mode & Machine Profile:",
            font=ctk.CTkFont(size=13, weight="bold")
        )
        lbl_mat_header.pack(anchor="w", padx=12, pady=(10, 4))

        row_mat1 = ctk.CTkFrame(self.mat_card, fg_color="transparent")
        row_mat1.pack(fill="x", padx=12, pady=4)

        ctk.CTkLabel(row_mat1, text="Material:").pack(side="left", padx=(0, 6))
        self.opt_material = ctk.CTkOptionMenu(
            row_mat1,
            values=[
                "Sheet Metal (Press Brake / Weld)",
                "EVA Foam (Bevel Glue)",
                "Papercraft / Cardboard"
            ],
            command=self._apply_material_preset,
            width=240
        )
        self.opt_material.set("Sheet Metal (Press Brake / Weld)")
        self.opt_material.pack(side="left", padx=(0, 20))
        attach_tooltip(self.opt_material, "Sheet Metal: No glue tabs, includes bend angle notations for press brake.\nEVA Foam: Edge-to-edge bevel cuts.\nPaper: Includes folding glue tabs.")

        ctk.CTkLabel(row_mat1, text="Machine Preset:").pack(side="left", padx=(0, 6))
        self.opt_machine = ctk.CTkOptionMenu(
            row_mat1,
            values=[
                "LightBurn (Laser)",
                "Glowforge (Laser)",
                "Cricut / Silhouette (Plotter)",
                "CNC Plasma / Sheet Metal",
                "Standard Papercraft (Generic)"
            ],
            width=210
        )
        self.opt_machine.set("LightBurn (Laser)")
        self.opt_machine.pack(side="left")
        attach_tooltip(self.opt_machine, "Formats vector SVG strokes and layer colors for specific laser or CNC software.")

        # Row Mat 2: Tabs and Seam Details
        row_mat2 = ctk.CTkFrame(self.mat_card, fg_color="transparent")
        row_mat2.pack(fill="x", padx=12, pady=(4, 10))

        self.switch_tabs = ctk.CTkSwitch(
            row_mat2,
            text="Glue Tabs",
            font=ctk.CTkFont(size=12)
        )
        self.switch_tabs.pack(side="left", padx=(0, 15))
        attach_tooltip(self.switch_tabs, "Toggle glue flaps. Typically OFF for sheet metal welding and EVA foam; ON for paper/cardboard.")

        self.lbl_tab_width = ctk.CTkLabel(row_mat2, text="Tab Width (mm):")
        self.lbl_tab_width.pack(side="left", padx=(0, 5))

        self.entry_tab = ctk.CTkEntry(row_mat2, width=65)
        self.entry_tab.insert(0, "5.0")
        self.entry_tab.pack(side="left", padx=(0, 20))
        attach_tooltip(self.entry_tab, "Width of assembly tabs in mm.")

        self.chk_bend_angles = ctk.CTkCheckBox(row_mat2, text="Print Bend/Bevel Angles")
        self.chk_bend_angles.select()
        self.chk_bend_angles.pack(side="left", padx=(0, 15))
        attach_tooltip(self.chk_bend_angles, "Prints dihedral bend angles (e.g. '45° UP', '30° DOWN') along folds for press brake and bevel blades.")

        self.chk_seam_numbers = ctk.CTkCheckBox(row_mat2, text="Print Seam / Weld IDs")
        self.chk_seam_numbers.select()
        self.chk_seam_numbers.pack(side="left", padx=(0, 15))
        attach_tooltip(self.chk_seam_numbers, "Prints matching edge numbers along seams to guide tack welding and assembly sequence.")

        self.lbl_kerf = ctk.CTkLabel(row_mat2, text="Kerf (mm):")
        self.lbl_kerf.pack(side="left", padx=(0, 4))
        self.entry_kerf = ctk.CTkEntry(row_mat2, width=50)
        self.entry_kerf.insert(0, "0.0")
        self.entry_kerf.pack(side="left")
        attach_tooltip(self.entry_kerf, "Cutter beam width offset (e.g. 0.1mm for laser, 0.5mm for plasma).")

        # 7. Card: Sheet Stock & Bed Layout
        self.sheet_card = ctk.CTkFrame(self.scroll_canvas)
        self.sheet_card.pack(fill="x", padx=15, pady=6)

        lbl_sheet_header = ctk.CTkLabel(
            self.sheet_card,
            text="Sheet Stock & Vector Format:",
            font=ctk.CTkFont(size=13, weight="bold")
        )
        lbl_sheet_header.pack(anchor="w", padx=12, pady=(10, 4))

        row_sheet = ctk.CTkFrame(self.sheet_card, fg_color="transparent")
        row_sheet.pack(fill="x", padx=12, pady=(4, 10))

        ctk.CTkLabel(row_sheet, text="Sheet / Bed Size:").pack(side="left", padx=(0, 6))
        self.opt_page = ctk.CTkOptionMenu(
            row_sheet,
            values=[
                "A3",
                "A4",
                "A2",
                "A1",
                "LETTER",
                "LEGAL",
                "600x400mm (Laser)",
                "24x12in (Sheet)",
                "24x24in (Sheet)",
                "48x24in (Sheet)"
            ],
            width=160
        )
        self.opt_page.set("A3")
        self.opt_page.pack(side="left", padx=(0, 20))
        attach_tooltip(self.opt_page, "Target sheet or cutting bed dimensions. Patterns will be arranged to fit this stock.")

        ctk.CTkLabel(row_sheet, text="Format:").pack(side="left", padx=(0, 6))
        self.opt_export_fmt = ctk.CTkOptionMenu(row_sheet, values=["SVG", "PDF"], width=90)
        self.opt_export_fmt.set("SVG")
        self.opt_export_fmt.pack(side="left", padx=(0, 20))
        attach_tooltip(self.opt_export_fmt, "SVG: Recommended for laser and CNC machines.\nPDF: Recommended for paper printers.")

        self.switch_join = ctk.CTkSwitch(row_sheet, text="Auto-join multi-part meshes")
        self.switch_join.select()
        self.switch_join.pack(side="left")
        attach_tooltip(self.switch_join, "Combines separate sub-meshes (e.g. cheek plates, visor, dome) into one piece before unfolding.")

        # 8. Card: Action Area, Progress, and Post-Export Buttons
        self.action_card = ctk.CTkFrame(self.scroll_canvas, fg_color="transparent")
        self.action_card.pack(fill="x", padx=15, pady=(12, 10))

        action_row = ctk.CTkFrame(self.action_card, fg_color="transparent")
        action_row.pack(fill="x")

        self.btn_preview = ctk.CTkButton(
            action_row,
            text="👁  Preview Pattern",
            command=self.preview_model,
            fg_color="#3a4a5a",
            hover_color="#2b3a4a",
            height=46,
            width=190,
            font=ctk.CTkFont(size=14, weight="bold"),
            state="disabled"
        )
        self.btn_preview.pack(side="left", padx=(0, 8))
        attach_tooltip(self.btn_preview, "Unfold with the current settings and view the resulting 2D cut/fold pattern on screen — without saving a file yet.")

        self.btn_process = ctk.CTkButton(
            action_row,
            text="2. Unfold & Export Vector Pattern",
            command=self.process_model,
            fg_color="#1f6aa5",
            hover_color="#144f7d",
            height=46,
            font=ctk.CTkFont(size=16, weight="bold"),
            state="disabled"
        )
        self.btn_process.pack(side="left", fill="x", expand=True)
        attach_tooltip(self.btn_process, "Executes the headless Blender engine to decimate, calculate seams, and generate 2D vector patterns.")

        self.progress_bar = ctk.CTkProgressBar(self.action_card, mode="indeterminate")
        self.progress_bar.pack(fill="x", pady=(10, 4))
        self.progress_bar.set(0)

        self.status_lbl = ctk.CTkLabel(
            self.action_card, 
            text="Ready. Select a 3D mesh model to begin.", 
            text_color="gray70", 
            font=ctk.CTkFont(size=12)
        )
        self.status_lbl.pack(pady=2)

        # Post-Export Quick Actions Frame (hidden until export succeeds)
        self.post_export_frame = ctk.CTkFrame(self.action_card, fg_color="transparent")

        self.btn_open_folder = ctk.CTkButton(
            self.post_export_frame,
            text="Open Output Folder",
            width=160,
            command=self._open_output_folder,
            fg_color="#2b3a4a"
        )
        self.btn_open_folder.pack(side="left", padx=10)

        self.btn_open_file = ctk.CTkButton(
            self.post_export_frame,
            text="Open Vector Pattern",
            width=160,
            command=self._open_pattern_file,
            fg_color="#2b3a4a"
        )
        self.btn_open_file.pack(side="left", padx=10)

        self.btn_preview_result = ctk.CTkButton(
            self.post_export_frame,
            text="👁  Preview Result",
            width=160,
            command=self._preview_last_export,
            fg_color="#2b3a4a"
        )
        self.btn_preview_result.pack(side="left", padx=10)

    def _set_actions_enabled(self, enabled):
        """Enable/disable the Preview and Export buttons together."""
        state = "normal" if enabled else "disabled"
        self.btn_process.configure(state=state)
        self.btn_preview.configure(state=state)

    def _update_engine_status(self):
        if self.blender_bin:
            short_path = self.blender_bin
            if len(short_path) > 50:
                short_path = "..." + short_path[-46:]
            self.lbl_engine.configure(
                text=f"Blender Engine Connected: {short_path}",
                text_color="#2FA572"
            )
            self.btn_browse_blender.configure(text="Change...")
        else:
            self.lbl_engine.configure(
                text="Blender Engine: Not Found (Click 'Locate Blender' to select)",
                text_color="#E57373"
            )
            self.btn_browse_blender.configure(text="Locate Blender...")

    def _manual_locate_blender(self):
        is_windows = platform.system() == "Windows"
        filetypes = [("Blender Executable", "blender.exe")] if is_windows else [("All Files", "*")]
        selected = filedialog.askopenfilename(
            title="Select Blender Binary",
            filetypes=filetypes
        )
        if selected and os.path.exists(selected):
            self.blender_bin = selected
            self._update_engine_status()
            if self.input_file and not self.is_processing:
                self._set_actions_enabled(True)

    def _apply_material_preset(self, mat_name):
        self.opt_material.set(mat_name)
        if mat_name == "Sheet Metal (Press Brake / Weld)":
            self.switch_tabs.deselect()
            self.chk_bend_angles.select()
            self.chk_seam_numbers.select()
            self.opt_machine.set("CNC Plasma / Sheet Metal")
        elif mat_name == "EVA Foam (Bevel Glue)":
            self.switch_tabs.deselect()
            self.chk_bend_angles.select()
            self.chk_seam_numbers.select()
            self.opt_machine.set("LightBurn (Laser)")
        elif mat_name == "Papercraft / Cardboard":
            self.switch_tabs.select()
            self.chk_bend_angles.deselect()
            self.chk_seam_numbers.select()
            self.opt_machine.set("Standard Papercraft (Generic)")

    def _apply_machine_preset(self, machine_name):
        self.opt_machine.set(machine_name)

    def _on_part_type_changed(self, part):
        unit = self.opt_unit.get()
        is_inch = "Inches" in unit

        # Typical adult reference sizing presets
        presets_mm = {
            "Head / Helmet": 290.0,
            "Torso / Breastplate / Cuirass": 480.0,
            "Shoulder / Pauldron": 260.0,
            "Arm / Gauntlet / Vambrace": 280.0,
            "Waist / Faulds / Tassets": 320.0,
            "Leg / Greave / Cuisses": 420.0,
            "Foot / Sabaton / Boot": 290.0,
            "Custom Part / Free Dimension": 250.0
        }
        val_mm = presets_mm.get(part, 250.0)
        target_val = round(val_mm / 25.4, 2) if is_inch else round(val_mm, 1)

        self.entry_target_dim.delete(0, "end")
        self.entry_target_dim.insert(0, str(target_val))
        self._update_scale_calculation()

    def _on_unit_changed(self, unit):
        is_inch = "Inches" in unit
        self.lbl_target_dim.configure(text=f"Target Height ({'in' if is_inch else 'mm'}):")
        self._update_scale_calculation()

    @staticmethod
    def _pos_to_target(pos):
        """Map a 0..1 slider position to a target face count (log scale)."""
        pos = max(0.0, min(1.0, float(pos)))
        lo, hi = math.log(TARGET_FACES_MIN), math.log(TARGET_FACES_MAX)
        return int(round(math.exp(lo + pos * (hi - lo))))

    @staticmethod
    def _target_to_pos(target):
        """Inverse of _pos_to_target: face count -> 0..1 slider position."""
        target = max(TARGET_FACES_MIN, min(TARGET_FACES_MAX, int(target)))
        lo, hi = math.log(TARGET_FACES_MIN), math.log(TARGET_FACES_MAX)
        return (math.log(target) - lo) / (hi - lo)

    def _target_faces(self):
        """The face budget currently selected on the slider."""
        return self._pos_to_target(self.slider_poly.get())

    def _current_decimate_ratio(self):
        """Decimate ratio = target budget / original polycount (clamped).

        Returns 1.0 (no decimation) when the model already has fewer faces than
        the target, or when the polycount is unknown.
        """
        target = self._target_faces()
        if not self.mesh_info or not self.mesh_info.get("poly_count"):
            return 1.0
        poly = self.mesh_info["poly_count"]
        if poly <= target:
            return 1.0
        return max(MIN_DECIMATE_RATIO, min(1.0, target / float(poly)))

    def _auto_set_decimation(self):
        """Pick a sensible polygon budget for the loaded model."""
        if self.mesh_info and self.mesh_info.get("poly_count"):
            target = min(RECOMMENDED_FACES, self.mesh_info["poly_count"])
        else:
            target = RECOMMENDED_FACES
        self.slider_poly.set(self._target_to_pos(target))
        self._update_slider_label(self.slider_poly.get())

    def _update_slider_label(self, val):
        target = self._pos_to_target(val)
        if self.mesh_info and self.mesh_info.get("poly_count"):
            poly = self.mesh_info["poly_count"]
            est = min(poly, target)
            ratio = self._current_decimate_ratio()
            if poly <= target:
                txt = (f"Target ≈ {target:,} faces  •  keeping all "
                       f"{poly:,} faces (no decimation needed)")
            else:
                txt = (f"Target ≈ {target:,} faces  •  ~{est:,} after "
                       f"decimation  ({ratio * 100:.2f}% of {poly:,})")
            if target > HEAVY_FACES_WARN:
                txt += "  ⚠ slow to unfold"
            self.lbl_slider_val.configure(text=txt)
        else:
            self.lbl_slider_val.configure(
                text=f"Target ≈ {target:,} faces (load a model to calibrate)")

    def select_file(self):
        file_path = filedialog.askopenfilename(
            title="Select 3D Mesh Model",
            filetypes=[("3D Meshes", "*.stl *.obj"), ("Stereolithography (.stl)", "*.stl"), ("Wavefront (.obj)", "*.obj")]
        )
        if file_path:
            self.input_file = file_path
            f_size_mb = os.path.getsize(file_path) / (1024 * 1024)
            self.lbl_filename.configure(
                text=f"{os.path.basename(file_path)} ({f_size_mb:.1f} MB)", 
                text_color="white"
            )
            self.status_lbl.configure(text="Inspecting 3D mesh geometry...", text_color="#3B8ED0")
            self._run_mesh_inspection(file_path)

    def _run_mesh_inspection(self, file_path):
        """Runs quick headless inspection to get bounding box dimensions and polycount."""
        if not self.blender_bin or not os.path.exists(self.blender_bin):
            self.lbl_inspect_dims.configure(text="Dimensions: Locate Blender to inspect model.")
            if not self.is_processing:
                self._set_actions_enabled(True)
            return

        worker_script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "blender_worker.py")
        if hasattr(sys, "_MEIPASS"):
            worker_script = os.path.join(sys._MEIPASS, "blender_worker.py")

        def inspect_thread():
            cmd = [
                self.blender_bin,
                "--background",
                "--python", worker_script,
                "--", "inspect", json.dumps({"input_file": file_path})
            ]
            try:
                res = subprocess.run(cmd, capture_output=True, text=True, check=True)
                for line in res.stdout.splitlines():
                    if line.startswith("BENFORGE_INSPECT_RESULT:"):
                        payload = line.replace("BENFORGE_INSPECT_RESULT:", "").strip()
                        data = json.loads(payload)
                        self.after(0, self._on_inspect_success, data)
                        return
                self.after(0, self._on_inspect_fallback)
            except Exception:
                self.after(0, self._on_inspect_fallback)

        threading.Thread(target=inspect_thread, daemon=True).start()

    def _on_inspect_success(self, data):
        self.mesh_info = data
        unit = self.opt_unit.get()
        is_inch = "Inches" in unit
        scale_u = 1.0 / 25.4 if is_inch else 1.0
        u_sym = "in" if is_inch else "mm"

        dx = data['dim_x_mm'] * scale_u
        dy = data['dim_y_mm'] * scale_u
        dz = data['dim_z_mm'] * scale_u
        polys = data['poly_count']

        self.lbl_inspect_dims.configure(
            text=f"Dimensions: {dx:.1f} × {dy:.1f} × {dz:.1f} {u_sym} | Polygons: {polys:,} faces",
            text_color="#A5D6A7"
        )
        self._update_scale_calculation()
        # Auto-calibrate the polygon budget to this model's complexity.
        self._auto_set_decimation()
        if self.blender_bin and not self.is_processing:
            self._set_actions_enabled(True)
        ratio = self._current_decimate_ratio()
        if polys > RECOMMENDED_FACES:
            self.status_lbl.configure(
                text=f"Model ready. Auto-set to ~{self._target_faces():,} faces "
                     f"({ratio * 100:.2f}% of {polys:,}). Adjust if needed.",
                text_color="gray70")
        else:
            self.status_lbl.configure(text="Model ready. Adjust settings and click Unfold.",
                                      text_color="gray70")

    def _on_inspect_fallback(self):
        self.lbl_inspect_dims.configure(text="Dimensions: Mesh loaded. (Direct inspection skipped)", text_color="gray75")
        if self.blender_bin and not self.is_processing:
            self._set_actions_enabled(True)
        self.status_lbl.configure(text="Model loaded. Ready to unfold.", text_color="gray70")

    def _update_scale_calculation(self):
        """Calculates uniform scale multiplier based on target dimension and padding allowance."""
        if not self.switch_autofit.get() or not self.mesh_info:
            self.lbl_calculated_scale.configure(text="Scale: 1.000x (Original 1:1)")
            return 1.0

        try:
            target_str = self.entry_target_dim.get().strip()
            target_val = float(target_str)
            if target_val <= 0:
                raise ValueError()
        except ValueError:
            self.lbl_calculated_scale.configure(text="Scale: Invalid input")
            return 1.0

        unit = self.opt_unit.get()
        is_inch = "Inches" in unit
        scale_u = 1.0 / 25.4 if is_inch else 1.0
        orig_height = self.mesh_info.get("dim_z_mm", 250.0) * scale_u

        # Parse padding allowance
        pad_str = self.entry_padding.get().strip().replace("+", "")
        pad_multiplier = 1.0
        if "%" in pad_str:
            try:
                pct = float(pad_str.replace("%", "").strip())
                pad_multiplier = 1.0 + (pct / 100.0)
            except ValueError:
                pass
        else:
            try:
                pad_val = float(pad_str.replace("mm", "").replace("in", "").strip())
                target_val += pad_val
            except ValueError:
                pass

        if orig_height > 0:
            final_scale = (target_val / orig_height) * pad_multiplier
            self.lbl_calculated_scale.configure(
                text=f"Scale: {final_scale:.3f}x ({final_scale * 100:.1f}%)"
            )
            return final_scale

        return 1.0

    def _check_ready(self):
        """Common guards for Preview/Export. Returns True if ready to run."""
        if self.is_processing:
            return False
        if not self.input_file:
            messagebox.showwarning("No Input", "Please select a 3D mesh model first.")
            return False
        if not self.blender_bin or not os.path.exists(self.blender_bin):
            messagebox.showerror(
                "Engine Missing",
                "Could not locate Blender binary.\n\nPlease install Blender or locate "
                "your Blender executable using the 'Locate Blender...' button."
            )
            return False
        return True

    def _build_config(self, output_file):
        """Validate inputs and assemble the worker config dict, or None on error."""
        try:
            tab_val = float(self.entry_tab.get())
        except ValueError:
            messagebox.showerror("Invalid Input", "Tab width must be a valid number.")
            return None
        try:
            kerf_val = float(self.entry_kerf.get())
        except ValueError:
            kerf_val = 0.0

        scale_mult = self._update_scale_calculation()
        return {
            "input_file": self.input_file,
            "output_file": output_file,
            "decimate_ratio": self._current_decimate_ratio(),
            "tab_size": tab_val,
            "use_tabs": bool(self.switch_tabs.get()),
            "page_format": self.opt_page.get(),
            "export_format": self.opt_export_fmt.get(),
            "join_meshes": bool(self.switch_join.get()),
            "scale_factor": scale_mult,
            "material_mode": self.opt_material.get(),
            "machine_preset": self.opt_machine.get(),
            "print_bend_angles": bool(self.chk_bend_angles.get()),
            "print_seam_numbers": bool(self.chk_seam_numbers.get()),
            "kerf_offset_mm": kerf_val
        }

    def _confirm_heavy_mesh(self):
        """Warn when the mesh is dense enough that unfolding may take very long.

        The paper-model unfolder is single-threaded pure Python; tens of
        thousands of faces can take many minutes. Returns True to proceed.
        """
        if not self.mesh_info or "poly_count" not in self.mesh_info:
            return True
        est = min(self.mesh_info["poly_count"], self._target_faces())
        if est <= HEAVY_FACES_WARN:
            return True
        return messagebox.askyesno(
            "Dense Mesh Warning",
            f"After decimation this pattern will have about {est:,} polygons.\n\n"
            "Unfolding is single-threaded and may take many minutes (or appear to "
            "hang) at this density, and a pattern with this many facets is rarely "
            "practical to cut or fold.\n\n"
            "Tip: drag the polygon-budget slider left (or click 'Auto') for a "
            "cleaner, faster result.\n\n"
            "Proceed anyway?"
        )

    def _worker_script(self):
        worker_script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "blender_worker.py")
        if hasattr(sys, "_MEIPASS"):
            worker_script = os.path.join(sys._MEIPASS, "blender_worker.py")
        return worker_script

    def process_model(self):
        if not self._check_ready():
            return

        fmt = self.opt_export_fmt.get().lower()
        output_file = filedialog.asksaveasfilename(
            title=f"Save 2D {fmt.upper()} Pattern",
            defaultextension=f".{fmt}",
            filetypes=[(f"{fmt.upper()} File", f"*.{fmt}")]
        )
        if not output_file:
            return

        config = self._build_config(output_file)
        if config is None:
            return
        if not self._confirm_heavy_mesh():
            return

        self.last_output_file = output_file
        self.post_export_frame.pack_forget()
        self._start_worker(config, output_file, kind="export",
                           status="Unfolding 3D mesh via Blender engine... please wait.")

    def preview_model(self):
        if not self._check_ready():
            return
        if PatternPreview is None:
            messagebox.showerror("Preview Unavailable",
                                 "The preview module could not be loaded.")
            return
        # Previews are always generated as SVG (vector) into a temp folder so we
        # can render them, regardless of the chosen export format.
        preview_dir = os.path.join(tempfile.gettempdir(), "benforge_preview")
        os.makedirs(preview_dir, exist_ok=True)
        # Clear stale pages from a previous preview run.
        for old in list(self.preview_files):
            try:
                os.remove(old)
            except OSError:
                pass
        base = os.path.join(preview_dir, "preview.svg")
        for stale in glob.glob(os.path.join(preview_dir, "preview*.svg")):
            try:
                os.remove(stale)
            except OSError:
                pass

        config = self._build_config(base)
        if config is None:
            return
        config["export_format"] = "SVG"
        if not self._confirm_heavy_mesh():
            return

        self._start_worker(config, base, kind="preview",
                           status="Generating preview pattern... please wait.")

    def _start_worker(self, config, output_file, kind, status):
        self.is_processing = True
        self._set_actions_enabled(False)
        self.btn_select.configure(state="disabled")
        self.status_lbl.configure(text=status, text_color="#3B8ED0")
        self.progress_bar.start()
        threading.Thread(
            target=self._run_worker_subprocess,
            args=(self.blender_bin, self._worker_script(), config, output_file, kind),
            daemon=True
        ).start()

    @staticmethod
    def _parse_worker_output(text):
        """Extract (files_list, error_message) from worker stdout markers."""
        files, error = [], None
        for line in (text or "").splitlines():
            line = line.strip()
            if line.startswith("BENFORGE_OUTPUT_FILES:"):
                try:
                    files = json.loads(line[len("BENFORGE_OUTPUT_FILES:"):])
                except Exception:
                    pass
            elif line.startswith("BENFORGE_ERROR:"):
                error = line[len("BENFORGE_ERROR:"):].strip()
        return files, error

    def _run_worker_subprocess(self, blender_bin, worker_script, config, output_file, kind):
        cmd = [blender_bin, "--background", "--python", worker_script,
               "--", "unfold", json.dumps(config)]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True)
            combined = (result.stdout or "") + "\n" + (result.stderr or "")
            files, error = self._parse_worker_output(combined)
            if "BENFORGE_SUCCESS" in combined and files:
                self.after(0, self._on_process_success, files, kind)
            else:
                msg = error or (result.stderr or result.stdout or "Unknown engine error.")
                self.after(0, self._on_process_failure, msg, kind)
        except Exception as ex:
            self.after(0, self._on_process_failure, str(ex), kind)

    def _finish_worker(self):
        self.is_processing = False
        self.progress_bar.stop()
        self._set_actions_enabled(True)
        self.btn_select.configure(state="normal")

    def _on_process_success(self, files, kind):
        self._finish_worker()
        self.progress_bar.set(1.0 if kind == "export" else 0)
        if kind == "preview":
            self.preview_files = files
            self.status_lbl.configure(text=f"Preview ready ({len(files)} page(s)).",
                                      text_color="#2FA572")
            self._open_preview_window(files, title="Pattern Preview")
            return
        # export
        self.last_output_files = files
        self.last_output_file = files[0]
        pages = f" ({len(files)} pages)" if len(files) > 1 else ""
        self.status_lbl.configure(text=f"Pattern generation complete!{pages}",
                                  text_color="#2FA572")
        self.post_export_frame.pack(pady=(8, 0))
        listing = "\n".join(os.path.basename(f) for f in files)
        messagebox.showinfo("Export Successful",
                            f"Vector pattern exported successfully:\n\n{listing}")

    def _on_process_failure(self, error_message, kind="export"):
        self._finish_worker()
        self.progress_bar.set(0)
        self.status_lbl.configure(text="Unfolding failed. Review error log.",
                                  text_color="#D32F2F")
        preview = error_message.strip()
        if len(preview) > 1200:
            preview = preview[-1200:]
        messagebox.showerror("Execution Error",
                             f"Worker engine failed to unfold mesh:\n\n{preview}")

    def _open_preview_window(self, files, title):
        existing = [f for f in files if os.path.exists(f)]
        if not existing:
            messagebox.showwarning("Nothing to Preview", "No pattern pages were found to display.")
            return
        try:
            PatternPreview(self, existing, title=title)
        except Exception as e:
            messagebox.showerror("Preview Error", f"Could not open preview window:\n\n{e}")

    def _preview_last_export(self):
        if not self.last_output_files:
            messagebox.showinfo("No Pattern", "Export a pattern first, then preview it.")
            return
        if PatternPreview is None:
            messagebox.showerror("Preview Unavailable", "The preview module could not be loaded.")
            return
        # Only SVG pages can be rendered by the lightweight previewer.
        svgs = [f for f in self.last_output_files if f.lower().endswith(".svg")]
        if not svgs:
            messagebox.showinfo("Preview Unavailable",
                                "On-screen preview supports SVG output. Use 'Open Vector Pattern' "
                                "to view PDF exports in your system viewer.")
            return
        self._open_preview_window(svgs, title="Exported Pattern Preview")

    def _open_output_folder(self):
        if self.last_output_file and os.path.exists(self.last_output_file):
            folder = os.path.dirname(os.path.abspath(self.last_output_file))
            if platform.system() == "Windows":
                os.startfile(folder)
            elif platform.system() == "Darwin":
                subprocess.Popen(["open", folder])
            else:
                subprocess.Popen(["xdg-open", folder])

    def _open_pattern_file(self):
        if self.last_output_file and os.path.exists(self.last_output_file):
            if platform.system() == "Windows":
                os.startfile(self.last_output_file)
            elif platform.system() == "Darwin":
                subprocess.Popen(["open", self.last_output_file])
            else:
                subprocess.Popen(["xdg-open", self.last_output_file])


if __name__ == "__main__":
    app = BenForgeApp()
    app.mainloop()
