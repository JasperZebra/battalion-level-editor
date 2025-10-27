"""
Trail Tab Manager
Handles the TRAIL tab functionality
"""
import re
import tkinter as tk
from tkinter import ttk


class TrailTabManager:
    """Manages the Trail tab interface and functionality"""
    
    def __init__(self, editor, notebook):
        self.editor = editor
        
        # State variables
        self.num_points_var = tk.DoubleVar(value=10.0)
        self.wiggle_var = tk.DoubleVar(value=0.0)
        self.disperse_var = tk.DoubleVar(value=0.0)
        
        self.setup_ui(notebook)
    
    def setup_ui(self, notebook):
        """Setup the trail tab UI"""
        trail_frame = ttk.Frame(notebook, style="TFrame")
        notebook.add(trail_frame, text="TRAIL")

        param_frame = ttk.LabelFrame(trail_frame, text="TRAIL PARAMETERS", padding="5", style="Card.TLabelframe")
        param_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        param_grid = ttk.Frame(param_frame, style="TFrame")
        param_grid.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Num Points
        ttk.Label(param_grid, text="TRAIL POINTS:", style="TLabel").grid(row=0, column=0, padx=5, pady=10, sticky=tk.W)
        num_points_slider = ttk.Scale(param_grid, from_=3, to=30, variable=self.num_points_var, orient=tk.HORIZONTAL)
        num_points_slider.grid(row=0, column=1, padx=5, pady=10, sticky=tk.EW)
        self.num_points_value = ttk.Label(param_grid, text="10", style='Value.TLabel')
        self.num_points_value.grid(row=0, column=2, padx=5, pady=10)
        num_points_slider.bind("<Motion>", lambda e: self.update_value_label(self.num_points_var, self.num_points_value, is_int=True))
        
        # Wiggle Factor
        ttk.Label(param_grid, text="WIGGLE FACTOR:", style="TLabel").grid(row=1, column=0, padx=5, pady=10, sticky=tk.W)
        wiggle_slider = ttk.Scale(param_grid, from_=0.0, to=20.0, variable=self.wiggle_var, orient=tk.HORIZONTAL)
        wiggle_slider.grid(row=1, column=1, padx=5, pady=10, sticky=tk.EW)
        self.wiggle_value = ttk.Label(param_grid, text="0.000", style='Value.TLabel')
        self.wiggle_value.grid(row=1, column=2, padx=5, pady=10)
        wiggle_slider.bind("<Motion>", lambda e: self.update_value_label(self.wiggle_var, self.wiggle_value))
        
        # Disperse Rate
        ttk.Label(param_grid, text="DISPERSE RATE:", style="TLabel").grid(row=2, column=0, padx=5, pady=10, sticky=tk.W)
        disperse_slider = ttk.Scale(param_grid, from_=0.0, to=0.1, variable=self.disperse_var, orient=tk.HORIZONTAL)
        disperse_slider.grid(row=2, column=1, padx=5, pady=10, sticky=tk.EW)
        self.disperse_value = ttk.Label(param_grid, text="0.000", style='Value.TLabel')
        self.disperse_value.grid(row=2, column=2, padx=5, pady=10)
        disperse_slider.bind("<Motion>", lambda e: self.update_value_label(self.disperse_var, self.disperse_value))
        
        param_grid.columnconfigure(1, weight=1)
    
    def update_value_label(self, var, label, is_int=False):
        """Update value label with current slider value"""
        value = var.get()
        if is_int:
            label.config(text=f"{int(value)}")
        else:
            label.config(text=f"{value:.3f}")
    
    def highlight_values(self):
        """Highlight trail-related parameters in the file viewer"""
        if not self.editor.file_content:
            return
        
        # Num_Points values
        pattern_points = r'(Num_Points )(\d+)'
        for match in re.finditer(pattern_points, self.editor.file_content):
            start_idx = f"1.0+{match.start(2)}c"
            end_idx = f"1.0+{match.end(2)}c"
            self.editor.file_viewer.tag_add("trail_value", start_idx, end_idx)
            self.editor.file_viewer.tag_add("highlight", start_idx, end_idx)
        
        # Wiggle_Factor values
        pattern_wiggle = r'(Wiggle_Factor )([\d.-]+)'
        for match in re.finditer(pattern_wiggle, self.editor.file_content):
            start_idx = f"1.0+{match.start(2)}c"
            end_idx = f"1.0+{match.end(2)}c"
            self.editor.file_viewer.tag_add("trail_value", start_idx, end_idx)
            self.editor.file_viewer.tag_add("highlight", start_idx, end_idx)
        
        # Disperse_Rate values
        pattern_disperse = r'(Disperse_Rate )([\d.-]+)'
        for match in re.finditer(pattern_disperse, self.editor.file_content):
            start_idx = f"1.0+{match.start(2)}c"
            end_idx = f"1.0+{match.end(2)}c"
            self.editor.file_viewer.tag_add("trail_value", start_idx, end_idx)
            self.editor.file_viewer.tag_add("highlight", start_idx, end_idx)
