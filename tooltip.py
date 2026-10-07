"""
tooltip.py
Lightweight, theme-aware tooltip system for CustomTkinter and Tkinter widgets.
Supports global enable/disable toggling.
"""

import tkinter as tk

class ToolTip:
    """
    Attaches an informative hover tooltip to any Tkinter / CustomTkinter widget.
    Tooltips can be globally enabled or disabled via ToolTip.enabled.
    """
    enabled = True  # Global toggle controlled via app menu / settings

    def __init__(self, widget, text, delay_ms=350):
        self.widget = widget
        self.text = text
        self.delay_ms = delay_ms
        self.tip_window = None
        self.schedule_id = None

        # Bind hover events
        self.widget.bind("<Enter>", self._on_enter, add="+")
        self.widget.bind("<Leave>", self._on_leave, add="+")
        self.widget.bind("<ButtonPress>", self._on_leave, add="+")

    def _on_enter(self, event=None):
        if not ToolTip.enabled or not self.text:
            return
        self._cancel_scheduled()
        self.schedule_id = self.widget.after(self.delay_ms, self._show_tooltip)

    def _on_leave(self, event=None):
        self._cancel_scheduled()
        self._hide_tooltip()

    def _cancel_scheduled(self):
        if self.schedule_id:
            try:
                self.widget.after_cancel(self.schedule_id)
            except Exception:
                pass
            self.schedule_id = None

    def _show_tooltip(self):
        if not ToolTip.enabled or self.tip_window or not self.widget.winfo_exists():
            return

        try:
            x = self.widget.winfo_rootx() + 20
            y = self.widget.winfo_rooty() + self.widget.winfo_height() + 5

            # Prevent rendering off-screen
            screen_width = self.widget.winfo_screenwidth()
            screen_height = self.widget.winfo_screenheight()

            self.tip_window = tw = tk.Toplevel(self.widget)
            tw.wm_overrideredirect(True)
            tw.wm_attributes("-topmost", True)

            # Styling: Dark theme tooltip matching CustomTkinter
            container = tk.Frame(
                tw,
                background="#1e1e24",
                highlightbackground="#3d5a80",
                highlightcolor="#3d5a80",
                highlightthickness=1,
                padx=8,
                pady=6
            )
            container.pack()

            label = tk.Label(
                container,
                text=self.text,
                justify="left",
                background="#1e1e24",
                foreground="#e0e0e0",
                font=("Helvetica", 9),
                wraplength=340
            )
            label.pack()

            tw.update_idletasks()
            w = tw.winfo_width()
            h = tw.winfo_height()

            if x + w > screen_width - 10:
                x = max(10, screen_width - w - 10)
            if y + h > screen_height - 35:
                y = max(10, self.widget.winfo_rooty() - h - 5)

            tw.wm_geometry(f"+{x}+{y}")
        except Exception:
            self._hide_tooltip()

    def _hide_tooltip(self):
        if self.tip_window:
            try:
                self.tip_window.destroy()
            except Exception:
                pass
            self.tip_window = None


def attach_tooltip(widget, text):
    """Helper to attach a tooltip to a widget or its internal sub-widgets."""
    if not text:
        return None
    tip = ToolTip(widget, text)
    # If this is a compound CustomTkinter widget (like CTkButton), also bind its internal canvas/label
    for attr in ("_canvas", "_text_label", "_label", "_entry"):
        sub = getattr(widget, attr, None)
        if sub and hasattr(sub, "bind"):
            ToolTip(sub, text)
    return tip
