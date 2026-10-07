"""
blender_worker.py
Headless execution engine executed by Blender for BenForge.
Supports mesh inspection (bounding box dimensions & polycount) and
unfolding 3D models into 2D cut/bend patterns for sheet metal, foam, and paper.
"""

import sys
import os
import json
import traceback
import bpy

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
        mod.ratio = max(0.01, min(1.0, decimate_ratio))
        bpy.ops.object.modifier_apply(modifier="Decimate")
        poly_after = len(obj.data.polygons)
        print(f"Mesh decimated: {poly_before} -> {poly_after} polygons ({decimate_ratio * 100:.1f}%)")

    # 6. Enable io_export_paper_model Addon
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
                print(f"Fatal: Cannot load {addon_name}: {e2}")
                sys.exit(1)

    # 7. Unfold Mesh
    print("Calculating optimal cut seams and unfolding mesh...")
    try:
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_all(action='SELECT')
        if hasattr(bpy.ops.mesh, 'unfold'):
            bpy.ops.mesh.unfold()
        bpy.ops.object.mode_set(mode='OBJECT')
    except Exception as e:
        print(f"Unfold operator notice: {e}")
        try:
            bpy.ops.object.mode_set(mode='OBJECT')
        except Exception:
            pass

    # 8. Export to Vector File
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
        print(f"Error executing paper model exporter: {e}")
        traceback.print_exc()
        sys.exit(1)

    # 9. Post-Process SVG into Machine Layers (for SVG exports)
    if export_format == "SVG" and os.path.exists(output_file):
        try:
            # Import post processor from current directory
            script_dir = os.path.dirname(os.path.abspath(__file__))
            if script_dir not in sys.path:
                sys.path.append(script_dir)
            import svg_layer_processor
            ok, msg = svg_layer_processor.process_svg_layers(
                svg_filepath=output_file,
                preset_name=machine_preset,
                material_mode=material_mode,
                use_tabs=use_tabs,
                print_bend_angles=print_bend_angles,
                print_seam_numbers=print_seam_numbers,
                kerf_offset_mm=kerf_offset_mm
            )
            print(f"SVG Layer Processor: {msg}")
        except Exception as pe:
            print(f"Notice: Post-processing layer separation skipped: {pe}")

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
