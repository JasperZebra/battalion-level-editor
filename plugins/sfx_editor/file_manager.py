"""
File Manager for Particle Effect Editor
Handles file I/O, parsing, and content management
"""
import re
from tkinter import messagebox


class FileManager:
    """Manages file operations including parsing and saving"""
    
    def __init__(self, editor):
        self.editor = editor
    
    def display_file_content(self):
        """Display file content in the viewer"""
        self.editor.file_viewer.config(state="normal")
        self.editor.file_viewer.delete("1.0", "end")
        self.editor.file_viewer.insert("1.0", self.editor.file_content)
        self.editor.file_viewer.config(state="disabled")
    
    def parse_particle_descriptors(self):
        """Parse the file into individual particle descriptors"""
        if not self.editor.file_content:
            return
        
        # Split by the separator pattern
        parts = re.split(r'(\*+\n)', self.editor.file_content)
        
        self.editor.descriptors = []
        current_content = ""
        separator = ""
        
        for i, part in enumerate(parts):
            if part.startswith('*'):
                separator = part
            elif part.strip():
                # Extract descriptor name if possible
                name_match = re.search(r'Particle_Descriptor_Name\s+(\S+)', part)
                name = name_match.group(1) if name_match else "Unknown"
                
                self.editor.descriptors.append({
                    'index': len(self.editor.descriptors),
                    'name': name,
                    'content': part,
                    'separator': separator,
                    'values': self._extract_values(part)
                })
    
    def _extract_values(self, content):
        """Extract all parameter values from a descriptor"""
        values = {}
        
        # Color values - improved regex with optional whitespace
        for color in ['Red', 'Green', 'Blue', 'Alpha']:
            for prefix in ['Start_', 'End_', 'Transition_']:
                pattern = fr'{prefix}{color}\s+NUMBER_VERSION_2\n\*+1:\s+([\d.-]+)'
                match = re.search(pattern, content)
                if match:
                    values[f'{prefix}{color}'] = float(match.group(1))
        
        # Use_End (0 or 1)
        pattern_use_end = r'Use_End\s+(\d+)'
        match = re.search(pattern_use_end, content)
        if match:
            values['Use_End'] = int(match.group(1))
        
        # Use_Transition (0 or 1)
        pattern_use_trans = r'Use_Transition\s+(\d+)'
        match = re.search(pattern_use_trans, content)
        if match:
            values['Use_Transition'] = int(match.group(1))
        
        # Transition_Point (float value)
        pattern_trans_point = r'Transition_Point\s+([\d.-]+)'
        match = re.search(pattern_trans_point, content)
        if match:
            values['Transition_Point'] = float(match.group(1))
        
        return values
    
    def populate_descriptor_selector(self):
        """Populate the descriptor selector dropdown"""
        if not hasattr(self.editor, 'descriptors') or len(self.editor.descriptors) == 0:
            return
        
        descriptor_names = [f"{d['index']}: {d['name']}" for d in self.editor.descriptors]
        
        if hasattr(self.editor.color_tab, 'descriptor_menu'):
            self.editor.color_tab.descriptor_menu['values'] = descriptor_names
            if len(descriptor_names) > 0:
                self.editor.color_tab.descriptor_var.set(descriptor_names[0])
                current_tab = self.editor.notebook.tab(self.editor.notebook.select(), "text")
                if current_tab == "ORDNANCE COLOR":
                    self.editor.root.after(100, lambda: self.editor.color_tab.load_descriptor_values(0))
                else:
                    self.editor.color_tab._should_load_descriptor = True
        else:
            self.editor.color_tab._pending_descriptors = descriptor_names
            self.editor.color_tab._should_load_descriptor = True
    
    def extract_parameters(self):
        """Extract all parameter values from the file for all tabs"""
        if not self.editor.file_content:
            return
        
        # ============ SIZE TAB PARAMETERS ============
        radius_pattern = r'Radius\s+NUMBER_VERSION_2\n\*+1:\s+([\d.-]+)'
        radius_match = re.search(radius_pattern, self.editor.file_content)
        if radius_match and hasattr(self.editor.size_tab, 'radius_var'):
            self.editor.size_tab.radius_var.set(float(radius_match.group(1)))
            self.editor.size_tab.update_value_label(self.editor.size_tab.radius_var, self.editor.size_tab.radius_value)
        
        final_radius_pattern = r'Final_Radius\s+([\d.-]+)'
        final_radius_match = re.search(final_radius_pattern, self.editor.file_content)
        if final_radius_match and hasattr(self.editor.size_tab, 'final_radius_var'):
            self.editor.size_tab.final_radius_var.set(float(final_radius_match.group(1)))
            self.editor.size_tab.update_value_label(self.editor.size_tab.final_radius_var, self.editor.size_tab.final_radius_value)
        
        length_pattern = r'Length\s+NUMBER_VERSION_2\n\*+1:\s+([\d.-]+)'
        length_match = re.search(length_pattern, self.editor.file_content)
        if length_match and hasattr(self.editor.size_tab, 'length_var'):
            self.editor.size_tab.length_var.set(float(length_match.group(1)))
            self.editor.size_tab.update_value_label(self.editor.size_tab.length_var, self.editor.size_tab.length_value)
        
        width_pattern = r'Width\s+([\d.-]+)'
        width_match = re.search(width_pattern, self.editor.file_content)
        if width_match and hasattr(self.editor.size_tab, 'width_var'):
            self.editor.size_tab.width_var.set(float(width_match.group(1)))
            self.editor.size_tab.update_value_label(self.editor.size_tab.width_var, self.editor.size_tab.width_value)
        
        # ============ EMISSION TAB PARAMETERS ============
        emit_pattern = r'Emit_Per_Turn\s+NUMBER_VERSION_2\n\*+1:\s+([\d.-]+)'
        emit_match = re.search(emit_pattern, self.editor.file_content)
        if emit_match and hasattr(self.editor.emission_tab, 'emit_rate_var'):
            self.editor.emission_tab.emit_rate_var.set(float(emit_match.group(1)))
            self.editor.emission_tab.update_value_label(self.editor.emission_tab.emit_rate_var, self.editor.emission_tab.emit_rate_value)
        
        life_pattern = r'Life\s+(-?\d+)'
        life_match = re.search(life_pattern, self.editor.file_content)
        if life_match and hasattr(self.editor.emission_tab, 'life_var'):
            self.editor.emission_tab.life_var.set(float(life_match.group(1)))
            self.editor.emission_tab.update_value_label(self.editor.emission_tab.life_var, self.editor.emission_tab.life_value)
        
        # ============ MOVEMENT TAB PARAMETERS ============
        velocity_x_pattern = r'Initial_Velocity_X\s+NUMBER_VERSION_2\n\*+1:\s+(-?[\d.-]+)'
        velocity_x_match = re.search(velocity_x_pattern, self.editor.file_content)
        if velocity_x_match and hasattr(self.editor.movement_tab, 'velocity_x_var'):
            self.editor.movement_tab.velocity_x_var.set(float(velocity_x_match.group(1)))
            self.editor.movement_tab.update_value_label(self.editor.movement_tab.velocity_x_var, self.editor.movement_tab.velocity_x_value)
        
        velocity_y_pattern = r'Initial_Velocity_Y\s+NUMBER_VERSION_2\n\*+1:\s+(-?[\d.-]+)'
        velocity_y_match = re.search(velocity_y_pattern, self.editor.file_content)
        if velocity_y_match and hasattr(self.editor.movement_tab, 'velocity_y_var'):
            self.editor.movement_tab.velocity_y_var.set(float(velocity_y_match.group(1)))
            self.editor.movement_tab.update_value_label(self.editor.movement_tab.velocity_y_var, self.editor.movement_tab.velocity_y_value)
        
        velocity_z_pattern = r'Initial_Velocity_Z\s+NUMBER_VERSION_2\n\*+1:\s+(-?[\d.-]+)'
        velocity_z_match = re.search(velocity_z_pattern, self.editor.file_content)
        if velocity_z_match and hasattr(self.editor.movement_tab, 'velocity_z_var'):
            self.editor.movement_tab.velocity_z_var.set(float(velocity_z_match.group(1)))
            self.editor.movement_tab.update_value_label(self.editor.movement_tab.velocity_z_var, self.editor.movement_tab.velocity_z_value)
        
        velocity_random_pattern = r'Velocity_Randomness\s+NUMBER_VERSION_2\n\*+1:\s+([\d.-]+)'
        velocity_random_match = re.search(velocity_random_pattern, self.editor.file_content)
        if velocity_random_match and hasattr(self.editor.movement_tab, 'velocity_random_var'):
            self.editor.movement_tab.velocity_random_var.set(float(velocity_random_match.group(1)))
            self.editor.movement_tab.update_value_label(self.editor.movement_tab.velocity_random_var, self.editor.movement_tab.velocity_random_value)
        
        velocity_damp_pattern = r'Velocity_Damp\s+([\d.-]+)'
        velocity_damp_match = re.search(velocity_damp_pattern, self.editor.file_content)
        if velocity_damp_match and hasattr(self.editor.movement_tab, 'velocity_damp_var'):
            self.editor.movement_tab.velocity_damp_var.set(float(velocity_damp_match.group(1)))
            self.editor.movement_tab.update_value_label(self.editor.movement_tab.velocity_damp_var, self.editor.movement_tab.velocity_damp_value)
        
        gravity_pattern = r'GravityScalar\s+([\d.-]+)'
        gravity_match = re.search(gravity_pattern, self.editor.file_content)
        if gravity_match and hasattr(self.editor.movement_tab, 'gravity_var'):
            self.editor.movement_tab.gravity_var.set(float(gravity_match.group(1)))
            self.editor.movement_tab.update_value_label(self.editor.movement_tab.gravity_var, self.editor.movement_tab.gravity_value)
        
        # ============ VISUAL TAB PARAMETERS ============
        blend_mode_pattern = r'Blend_Mode\s+(\d+)'
        blend_mode_match = re.search(blend_mode_pattern, self.editor.file_content)
        if blend_mode_match and hasattr(self.editor.visual_tab, 'blend_mode_var'):
            value = int(blend_mode_match.group(1))
            blend_map = {0: "0 - Normal", 1: "1 - Additive", 2: "2 - Multiply", 3: "3 - Screen"}
            self.editor.visual_tab.blend_mode_var.set(blend_map.get(value, "0 - Normal"))
        
        axis_aligned_pattern = r'Axis_Aligned\s+(\d+)'
        axis_aligned_match = re.search(axis_aligned_pattern, self.editor.file_content)
        if axis_aligned_match and hasattr(self.editor.visual_tab, 'axis_aligned_var'):
            value = int(axis_aligned_match.group(1))
            axis_map = {0: "0 - World", 1: "1 - Camera", 3: "3 - Motion"}
            self.editor.visual_tab.axis_aligned_var.set(axis_map.get(value, "1 - Camera"))
        
        rotation_pattern = r'Rotation\s+NUMBER_VERSION_2\n\*+1:\s+([\d.-]+)'
        rotation_match = re.search(rotation_pattern, self.editor.file_content)
        if rotation_match and hasattr(self.editor.visual_tab, 'rotation_var'):
            self.editor.visual_tab.rotation_var.set(float(rotation_match.group(1)))
            self.editor.visual_tab.update_value_label(self.editor.visual_tab.rotation_var, self.editor.visual_tab.rotation_value)
        
        anim_type_pattern = r'Anim_Type\s+(\d+)'
        anim_type_match = re.search(anim_type_pattern, self.editor.file_content)
        if anim_type_match and hasattr(self.editor.visual_tab, 'anim_type_var'):
            value = int(anim_type_match.group(1))
            anim_map = {0: "0 - Static", 1: "1 - Play Once", 2: "2 - Loop"}
            self.editor.visual_tab.anim_type_var.set(anim_map.get(value, "0 - Static"))
        
        anim_speed_pattern = r'Anim_Speed\s+([\d.-]+)'
        anim_speed_match = re.search(anim_speed_pattern, self.editor.file_content)
        if anim_speed_match and hasattr(self.editor.visual_tab, 'anim_speed_var'):
            self.editor.visual_tab.anim_speed_var.set(float(anim_speed_match.group(1)))
            self.editor.visual_tab.update_value_label(self.editor.visual_tab.anim_speed_var, self.editor.visual_tab.anim_speed_value)
        
        end_frame_pattern = r'End_Frame\s+(\d+)'
        end_frame_match = re.search(end_frame_pattern, self.editor.file_content)
        if end_frame_match and hasattr(self.editor.visual_tab, 'end_frame_var'):
            self.editor.visual_tab.end_frame_var.set(int(end_frame_match.group(1)))
            self.editor.visual_tab.update_value_label(self.editor.visual_tab.end_frame_var, self.editor.visual_tab.end_frame_value, is_int=True)
        
        texture_number_pattern = r'Texture_Number\s+(-?\d+)'
        texture_number_match = re.search(texture_number_pattern, self.editor.file_content)
        if texture_number_match and hasattr(self.editor.visual_tab, 'texture_number_var'):
            self.editor.visual_tab.texture_number_var.set(int(texture_number_match.group(1)))
            self.editor.visual_tab.update_value_label(self.editor.visual_tab.texture_number_var, self.editor.visual_tab.texture_number_value, is_int=True)
        
        cylinder_length_pattern = r'Cylinder_Length\s+NUMBER_VERSION_2\n\*+1:\s+([\d.-]+)'
        cylinder_length_match = re.search(cylinder_length_pattern, self.editor.file_content)
        if cylinder_length_match and hasattr(self.editor.visual_tab, 'cylinder_length_var'):
            self.editor.visual_tab.cylinder_length_var.set(float(cylinder_length_match.group(1)))
            self.editor.visual_tab.update_value_label(self.editor.visual_tab.cylinder_length_var, self.editor.visual_tab.cylinder_length_value)
        
        # ============ TRAIL TAB PARAMETERS ============
        num_points_pattern = r'Num_Points\s+(\d+)'
        num_points_match = re.search(num_points_pattern, self.editor.file_content)
        if num_points_match and hasattr(self.editor.trail_tab, 'num_points_var'):
            self.editor.trail_tab.num_points_var.set(float(num_points_match.group(1)))
            self.editor.trail_tab.update_value_label(self.editor.trail_tab.num_points_var, self.editor.trail_tab.num_points_value, is_int=True)
        
        wiggle_pattern = r'Wiggle_Factor\s+([\d.-]+)'
        wiggle_match = re.search(wiggle_pattern, self.editor.file_content)
        if wiggle_match and hasattr(self.editor.trail_tab, 'wiggle_var'):
            self.editor.trail_tab.wiggle_var.set(float(wiggle_match.group(1)))
            self.editor.trail_tab.update_value_label(self.editor.trail_tab.wiggle_var, self.editor.trail_tab.wiggle_value)
        
        disperse_pattern = r'Disperse_Rate\s+([\d.-]+)'
        disperse_match = re.search(disperse_pattern, self.editor.file_content)
        if disperse_match and hasattr(self.editor.trail_tab, 'disperse_var'):
            self.editor.trail_tab.disperse_var.set(float(disperse_match.group(1)))
            self.editor.trail_tab.update_value_label(self.editor.trail_tab.disperse_var, self.editor.trail_tab.disperse_value)
        
        self.editor.status_var.set("PARAMETERS EXTRACTED SUCCESSFULLY")
    
    def apply_changes(self):
        """Apply changes to the selected descriptor"""
        if not self.editor.file_path or not self.editor.file_content:
            messagebox.showerror("Error", "No file loaded")
            return
        
        if not hasattr(self.editor, 'descriptors') or len(self.editor.descriptors) == 0:
            messagebox.showerror("Error", "No particle descriptors found")
            return
        
        # Get selected descriptor
        selected = self.editor.color_tab.descriptor_var.get()
        idx = int(selected.split(':')[0])
        descriptor = self.editor.descriptors[idx]
        
        # Apply changes from ALL tabs
        modified_section = descriptor['content']
        modified_section = self._apply_color_changes(modified_section)
        modified_section = self._apply_size_changes(modified_section)
        modified_section = self._apply_emission_changes(modified_section)
        modified_section = self._apply_movement_changes(modified_section)
        modified_section = self._apply_visual_changes(modified_section)
        modified_section = self._apply_trail_changes(modified_section)
        
        descriptor['content'] = modified_section
        
        # Rebuild the full file
        rebuilt_content = []
        for d in self.editor.descriptors:
            rebuilt_content.append(d['content'])
            rebuilt_content.append(d['separator'])
        
        modified_content = ''.join(rebuilt_content)
        
        # Save
        try:
            with open(self.editor.file_path, 'w') as file:
                file.write(modified_content)
            
            self.editor.file_content = modified_content
            self.display_file_content()
            self.parse_particle_descriptors()
            
            messagebox.showinfo("SUCCESS", f"Updated descriptor: {descriptor['name']}")
            self.editor.status_var.set(f"UPDATED: {descriptor['name']}")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to save: {str(e)}")
    
    def _apply_color_changes(self, modified_section):
        """Apply color changes to descriptor content"""
        # Get color values from color tab
        start_red = f"{self.editor.color_tab.start_red_var.get():.6f}"
        start_green = f"{self.editor.color_tab.start_green_var.get():.6f}"
        start_blue = f"{self.editor.color_tab.start_blue_var.get():.6f}"
        start_alpha = f"{self.editor.color_tab.start_alpha_var.get():.6f}"
        
        end_red = f"{self.editor.color_tab.end_red_var.get():.6f}"
        end_green = f"{self.editor.color_tab.end_green_var.get():.6f}"
        end_blue = f"{self.editor.color_tab.end_blue_var.get():.6f}"
        end_alpha = f"{self.editor.color_tab.end_alpha_var.get():.6f}"
        
        # Replace values using regex
        modified_section = re.sub(
            r'(Start_Red\s+NUMBER_VERSION_2\n\*+1:\s+)[\d.-]+',
            r'\g<1>' + start_red,
            modified_section
        )
        modified_section = re.sub(
            r'(Start_Green\s+NUMBER_VERSION_2\n\*+1:\s+)[\d.-]+',
            r'\g<1>' + start_green,
            modified_section
        )
        modified_section = re.sub(
            r'(Start_Blue\s+NUMBER_VERSION_2\n\*+1:\s+)[\d.-]+',
            r'\g<1>' + start_blue,
            modified_section
        )
        modified_section = re.sub(
            r'(Start_Alpha\s+NUMBER_VERSION_2\n\*+1:\s+)[\d.-]+',
            r'\g<1>' + start_alpha,
            modified_section
        )
        
        modified_section = re.sub(
            r'(End_Red\s+NUMBER_VERSION_2\n\*+1:\s+)[\d.-]+',
            r'\g<1>' + end_red,
            modified_section
        )
        modified_section = re.sub(
            r'(End_Green\s+NUMBER_VERSION_2\n\*+1:\s+)[\d.-]+',
            r'\g<1>' + end_green,
            modified_section
        )
        modified_section = re.sub(
            r'(End_Blue\s+NUMBER_VERSION_2\n\*+1:\s+)[\d.-]+',
            r'\g<1>' + end_blue,
            modified_section
        )
        modified_section = re.sub(
            r'(End_Alpha\s+NUMBER_VERSION_2\n\*+1:\s+)[\d.-]+',
            r'\g<1>' + end_alpha,
            modified_section
        )
        
        return modified_section
    
    def _apply_size_changes(self, modified_section):
        """Apply size tab changes to descriptor content"""
        # Radius
        radius_value = f"{self.editor.size_tab.radius_var.get():.6f}"
        modified_section = re.sub(
            r'(Radius\s+NUMBER_VERSION_2\n\*+1:\s+)[\d.-]+',
            r'\g<1>' + radius_value,
            modified_section
        )
        
        # Final_Radius
        final_radius_value = f"{self.editor.size_tab.final_radius_var.get():.6f}"
        modified_section = re.sub(
            r'(Final_Radius\s+)[\d.-]+',
            r'\g<1>' + final_radius_value,
            modified_section
        )
        
        # Length
        length_value = f"{self.editor.size_tab.length_var.get():.6f}"
        modified_section = re.sub(
            r'(Length\s+NUMBER_VERSION_2\n\*+1:\s+)[\d.-]+',
            r'\g<1>' + length_value,
            modified_section
        )
        
        # Width (trail width)
        width_value = f"{self.editor.size_tab.width_var.get():.6f}"
        modified_section = re.sub(
            r'(Width\s+)[\d.-]+',
            r'\g<1>' + width_value,
            modified_section
        )
        
        return modified_section
    
    def _apply_emission_changes(self, modified_section):
        """Apply emission tab changes to descriptor content"""
        # Emit_Per_Turn
        emit_rate_value = f"{self.editor.emission_tab.emit_rate_var.get():.6f}"
        modified_section = re.sub(
            r'(Emit_Per_Turn\s+NUMBER_VERSION_2\n\*+1:\s+)[\d.-]+',
            r'\g<1>' + emit_rate_value,
            modified_section
        )
        
        # Life
        life_value = int(self.editor.emission_tab.life_var.get())
        modified_section = re.sub(
            r'(Life\s+)-?\d+',
            r'\g<1>' + str(life_value),
            modified_section
        )
        
        return modified_section
    
    def _apply_movement_changes(self, modified_section):
        """Apply movement tab changes to descriptor content"""
        # Initial_Velocity_X
        velocity_x_value = f"{self.editor.movement_tab.velocity_x_var.get():.6f}"
        modified_section = re.sub(
            r'(Initial_Velocity_X\s+NUMBER_VERSION_2\n\*+1:\s+)-?[\d.-]+',
            r'\g<1>' + velocity_x_value,
            modified_section
        )
        
        # Initial_Velocity_Y
        velocity_y_value = f"{self.editor.movement_tab.velocity_y_var.get():.6f}"
        modified_section = re.sub(
            r'(Initial_Velocity_Y\s+NUMBER_VERSION_2\n\*+1:\s+)-?[\d.-]+',
            r'\g<1>' + velocity_y_value,
            modified_section
        )
        
        # Initial_Velocity_Z
        velocity_z_value = f"{self.editor.movement_tab.velocity_z_var.get():.6f}"
        modified_section = re.sub(
            r'(Initial_Velocity_Z\s+NUMBER_VERSION_2\n\*+1:\s+)-?[\d.-]+',
            r'\g<1>' + velocity_z_value,
            modified_section
        )
        
        # Velocity_Randomness
        velocity_random_value = f"{self.editor.movement_tab.velocity_random_var.get():.6f}"
        modified_section = re.sub(
            r'(Velocity_Randomness\s+NUMBER_VERSION_2\n\*+1:\s+)[\d.-]+',
            r'\g<1>' + velocity_random_value,
            modified_section
        )
        
        # Velocity_Damp
        velocity_damp_value = f"{self.editor.movement_tab.velocity_damp_var.get():.6f}"
        modified_section = re.sub(
            r'(Velocity_Damp\s+)[\d.-]+',
            r'\g<1>' + velocity_damp_value,
            modified_section
        )
        
        # GravityScalar
        gravity_value = f"{self.editor.movement_tab.gravity_var.get():.6f}"
        modified_section = re.sub(
            r'(GravityScalar\s+)[\d.-]+',
            r'\g<1>' + gravity_value,
            modified_section
        )
        
        return modified_section
    
    def _apply_visual_changes(self, modified_section):
        """Apply visual tab changes to descriptor content"""
        # Blend_Mode
        blend_value = int(self.editor.visual_tab.blend_mode_var.get().split(' ')[0])
        modified_section = re.sub(
            r'(Blend_Mode\s+)\d+',
            r'\g<1>' + str(blend_value),
            modified_section
        )
        
        # Axis_Aligned
        axis_value = int(self.editor.visual_tab.axis_aligned_var.get().split(' ')[0])
        modified_section = re.sub(
            r'(Axis_Aligned\s+)\d+',
            r'\g<1>' + str(axis_value),
            modified_section
        )
        
        # Rotation
        rotation_value = f"{self.editor.visual_tab.rotation_var.get():.6f}"
        modified_section = re.sub(
            r'(Rotation\s+NUMBER_VERSION_2\n\*+1:\s+)[\d.-]+',
            r'\g<1>' + rotation_value,
            modified_section
        )
        
        # Anim_Type
        anim_type_value = int(self.editor.visual_tab.anim_type_var.get().split(' ')[0])
        modified_section = re.sub(
            r'(Anim_Type\s+)\d+',
            r'\g<1>' + str(anim_type_value),
            modified_section
        )
        
        # Anim_Speed
        anim_speed_value = f"{self.editor.visual_tab.anim_speed_var.get():.6f}"
        modified_section = re.sub(
            r'(Anim_Speed\s+)[\d.-]+',
            r'\g<1>' + anim_speed_value,
            modified_section
        )
        
        # End_Frame
        end_frame_value = int(self.editor.visual_tab.end_frame_var.get())
        modified_section = re.sub(
            r'(End_Frame\s+)\d+',
            r'\g<1>' + str(end_frame_value),
            modified_section
        )
        
        # Texture_Number
        texture_number_value = int(self.editor.visual_tab.texture_number_var.get())
        modified_section = re.sub(
            r'(Texture_Number\s+)-?\d+',
            r'\g<1>' + str(texture_number_value),
            modified_section
        )
        
        # Cylinder_Length
        cylinder_length_value = f"{self.editor.visual_tab.cylinder_length_var.get():.6f}"
        modified_section = re.sub(
            r'(Cylinder_Length\s+NUMBER_VERSION_2\n\*+1:\s+)[\d.-]+',
            r'\g<1>' + cylinder_length_value,
            modified_section
        )
        
        return modified_section
    
    def _apply_trail_changes(self, modified_section):
        """Apply trail tab changes to descriptor content"""
        # Num_Points
        num_points_value = int(self.editor.trail_tab.num_points_var.get())
        modified_section = re.sub(
            r'(Num_Points\s+)\d+',
            r'\g<1>' + str(num_points_value),
            modified_section
        )
        
        # Wiggle_Factor
        wiggle_value = f"{self.editor.trail_tab.wiggle_var.get():.6f}"
        modified_section = re.sub(
            r'(Wiggle_Factor\s+)[\d.-]+',
            r'\g<1>' + wiggle_value,
            modified_section
        )
        
        # Disperse_Rate
        disperse_value = f"{self.editor.trail_tab.disperse_var.get():.6f}"
        modified_section = re.sub(
            r'(Disperse_Rate\s+)[\d.-]+',
            r'\g<1>' + disperse_value,
            modified_section
        )
        
        return modified_section