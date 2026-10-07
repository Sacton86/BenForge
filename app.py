"""
app.py
CustomTkinter GUI frontend for the 3D Helmet Cut Pattern Generator.
"""

import os
import sys
import json
import shutil
import platform
import subprocess
import threading
import customtkinter as ctk
from tkinter import filedialog, messagebox

# Resolve Application Version
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


class HelmetUnfolderApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title(f"3D Helmet Cut Pattern Generator — {VERSION}")
        self.geometry("720x680")
        self.minsize(640, 580)
        ctk.set_appearance_mode("Dark")
        ctk.set_default_color_theme("blue")

        self.input_file = None
        self.is_processing = False
        self.blender_bin = self._resolve_blender_binary()

        self._build_ui()
        self._update_engine_status()

    def _resolve_blender_binary(self):
        """Finds Blender executable across development, portable, and packaged environments."""
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

        # 2. Local bundled portable engine (development or portable release folder)
        portable_win = os.path.join(base_dir, "engine", "blender_portable", "blender.exe")
        if is_windows and os.path.exists(portable_win):
            return portable_win

        portable_linux = os.path.join(base_dir, "engine", "blender_linux", "blender")
        if not is_windows and os.path.exists(portable_linux):
            return portable_linux

        # 3. System PATH detection
        system_blender = shutil.which("blender.exe" if is_windows else "blender")
        if system_blender:
            return system_blender

        # 4. Standard Linux installation locations
        if not is_windows:
            candidates = [
                "/usr/bin/blender",
                "/usr/local/bin/blender",
                "/snap/bin/blender",
                os.path.expanduser("~/.local/bin/blender"),
                os.path.expanduser("~/blender/blender")
            ]
            for c in candidates:
                if os.path.exists(c) and os.access(c, os.X_OK):
                    return c
        else:
            # Common Windows Program Files locations
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

    def _build_ui(self):
        # Header Section
        self.header_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.header_frame.pack(fill="x", padx=25, pady=(18, 5))

        self.header = ctk.CTkLabel(
            self.header_frame, 
            text="3D Helmet Cut Pattern Generator", 
            font=ctk.CTkFont(size=22, weight="bold")
        )
        self.header.pack(anchor="w")

        self.sub_header = ctk.CTkLabel(
            self.header_frame, 
            text="Convert complex 3D meshes into flattened 2D vector cut patterns for laser cutters & plotters.", 
            text_color="gray70"
        )
        self.sub_header.pack(anchor="w", pady=(2, 0))

        # Engine Status Bar
        self.engine_card = ctk.CTkFrame(self, height=36)
        self.engine_card.pack(fill="x", padx=25, pady=(5, 10))

        self.lbl_engine = ctk.CTkLabel(
            self.engine_card,
            text="Detecting Blender engine...",
            font=ctk.CTkFont(size=12)
        )
        self.lbl_engine.pack(side="left", padx=15, pady=6)

        self.btn_browse_blender = ctk.CTkButton(
            self.engine_card,
            text="Locate Blender...",
            width=110,
            height=26,
            font=ctk.CTkFont(size=11),
            command=self._manual_locate_blender
        )
        self.btn_browse_blender.pack(side="right", padx=10, pady=5)

        # Card 1: File Selection
        self.file_card = ctk.CTkFrame(self)
        self.file_card.pack(fill="x", padx=25, pady=8)

        self.btn_select = ctk.CTkButton(
            self.file_card, 
            text="1. Select 3D Mesh (.stl / .obj)", 
            command=self.select_file,
            width=220,
            height=36,
            font=ctk.CTkFont(weight="bold")
        )
        self.btn_select.pack(side="left", padx=15, pady=15)

        self.lbl_filename = ctk.CTkLabel(
            self.file_card, 
            text="No model selected", 
            text_color="gray60",
            anchor="w"
        )
        self.lbl_filename.pack(side="left", padx=10, fill="x", expand=True)

        # Card 2: Mesh Decimation Settings
        self.settings_card = ctk.CTkFrame(self)
        self.settings_card.pack(fill="x", padx=25, pady=8)

        self.lbl_decimate = ctk.CTkLabel(
            self.settings_card, 
            text="Mesh Detail Reduction (Decimation for dense internet meshes):",
            font=ctk.CTkFont(size=13, weight="bold")
        )
        self.lbl_decimate.pack(anchor="w", padx=15, pady=(12, 2))

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
            text="Retain 30% of polygons (Recommended for high-density 3D scans & internet STL files)",
            text_color="gray70",
            font=ctk.CTkFont(size=12)
        )
        self.lbl_slider_val.pack(anchor="w", padx=15, pady=(0, 10))

        # Card 3: Tabs, Output Format, and Page Settings
        self.opt_card = ctk.CTkFrame(self)
        self.opt_card.pack(fill="x", padx=25, pady=8)

        # Row 1: Tab width & Page Size
        self.row1 = ctk.CTkFrame(self.opt_card, fg_color="transparent")
        self.row1.pack(fill="x", padx=15, pady=(12, 6))

        self.lbl_tab = ctk.CTkLabel(self.row1, text="Glue Tab Width (mm):", font=ctk.CTkFont(weight="bold"))
        self.lbl_tab.pack(side="left", padx=(0, 6))

        self.entry_tab = ctk.CTkEntry(self.row1, width=70)
        self.entry_tab.insert(0, "5.0")
        self.entry_tab.pack(side="left", padx=(0, 25))

        self.lbl_page = ctk.CTkLabel(self.row1, text="Page Size:", font=ctk.CTkFont(weight="bold"))
        self.lbl_page.pack(side="left", padx=(0, 6))

        self.opt_page = ctk.CTkOptionMenu(self.row1, values=["A4", "A3", "A2", "A1", "LETTER", "LEGAL"])
        self.opt_page.set("A3")
        self.opt_page.pack(side="left")

        # Row 2: Export Format & Multi-part joining
        self.row2 = ctk.CTkFrame(self.opt_card, fg_color="transparent")
        self.row2.pack(fill="x", padx=15, pady=(6, 12))

        self.lbl_export_fmt = ctk.CTkLabel(self.row2, text="Output Format:", font=ctk.CTkFont(weight="bold"))
        self.lbl_export_fmt.pack(side="left", padx=(0, 6))

        self.opt_export_fmt = ctk.CTkOptionMenu(self.row2, values=["SVG", "PDF"])
        self.opt_export_fmt.set("SVG")
        self.opt_export_fmt.pack(side="left", padx=(0, 25))

        self.switch_join = ctk.CTkSwitch(self.row2, text="Auto-join multi-part meshes", onvalue=True, offvalue=False)
        self.switch_join.select()
        self.switch_join.pack(side="left")

        # Card 4: Action Area & Progress
        self.action_card = ctk.CTkFrame(self, fg_color="transparent")
        self.action_card.pack(fill="x", padx=25, pady=(15, 10))

        self.btn_process = ctk.CTkButton(
            self.action_card, 
            text="2. Unfold & Export Vector Pattern", 
            command=self.process_model, 
            fg_color="#1f6aa5", 
            hover_color="#144f7d",
            height=44,
            font=ctk.CTkFont(size=15, weight="bold"),
            state="disabled"
        )
        self.btn_process.pack(fill="x")

        self.progress_bar = ctk.CTkProgressBar(self.action_card, mode="indeterminate")
        self.progress_bar.pack(fill="x", pady=(10, 5))
        self.progress_bar.set(0)

        self.status_lbl = ctk.CTkLabel(self.action_card, text="Ready", text_color="gray70", font=ctk.CTkFont(size=12))
        self.status_lbl.pack(pady=2)

    def _update_engine_status(self):
        if self.blender_bin:
            short_path = self.blender_bin
            if len(short_path) > 45:
                short_path = "..." + short_path[-42:]
            self.lbl_engine.configure(
                text=f"Blender Engine Connected: {short_path}",
                text_color="#2FA572"
            )
            self.btn_browse_blender.configure(text="Change...")
        else:
            self.lbl_engine.configure(
                text="Blender Engine: Not Found (Click 'Locate Blender' or install locally)",
                text_color="#E57373"
            )
            self.btn_browse_blender.configure(text="Locate Blender...")

    def _manual_locate_blender(self):
        is_windows = platform.system() == "Windows"
        filetypes = [("Blender Executable", "blender.exe")] if is_windows else [("All Files", "*")]
        selected = filedialog.askopenfilename(
            title="Select Blender Executable",
            filetypes=filetypes
        )
        if selected and os.path.exists(selected):
            self.blender_bin = selected
            self._update_engine_status()
            if self.input_file and not self.is_processing:
                self.btn_process.configure(state="normal")

    def _update_slider_label(self, val):
        pct = int(val * 100)
        self.lbl_slider_val.configure(text=f"Retain {pct}% of polygons (Recommended for high-density models)")

    def select_file(self):
        file_path = filedialog.askopenfilename(
            title="Select 3D Helmet Model",
            filetypes=[("3D Meshes", "*.stl *.obj"), ("Stereolithography (.stl)", "*.stl"), ("Wavefront (.obj)", "*.obj")]
        )
        if file_path:
            self.input_file = file_path
            f_size_mb = os.path.getsize(file_path) / (1024 * 1024)
            self.lbl_filename.configure(
                text=f"{os.path.basename(file_path)} ({f_size_mb:.1f} MB)", 
                text_color="white"
            )
            if self.blender_bin and not self.is_processing:
                self.btn_process.configure(state="normal")
            self.status_lbl.configure(text="Model selected. Ready to unfold.", text_color="gray70")

    def process_model(self):
        if not self.input_file:
            messagebox.showwarning("No Input", "Please select a 3D mesh file first.")
            return

        if not self.blender_bin or not os.path.exists(self.blender_bin):
            messagebox.showerror(
                "Engine Missing", 
                "Could not locate Blender binary.\n\nPlease install Blender or locate your Blender executable using the 'Locate Blender...' button."
            )
            return

        fmt = self.opt_export_fmt.get().lower()
        def_ext = f".{fmt}"
        output_file = filedialog.asksaveasfilename(
            title=f"Save 2D {fmt.upper()} Pattern",
            defaultextension=def_ext,
            filetypes=[(f"{fmt.upper()} File", f"*.{fmt}")]
        )
        if not output_file:
            return

        # Validate numeric tab input
        try:
            tab_val = float(self.entry_tab.get())
            if tab_val < 0:
                raise ValueError()
        except ValueError:
            messagebox.showerror("Invalid Input", "Glue tab width must be a positive number.")
            return

        # Prepare execution parameters
        worker_script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "blender_worker.py")
        if hasattr(sys, "_MEIPASS"):
            worker_script = os.path.join(sys._MEIPASS, "blender_worker.py")

        config = {
            "input_file": self.input_file,
            "output_file": output_file,
            "decimate_ratio": float(self.slider_poly.get()),
            "tab_size": tab_val,
            "page_format": self.opt_page.get(),
            "export_format": self.opt_export_fmt.get(),
            "join_meshes": bool(self.switch_join.get()),
            "scale_factor": 1.0
        }

        # Start execution in background thread to prevent UI freezing
        self.is_processing = True
        self.btn_process.configure(state="disabled")
        self.btn_select.configure(state="disabled")
        self.status_lbl.configure(text="Decimating and unfolding mesh via Blender engine... please wait.", text_color="#3B8ED0")
        self.progress_bar.start()

        worker_thread = threading.Thread(
            target=self._run_worker_subprocess,
            args=(self.blender_bin, worker_script, config, output_file),
            daemon=True
        )
        worker_thread.start()

    def _run_worker_subprocess(self, blender_bin, worker_script, config, output_file):
        cmd = [
            blender_bin,
            "--background",
            "--python", worker_script,
            "--", json.dumps(config)
        ]

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            self.after(0, self._on_process_success, output_file)
        except subprocess.CalledProcessError as e:
            err_output = e.stderr if e.stderr else e.stdout
            self.after(0, self._on_process_failure, err_output or str(e))
        except Exception as ex:
            self.after(0, self._on_process_failure, str(ex))

    def _on_process_success(self, output_file):
        self.is_processing = False
        self.progress_bar.stop()
        self.progress_bar.set(1.0)
        self.btn_process.configure(state="normal")
        self.btn_select.configure(state="normal")
        self.status_lbl.configure(text="Unfolding complete! Pattern saved.", text_color="#2FA572")
        messagebox.showinfo("Export Successful", f"Vector pattern successfully exported to:\n\n{output_file}")

    def _on_process_failure(self, error_message):
        self.is_processing = False
        self.progress_bar.stop()
        self.progress_bar.set(0)
        self.btn_process.configure(state="normal")
        self.btn_select.configure(state="normal")
        self.status_lbl.configure(text="Processing failed. Check error log.", text_color="#D32F2F")

        # Show truncated error message dialog
        preview = error_message.strip()[-800:] if len(error_message) > 800 else error_message
        messagebox.showerror("Execution Error", f"Blender worker failed to unfold mesh:\n\n{preview}")


if __name__ == "__main__":
    app = HelmetUnfolderApp()
    app.mainloop()
