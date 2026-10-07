# BenForge — 3D Pattern Unfolder & Metal/Armor Fabrication Suite

**BenForge** is a standalone 3D-to-2D cut and bend pattern generator. It converts 3D meshes (`.stl`, `.obj`) into flattened 2D vector patterns (`.svg`, `.pdf`) optimized for CNC sheet metal cutting & bending, laser cutters, vinyl plotters, EVA foam armor crafting, and papercraft prototyping.

---

## Features

- **Full-Body Anatomical Fitment**: Sizing presets for Head/Helmet, Torso/Cuirass, Shoulders, Arms/Gauntlets, Legs/Greaves, and Custom dimensions with padding allowance calculations.
- **Material Modes**:
  - **Sheet Metal**: Clean weld-ready edges (no tabs), dihedral press brake angle annotations (`45° UP`, `90° DOWN`), and numbered weld seams.
  - **EVA Foam Armor**: Edge-to-edge bevel gluing with printed dihedral bevel angles.
  - **Papercraft / Cardboard**: Standard folding glue tabs with adjustable widths and mountain/valley score lines.
- **Machine Layer Coding**: Output SVGs pre-structured into dedicated color-coded layers for **LightBurn**, **Glowforge**, **Cricut**, and **CNC Plasma/Waterjet**.
- **Interactive Tooltips**: Built-in contextual guidance on mouse hover across every control, with instant toggle control via the menu bar and header switch.
- **Mesh Inspector**: Live readout of 3D bounding box dimensions ($X \times Y \times Z$) and polygon complexity.
- **Non-Blocking Architecture**: Background threading ensures smooth UI responsiveness during decimation and unfolding.
- **Automated CI/CD**: Pushing a git release tag automatically builds portable Windows (`.exe`) and Linux releases.

---

## Local Development (Linux)

### 1. Requirements
- Python 3.10+
- Tkinter (`python3-tk`)
- Blender (installed via package manager or detected via PATH)

### 2. Setup Virtual Environment
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 3. Run Application
```bash
python3 app.py
```

---

## Compiling Standalone Executable Locally

To compile the local standalone Linux binary:
```bash
.venv/bin/python3 -m PyInstaller --noconfirm --onedir --windowed \
  --add-data "blender_worker.py:." \
  --add-data "svg_layer_processor.py:." \
  --add-data "tooltip.py:." \
  --add-data "VERSION.txt:." \
  --name "BenForge_v1.0.0" \
  app.py
```
The compiled binary will be located in `dist/BenForge_v1.0.0/BenForge_v1.0.0`.

---

## Automated GitHub Releases

When you are ready to publish a new release:
```bash
git add .
git commit -m "Release v1.0.0"
git tag v1.0.0
git push origin main --tags
```
GitHub Actions will automatically build:
1. `BenForge_v1.0.0_Windows_x64.zip` (Portable Windows `.exe` with embedded Blender engine)
2. `BenForge_v1.0.0_Linux_x64.tar.gz` (Portable Linux bundle)
And upload both directly to your repository's Releases page.
