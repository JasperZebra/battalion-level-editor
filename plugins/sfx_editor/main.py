import tkinter as tk
import sys
import traceback
from .particle_editor import ParticleEffectEditor


def main(args):
    root = tk.Tk()
    try:
        print("[DEBUG] Initializing ParticleEffectEditor...")
        app = ParticleEffectEditor(root)
        print("[DEBUG] ParticleEffectEditor initialized successfully")

        # Check if a file path was provided as an argument
        if len(args) > 1:
            # Load the specified file
            file_path = args[1]
            print(f"[DEBUG] Loading file: {file_path}")
            
            app.file_path = file_path
            app.file_label.config(text=file_path.split('/')[-1].split('\\')[-1])

            # Read the file content
            try:
                print("[DEBUG] Reading file content...")
                with open(file_path, 'r') as file:
                    app.file_content = file.read()
                print(f"[DEBUG] File read successfully ({len(app.file_content)} bytes)")

                # Display the content and extract parameters
                print("[DEBUG] Calling display_file_content()...")
                app.file_manager.display_file_content()
                
                print("[DEBUG] Calling parse_particle_descriptors()...")
                app.file_manager.parse_particle_descriptors()
                
                print("[DEBUG] Calling populate_descriptor_selector()...")
                app.file_manager.populate_descriptor_selector()
                
                print("[DEBUG] Calling extract_parameters()...")
                app.file_manager.extract_parameters()

                # Update status
                app.status_var.set(f"LOADED: {file_path}")
                print("[DEBUG] File loading completed successfully")
            except Exception as e:
                error_msg = f"ERROR: {str(e)}"
                print(f"[DEBUG] {error_msg}")
                print("[DEBUG] Full traceback:")
                traceback.print_exc()
                app.status_var.set(error_msg)
        else:
            print("[DEBUG] No file argument provided, starting with empty editor")

        print("[DEBUG] Starting mainloop...")
        root.mainloop()
    except Exception as e:
        print(f"[CRITICAL] Application initialization failed: {str(e)}")
        print("[CRITICAL] Full traceback:")
        traceback.print_exc()
        root.destroy()


if __name__ == "__main__":
    main(sys.argv)