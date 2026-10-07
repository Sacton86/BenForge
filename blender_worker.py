"""
blender_worker.py
Headless execution script executed by Blender to import,
decimate, unfold, and export 3D meshes to 2D vector/paper patterns.
"""

import sys
import json
import traceback
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
    export_format = config.get("export_format", "SVG").upper()
    join_meshes = config.get("join_meshes", True)
    scale_factor = float(config.get("scale_factor", 1.0))

    print(f"Processing input file: {input_file}")
    print(f"Output target: {output_file} (Format: {export_format}, Page: {page_format})")
    print(f"Settings: decimate={decimate_ratio:.2f}, tab_size={tab_size}mm, scale={scale_factor}")

    # 2. Reset Scene to a completely clean state
    bpy.ops.wm.read_factory_settings(use_empty=True)

    # 3. Import Mesh (Support both modern Blender 4.x and legacy Blender 3.x operators)
    file_lower = input_file.lower()
    try:
        if file_lower.endswith('.stl'):
            if hasattr(bpy.ops.wm, 'stl_import'):
                bpy.ops.wm.stl_import(filepath=input_file)
            elif hasattr(bpy.ops.import_mesh, 'stl'):
                bpy.ops.import_mesh.stl(filepath=input_file)
            else:
                raise RuntimeError("No STL import operator available in this Blender environment.")
        elif file_lower.endswith('.obj'):
            if hasattr(bpy.ops.wm, 'obj_import'):
                bpy.ops.wm.obj_import(filepath=input_file)
            elif hasattr(bpy.ops.import_scene, 'obj'):
                bpy.ops.import_scene.obj(filepath=input_file)
            else:
                raise RuntimeError("No OBJ import operator available in this Blender environment.")
        else:
            print(f"Unsupported format: {input_file}")
            sys.exit(1)
    except Exception as e:
        print(f"Failed to import mesh: {e}")
        traceback.print_exc()
        sys.exit(1)

    # 4. Mesh Resolution & Multi-mesh handling
    selected_objs = [o for o in bpy.context.selected_objects if o.type == 'MESH']
    if not selected_objs:
        # Fallback check all objects in scene
        selected_objs = [o for o in bpy.context.scene.objects if o.type == 'MESH']

    if not selected_objs:
        print("No valid mesh objects found in imported file.")
        sys.exit(1)

    print(f"Found {len(selected_objs)} mesh object(s).")

    # If multiple meshes exist and join is requested, join them into one unified model
    if len(selected_objs) > 1 and join_meshes:
        print("Joining multiple mesh objects into a single object...")
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

    # Apply any pre-existing transforms (location, rotation, scale)
    bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)

    # Optional uniform scaling if requested
    if scale_factor != 1.0 and scale_factor > 0:
        obj.scale = (scale_factor, scale_factor, scale_factor)
        bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
        print(f"Applied scale multiplier: {scale_factor}")

    # 5. Decimate Mesh (Essential for dense internet models / 3D scans)
    if decimate_ratio < 0.999:
        poly_before = len(obj.data.polygons)
        mod = obj.modifiers.new(name="Decimate", type='DECIMATE')
        mod.ratio = max(0.01, min(1.0, decimate_ratio))
        bpy.ops.object.modifier_apply(modifier="Decimate")
        poly_after = len(obj.data.polygons)
        print(f"Decimation applied: {poly_before} -> {poly_after} polygons ({decimate_ratio * 100:.1f}%)")

    # 6. Enable Built-in Paper Model Addon
    addon_name = "io_export_paper_model"
    if addon_name not in bpy.context.preferences.addons:
        try:
            bpy.ops.preferences.addon_enable(module=addon_name)
            print(f"Addon '{addon_name}' enabled successfully.")
        except Exception as e:
            print(f"Warning: Could not enable '{addon_name}' via standard preferences: {e}")
            # Try to register manually if present in path
            try:
                import io_export_paper_model
                io_export_paper_model.register()
                print("Registered io_export_paper_model directly via Python import.")
            except Exception as e2:
                print(f"Fatal: Failed to load '{addon_name}': {e2}")
                sys.exit(1)

    # 7. Unfold and Export
    print("Unfolding 3D mesh into 2D cut pattern islands...")
    try:
        bpy.ops.export_paper_model.unfold()
    except Exception as e:
        print(f"Paper model unfolding step warning: {e}")

    # tab_size in mm converted to meters (assuming standard metric unit scene)
    tab_size_m = tab_size / 1000.0

    print(f"Exporting pattern to {output_file}...")
    try:
        bpy.ops.export_paper_model.execute(
            filepath=output_file,
            page_size_preset=page_format,
            use_tabs=True,
            tabs_width=tab_size_m,
            export_format=export_format
        )
        print("Unfold and export completed successfully.")
    except Exception as e:
        print(f"Fatal error during export_paper_model.execute: {e}")
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    run_unfolder()
