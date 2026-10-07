# BenForge: 3D Pattern Unfolder & Metal/Armor Fabrication Suite

## Technical Architecture & Implementation Guide

**BenForge** is a standalone 3D-to-2D cut and bend pattern generator designed for CNC sheet metal fabrication, laser cutting, plasma cutting, EVA foam armor crafting, and papercraft prototyping.

The application combines a modern **CustomTkinter** GUI with an embedded headless **Blender** geometry engine, allowing makers to take raw 3D meshes (`.stl`, `.obj`), automatically reduce polygon counts, scale to human anatomical body dimensions, and generate clean, machine-ready layered vector patterns (`.svg`, `.pdf`).

---

## 1. System Architecture

```
┌────────────────────────────────────────────────────────────────────────┐
│                          BenForge GUI (Desktop)                        │
│   • 3D Mesh Inspector (Live Dimensions X×Y×Z & Polygon Count)          │
│   • Full-Body Anatomical Fitment (Head, Torso, Arms, Legs, Custom)     │
│   • Material Presets: Sheet Metal, EVA Foam, Papercraft                │
│   • Machine Layer Profiles: LightBurn, Glowforge, Cricut, CNC Plasma   │
│   • Polygon Decimation Slider & Stock Bed Sizing                       │
│   • Contextual Tooltips (Toggleable via Settings / Menu)               │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
                      Subprocess IPC (JSON Payload)
                                    │
┌───────────────────────────────────▼────────────────────────────────────┐
│                  Embedded Headless Blender Engine                      │
│   1. Inspect / Measure 3D Bounding Box Dimensions                      │
│   2. Multi-mesh Auto-Join & Transform Normalization                    │
│   3. Uniform Anatomical Scaling & Decimation Modifier                  │
│   4. io_export_paper_model Unfolding & Seam Calculation                │
│   5. Raw Vector Export (SVG / PDF)                                     │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
┌───────────────────────────────────▼────────────────────────────────────┐
│                  SVG Layer Post-Processor Engine                       │
│   • Layer <g id="benforge_cut_paths">: Solid Red Outer Boundary Cuts   │
│   • Layer <g id="benforge_mountain_folds">: Blue Up-Bends / Creases    │
│   • Layer <g id="benforge_valley_folds">: Green Down-Bends / Creases   │
│   • Layer <g id="benforge_annotations">: Press Brake Angles & Seam IDs │
└────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Key Modules & Repository Structure

```
BenForge/
├── .github/
│   └── workflows/
│       └── build-release.yml    # Automated CI/CD release workflow (Windows & Linux)
├── .gitignore                   # Excludes build artifacts, binaries, and venv
├── app.py                       # Main BenForge CustomTkinter UI application
├── blender_worker.py            # Headless Blender worker (inspect & unfold modes)
├── svg_layer_processor.py       # Post-processes SVG into machine-coded layers
├── tooltip.py                   # Reusable, toggleable hover tooltip engine
├── requirements.txt             # Python dependencies
├── VERSION.txt                  # Version release tracker
├── README.md                    # Project documentation & user guide
└── BenForge.md                  # Complete architectural specification
```

---

## 3. Anatomical Fitment & Scaling System

Internet 3D models frequently lack standardized real-world units. BenForge includes full-body anatomical reference sizing to ensure wearable armor fits human bodies accurately:

* **Head / Helmet**: Reference height ~290 mm (standard adult head ~56–60 cm circumference with clearance).
* **Torso / Breastplate / Cuirass**: Reference height ~480 mm, chest width ~380–450 mm.
* **Shoulder / Pauldron**: Reference length ~260 mm.
* **Arm / Gauntlet / Vambrace**: Reference forearm length ~280 mm.
* **Waist / Faulds / Tassets**: Reference span ~320 mm.
* **Leg / Greave / Cuisses**: Reference shin length ~420 mm.
* **Foot / Sabaton / Boot**: Reference foot length ~290 mm.
* **Custom Part**: Freeform target dimension input.
* **Padding / Allowance Clearance**: Adds padding allowances (e.g. `+10mm` or `+5%`) for gambesons, armor doublets, foam liners, or comfort spacing.

---

## 4. Fabrication & Material Modes

### A. Sheet Metal (Press Brake / Welding)
* **Glue Tabs**: Disabled (edges touch edge-to-edge for welding).
* **Bend Angles**: Dihedral press brake angles (e.g. `BEND 45° UP`, `BEND 30° DOWN`) printed directly along fold seams.
* **Weld Seam IDs**: Matching numbers printed on adjacent seams to guide tack welding sequence.
* **Kerf Compensation**: Configurable offset (e.g. 0.2 mm fine plasma, 0.5 mm standard torch).

### B. EVA Foam (Armor & Cosplay)
* **Glue Tabs**: Disabled (foam smiths use contact cement edge-to-edge).
* **Bevel Angles**: Dihedral bevel cut angles (e.g. `35° Valley Bevel`) printed along seams for accurate razor cuts.
* **Seam Numbers**: Printed to ensure complex multi-facet domes align correctly.

### C. Papercraft / Cardboard
* **Glue Tabs**: Enabled with customizable width (3–15 mm) and angle (45°/60°).
* **Fold Scoring**: Differentiated dashed lines for mountain and valley folds.

---

## 5. Machine Vector Presets (Laser & CNC)

| Machine Preset | Cut Path Layer | Mountain Fold Layer | Valley Fold Layer | Annotations Layer |
| :--- | :--- | :--- | :--- | :--- |
| **LightBurn (Laser)** | `#FF0000` (Red Solid) | `#0000FF` (Blue Dashed) | `#00CC00` (Green Dashed) | `#000000` (Black Engrave) |
| **Glowforge (Laser)** | `#FF0000` (Red Cut) | `#0000FF` (Blue Score) | `#800080` (Purple Score) | `#000000` (Black Engrave) |
| **Cricut / Plotter** | `#FF0000` (Red Blade) | `#0000FF` (Scoring Stylus) | `#FF8C00` (Scoring Wheel) | `#000000` (Pen Tool) |
| **CNC Plasma / Metal** | `#FF0000` (Torch Cut) | `#0066FF` (Scribe / Mark) | `#009900` (Scribe / Mark) | `#000000` (Stamp / Text) |
| **Generic Papercraft** | `#000000` (Solid Cut) | `#000000` (Dashed Mountain) | `#000000` (Dotted Valley) | `#444444` (Gray Text) |

---

## 6. CI/CD Packaging Pipeline

GitHub Actions builds standalone release packages when a release tag (e.g. `v1.0.0`) is pushed:
* **Windows Runner (`windows-latest`)**: Downloads portable Blender 4.1.1, packages standalone executable with PyInstaller, and compresses into `.zip`.
* **Linux Runner (`ubuntu-latest`)**: Downloads portable Blender 4.1.1 Linux engine, packages standalone binary with PyInstaller, and bundles into `.tar.gz`.
* Both binaries are automatically published to GitHub Releases.