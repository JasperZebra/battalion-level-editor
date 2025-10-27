"""
Visual Tab Manager
Handles the VISUAL tab functionality
"""
import re
import tkinter as tk
from tkinter import ttk


class VisualTabManager:
    """Manages the Visual tab interface and functionality"""
    
    def __init__(self, editor, notebook):
        self.editor = editor
        
        # State variables
        self.blend_mode_var = tk.StringVar(value="0 - Normal")
        self.anim_speed_var = tk.DoubleVar(value=1.0)
        self.cylinder_length_var = tk.DoubleVar(value=2.0)
        
        # NEW: Critical missing parameters
        self.axis_aligned_var = tk.StringVar(value="1 - Camera")
        self.rotation_var = tk.DoubleVar(value=0.0)
        self.anim_type_var = tk.StringVar(value="0 - Static")
        self.texture_number_var = tk.IntVar(value=-1)
        self.end_frame_var = tk.IntVar(value=0)
        
        self.setup_ui(notebook)
    
    def setup_ui(self, notebook):
        """Setup the visual tab UI"""
        visual_frame = ttk.Frame(notebook, style="TFrame")
        notebook.add(visual_frame, text="VISUAL")

        param_frame = ttk.LabelFrame(visual_frame, text="VISUAL PARAMETERS", padding="5", style="Card.TLabelframe")
        param_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        param_grid = ttk.Frame(param_frame, style="TFrame")
        param_grid.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        row = 0
        
        # Blend Mode
        ttk.Label(param_grid, text="BLEND MODE:", style="TLabel").grid(row=row, column=0, padx=5, pady=10, sticky=tk.W)
        blend_modes = ["0 - Normal", "1 - Additive", "2 - Multiply", "3 - Screen"]
        blend_mode_menu = ttk.Combobox(param_grid, textvariable=self.blend_mode_var, values=blend_modes, state="readonly")
        blend_mode_menu.grid(row=row, column=1, padx=5, pady=10, sticky=tk.EW)
        row += 1
        
        # NEW: Axis Aligned (CRITICAL - controls billboard orientation)
        ttk.Label(param_grid, text="AXIS ALIGNED:", style="TLabel").grid(row=row, column=0, padx=5, pady=10, sticky=tk.W)
        axis_modes = ["0 - World", "1 - Camera", "3 - Motion"]
        axis_menu = ttk.Combobox(param_grid, textvariable=self.axis_aligned_var, values=axis_modes, state="readonly")
        axis_menu.grid(row=row, column=1, padx=5, pady=10, sticky=tk.EW)
        row += 1
        
        # NEW: Rotation
        ttk.Label(param_grid, text="ROTATION:", style="TLabel").grid(row=row, column=0, padx=5, pady=10, sticky=tk.W)
        rotation_slider = ttk.Scale(param_grid, from_=0.0, to=6.28319, variable=self.rotation_var, orient=tk.HORIZONTAL)
        rotation_slider.grid(row=row, column=1, padx=5, pady=10, sticky=tk.EW)
        self.rotation_value = ttk.Label(param_grid, text="0.000", style='Value.TLabel')
        self.rotation_value.grid(row=row, column=2, padx=5, pady=10)
        rotation_slider.bind("<Motion>", lambda e: self.update_value_label(self.rotation_var, self.rotation_value))
        row += 1
        
        # NEW: Animation Type
        ttk.Label(param_grid, text="ANIM TYPE:", style="TLabel").grid(row=row, column=0, padx=5, pady=10, sticky=tk.W)
        anim_types = ["0 - Static", "1 - Play Once", "2 - Loop"]
        anim_type_menu = ttk.Combobox(param_grid, textvariable=self.anim_type_var, values=anim_types, state="readonly")
        anim_type_menu.grid(row=row, column=1, padx=5, pady=10, sticky=tk.EW)
        row += 1
        
        # Animation Speed
        ttk.Label(param_grid, text="ANIM SPEED:", style="TLabel").grid(row=row, column=0, padx=5, pady=10, sticky=tk.W)
        anim_speed_slider = ttk.Scale(param_grid, from_=0.1, to=2.0, variable=self.anim_speed_var, orient=tk.HORIZONTAL)
        anim_speed_slider.grid(row=row, column=1, padx=5, pady=10, sticky=tk.EW)
        self.anim_speed_value = ttk.Label(param_grid, text="1.000", style='Value.TLabel')
        self.anim_speed_value.grid(row=row, column=2, padx=5, pady=10)
        anim_speed_slider.bind("<Motion>", lambda e: self.update_value_label(self.anim_speed_var, self.anim_speed_value))
        row += 1
        
        # NEW: End Frame
        ttk.Label(param_grid, text="END FRAME:", style="TLabel").grid(row=row, column=0, padx=5, pady=10, sticky=tk.W)
        end_frame_slider = ttk.Scale(param_grid, from_=0, to=100, variable=self.end_frame_var, orient=tk.HORIZONTAL)
        end_frame_slider.grid(row=row, column=1, padx=5, pady=10, sticky=tk.EW)
        self.end_frame_value = ttk.Label(param_grid, text="0", style='Value.TLabel')
        self.end_frame_value.grid(row=row, column=2, padx=5, pady=10)
        end_frame_slider.bind("<Motion>", lambda e: self.update_value_label(self.end_frame_var, self.end_frame_value, is_int=True))
        row += 1
        
        # NEW: Texture Number
        ttk.Label(param_grid, text="TEXTURE NUMBER:", style="TLabel").grid(row=row, column=0, padx=5, pady=10, sticky=tk.W)
        texture_number_slider = ttk.Scale(param_grid, from_=-1, to=10, variable=self.texture_number_var, orient=tk.HORIZONTAL)
        texture_number_slider.grid(row=row, column=1, padx=5, pady=10, sticky=tk.EW)
        self.texture_number_value = ttk.Label(param_grid, text="-1", style='Value.TLabel')
        self.texture_number_value.grid(row=row, column=2, padx=5, pady=10)
        texture_number_slider.bind("<Motion>", lambda e: self.update_value_label(self.texture_number_var, self.texture_number_value, is_int=True))
        row += 1
        
        # Cylinder Length (for cone effects)
        ttk.Label(param_grid, text="CYLINDER LENGTH:", style="TLabel").grid(row=row, column=0, padx=5, pady=10, sticky=tk.W)
        cylinder_length_slider = ttk.Scale(param_grid, from_=0.5, to=10.0, variable=self.cylinder_length_var, orient=tk.HORIZONTAL)
        cylinder_length_slider.grid(row=row, column=1, padx=5, pady=10, sticky=tk.EW)
        self.cylinder_length_value = ttk.Label(param_grid, text="2.000", style='Value.TLabel')
        self.cylinder_length_value.grid(row=row, column=2, padx=5, pady=10)
        cylinder_length_slider.bind("<Motion>", lambda e: self.update_value_label(self.cylinder_length_var, self.cylinder_length_value))
        
        param_grid.columnconfigure(1, weight=1)
    
    def update_value_label(self, var, label, is_int=False):
        """Update value label with current slider value"""
        value = var.get()
        if is_int:
            label.config(text=f"{int(value)}")
        else:
            label.config(text=f"{value:.3f}")
    
    def highlight_values(self):
        """Highlight visual-related parameters in the file viewer"""
        if not self.editor.file_content:
            return
        
        # Blend_Mode values
        pattern_blend = r'(Blend_Mode )(\d+)'
        for match in re.finditer(pattern_blend, self.editor.file_content):
            start_idx = f"1.0+{match.start(2)}c"
            end_idx = f"1.0+{match.end(2)}c"
            self.editor.file_viewer.tag_add("visual_value", start_idx, end_idx)
            self.editor.file_viewer.tag_add("highlight", start_idx, end_idx)
        
        # Axis_Aligned values
        pattern_axis = r'(Axis_Aligned )(\d+)'
        for match in re.finditer(pattern_axis, self.editor.file_content):
            start_idx = f"1.0+{match.start(2)}c"
            end_idx = f"1.0+{match.end(2)}c"
            self.editor.file_viewer.tag_add("visual_value", start_idx, end_idx)
            self.editor.file_viewer.tag_add("highlight", start_idx, end_idx)
        
        # Rotation values
        pattern_rotation = r'(Rotation NUMBER_VERSION_2\n\*+1: )([\d.-]+)'
        for match in re.finditer(pattern_rotation, self.editor.file_content):
            start_idx = f"1.0+{match.start(2)}c"
            end_idx = f"1.0+{match.end(2)}c"
            self.editor.file_viewer.tag_add("visual_value", start_idx, end_idx)
            self.editor.file_viewer.tag_add("highlight", start_idx, end_idx)
        
        # Anim_Type values
        pattern_anim_type = r'(Anim_Type )(\d+)'
        for match in re.finditer(pattern_anim_type, self.editor.file_content):
            start_idx = f"1.0+{match.start(2)}c"
            end_idx = f"1.0+{match.end(2)}c"
            self.editor.file_viewer.tag_add("visual_value", start_idx, end_idx)
            self.editor.file_viewer.tag_add("highlight", start_idx, end_idx)
        
        # Anim_Speed values
        pattern_anim = r'(Anim_Speed )([\d.-]+)'
        for match in re.finditer(pattern_anim, self.editor.file_content):
            start_idx = f"1.0+{match.start(2)}c"
            end_idx = f"1.0+{match.end(2)}c"
            self.editor.file_viewer.tag_add("visual_value", start_idx, end_idx)
            self.editor.file_viewer.tag_add("highlight", start_idx, end_idx)
        
        # End_Frame values
        pattern_end_frame = r'(End_Frame )(\d+)'
        for match in re.finditer(pattern_end_frame, self.editor.file_content):
            start_idx = f"1.0+{match.start(2)}c"
            end_idx = f"1.0+{match.end(2)}c"
            self.editor.file_viewer.tag_add("visual_value", start_idx, end_idx)
            self.editor.file_viewer.tag_add("highlight", start_idx, end_idx)
        
        # Texture_Number values
        pattern_texture = r'(Texture_Number )(-?\d+)'
        for match in re.finditer(pattern_texture, self.editor.file_content):
            start_idx = f"1.0+{match.start(2)}c"
            end_idx = f"1.0+{match.end(2)}c"
            self.editor.file_viewer.tag_add("visual_value", start_idx, end_idx)
            self.editor.file_viewer.tag_add("highlight", start_idx, end_idx)
        
        # Cylinder_Length values
        pattern_cylinder = r'(Cylinder_Length NUMBER_VERSION_2\n\*+1: )([\d.-]+)'
        for match in re.finditer(pattern_cylinder, self.editor.file_content):
            start_idx = f"1.0+{match.start(2)}c"
            end_idx = f"1.0+{match.end(2)}c"
            self.editor.file_viewer.tag_add("visual_value", start_idx, end_idx)
            self.editor.file_viewer.tag_add("highlight", start_idx, end_idx)