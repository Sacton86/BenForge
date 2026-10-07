"""
blender_worker.py
Headless execution engine executed by Blender for BenForge.
Supports mesh inspection (bounding box dimensions & polycount) and
unfolding 3D models into 2D cut/bend patterns for sheet metal, foam, and paper.
"""

import sys
import os
import json
import glob
import functools
import traceback
import bpy
import bmesh

# Force line-buffered/flushed output so the parent GUI can read progress and
# error markers even if Blender is terminated mid-run (background mode buffers
# stdout heavily by default).
print = functools.partial(print, flush=True)
try:
    sys.stdout.reconfigure(line_buffering=True)
except Exception:
    pass


def emit_error(message):
    """Print a clean, single-line error marker the GUI can surface verbatim."""
    flat = " ".join(str(message).split())
    print("BENFORGE_ERROR:" + flat)

def run_inspect(config):
    """Loads a 3D mesh and returns its bounding box dimensions and polygon count."""
    input_file = config.get("input_file")
    bpy.ops.wm.read_factory_settings(use_empty=True)

    file_lower = input_file.lower()
    if file_lower.endswith('.stl'):
        if hasattr(bpy.ops.wm, 'stl_import'):
            bpy.ops.wm.stl_import(filepath=input_file)
        elif hasattr(bpy.ops.import_mesh, 'stl'):
            bpy.ops.import_mesh.stl(filepath=input_file)
    elif file_lower.endswith('.obj'):
        if hasattr(bpy.ops.wm, 'obj_import'):
            bpy.ops.wm.obj_import(filepath=input_file)
        elif hasattr(bpy.ops.import_scene, 'obj'):
            bpy.ops.import_scene.obj(filepath=input_file)
    else:
        print(f"Unsupported format: {input_file}")
        sys.exit(1)

    meshes = [o for o in bpy.context.scene.objects if o.type == 'MESH']
    if not meshes:
        print("No valid mesh objects found.")
        sys.exit(1)

    # Join meshes if multiple to measure full bounding box
    if len(meshes) > 1:
        bpy.ops.object.select_all(action='DESELECT')
        for m in meshes:
            m.select_set(True)
        bpy.context.view_layer.objects.active = meshes[0]
        bpy.ops.object.join()
        active_obj = bpy.context.view_layer.objects.active
    else:
        active_obj = meshes[0]

    if active_obj.data.users > 1:
        active_obj.data = active_obj.data.copy()
    bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)
    dims = active_obj.dimensions  # Vector (X, Y, Z) in meters / scene units
    poly_count = len(active_obj.data.polygons)
    vert_count = len(active_obj.data.vertices)

    # Standard STL/OBJ files from CAD are usually exported in mm.
    # If dimensions are under 5 units, model might be in meters; otherwise in mm.
    dim_x_mm = float(dims.x * 1000.0) if max(dims.x, dims.y, dims.z) < 2.0 else float(dims.x)
    dim_y_mm = float(dims.y * 1000.0) if max(dims.x, dims.y, dims.z) < 2.0 else float(dims.y)
    dim_z_mm = float(dims.z * 1000.0) if max(dims.x, dims.y, dims.z) < 2.0 else float(dims.z)

    result = {
        "dim_x_mm": round(dim_x_mm, 2),
        "dim_y_mm": round(dim_y_mm, 2),
        "dim_z_mm": round(dim_z_mm, 2),
        "poly_count": poly_count,
        "vertex_count": vert_count
    }
    print("BENFORGE_INSPECT_RESULT:" + json.dumps(result))
    sys.exit(0)


def run_unfolder(config):
    """Executes the decimation, scaling, and unfolding pipeline."""
    input_file = config["input_file"]
    output_file = config["output_file"]
    decimate_ratio = float(config.get("decimate_ratio", 1.0))
    tab_size = float(config.get("tab_size", 5.0))
    use_tabs = bool(config.get("use_tabs", False))
    page_format = config.get("page_format", "A3")
    export_format = config.get("export_format", "SVG").upper()
    join_meshes = config.get("join_meshes", True)
    scale_factor = float(config.get("scale_factor", 1.0))
    material_mode = config.get("material_mode", "Sheet Metal")
    machine_preset = config.get("machine_preset", "LightBurn (Laser)")
    print_bend_angles = config.get("print_bend_angles", True)
    print_seam_numbers = config.get("print_seam_numbers", True)
    kerf_offset_mm = float(config.get("kerf_offset_mm", 0.0))

    print(f"BenForge Unfold Task: {input_file} -> {output_file}")
    print(f"Material: {material_mode} | Machine: {machine_preset} | Scale Factor: {scale_factor:.4f}")
    print(f"Decimate: {decimate_ratio:.2f} | Tabs: {'ON (' + str(tab_size) + 'mm)' if use_tabs else 'OFF (Weld/Bevel Edge)'}")

    # 1. Reset Scene
    bpy.ops.wm.read_factory_settings(use_empty=True)

    # 2. Import Mesh
    file_lower = input_file.lower()
    try:
        if file_lower.endswith('.stl'):
            if hasattr(bpy.ops.wm, 'stl_import'):
                bpy.ops.wm.stl_import(filepath=input_file)
            elif hasattr(bpy.ops.import_mesh, 'stl'):
                bpy.ops.import_mesh.stl(filepath=input_file)
            else:
                raise RuntimeError("No STL import operator available in this Blender build.")
        elif file_lower.endswith('.obj'):
            if hasattr(bpy.ops.wm, 'obj_import'):
                bpy.ops.wm.obj_import(filepath=input_file)
            elif hasattr(bpy.ops.import_scene, 'obj'):
                bpy.ops.import_scene.obj(filepath=input_file)
            else:
                raise RuntimeError("No OBJ import operator available in this Blender build.")
        else:
            print(f"Unsupported format: {input_file}")
            sys.exit(1)
    except Exception as e:
        print(f"Failed to import mesh: {e}")
        traceback.print_exc()
        sys.exit(1)

    # 3. Select and join mesh objects
    selected_objs = [o for o in bpy.context.selected_objects if o.type == 'MESH']
    if not selected_objs:
        selected_objs = [o for o in bpy.context.scene.objects if o.type == 'MESH']

    if not selected_objs:
        print("No valid mesh objects found in imported file.")
        sys.exit(1)

    if len(selected_objs) > 1 and join_meshes:
        print(f"Joining {len(selected_objs)} mesh parts into a unified model...")
        bpy.ops.object.select_all(action='DESELECT')
        for o in selected_objs:
            o.select_set(True)
        bpy.context.view_layer.objects.active = selected_objs[0]
        bpy.ops.object.join()
        obj = bpy.context.view_layer.objects.active
    else:
        obj = selected_objs[0]
        bpy.context.view_layer.objects.active = obj
        obj.select_set(True)

    # Apply initial transforms
    if obj.data.users > 1:
        obj.data = obj.data.copy()
    bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)

    # 4. Anatomical / User Scaling
    if scale_factor != 1.0 and scale_factor > 0:
        obj.scale = (scale_factor, scale_factor, scale_factor)
        bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
        print(f"Applied scaling multiplier: {scale_factor:.4f}")

    # 5. Polygon Decimation
    if decimate_ratio < 0.999:
        poly_before = len(obj.data.polygons)
        mod = obj.modifiers.new(name="Decimate", type='DECIMATE')
        mod.ratio = max(0.0002, min(1.0, decimate_ratio))
        bpy.ops.object.modifier_apply(modifier="Decimate")
        poly_after = len(obj.data.polygons)
        print(f"Mesh decimated: {poly_before} -> {poly_after} polygons ({decimate_ratio * 100:.1f}%)")

    # 6. Mesh Cleanup / Repair
    # The paper-model unfolder refuses to process meshes containing zero-length
    # edges, zero-area faces, or non-planar ("twisted") polygons. Decimation and
    # imported scans routinely introduce these, so we repair the mesh here.
    # Order matters: triangulate FIRST (guarantees planar faces and exposes
    # slivers), THEN merge/dissolve the degenerate geometry that triangulation
    # can create.
    print("Cleaning and repairing mesh geometry before unfolding...")
    try:
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_all(action='SELECT')
        bpy.ops.mesh.quads_convert_to_tris(quad_method='BEAUTY', ngon_method='BEAUTY')
        bpy.ops.mesh.remove_doubles(threshold=1e-5)
        bpy.ops.mesh.dissolve_degenerate(threshold=1e-5)
        bpy.ops.mesh.delete_loose()
        bpy.ops.mesh.normals_make_consistent(inside=False)
        bpy.ops.object.mode_set(mode='OBJECT')

        # Final guarantee: remove any face the unfolder would still reject.
        # This matches io_export_paper_model's own epsilon (area < 1e-6).
        me = obj.data
        bm = bmesh.new()
        bm.from_mesh(me)
        degen_faces = [f for f in bm.faces if f.calc_area() < 1e-6]
        if degen_faces:
            bmesh.ops.delete(bm, geom=degen_faces, context='FACES')
        bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-5)
        bm.to_mesh(me)
        bm.free()
        me.update()
        print(f"Mesh cleanup complete: {len(me.polygons)} faces ready "
              f"(removed {len(degen_faces)} degenerate face(s)).")
    except Exception as e:
        print(f"Mesh cleanup notice: {e}")
        try:
            bpy.ops.object.mode_set(mode='OBJECT')
        except Exception:
            pass

    # 7. Enable io_export_paper_model Addon
    addon_name = "io_export_paper_model"
    if addon_name not in bpy.context.preferences.addons:
        try:
            bpy.ops.preferences.addon_enable(module=addon_name)
        except Exception as e:
            print(f"Warning on addon_enable: {e}")
            try:
                import io_export_paper_model
                io_export_paper_model.register()
            except Exception as e2:
                emit_error(f"Cannot load unfolding engine ({addon_name}): {e2}")
                sys.exit(1)

    # 8. Export to Vector File
    # NOTE: the exporter performs the unfold internally during prepare(), so we
    # do NOT pre-call mesh.unfold() (that would double the expensive compute).
    print("Calculating optimal cut seams and unfolding mesh...")
    tab_size_m = (tab_size / 1000.0) if use_tabs else 0.005
    page_preset = page_format.upper().split()[0] if page_format else "A3"
    valid_presets = ["A4", "A3", "A2", "A1", "LETTER", "LEGAL"]
    page_arg = page_preset if page_preset in valid_presets else "A3"

    print(f"Exporting pattern to {output_file} (Page: {page_arg}, Format: {export_format})...")
    try:
        if hasattr(bpy.ops.export_mesh, 'paper_model'):
            bpy.ops.export_mesh.paper_model(
                filepath=output_file,
                page_size_preset=page_arg,
                do_create_stickers=use_tabs,
                do_create_numbers=print_seam_numbers,
                sticker_width=tab_size_m,
                file_format=export_format
            )
        elif hasattr(bpy.ops.export_paper_model, 'execute'):
            bpy.ops.export_paper_model.execute(
                filepath=output_file,
                page_size_preset=page_arg,
                use_tabs=use_tabs,
                tabs_width=tab_size_m,
                export_format=export_format
            )
        else:
            raise RuntimeError("No paper model exporter operator found in Blender.")
        print("Raw pattern exported successfully.")
    except Exception as e:
        # The unfolder raises UnfoldError with a human-readable first arg when
        # the mesh is unsuitable (e.g. still-degenerate geometry). Surface that
        # clean message instead of the raw BMesh traceback.
        msg = str(e)
        if "zero-area" in msg or "zero-length" in msg or "twisted" in msg or "inside-out" in msg:
            clean = msg.split("Export failed")[0].strip() or msg
            emit_error(
                "The mesh could not be unfolded: " + clean + ". "
                "Try increasing decimation (fewer polygons) or using a cleaner model."
            )
        elif "no UV Map slots" in msg:
            emit_error("The mesh has no free UV map slots. Remove a UV map and retry.")
        else:
            emit_error("Unfolding engine error: " + msg)
        traceback.print_exc()
        sys.exit(1)

    # 9. Resolve the actual files written. The SVG exporter writes ONE file
    # (output_file) for single-page nets, but "<base>_<page>.svg" per page when
    # a net spans multiple pages. Discover whichever were produced.
    base, ext = os.path.splitext(output_file)
    produced = []
    if os.path.exists(output_file):
        produced.append(output_file)
    produced.extend(sorted(p for p in glob.glob(f"{base}_*{ext}") if p not in produced))
    if not produced:
        emit_error(
            "The unfold completed but produced no output pages. The pattern may "
            "be empty; try a different model or less aggressive decimation."
        )
        sys.exit(1)
    print(f"Produced {len(produced)} page file(s).")

    # 10. Post-Process every SVG page into Machine Layers (for SVG exports)
    if export_format == "SVG":
        try:
            script_dir = os.path.dirname(os.path.abspath(__file__))
            if script_dir not in sys.path:
                sys.path.append(script_dir)
            import svg_layer_processor
            for page_path in produced:
                ok, msg = svg_layer_processor.process_svg_layers(
                    svg_filepath=page_path,
                    preset_name=machine_preset,
                    material_mode=material_mode,
                    use_tabs=use_tabs,
                    print_bend_angles=print_bend_angles,
                    print_seam_numbers=print_seam_numbers,
                    kerf_offset_mm=kerf_offset_mm
                )
                print(f"SVG Layer Processor [{os.path.basename(page_path)}]: {msg}")
        except Exception as pe:
            print(f"Notice: Post-processing layer separation skipped: {pe}")

    # Report the concrete output paths back to the GUI.
    print("BENFORGE_OUTPUT_FILES:" + json.dumps(produced))
    print("BENFORGE_SUCCESS")


def main():
    if "--" not in sys.argv:
        print("Usage: blender --background --python blender_worker.py -- [inspect|unfold] <json_payload>")
        sys.exit(1)

    args = sys.argv[sys.argv.index("--") + 1:]
    if not args:
        print("No operation specified.")
        sys.exit(1)

    op = args[0].lower()
    if op in ("inspect", "unfold"):
        payload_str = args[1] if len(args) > 1 else "{}"
    else:
        # Default backward compatibility: first argument is json payload for unfold
        op = "unfold"
        payload_str = args[0]

    try:
        config = json.loads(payload_str)
    except Exception as e:
        print(f"Failed to parse config JSON: {e}")
        sys.exit(1)

    if op == "inspect":
        run_inspect(config)
    else:
        run_unfolder(config)


if __name__ == "__main__":
    main()
