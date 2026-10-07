# 3D Helmet Pattern Unfolder: Architecture & Implementation Guide

This document contains the complete technical architecture, source code, and automated CI/CD build configuration for creating a standalone 3D-to-2D cut pattern generator. 

The application uses **CustomTkinter** for an intuitive, dark-mode user interface and embeds **Blender** headlessly to handle complex, high-poly internet 3D meshes (`.stl`, `.obj`), automatically generating cut seams, assembly tabs, and clean 2D vector outputs (`.svg`) for CNC routers, plotters, and laser cutters.

---

## 1. System Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    CustomTkinter GUI                        │
│   - Drag & Drop 3D File (.stl, .obj)                        │
│   - Decimation Slider (for high-poly internet meshes)       │
│   - Glue Tab Width & Page Size Configuration                │
└──────────────────────────────┬──────────────────────────────┘
                               │
                 Subprocess IPC (JSON Payload)
                               │
┌──────────────────────────────▼──────────────────────────────┐
│             Embedded Portable Blender Engine                │
│         (Runs headlessly in the background via CLI)         │
├─────────────────────────────────────────────────────────────┤
│  1. Clear default scene & import STL / OBJ                  │
│  2. Apply Decimate Modifier (reduces polygon count)         │
│  3. Activate native `io_export_paper_model` engine          │
│  4. Calculate optimal seams, cut islands, & glue tabs       │
│  5. Export layered vector pattern (.svg)                    │
└──────────────────────────────┬──────────────────────────────┘
                               │
┌──────────────────────────────▼──────────────────────────────┐
│            Finished CNC & Plotter Vector Files              │
│   - Solid Red Lines: Cutting paths                          │
│   - Dashed Lines: Mountain & Valley folds                   │
│   - Flaps / Tabs: Numbered assembly glue joints             │
└─────────────────────────────────────────────────────────────┘
```

---

## 2. Repository File Tree

```
helmet-unfolder/
├── .github/
│   └── workflows/
│       └── build-release.yml    # Automated CI/CD release workflow
├── .gitignore                   # Excludes binaries, build artifacts, and caches
├── app.py                       # Main CustomTkinter UI application
├── blender_worker.py            # Headless Blender worker script
├── requirements.txt             # Python dependencies
└── README.md                    # Project documentation
```

---

## 3. Source Code Files

### `requirements.txt`
```text
customtkinter>=5.2.0
pyinstaller>=6.0.0
```

### `.gitignore`
```gitignore
# Python & Bytecode
__pycache__/
*.py[cod]
*$py.class
*.spec

# Build Outputs & Packaging
dist/
build/
*.exe
*.zip
VERSION.txt

# Embedded Binaries (Never track portable blender in git)
engine/
blender_portable/

# Operating System Files
.DS_Store
Thumbs.db
```

### `blender_worker.py`
This script runs entirely inside Blender's embedded Python environment without opening any graphical window.

```python
"""
blender_worker.py
Headless execution script executed by Blender to import,
decimate, unfold, and export 3D meshes to 2D vector patterns.
"""

import sys
import json
import bpy

def run_unfolder():
    # 1. Parse JSON configuration passed after '--'
    try:
        argv = sys.argv[sys.argv.index("--") + 1:]
        config = json.loads(argv[0])
    except (ValueError, IndexError) as e:
        print(f"Error parsing CLI arguments: {e}")
        sys.exit(1)

    input_file = config["input_file"]
    output_file = config["output_file"]
    decimate_ratio = float(config.get("decimate_ratio", 1.0))
    tab_size = float(config.get("tab_size", 5.0))
    page_format = config.get("page_format", "A3")

    # 2. Reset Scene
    bpy.ops.wm.read_factory_settings(use_empty=True)

    # 3. Import Mesh
    file_lower = input_file.lower()
    if file_lower.endswith('.stl'):
        bpy.ops.wm.stl_import(filepath=input_file)
    elif file_lower.endswith('.obj'):
        bpy.ops.wm.obj_import(filepath=input_file)
    else:
        print(f"Unsupported format: {input_file}")
        sys.exit(1)

    selected_objs = [o for o in bpy.context.selected_objects if o.type == 'MESH']
    if not selected_objs:
        print("No valid mesh objects found in file.")
        sys.exit(1)

    obj = selected_objs[0]
    bpy.context.view_layer.objects.active = obj

    # 4. Decimate Mesh (Essential for dense internet models / 3D scans)
    if decimate_ratio < 1.0:
        mod = obj.modifiers.new(name="Decimate", type='DECIMATE')
        mod.ratio = max(0.01, min(1.0, decimate_ratio))
        bpy.ops.object.modifier_apply(modifier="Decimate")

    # 5. Enable Built-in Paper Model Addon
    bpy.ops.preferences.addon_enable(module="io_export_paper_model")

    # 6. Unfold and Export
    # Blender paper model addon uses properties set on export operator
    try:
        bpy.ops.export_paper_model.unfold()
    except Exception as e:
        print(f"Paper model unfolding step warning/error: {e}")

    bpy.ops.export_paper_model.execute(
        filepath=output_file,
        page_size_preset=page_format,
        use_tabs=True,
        tabs_width=tab_size / 1000.0, # Converted to meters if using metric units
        export_format='SVG'
    )
    print("Unfold and export completed successfully.")

if __name__ == "__main__":
    run_unfolder()
```

### `app.py`
The desktop GUI supporting local cross-platform development (Linux & Windows) and standalone bundled deployment.

```python
"""
app.py
CustomTkinter GUI frontend for the 3D Helmet Cut Pattern Generator.
"""

import os
import sys
import json
import shutil
import subprocess
import customtkinter as ctk
from tkinter import filedialog, messagebox

# Resolve Application Version
VERSION = "v1.0.0-dev"
version_file = os.path.join(os.path.dirname(__file__), "VERSION.txt")
if os.path.exists(version_file):
    with open(version_file, "r", encoding="utf-8") as f:
        VERSION = f.read().strip()

class HelmetUnfolderApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title(f"3D Helmet Cut Pattern Generator — {VERSION}")
        self.geometry("680x560")
        self.minsize(600, 500)
        ctk.set_appearance_mode("Dark")
        ctk.set_default_color_theme("blue")

        self.input_file = None

        self._build_ui()

    def _build_ui(self):
        # Header
        self.header = ctk.CTkLabel(
            self, 
            text="3D Helmet Cut Pattern Generator", 
            font=ctk.CTkFont(size=22, weight="bold")
        )
        self.header.pack(pady=(20, 5))

        self.sub_header = ctk.CTkLabel(
            self, 
            text="Convert complex 3D meshes into flattened 2D routable vector patterns.", 
            text_color="gray"
        )
        self.sub_header.pack(pady=(0, 15))

        # Card 1: File Selection
        self.file_card = ctk.CTkFrame(self)
        self.file_card.pack(fill="x", padx=25, pady=10)

        self.btn_select = ctk.CTkButton(
            self.file_card, 
            text="1. Select 3D Helmet (.stl / .obj)", 
            command=self.select_file,
            width=220
        )
        self.btn_select.pack(side="left", padx=15, pady=15)

        self.lbl_filename = ctk.CTkLabel(
            self.file_card, 
            text="No file selected", 
            text_color="gray70",
            anchor="w"
        )
        self.lbl_filename.pack(side="left", padx=10, fill="x", expand=True)

        # Card 2: Conversion Settings
        self.settings_card = ctk.CTkFrame(self)
        self.settings_card.pack(fill="x", padx=25, pady=10)

        # Decimation / Poly Reduction
        self.lbl_decimate = ctk.CTkLabel(
            self.settings_card, 
            text="Mesh Detail Reduction (Decimation for Internet Meshes):",
            font=ctk.CTkFont(weight="bold")
        )
        self.lbl_decimate.pack(anchor="w", padx=15, pady=(15, 2))

        self.slider_poly = ctk.CTkSlider(
            self.settings_card, 
            from_=0.05, 
            to=1.0, 
            number_of_steps=19,
            command=self._update_slider_label
        )
        self.slider_poly.set(0.30)
        self.slider_poly.pack(fill="x", padx=15, pady=5)

        self.lbl_slider_val = ctk.CTkLabel(
            self.settings_card, 
            text="Retain 30% of polygons (Recommended for high-density models)",
            text_color="gray70"
        )
        self.lbl_slider_val.pack(anchor="w", padx=15, pady=(0, 10))

        # Glue Tab Width & Page Format
        self.row_frame = ctk.CTkFrame(self.settings_card, fg_color="transparent")
        self.row_frame.pack(fill="x", padx=15, pady=(5, 15))

        self.lbl_tab = ctk.CTkLabel(self.row_frame, text="Tab Width (mm):")
        self.lbl_tab.pack(side="left", padx=(0, 5))

        self.entry_tab = ctk.CTkEntry(self.row_frame, width=70)
        self.entry_tab.insert(0, "5.0")
        self.entry_tab.pack(side="left", padx=(0, 25))

        self.lbl_page = ctk.CTkLabel(self.row_frame, text="Page Size:")
        self.lbl_page.pack(side="left", padx=(0, 5))

        self.opt_page = ctk.CTkOptionMenu(self.row_frame, values=["A4", "A3", "A2", "A1", "LETTER"])
        self.opt_page.set("A3")
        self.opt_page.pack(side="left")

        # Action Buttons & Status
        self.btn_process = ctk.CTkButton(
            self, 
            text="2. Unfold & Export Vector Pattern", 
            command=self.process_model, 
            fg_color="#1f6aa5", 
            height=40,
            font=ctk.CTkFont(size=14, weight="bold"),
            state="disabled"
        )
        self.btn_process.pack(fill="x", padx=25, pady=(20, 10))

        self.status_lbl = ctk.CTkLabel(self, text="Ready", text_color="gray70")
        self.status_lbl.pack(pady=5)

    def _update_slider_label(self, val):
        pct = int(val * 100)
        self.lbl_slider_val.configure(text=f"Retain {pct}% of polygons")

    def select_file(self):
        file_path = filedialog.askopenfilename(
            title="Select 3D Mesh",
            filetypes=[("3D Models", "*.stl *.obj")]
        )
        if file_path:
            self.input_file = file_path
            self.lbl_filename.configure(text=os.path.basename(file_path), text_color="white")
            self.btn_process.configure(state="normal")
            self.status_lbl.configure(text="Ready to unfold.", text_color="gray70")

    def _resolve_blender_binary(self):
        """Finds Blender executable across development and packaged environments."""
        base_dir = os.path.dirname(os.path.abspath(__file__))

        # Check for bundled portable blender (Windows release bundle)
        portable_path = os.path.join(base_dir, "engine", "blender_portable", "blender.exe")
        if os.path.exists(portable_path):
            return portable_path

        # Check PyInstaller sys._MEIPASS extraction directory
        if hasattr(sys, "_MEIPASS"):
            meipass_portable = os.path.join(sys._MEIPASS, "engine", "blender_portable", "blender.exe")
            if os.path.exists(meipass_portable):
                return meipass_portable

        # Fallback to local system installation (Linux or Windows dev environment)
        system_blender = shutil.which("blender")
        if system_blender:
            return system_blender

        return None

    def process_model(self):
        output_file = filedialog.asksaveasfilename(
            title="Save 2D Vector Pattern",
            defaultextension=".svg",
            filetypes=[("Scalable Vector Graphics", "*.svg")]
        )
        if not output_file:
            return

        blender_bin = self._resolve_blender_binary()
        if not blender_bin:
            messagebox.showerror(
                "Engine Missing", 
                "Could not locate Blender binary.\nEnsure Blender is installed locally or bundled in 'engine/blender_portable/'."
            )
            return

        worker_script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "blender_worker.py")
        if hasattr(sys, "_MEIPASS"):
            worker_script = os.path.join(sys._MEIPASS, "blender_worker.py")

        config = {
            "input_file": self.input_file,
            "output_file": output_file,
            "decimate_ratio": float(self.slider_poly.get()),
            "tab_size": float(self.entry_tab.get()),
            "page_format": self.opt_page.get()
        }

        cmd = [
            blender_bin,
            "--background",
            "--python", worker_script,
            "--", json.dumps(config)
        ]

        self.status_lbl.configure(text="Processing and unrolling mesh... please wait.", text_color="#3B8ED0")
        self.update_idletasks()

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            self.status_lbl.configure(text="Processing complete!", text_color="#2FA572")
            messagebox.showinfo("Export Successful", f"Vector pattern exported to:\n{output_file}")
        except subprocess.CalledProcessError as e:
            self.status_lbl.configure(text="Processing failed.", text_color="#D32F2F")
            error_details = e.stderr or e.stdout or str(e)
            messagebox.showerror("Execution Error", f"Failed to unfold 3D model:\n{error_details[:500]}")

if __name__ == "__main__":
    app = HelmetUnfolderApp()
    app.mainloop()
```

---

## 4. GitHub Actions CI/CD Release Workflow

### `.github/workflows/build-release.yml`
This workflow triggers automatically when you push a version tag (e.g. `v1.0.0`). It downloads portable Blender on the Windows runner, packages the executable with PyInstaller, and uploads the `.zip` archive to GitHub Releases.

```yaml
name: Build and Release Executable

on:
  push:
    tags:
      - 'v*.*.*'

permissions:
  contents: write

jobs:
  build-windows:
    runs-on: windows-latest

    steps:
      - name: Checkout Code
        uses: actions/checkout@v4

      - name: Setup Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Inject Version Tag
        shell: bash
        run: |
          TAG_VERSION=${GITHUB_REF_NAME}
          echo "$TAG_VERSION" > VERSION.txt
          echo "RELEASE_VERSION=$TAG_VERSION" >> $GITHUB_ENV

      - name: Download Portable Blender
        shell: powershell
        run: |
          New-Item -ItemType Directory -Force -Path engine/blender_portable
          Write-Host "Downloading Blender 4.2 Portable Archive..."
          Invoke-WebRequest -Uri "https://download.blender.org/release/Blender4.2/blender-4.2.0-windows-x64.zip" -OutFile "blender.zip"
          Write-Host "Extracting Blender Archive..."
          Expand-Archive -Path "blender.zip" -DestinationPath "engine/blender_temp"
          Get-ChildItem -Path "engine/blender_temp/*" | Move-Item -Destination "engine/blender_portable"
          Remove-Item -Recurse -Force engine/blender_temp, blender.zip

      - name: Install Python Dependencies
        run: |
          python -m pip install --upgrade pip
          pip install -r requirements.txt

      - name: Compile Executable with PyInstaller
        run: |
          pyinstaller --noconfirm --onedir --windowed `
            --add-data "engine/blender_portable;engine/blender_portable" `
            --add-data "blender_worker.py;." `
            --add-data "VERSION.txt;." `
            --name "HelmetUnfolder_${{ env.RELEASE_VERSION }}" `
            app.py

      - name: Compress Release Archive
        shell: powershell
        run: |
          Compress-Archive -Path "dist/HelmetUnfolder_${{ env.RELEASE_VERSION }}/*" `
            -DestinationPath "HelmetUnfolder_${{ env.RELEASE_VERSION }}_Windows_x64.zip"

      - name: Publish GitHub Release
        uses: softprops/action-gh-release@v2
        with:
          files: HelmetUnfolder_${{ env.RELEASE_VERSION }}_Windows_x64.zip
          name: Release ${{ env.RELEASE_VERSION }}
          body: |
            ## Helmet Unfolder Release ${{ env.RELEASE_VERSION }}
            
            ### Installation Instructions:
            1. Download `HelmetUnfolder_${{ env.RELEASE_VERSION }}_Windows_x64.zip` below.
            2. Extract all contents to a folder on your computer.
            3. Run `HelmetUnfolder_${{ env.RELEASE_VERSION }}.exe` (no installation required).
          draft: false
          prerelease: false
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
```

---

## 5. Development & Testing Workflow

### Local Development on Linux
1. Install system Blender and Python dependencies:
   ```bash
   sudo apt-get update && sudo apt-get install blender python3-pip
   pip install -r requirements.txt
   ```
2. Launch the application:
   ```bash
   python3 app.py
   ```
   *The application automatically detects `/usr/bin/blender` on Linux.*

### Local Development on Windows
1. Install dependencies:
   ```powershell
   pip install -r requirements.txt
   ```
2. If Blender is installed locally, `app.py` will discover it via `PATH`. 
3. Launch the application:
   ```powershell
   python app.py
   ```

---

## 6. How to Trigger an Automated Release

Whenever you are ready to publish a new build:

1. Commit and push your code changes to GitHub:
   ```bash
   git add .
   git commit -m "Optimize decimation presets and tab calculation"
   git push origin main
   ```
2. Tag the commit with your new version number and push the tag:
   ```bash
   git tag v1.0.0
   git push origin v1.0.0
   ```
3. Open your GitHub repository and go to the **Actions** tab to watch the build progress.
4. Once completed, download the release `.zip` directly from your repository's **Releases** tab.