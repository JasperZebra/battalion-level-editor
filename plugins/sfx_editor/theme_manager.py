import tkinter as tk
from tkinter import ttk

class ThemeManager:
    def __init__(self, root):
        self.root = root
        self.colors = self.define_colors()
    
    def define_colors(self):
        """Define a modern, clean color palette"""
        return {
            # Main colors - softer, more modern palette
            'background': '#1E1E2E',       # Deep blue-gray background
            'foreground': '#CDD6F4',       # Soft white text
            'surface': '#313244',          # Elevated surface color
            'surface_light': '#45475A',    # Lighter surface for hover
            
            # Accent colors - vibrant but not harsh
            'primary': '#89B4FA',          # Soft blue (primary actions)
            'secondary': '#F5C2E7',        # Soft pink (secondary)
            'success': '#A6E3A1',          # Soft green (success/apply)
            'warning': '#FAB387',          # Soft orange (warnings)
            'error': '#F38BA8',            # Soft red (errors)
            'info': '#94E2D5',             # Soft cyan (info)
            
            # UI element colors
            'border': '#585B70',           # Subtle borders
            'input_bg': '#313244',         # Input backgrounds
            'input_border': '#585B70',     # Input borders
            'button_hover': '#6C7086',     # Button hover state
            'title_bg': '#181825',         # Title background (darker)
            'status_bg': '#181825',        # Status bar background
            
            # Text colors
            'text_primary': '#CDD6F4',     # Primary text
            'text_secondary': '#BAC2DE',   # Secondary text
            'text_muted': '#6C7086',       # Muted text
            
            # Tab colors - subtle variations
            'tab_bg': '#313244',
            'tab_fg': '#BAC2DE',
            'tab_selected_bg': '#45475A',
            'tab_selected_fg': '#CDD6F4',
            'tab_hover': '#3E4051',
            
            # Color-specific backgrounds for sliders
            'red_bg': '#2D1B1B',
            'green_bg': '#1B2D1B',
            'blue_bg': '#1B1B2D',
            'alpha_bg': '#252525',
        }
    
    def setup_theme(self):
        """Configure modern, clean styling for the application"""
        style = ttk.Style()
        style.theme_use('clam')
        
        c = self.colors  # Shorthand for colors

        # GLOBAL CONFIGURATION
        style.configure('.',
            background=c['background'],
            foreground=c['foreground'],
            fieldbackground=c['input_bg'],
            troughcolor=c['input_bg'],
            borderwidth=0,
            font=('Segoe UI', 10)
        )

        # FRAME STYLING - Modern flat design
        style.configure('TFrame',
            background=c['background'],
            borderwidth=0
        )
        
        style.configure('Card.TFrame',
            background=c['surface'],
            borderwidth=0,
            relief='flat'
        )
        
        style.configure('TitleBG.TFrame',
            background=c['title_bg']
        )

        # LABEL FRAME STYLING - Modern card style
        style.configure('TLabelframe',
            background=c['background'],
            bordercolor=c['border'],
            borderwidth=1,
            relief='flat'
        )
        style.configure('TLabelframe.Label',
            background=c['background'],
            foreground=c['primary'],
            font=('Segoe UI Semibold', 11)
        )
        
        # Card style label frames
        style.configure('Card.TLabelframe',
            background=c['surface'],
            bordercolor=c['border'],
            borderwidth=1,
            relief='flat'
        )
        style.configure('Card.TLabelframe.Label',
            background=c['surface'],
            foreground=c['primary'],
            font=('Segoe UI Semibold', 11)
        )

        # BUTTON STYLING - Modern flat buttons
        style.configure('TButton',
            background=c['surface'],
            foreground=c['text_primary'],
            bordercolor=c['border'],
            borderwidth=1,
            relief='flat',
            padding=(12, 8),
            font=('Segoe UI Semibold', 10)
        )
        style.map('TButton',
            background=[('pressed', c['button_hover']), ('active', c['surface_light'])],
            bordercolor=[('active', c['primary'])]
        )
        
        # Primary button (Apply/Save actions)
        style.configure('Primary.TButton',
            background=c['success'],
            foreground=c['background'],
            borderwidth=0,
            relief='flat',
            padding=(16, 10),
            font=('Segoe UI Semibold', 11)
        )
        style.map('Primary.TButton',
            background=[('pressed', '#8DD889'), ('active', '#B5F0B1')]
        )
        
        # Secondary button
        style.configure('Secondary.TButton',
            background=c['primary'],
            foreground=c['background'],
            borderwidth=0,
            relief='flat',
            padding=(12, 8),
            font=('Segoe UI Semibold', 10)
        )
        style.map('Secondary.TButton',
            background=[('pressed', '#6C9FE8'), ('active', '#A5C7FA')]
        )

        # LABEL STYLING - Modern typography
        style.configure('TLabel',
            background=c['background'],
            foreground=c['text_primary'],
            font=('Segoe UI', 10)
        )
        
        # Title
        style.configure('Title.TLabel', 
            background=c['title_bg'],
            foreground=c['primary'],
            font=('Segoe UI', 22, 'bold'),
            anchor='center'
        )
        
        # Subtitle
        style.configure('Subtitle.TLabel', 
            background=c['background'],
            foreground=c['text_secondary'],
            font=('Segoe UI', 12),
            anchor='center'
        )
        
        # Value labels (for slider values)
        style.configure('Value.TLabel', 
            background=c['background'],
            foreground=c['primary'],
            font=('Segoe UI Semibold', 11)
        )
        
        # Section headers
        style.configure('Header.TLabel', 
            background=c['background'],
            foreground=c['text_primary'],
            font=('Segoe UI Semibold', 10)
        )
        
        # Muted text
        style.configure('Muted.TLabel', 
            background=c['background'],
            foreground=c['text_muted'],
            font=('Segoe UI', 9)
        )
        
        # Status bar
        style.configure('Status.TFrame',
            background=c['status_bg'],
            relief='flat'
        )
        
        style.configure('Status.TLabel', 
            background=c['status_bg'],
            foreground=c['text_secondary'],
            font=('Segoe UI', 9),
            padding=5
        )

        # SCALE (SLIDER) STYLING - Modern minimal design
        style.configure('TScale',
            background=c['background'],
            troughcolor=c['input_bg'],
            bordercolor=c['border'],
            borderwidth=0,
            sliderrelief='flat'
        )
        
        # Color-specific sliders
        style.configure('Red.Horizontal.TScale',
            background=c['background'],
            troughcolor=c['red_bg'],
            borderwidth=0,
            sliderrelief='flat'
        )
        
        style.configure('Green.Horizontal.TScale',
            background=c['background'],
            troughcolor=c['green_bg'],
            borderwidth=0,
            sliderrelief='flat'
        )
        
        style.configure('Blue.Horizontal.TScale',
            background=c['background'],
            troughcolor=c['blue_bg'],
            borderwidth=0,
            sliderrelief='flat'
        )
        
        style.configure('Alpha.Horizontal.TScale',
            background=c['background'],
            troughcolor=c['alpha_bg'],
            borderwidth=0,
            sliderrelief='flat'
        )

        # COMBOBOX STYLING - Modern dropdown
        style.configure('TCombobox',
            background=c['input_bg'],
            foreground=c['text_primary'],
            fieldbackground=c['input_bg'],
            arrowcolor=c['primary'],
            borderwidth=1,
            bordercolor=c['border']
        )
        style.map('TCombobox',
            fieldbackground=[('readonly', c['input_bg'])],
            foreground=[('readonly', c['text_primary'])],
            bordercolor=[('focus', c['primary'])]
        )

        # NOTEBOOK (TABS) STYLING - Modern tab design
        style.configure('TNotebook',
            background=c['background'],
            borderwidth=0,
            tabmargins=[0, 5, 0, 0]
        )
        
        style.configure('TNotebook.Tab',
            background=c['tab_bg'],
            foreground=c['tab_fg'],
            padding=[20, 10],
            borderwidth=0,
            font=('Segoe UI Semibold', 10)
        )
        
        style.map('TNotebook.Tab',
            background=[
                ('selected', c['tab_selected_bg']),
                ('active', c['tab_hover'])
            ],
            foreground=[('selected', c['tab_selected_fg'])],
            expand=[('selected', [1, 1, 1, 0])]
        )

        # SCROLLBAR STYLING - Modern thin scrollbar
        style.configure('TScrollbar',
            background=c['surface'],
            troughcolor=c['background'],
            borderwidth=0,
            arrowsize=12
        )
        style.map('TScrollbar',
            background=[('active', c['surface_light'])]
        )

        # ROOT WINDOW
        self.root.configure(bg=c['background'])

        return style, self.colors