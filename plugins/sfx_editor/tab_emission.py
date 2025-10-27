"""
Emission Tab Manager
Handles the EMISSION tab functionality
"""
import re
import tkinter as tk
from tkinter import ttk


class EmissionTabManager:
    """Manages the Emission tab interface and functionality"""
    
    def __init__(self, editor, notebook):
        self.editor = editor
        
        # State variables
        self.emit_rate_var = tk.DoubleVar(value=1.0)
        self.life_var = tk.DoubleVar(value=15.0)
        
        self.setup_ui(notebook)
    
    def setup_ui(self, notebook):
        """Setup the emission tab UI"""
        emission_frame = ttk.Frame(notebook, style="TFrame")
        notebook.add(emission_frame, text="EMISSION")

        param_frame = ttk.LabelFrame(emission_frame, text="EMISSION PARAMETERS", padding="5", style="Card.TLabelframe")
        param_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        param_grid = ttk.Frame(param_frame, style="TFrame")
        param_grid.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Emit_Per_Turn parameter
        ttk.Label(param_grid, text="EMIT RATE:", style="TLabel").grid(row=0, column=0, padx=5, pady=10, sticky=tk.W)
        emit_rate_slider = ttk.Scale(param_grid, from_=0.1, to=5.0, variable=self.emit_rate_var, orient=tk.HORIZONTAL)
        emit_rate_slider.grid(row=0, column=1, padx=5, pady=10, sticky=tk.EW)
        self.emit_rate_value = ttk.Label(param_grid, text="1.000", style='Value.TLabel')
        self.emit_rate_value.grid(row=0, column=2, padx=5, pady=10)
        emit_rate_slider.bind("<Motion>", lambda e: self.update_value_label(self.emit_rate_var, self.emit_rate_value))
        
        # Life parameter
        ttk.Label(param_grid, text="LIFE:", style="TLabel").grid(row=1, column=0, padx=5, pady=10, sticky=tk.W)
        life_slider = ttk.Scale(param_grid, from_=-2, to=30.0, variable=self.life_var, orient=tk.HORIZONTAL)
        life_slider.grid(row=1, column=1, padx=5, pady=10, sticky=tk.EW)
        self.life_value = ttk.Label(param_grid, text="15.000", style='Value.TLabel')
        self.life_value.grid(row=1, column=2, padx=5, pady=10)
        life_slider.bind("<Motion>", lambda e: self.update_value_label(self.life_var, self.life_value))
        
        param_grid.columnconfigure(1, weight=1)
    
    def update_value_label(self, var, label, is_int=False):
        """Update value label with current slider value"""
        value = var.get()
        if is_int:
            label.config(text=f"{int(value)}")
        else:
            label.config(text=f"{value:.3f}")
    
    def highlight_values(self):
        """Highlight emission-related parameters in the file viewer"""
        if not self.editor.file_content:
            return
        
        # Emit_Per_Turn values
        pattern_emit = r'(Emit_Per_Turn NUMBER_VERSION_2\n\*+1: )([\d.-]+)'
        for match in re.finditer(pattern_emit, self.editor.file_content):
            start_idx = f"1.0+{match.start(2)}c"
            end_idx = f"1.0+{match.end(2)}c"
            self.editor.file_viewer.tag_add("emission_value", start_idx, end_idx)
            self.editor.file_viewer.tag_add("highlight", start_idx, end_idx)
        
        # Life values
        pattern_life = r'(Life )(-?\d+)'
        for match in re.finditer(pattern_life, self.editor.file_content):
            start_idx = f"1.0+{match.start(2)}c"
            end_idx = f"1.0+{match.end(2)}c"
            self.editor.file_viewer.tag_add("emission_value", start_idx, end_idx)
            self.editor.file_viewer.tag_add("highlight", start_idx, end_idx)
