"""
Main Particle Effect Editor
Central orchestrator that combines all tabs and core functionality
"""
import tkinter as tk
from tkinter import filedialog, messagebox, ttk, scrolledtext
import os
from PIL import Image, ImageTk

from .theme_manager import ThemeManager
from .utils import create_military_background
from .file_manager import FileManager
from .tab_ordnance_color import ColorTabManager
from .tab_size import SizeTabManager
from .tab_emission import EmissionTabManager
from .tab_movement import MovementTabManager
from .tab_visual import VisualTabManager
from .tab_trail import TrailTabManager


class ParticleEffectEditor:
    """Main editor class that orchestrates all tabs and functionality"""
    
    def __init__(self, root):
        self.root = root
        self.root.title("Battalion Wars SFX Editor | Made By: Jasper_Zebra | Version 2.0")

        # Screen dimensions
        screen_width = root.winfo_screenwidth()
        screen_height = root.winfo_screenheight()

        # Dynamic window size (max 1100x850)
        window_width = min(1100, int(screen_width * 0.9))
        window_height = min(850, int(screen_height * 0.9))
        x_position = (screen_width - window_width) // 2
        y_position = (screen_height - window_height) // 2

        self.root.geometry(f"{window_width}x{window_height}+{x_position}+{y_position}")
        self.root.minsize(900, 600)  # Prevent shrinking too far

        # Theme setup
        theme_manager = ThemeManager(root)
        self.style, self.colors = theme_manager.setup_theme()

        # Set app icon
        self.set_app_icon()

        # State variables
        self.file_path = None
        self.file_content = None
        self.editable_values = {}
        self.descriptors = []
        self.file_viewer = None
        self.notebook = None
        self.status_var = tk.StringVar(value="Ready")

        # Background
        self.bg_image = create_military_background(950, 700)
        self.bg_label = tk.Label(root, image=self.bg_image)
        self.bg_label.place(x=0, y=0, relwidth=1, relheight=1)

        # Initialize file manager
        self.file_manager = FileManager(self)

        # Build UI
        self.setup_ui()

    def set_app_icon(self):
        """Set the application icon"""
        try:
            base = os.path.dirname(__file__)
            icon_path = os.path.join(base, "assets", "sfx_editor_icon.png")
            
            if os.path.exists(icon_path):
                icon = Image.open(icon_path)
                photo_icon = ImageTk.PhotoImage(icon)
                self.root.iconphoto(True, photo_icon)
                self.update_status("ICON LOADED SUCCESSFULLY")
            else:
                self.update_status("WARNING: ICON FILE NOT FOUND")
                print(f"Icon file not found at {icon_path}")
        except Exception as e:
            self.update_status("WARNING: FAILED TO LOAD ICON")
            print(f"Failed to set application icon: {str(e)}")
    
    def update_status(self, message):
        """Update status bar message"""
        if hasattr(self, 'status_var'):
            self.status_var.set(message)
        else:
            self._pending_status = message
            
    def setup_ui(self):
        """Setup the user interface"""
        container = ttk.Frame(self.root)
        container.pack(fill=tk.BOTH, expand=True)

        # Create main canvas + scrollbar
        canvas = tk.Canvas(
            container,
            bg=self.colors["background"],
            highlightthickness=0,
            borderwidth=0
        )
        v_scrollbar = ttk.Scrollbar(container, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=v_scrollbar.set)

        # Scrollable inner frame
        scrollable_frame = ttk.Frame(canvas, style="TFrame")
        frame_window = canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")

        # Track size of inner frame and update scroll region
        def update_scroll_region(event=None):
            canvas.configure(scrollregion=canvas.bbox("all"))
            canvas.itemconfig(frame_window, width=canvas.winfo_width())
            needs_scroll = canvas.bbox("all")[3] > canvas.winfo_height() + 2
            if needs_scroll:
                v_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
            else:
                v_scrollbar.pack_forget()

        scrollable_frame.bind("<Configure>", update_scroll_region)
        canvas.bind("<Configure>", update_scroll_region)

        # Scroll with mouse wheel
        def on_mousewheel(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

        canvas.bind_all("<MouseWheel>", on_mousewheel)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # Actual UI contents
        main_frame = ttk.Frame(scrollable_frame, padding="10", style="TFrame")
        main_frame.pack(fill=tk.BOTH, expand=True, padx=15, pady=15)

        # Title
        title_frame = ttk.Frame(main_frame, style="TitleBG.TFrame")
        title_frame.pack(fill=tk.X, pady=(0, 10))
        ttk.Label(title_frame, text="SFX Editor", style='Title.TLabel').pack(fill=tk.X, pady=10)

        # File picker
        file_frame = ttk.LabelFrame(main_frame, text="File", padding="5", style="Card.TLabelframe")
        file_frame.pack(fill=tk.X, pady=5)
        self.file_label = ttk.Label(file_frame, text="No file selected", style="Muted.TLabel")
        self.file_label.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)
        ttk.Button(file_frame, text="Browse", command=self.browse_file, style="Secondary.TButton").pack(side=tk.RIGHT, padx=5)

        # Paned window for viewer + parameter editor
        paned_window = ttk.PanedWindow(main_frame, orient=tk.HORIZONTAL)
        paned_window.pack(fill=tk.BOTH, expand=True, pady=5)

        # Left: File viewer
        self.setup_file_viewer(paned_window)

        # Right: Tabs
        param_container = ttk.Frame(paned_window, style="TFrame")
        paned_window.add(param_container, weight=1)

        self.notebook = ttk.Notebook(param_container)
        self.notebook.pack(fill=tk.BOTH, expand=True, pady=5)
        self.notebook.bind("<<NotebookTabChanged>>", self.on_tab_change)

        # Initialize tab managers
        self.color_tab = ColorTabManager(self, self.notebook)
        self.size_tab = SizeTabManager(self, self.notebook)
        self.emission_tab = EmissionTabManager(self, self.notebook)
        self.movement_tab = MovementTabManager(self, self.notebook)
        self.visual_tab = VisualTabManager(self, self.notebook)
        self.trail_tab = TrailTabManager(self, self.notebook)

        # Apply button
        button_frame = ttk.Frame(main_frame, style="TFrame")
        button_frame.pack(fill=tk.X, pady=10)
        ttk.Button(button_frame, text="Apply Changes", command=self.file_manager.apply_changes, style="Primary.TButton").pack(side=tk.RIGHT, padx=5)

        # Status bar
        status_frame = ttk.Frame(self.root, style="Status.TFrame")
        status_frame.pack(fill=tk.X, side=tk.BOTTOM)
        self.status_var = tk.StringVar(value="Ready")

        if hasattr(self, "_pending_status"):
            self.status_var.set(self._pending_status)
            delattr(self, "_pending_status")

        ttk.Label(status_frame, textvariable=self.status_var, style="Status.TLabel").pack(fill=tk.X)

    def on_tab_change(self, event):
        """Handle tab change events to update parameter highlighting"""
        selected_tab = self.notebook.tab(self.notebook.select(), "text")
        
        # Clear all highlight tags first
        if hasattr(self, 'file_viewer'):
            self.file_viewer.tag_remove("highlight", "1.0", tk.END)
        
        # If no file loaded, do nothing
        if not self.file_content:
            return
        
        # Delegate to appropriate tab manager
        if selected_tab == "ORDNANCE COLOR":
            self.color_tab.highlight_values()
        elif selected_tab == "SIZE":
            self.size_tab.highlight_values()
        elif selected_tab == "EMISSION":
            self.emission_tab.highlight_values()
        elif selected_tab == "MOVEMENT":
            self.movement_tab.highlight_values()
        elif selected_tab == "VISUAL":
            self.visual_tab.highlight_values()
        elif selected_tab == "TRAIL":
            self.trail_tab.highlight_values()

    def browse_file(self):
        """Browse for a particle effect file to load"""
        file_path = filedialog.askopenfilename(
            title="Select Particle Effect File",
            filetypes=[("Text Files", "*.txt"), ("All Files", "*.*")]
        )
        
        if file_path:
            self.file_path = file_path
            self.file_label.config(text=os.path.basename(file_path))
            
            try:
                with open(file_path, 'r') as file:
                    self.file_content = file.read()
                    
                self.file_manager.display_file_content()
                self.file_manager.parse_particle_descriptors()
                self.file_manager.populate_descriptor_selector()
                self.file_manager.extract_parameters()
                
                self.status_var.set(f"LOADED: {os.path.basename(file_path)}")
            except Exception as e:
                messagebox.showerror("Error", f"Failed to load file: {str(e)}")

    def setup_file_viewer(self, parent):
        """Setup the file viewer panel with its own independent scrolling"""
        file_viewer_frame = ttk.LabelFrame(parent, text="FILE CONTENTS", padding="5", style="Card.TLabelframe")
        
        self.file_viewer = scrolledtext.ScrolledText(
            file_viewer_frame, 
            wrap=tk.WORD,
            width=50,
            height=25,
            font=("Courier New", 9),
            bg=self.colors['input_bg'],
            fg=self.colors['foreground'],
            insertbackground=self.colors['foreground']
        )
        self.file_viewer.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Configure tags for highlighting
        self.file_viewer.tag_configure("red_value", foreground=self.colors['error'], background="#401010")
        self.file_viewer.tag_configure("green_value", foreground=self.colors['success'], background="#104010")
        self.file_viewer.tag_configure("blue_value", foreground=self.colors['primary'], background="#102040")
        self.file_viewer.tag_configure("alpha_value", foreground=self.colors['text_primary'], background="#404040")
        
        self.file_viewer.tag_configure("size_value", foreground=self.colors['text_primary'], background="#403010")
        self.file_viewer.tag_configure("emission_value", foreground=self.colors['text_primary'], background="#104040")
        self.file_viewer.tag_configure("movement_value", foreground=self.colors['text_primary'], background="#301040")
        self.file_viewer.tag_configure("visual_value", foreground=self.colors['text_primary'], background="#404010")
        self.file_viewer.tag_configure("trail_value", foreground=self.colors['text_primary'], background="#104040")
        
        self.file_viewer.tag_configure("highlight", background=self.colors['surface_light'])
        
        self.file_viewer.config(state=tk.DISABLED)
        
        # Bind mousewheel to ONLY scroll the file viewer when mouse is over it
        def on_file_viewer_mousewheel(event):
            # Only scroll the file viewer, don't propagate to parent
            self.file_viewer.yview_scroll(int(-1 * (event.delta / 120)), "units")
            return "break"  # Prevent event from propagating
        
        self.file_viewer.bind("<MouseWheel>", on_file_viewer_mousewheel)
        
        parent.add(file_viewer_frame, weight=2)