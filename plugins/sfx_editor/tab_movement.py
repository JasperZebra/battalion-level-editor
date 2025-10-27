"""
Movement Tab Manager
Handles the MOVEMENT tab functionality
"""
import re
import tkinter as tk
from tkinter import ttk


class MovementTabManager:
    """Manages the Movement tab interface and functionality"""
    
    def __init__(self, editor, notebook):
        self.editor = editor
        
        # State variables
        self.velocity_x_var = tk.DoubleVar(value=0.0)
        self.velocity_y_var = tk.DoubleVar(value=0.0)
        self.velocity_z_var = tk.DoubleVar(value=0.0)
        self.velocity_random_var = tk.DoubleVar(value=0.01)
        self.gravity_var = tk.DoubleVar(value=0.0)
        
        # NEW: Velocity damping (critical physics parameter)
        self.velocity_damp_var = tk.DoubleVar(value=1.0)
        
        self.setup_ui(notebook)
    
    def setup_ui(self, notebook):
        """Setup the movement tab UI"""
        movement_frame = ttk.Frame(notebook, style="TFrame")
        notebook.add(movement_frame, text="MOVEMENT")

        param_frame = ttk.LabelFrame(movement_frame, text="MOVEMENT PARAMETERS", padding="5", style="Card.TLabelframe")
        param_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        param_grid = ttk.Frame(param_frame, style="TFrame")
        param_grid.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        row = 0
        
        # Initial Velocity X
        ttk.Label(param_grid, text="VELOCITY X:", style="TLabel").grid(row=row, column=0, padx=5, pady=10, sticky=tk.W)
        velocity_x_slider = ttk.Scale(param_grid, from_=-1.0, to=1.0, variable=self.velocity_x_var, orient=tk.HORIZONTAL)
        velocity_x_slider.grid(row=row, column=1, padx=5, pady=10, sticky=tk.EW)
        self.velocity_x_value = ttk.Label(param_grid, text="0.000", style='Value.TLabel')
        self.velocity_x_value.grid(row=row, column=2, padx=5, pady=10)
        velocity_x_slider.bind("<Motion>", lambda e: self.update_value_label(self.velocity_x_var, self.velocity_x_value))
        row += 1
        
        # Initial Velocity Y
        ttk.Label(param_grid, text="VELOCITY Y:", style="TLabel").grid(row=row, column=0, padx=5, pady=10, sticky=tk.W)
        velocity_y_slider = ttk.Scale(param_grid, from_=-1.0, to=1.0, variable=self.velocity_y_var, orient=tk.HORIZONTAL)
        velocity_y_slider.grid(row=row, column=1, padx=5, pady=10, sticky=tk.EW)
        self.velocity_y_value = ttk.Label(param_grid, text="0.000", style='Value.TLabel')
        self.velocity_y_value.grid(row=row, column=2, padx=5, pady=10)
        velocity_y_slider.bind("<Motion>", lambda e: self.update_value_label(self.velocity_y_var, self.velocity_y_value))
        row += 1
        
        # Initial Velocity Z
        ttk.Label(param_grid, text="VELOCITY Z:", style="TLabel").grid(row=row, column=0, padx=5, pady=10, sticky=tk.W)
        velocity_z_slider = ttk.Scale(param_grid, from_=-1.0, to=1.0, variable=self.velocity_z_var, orient=tk.HORIZONTAL)
        velocity_z_slider.grid(row=row, column=1, padx=5, pady=10, sticky=tk.EW)
        self.velocity_z_value = ttk.Label(param_grid, text="0.000", style='Value.TLabel')
        self.velocity_z_value.grid(row=row, column=2, padx=5, pady=10)
        velocity_z_slider.bind("<Motion>", lambda e: self.update_value_label(self.velocity_z_var, self.velocity_z_value))
        row += 1
        
        # Velocity Randomness
        ttk.Label(param_grid, text="RANDOMNESS:", style="TLabel").grid(row=row, column=0, padx=5, pady=10, sticky=tk.W)
        velocity_random_slider = ttk.Scale(param_grid, from_=0.0, to=0.1, variable=self.velocity_random_var, orient=tk.HORIZONTAL)
        velocity_random_slider.grid(row=row, column=1, padx=5, pady=10, sticky=tk.EW)
        self.velocity_random_value = ttk.Label(param_grid, text="0.010", style='Value.TLabel')
        self.velocity_random_value.grid(row=row, column=2, padx=5, pady=10)
        velocity_random_slider.bind("<Motion>", lambda e: self.update_value_label(self.velocity_random_var, self.velocity_random_value))
        row += 1
        
        # NEW: Velocity Damping (physics)
        ttk.Label(param_grid, text="VELOCITY DAMP:", style="TLabel").grid(row=row, column=0, padx=5, pady=10, sticky=tk.W)
        velocity_damp_slider = ttk.Scale(param_grid, from_=0.0, to=1.0, variable=self.velocity_damp_var, orient=tk.HORIZONTAL)
        velocity_damp_slider.grid(row=row, column=1, padx=5, pady=10, sticky=tk.EW)
        self.velocity_damp_value = ttk.Label(param_grid, text="1.000", style='Value.TLabel')
        self.velocity_damp_value.grid(row=row, column=2, padx=5, pady=10)
        velocity_damp_slider.bind("<Motion>", lambda e: self.update_value_label(self.velocity_damp_var, self.velocity_damp_value))
        row += 1
        
        # Gravity Scale
        ttk.Label(param_grid, text="GRAVITY:", style="TLabel").grid(row=row, column=0, padx=5, pady=10, sticky=tk.W)
        gravity_slider = ttk.Scale(param_grid, from_=-0.1, to=0.1, variable=self.gravity_var, orient=tk.HORIZONTAL)
        gravity_slider.grid(row=row, column=1, padx=5, pady=10, sticky=tk.EW)
        self.gravity_value = ttk.Label(param_grid, text="0.000", style='Value.TLabel')
        self.gravity_value.grid(row=row, column=2, padx=5, pady=10)
        gravity_slider.bind("<Motion>", lambda e: self.update_value_label(self.gravity_var, self.gravity_value))
        
        param_grid.columnconfigure(1, weight=1)
    
    def update_value_label(self, var, label, is_int=False):
        """Update value label with current slider value"""
        value = var.get()
        if is_int:
            label.config(text=f"{int(value)}")
        else:
            label.config(text=f"{value:.3f}")
    
    def highlight_values(self):
        """Highlight movement-related parameters in the file viewer"""
        if not self.editor.file_content:
            return
        
        # Initial Velocity values
        for param in ["Initial_Velocity_X", "Initial_Velocity_Y", "Initial_Velocity_Z"]:
            pattern = fr'({param} NUMBER_VERSION_2\n\*+1: )(-?[\d.-]+)'
            for match in re.finditer(pattern, self.editor.file_content):
                start_idx = f"1.0+{match.start(2)}c"
                end_idx = f"1.0+{match.end(2)}c"
                self.editor.file_viewer.tag_add("movement_value", start_idx, end_idx)
                self.editor.file_viewer.tag_add("highlight", start_idx, end_idx)
        
        # Velocity_Randomness
        pattern_random = r'(Velocity_Randomness NUMBER_VERSION_2\n\*+1: )([\d.-]+)'
        for match in re.finditer(pattern_random, self.editor.file_content):
            start_idx = f"1.0+{match.start(2)}c"
            end_idx = f"1.0+{match.end(2)}c"
            self.editor.file_viewer.tag_add("movement_value", start_idx, end_idx)
            self.editor.file_viewer.tag_add("highlight", start_idx, end_idx)
        
        # NEW: Velocity_Damp
        pattern_damp = r'(Velocity_Damp )([\d.-]+)'
        for match in re.finditer(pattern_damp, self.editor.file_content):
            start_idx = f"1.0+{match.start(2)}c"
            end_idx = f"1.0+{match.end(2)}c"
            self.editor.file_viewer.tag_add("movement_value", start_idx, end_idx)
            self.editor.file_viewer.tag_add("highlight", start_idx, end_idx)
        
        # Gravity values
        for param in ["GravityScalar", "GravityPC"]:
            pattern = fr'({param} .*?\n.*?: )(-?[\d.-]+)'
            for match in re.finditer(pattern, self.editor.file_content):
                start_idx = f"1.0+{match.start(2)}c"
                end_idx = f"1.0+{match.end(2)}c"
                self.editor.file_viewer.tag_add("movement_value", start_idx, end_idx)
                self.editor.file_viewer.tag_add("highlight", start_idx, end_idx)