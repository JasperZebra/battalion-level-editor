from PIL import Image, ImageTk, ImageDraw

def create_military_background(width, height):
    """Create a clean, modern background for the application
    
    Args:
        width (int): Width of the background image
        height (int): Height of the background image
        
    Returns:
        PhotoImage: Tkinter-compatible image for use as background
    """
    # Create a clean gradient background
    bg = Image.new('RGB', (width, height), (30, 30, 46))
    
    draw = ImageDraw.Draw(bg)
    
    # Add subtle vertical gradient
    for y in range(height):
        # Gradual color shift from top to bottom
        intensity = 30 + int((y / height) * 16)  # 30 to 46
        color = (intensity, intensity, intensity + 16)
        draw.line([(0, y), (width, y)], fill=color, width=1)
    
    # Add very subtle grid pattern (optional, can be removed for even cleaner look)
    grid_spacing = 50
    grid_color = (40, 40, 56)
    
    for x in range(0, width, grid_spacing):
        draw.line([(x, 0), (x, height)], fill=grid_color, width=1)
    
    for y in range(0, height, grid_spacing):
        draw.line([(0, y), (width, y)], fill=grid_color, width=1)
    
    # Convert to PhotoImage for Tkinter
    photo = ImageTk.PhotoImage(bg)
    return photo