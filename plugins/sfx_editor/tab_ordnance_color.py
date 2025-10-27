"""
Color Tab Manager
Handles the ORDNANCE COLOR tab functionality
"""
import re
import tkinter as tk
from tkinter import ttk, colorchooser


class ColorTabManager:
    """Manages the Color tab interface and functionality"""
    
    def __init__(self, editor, notebook):
        self.editor = editor
        self.notebook = notebook
        self.colors = editor.colors
        
        # State variables
        self.descriptor_var = tk.StringVar()
        self.start_red_var = tk.DoubleVar(value=0.0)
        self.start_green_var = tk.DoubleVar(value=0.0)
        self.start_blue_var = tk.DoubleVar(value=0.0)
        self.start_alpha_var = tk.DoubleVar(value=1.0)
        
        self.end_red_var = tk.DoubleVar(value=0.0)
        self.end_green_var = tk.DoubleVar(value=0.0)
        self.end_blue_var = tk.DoubleVar(value=0.0)
        self.end_alpha_var = tk.DoubleVar(value=1.0)
        
        self.transition_red_var = tk.DoubleVar(value=0.0)
        self.transition_green_var = tk.DoubleVar(value=0.0)
        self.transition_blue_var = tk.DoubleVar(value=0.0)
        self.transition_alpha_var = tk.DoubleVar(value=1.0)
        
        # Settings variables
        self.use_end_var = tk.BooleanVar(value=True)
        self.use_transition_var = tk.BooleanVar(value=True)
        self.transition_point_var = tk.DoubleVar(value=0.4)
        
        # Subscribe to variable changes to update previews
        self.start_red_var.trace('w', lambda *args: self.update_preview('start'))
        self.start_green_var.trace('w', lambda *args: self.update_preview('start'))
        self.start_blue_var.trace('w', lambda *args: self.update_preview('start'))
        self.start_alpha_var.trace('w', lambda *args: self.update_preview('start'))
        
        self.end_red_var.trace('w', lambda *args: self.update_preview('end'))
        self.end_green_var.trace('w', lambda *args: self.update_preview('end'))
        self.end_blue_var.trace('w', lambda *args: self.update_preview('end'))
        self.end_alpha_var.trace('w', lambda *args: self.update_preview('end'))
        
        self.transition_red_var.trace('w', lambda *args: self.update_preview('transition'))
        self.transition_green_var.trace('w', lambda *args: self.update_preview('transition'))
        self.transition_blue_var.trace('w', lambda *args: self.update_preview('transition'))
        self.transition_alpha_var.trace('w', lambda *args: self.update_preview('transition'))
        
        self.setup_ui()
    
    def setup_ui(self):
        """Setup the color tab UI"""
        color_frame = ttk.Frame(self.notebook, style="TFrame")
        self.notebook.add(color_frame, text="ORDNANCE COLOR")
        
        scroll_frame = ttk.Frame(color_frame)
        scroll_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Descriptor selector
        self.setup_descriptor_selector(scroll_frame)
        
        # Color sections
        self.setup_color_section(scroll_frame, "START", "start", "Start color (initial state)")
        self.setup_color_section(scroll_frame, "END", "end", "End color (final state)")
        self.setup_color_section(scroll_frame, "TRANSITION", "transition", "Transition color (midpoint)")
    
    def setup_descriptor_selector(self, parent):
        """Setup descriptor selector dropdown"""
        selector_frame = ttk.LabelFrame(parent, text="SELECT PARTICLE SYSTEM", padding="5", style="Card.TLabelframe")
        selector_frame.pack(fill=tk.X, pady=5)
        
        info_label = ttk.Label(
            selector_frame, 
            text="Choose which color range descriptor to edit (files can have multiple color systems):", 
            style="Muted.TLabel",
            wraplength=500
        )
        info_label.pack(anchor=tk.W, padx=5, pady=2)
        
        self.descriptor_menu = ttk.Combobox(
            selector_frame,
            textvariable=self.descriptor_var,
            state="readonly",
            width=60
        )
        self.descriptor_menu.pack(fill=tk.X, padx=5, pady=5)
        self.descriptor_menu.bind('<<ComboboxSelected>>', self.on_descriptor_changed)
        
        # If we have pending descriptors from file load, populate now
        if hasattr(self, '_pending_descriptors'):
            self.descriptor_menu['values'] = self._pending_descriptors
            if len(self._pending_descriptors) > 0:
                self.descriptor_var.set(self._pending_descriptors[0])
                current_tab = self.notebook.tab(self.notebook.select(), "text")
                if current_tab == "ORDNANCE COLOR":
                    self.editor.root.after(100, lambda: self.load_descriptor_values(0))
            delattr(self, '_pending_descriptors')
        
        # Add settings section
        self.setup_color_settings(parent)
    
    def setup_color_settings(self, parent):
        """Setup color range settings (Use_End, Use_Transition, Transition_Point)"""
        settings_frame = ttk.LabelFrame(parent, text="COLOR RANGE SETTINGS", padding="5", style="Card.TLabelframe")
        settings_frame.pack(fill=tk.X, pady=5)
        
        settings_grid = ttk.Frame(settings_frame, style="TFrame")
        settings_grid.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # State variables for settings
        self.use_end_var = tk.IntVar(value=1)
        self.use_transition_var = tk.IntVar(value=1)
        self.transition_point_var = tk.DoubleVar(value=0.4)
        
        # Use End (checkbox)
        ttk.Label(settings_grid, text="USE END COLOR:", style="TLabel").grid(row=0, column=0, padx=5, pady=10, sticky=tk.W)
        use_end_check = ttk.Checkbutton(settings_grid, variable=self.use_end_var, text="Enable end color")
        use_end_check.grid(row=0, column=1, padx=5, pady=10, sticky=tk.W)
        self.use_end_value = ttk.Label(settings_grid, text="1", style='Value.TLabel')
        self.use_end_value.grid(row=0, column=2, padx=5, pady=10)
        self.use_end_var.trace('w', lambda *args: self.update_setting_label(self.use_end_var, self.use_end_value))
        
        # Use Transition (checkbox)
        ttk.Label(settings_grid, text="USE TRANSITION COLOR:", style="TLabel").grid(row=1, column=0, padx=5, pady=10, sticky=tk.W)
        use_trans_check = ttk.Checkbutton(settings_grid, variable=self.use_transition_var, text="Enable transition color")
        use_trans_check.grid(row=1, column=1, padx=5, pady=10, sticky=tk.W)
        self.use_transition_value = ttk.Label(settings_grid, text="1", style='Value.TLabel')
        self.use_transition_value.grid(row=1, column=2, padx=5, pady=10)
        self.use_transition_var.trace('w', lambda *args: self.update_setting_label(self.use_transition_var, self.use_transition_value))
        
        # Transition Point (slider)
        ttk.Label(settings_grid, text="TRANSITION POINT:", style="TLabel").grid(row=2, column=0, padx=5, pady=10, sticky=tk.W)
        transition_slider = ttk.Scale(settings_grid, from_=0.0, to=1.0, variable=self.transition_point_var, orient=tk.HORIZONTAL)
        transition_slider.grid(row=2, column=1, padx=5, pady=10, sticky=tk.EW)
        self.transition_point_value = ttk.Label(settings_grid, text="0.400", style='Value.TLabel')
        self.transition_point_value.grid(row=2, column=2, padx=5, pady=10)
        transition_slider.bind("<Motion>", lambda e: self.update_value_label(self.transition_point_var, self.transition_point_value))
        
        settings_grid.columnconfigure(1, weight=1)
    
    def update_setting_label(self, var, label):
        """Update setting label with current value (0 or 1 for checkboxes)"""
        value = var.get()
        label.config(text=f"{value}")
    
    def on_descriptor_changed(self, event=None):
        """Handle descriptor selection change"""
        if not hasattr(self, 'descriptor_var'):
            return
            
        selected = self.descriptor_var.get()
        if not selected:
            return
            
        idx = int(selected.split(':')[0])
        self.load_descriptor_values(idx)
    
    def load_descriptor_values(self, idx):
        """Load a specific descriptor's values into the UI"""
        if not hasattr(self.editor, 'descriptors') or idx >= len(self.editor.descriptors):
            print(f"[DEBUG] Cannot load descriptor {idx}")
            return
        
        descriptor = self.editor.descriptors[idx]
        print(f"[DEBUG] Loading descriptor: {descriptor['name']}")
        print(f"[DEBUG] Extracted values: {descriptor['values']}")
        
        # Load START colors and update labels/previews
        for color in ['Red', 'Green', 'Blue', 'Alpha']:
            key = f'Start_{color}'
            if key in descriptor['values']:
                value = descriptor['values'][key]
                var = getattr(self, f'start_{color.lower()}_var')
                label = getattr(self, f'start_{color.lower()}_value')
                var.set(value)
                self.update_value_label(var, label)
                print(f"[DEBUG] Set {key}: {value}")
        
        # Load END colors and update labels/previews
        for color in ['Red', 'Green', 'Blue', 'Alpha']:
            key = f'End_{color}'
            if key in descriptor['values']:
                value = descriptor['values'][key]
                var = getattr(self, f'end_{color.lower()}_var')
                label = getattr(self, f'end_{color.lower()}_value')
                var.set(value)
                self.update_value_label(var, label)
                print(f"[DEBUG] Set {key}: {value}")
        
        # Load TRANSITION colors and update labels/previews
        for color in ['Red', 'Green', 'Blue', 'Alpha']:
            key = f'Transition_{color}'
            if key in descriptor['values']:
                value = descriptor['values'][key]
                var = getattr(self, f'transition_{color.lower()}_var')
                label = getattr(self, f'transition_{color.lower()}_value')
                var.set(value)
                self.update_value_label(var, label)
                print(f"[DEBUG] Set {key}: {value}")
        
        # Load settings - Use_End, Use_Transition, Transition_Point
        if 'Use_End' in descriptor['values']:
            value = descriptor['values']['Use_End']
            self.use_end_var.set(value)
            self.update_setting_label(self.use_end_var, self.use_end_value)
            print(f"[DEBUG] Set Use_End: {value}")
        
        if 'Use_Transition' in descriptor['values']:
            value = descriptor['values']['Use_Transition']
            self.use_transition_var.set(value)
            self.update_setting_label(self.use_transition_var, self.use_transition_value)
            print(f"[DEBUG] Set Use_Transition: {value}")
        
        if 'Transition_Point' in descriptor['values']:
            value = descriptor['values']['Transition_Point']
            self.transition_point_var.set(value)
            self.update_value_label(self.transition_point_var, self.transition_point_value)
            print(f"[DEBUG] Set Transition_Point: {value}")
        
        # Update all previews after loading
        self.update_preview('start')
        self.update_preview('end')
        self.update_preview('transition')
        print("[DEBUG] All previews updated")
    
    def setup_color_section(self, parent, label, prefix, description):
        """Setup a color section (START, END, or TRANSITION)"""
        section_frame = ttk.LabelFrame(parent, text=f"{label} COLOR", padding="5", style="Card.TLabelframe")
        section_frame.pack(fill=tk.BOTH, expand=True, pady=5)
        
        # Description
        ttk.Label(section_frame, text=description, style="Muted.TLabel", wraplength=500).pack(anchor=tk.W, padx=5, pady=2)
        
        # Color picker button
        picker_frame = ttk.Frame(section_frame, style="TFrame")
        picker_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(picker_frame, text=f"{label} COLOR SELECTION:", style="TLabel").pack(side=tk.LEFT, padx=5)
        
        ttk.Button(
            picker_frame, 
            text="CUSTOM COLOR", 
            command=lambda: self.open_color_picker(prefix), 
            style="Secondary.TButton"
        ).pack(side=tk.LEFT, padx=5)
        
        # RGB sliders
        rgb_frame = ttk.Frame(section_frame, style="TFrame")
        rgb_frame.pack(fill=tk.BOTH, expand=True, pady=5)
        
        for idx, (color_name, color_key) in enumerate([('RED', 'red'), ('GREEN', 'green'), ('BLUE', 'blue'), ('OPACITY', 'alpha')]):
            ttk.Label(rgb_frame, text=f"{color_name}:", style="TLabel", 
                     foreground=self.colors.get(color_key, self.colors['text_primary'])).grid(row=idx, column=0, padx=5, pady=5, sticky=tk.W)
            
            var = getattr(self, f'{prefix}_{color_key}_var')
            slider = ttk.Scale(rgb_frame, from_=0.0, to=1.0, variable=var, orient=tk.HORIZONTAL)
            slider.grid(row=idx, column=1, padx=5, pady=5, sticky=tk.EW)
            
            value_label = ttk.Label(rgb_frame, text="0.000", style='Value.TLabel')
            value_label.grid(row=idx, column=2, padx=5, pady=5)
            setattr(self, f'{prefix}_{color_key}_value', value_label)
            
            slider.bind("<Motion>", lambda e, v=var, l=value_label: self.update_value_label(v, l))
            slider.bind("<ButtonRelease-1>", lambda e: self.update_preview(prefix))
        
        # Color preview
        preview_frame = ttk.Frame(section_frame, style="TFrame")
        preview_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(preview_frame, text="PREVIEW:", style="TLabel").pack(side=tk.LEFT, padx=5)
        
        preview_container = ttk.Frame(preview_frame, style="TFrame", relief='solid', borderwidth=2)
        preview_container.pack(side=tk.LEFT, padx=10)
        
        preview_canvas = tk.Canvas(preview_container, width=120, height=40, bg="#000000", highlightthickness=0)
        preview_canvas.pack(padx=2, pady=2)
        setattr(self, f'{prefix}_color_preview', preview_canvas)
        
        hex_label = ttk.Label(preview_frame, text="#000000", style='Value.TLabel')
        hex_label.pack(side=tk.LEFT, padx=10)
        setattr(self, f'{prefix}_hex_color', hex_label)
        
        rgb_frame.columnconfigure(1, weight=1)
    
    def update_value_label(self, var, label, is_int=False):
        """Update value label with current slider value"""
        value = var.get()
        if is_int:
            label.config(text=f"{int(value)}")
        else:
            label.config(text=f"{value:.3f}")
    
    def open_color_picker(self, prefix):
        """Open color picker dialog"""
        r = int(getattr(self, f'{prefix}_red_var').get() * 255)
        g = int(getattr(self, f'{prefix}_green_var').get() * 255)
        b = int(getattr(self, f'{prefix}_blue_var').get() * 255)
        current_color = f"#{r:02x}{g:02x}{b:02x}"
        
        color_result = colorchooser.askcolor(
            color=current_color,
            title=f"{prefix.upper()} COLOR SELECTION"
        )
        
        if color_result[1]:
            r, g, b = color_result[0]
            getattr(self, f'{prefix}_red_var').set(r / 255)
            getattr(self, f'{prefix}_green_var').set(g / 255)
            getattr(self, f'{prefix}_blue_var').set(b / 255)
            
            self.update_preview(prefix)
    
    def update_preview(self, prefix):
        """Update the color preview for a section"""
        r = int(getattr(self, f'{prefix}_red_var').get() * 255)
        g = int(getattr(self, f'{prefix}_green_var').get() * 255)
        b = int(getattr(self, f'{prefix}_blue_var').get() * 255)
        color = f"#{r:02x}{g:02x}{b:02x}"
        
        preview_canvas = getattr(self, f'{prefix}_color_preview', None)
        hex_label = getattr(self, f'{prefix}_hex_color', None)
        
        if preview_canvas:
            preview_canvas.config(bg=color)
        if hex_label:
            hex_label.config(text=color.upper())
    
    def highlight_values(self):
        """Highlight all color values in the file viewer"""
        if not self.editor.file_content:
            return
        
        for color, tag in [
            ("Start_Red", "red_value"), 
            ("Start_Green", "green_value"), 
            ("Start_Blue", "blue_value"),
            ("Start_Alpha", "alpha_value"),
            ("End_Red", "red_value"),
            ("End_Green", "green_value"),
            ("End_Blue", "blue_value"),
            ("End_Alpha", "alpha_value"),
            ("Transition_Red", "red_value"),
            ("Transition_Green", "green_value"),
            ("Transition_Blue", "blue_value"),
            ("Transition_Alpha", "alpha_value")
        ]:
            pattern = fr'({color}\s+NUMBER_VERSION_2\n\*+1:\s+)([\d.-]+)'
            for match in re.finditer(pattern, self.editor.file_content):
                start_idx = f"1.0+{match.start(2)}c"
                end_idx = f"1.0+{match.end(2)}c"
                self.editor.file_viewer.tag_add(tag, start_idx, end_idx)
                self.editor.file_viewer.tag_add("highlight", start_idx, end_idx)