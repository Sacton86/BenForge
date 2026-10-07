# 3D Helmet Pattern Unfolder (BenFold)

A standalone 3D-to-2D cut pattern generator. Converts complex 3D meshes (`.stl`, `.obj`) into flattened 2D vector patterns (`.svg`, `.pdf`) for laser cutters, CNC routers, vinyl cutters, and papercraft/foam helmet fabrication.

## Features
- **Modern Dark-Mode UI**: Built with CustomTkinter.
- **Embedded Portable Blender Engine**: Unfolds complex meshes headlessly using the proven `io_export_paper_model` engine.
- **Mesh Decimation Slider**: Reduces high-poly 3D scans and internet models to clean, foldable polygon counts.
- **Multi-Mesh Auto-Join**: Combines multi-part helmet models (visors, shells, cheeks) automatically.
- **Responsive Non-Blocking Processing**: Background worker thread keeps the UI smooth and responsive during mesh processing.
- **Cross-Platform Releases**: Automated GitHub Actions workflow compiles standalone releases for Windows (`.exe`) and Linux.

---

## Local Development (Linux)

### 1. Requirements
- Python 3.10+
- Tkinter (`python3-tk`)
- Blender (optional if using portable engine, or detected via PATH)

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

To compile a local standalone Linux binary:
```bash
.venv/bin/pyinstaller --noconfirm --onedir --windowed \
  --add-data "blender_worker.py:." \
  --add-data "VERSION.txt:." \
  --name "HelmetUnfolder_v1.0.0" \
  app.py
```
The output binary will be created in `dist/HelmetUnfolder_v1.0.0/HelmetUnfolder_v1.0.0`.

---

## Automated GitHub CI/CD Releases

When you push a version tag to GitHub:
```bash
git add .
git commit -m "Release v1.0.0"
git tag v1.0.0
git push origin main --tags
```
GitHub Actions will automatically:
1. Build Windows x64 standalone executable bundled with portable Blender.
2. Build Linux x64 standalone bundle.
3. Publish both to your GitHub repository Releases page.
