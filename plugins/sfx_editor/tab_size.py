"""
Size Tab Manager
Handles the SIZE tab functionality
"""
import re
import tkinter as tk
from tkinter import ttk


class SizeTabManager:
    """Manages the Size tab interface and functionality"""
    
    def __init__(self, editor, notebook):
        self.editor = editor
        self.colors = editor.colors
        
        # State variables
        self.radius_var = tk.DoubleVar(value=1.0)
        self.final_radius_var = tk.DoubleVar(value=2.0)
        self.width_var = tk.DoubleVar(value=0.25)
        
        # NEW: Length parameter (critical for trails and particles)
        self.length_var = tk.DoubleVar(value=1.0)
        
        self.setup_ui(notebook)
    
    def setup_ui(self, notebook):
        """Setup the size tab UI"""
        size_frame = ttk.Frame(notebook, style="TFrame")
        notebook.add(size_frame, text="SIZE")

        param_frame = ttk.LabelFrame(size_frame, text="SIZE PARAMETERS", padding="5", style="Card.TLabelframe")
        param_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        param_grid = ttk.Frame(param_frame, style="TFrame")
        param_grid.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        row = 0
        
        # Radius
        ttk.Label(param_grid, text="RADIUS:", style="TLabel").grid(row=row, column=0, padx=5, pady=10, sticky=tk.W)
        radius_slider = ttk.Scale(param_grid, from_=0.1, to=5.0, variable=self.radius_var, orient=tk.HORIZONTAL)
        radius_slider.grid(row=row, column=1, padx=5, pady=10, sticky=tk.EW)
        self.radius_value = ttk.Label(param_grid, text="1.000", style='Value.TLabel')
        self.radius_value.grid(row=row, column=2, padx=5, pady=10)
        radius_slider.bind("<Motion>", lambda e: self.update_value_label(self.radius_var, self.radius_value))
        row += 1
        
        # Final Radius
        ttk.Label(param_grid, text="FINAL RADIUS:", style="TLabel").grid(row=row, column=0, padx=5, pady=10, sticky=tk.W)
        final_radius_slider = ttk.Scale(param_grid, from_=0.1, to=5.0, variable=self.final_radius_var, orient=tk.HORIZONTAL)
        final_radius_slider.grid(row=row, column=1, padx=5, pady=10, sticky=tk.EW)
        self.final_radius_value = ttk.Label(param_grid, text="2.000", style='Value.TLabel')
        self.final_radius_value.grid(row=row, column=2, padx=5, pady=10)
        final_radius_slider.bind("<Motion>", lambda e: self.update_value_label(self.final_radius_var, self.final_radius_value))
        row += 1
        
        # NEW: Length (for particles and trails)
        ttk.Label(param_grid, text="LENGTH:", style="TLabel").grid(row=row, column=0, padx=5, pady=10, sticky=tk.W)
        length_slider = ttk.Scale(param_grid, from_=0.1, to=10.0, variable=self.length_var, orient=tk.HORIZONTAL)
        length_slider.grid(row=row, column=1, padx=5, pady=10, sticky=tk.EW)
        self.length_value = ttk.Label(param_grid, text="1.000", style='Value.TLabel')
        self.length_value.grid(row=row, column=2, padx=5, pady=10)
        length_slider.bind("<Motion>", lambda e: self.update_value_label(self.length_var, self.length_value))
        row += 1
        
        # Trail width
        ttk.Label(param_grid, text="TRAIL WIDTH:", style="TLabel").grid(row=row, column=0, padx=5, pady=10, sticky=tk.W)
        width_slider = ttk.Scale(param_grid, from_=0.05, to=1.0, variable=self.width_var, orient=tk.HORIZONTAL)
        width_slider.grid(row=row, column=1, padx=5, pady=10, sticky=tk.EW)
        self.width_value = ttk.Label(param_grid, text="0.250", style='Value.TLabel')
        self.width_value.grid(row=row, column=2, padx=5, pady=10)
        width_slider.bind("<Motion>", lambda e: self.update_value_label(self.width_var, self.width_value))
        
        param_grid.columnconfigure(1, weight=1)
    
    def update_value_label(self, var, label, is_int=False):
        """Update value label with current slider value"""
        value = var.get()
        if is_int:
            label.config(text=f"{int(value)}")
        else:
            label.config(text=f"{value:.3f}")
    
    def highlight_values(self):
        """Highlight size-related parameters in the file viewer"""
        if not self.editor.file_content:
            return
        
        # Radius values
        pattern_radius = r'(Radius NUMBER_VERSION_2\n\*+1: )([\d.-]+)'
        for match in re.finditer(pattern_radius, self.editor.file_content):
            start_idx = f"1.0+{match.start(2)}c"
            end_idx = f"1.0+{match.end(2)}c"
            self.editor.file_viewer.tag_add("size_value", start_idx, end_idx)
            self.editor.file_viewer.tag_add("highlight", start_idx, end_idx)
        
        # Final_Radius values
        pattern_final = r'(Final_Radius )([\d.-]+)'
        for match in re.finditer(pattern_final, self.editor.file_content):
            start_idx = f"1.0+{match.start(2)}c"
            end_idx = f"1.0+{match.end(2)}c"
            self.editor.file_viewer.tag_add("size_value", start_idx, end_idx)
            self.editor.file_viewer.tag_add("highlight", start_idx, end_idx)
        
        # NEW: Length values
        pattern_length = r'(Length NUMBER_VERSION_2\n\*+1: )([\d.-]+)'
        for match in re.finditer(pattern_length, self.editor.file_content):
            start_idx = f"1.0+{match.start(2)}c"
            end_idx = f"1.0+{match.end(2)}c"
            self.editor.file_viewer.tag_add("size_value", start_idx, end_idx)
            self.editor.file_viewer.tag_add("highlight", start_idx, end_idx)
        
        # Width and Start_Width values
        for param in ["Width", "Start_Width"]:
            pattern = fr'({param} )([\d.-]+)'
            for match in re.finditer(pattern, self.editor.file_content):
                start_idx = f"1.0+{match.start(2)}c"
                end_idx = f"1.0+{match.end(2)}c"
                self.editor.file_viewer.tag_add("size_value", start_idx, end_idx)
                self.editor.file_viewer.tag_add("highlight", start_idx, end_idx)