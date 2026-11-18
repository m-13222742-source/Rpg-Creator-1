import customtkinter as ctk
from tkinter import messagebox
import tkinter as tk
import os
import platform
import subprocess
from datetime import datetime

try:
    from PIL import Image, ImageTk
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

# Configure the modern look for the Engine
ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

class RpgCreatorEngine:
    def __init__(self, root):
        self.root = root
        self.root.title("RPG Creator - Engine Workspace")
        self.root.geometry("1400x900")
        
        # Paths
        self.base_dir = os.path.dirname(os.path.abspath(__file__))
        self.saved_games_dir = os.path.join(self.base_dir, "Saved Games")
        self.icon_path = os.path.join(self.base_dir, "RpgCreator.ico") 
        
        # Map State
        self.tile_size = 32
        self.grid_width = 25
        self.grid_height = 18
        self.current_tool = "Pencil"
        self.current_layer = "Background"
        self.selected_color = "#4CAF50" # Default grass green
        
        self.setup_icon()
        self.build_workspace()
        self.log_message("Engine initialized successfully.")

    def setup_icon(self):
        """Load the .ico file safely."""
        if os.path.exists(self.icon_path) and HAS_PIL:
            try:
                ico_img = Image.open(self.icon_path)
                self.icon_photo = ImageTk.PhotoImage(ico_img)
                self.root.iconphoto(True, self.icon_photo)
            except Exception:
                pass

    def build_workspace(self):
        """Constructs the comprehensive 4-panel engine UI."""
        # --- Top Toolbar ---
        self.toolbar = ctk.CTkFrame(self.root, height=55, corner_radius=0, fg_color="#1e1e1e")
        self.toolbar.pack(side="top", fill="x")
        
        self.create_toolbar_btn("New Project", self.dummy_command)
        self.create_toolbar_btn("Save Map", self.dummy_command)
        self.create_toolbar_btn("Load Map", self.dummy_command)
        
        # Spacer
        ctk.CTkLabel(self.toolbar, text=" | ").pack(side="left", padx=10)
        
        self.create_toolbar_btn("Compile Engine", self.compile_game)
        self.create_toolbar_btn("▶ Test Play", self.dummy_command, fg_color="#2b8a3e", hover_color="#237032")

        # --- Main Content Area ---
        self.content_frame = ctk.CTkFrame(self.root, corner_radius=0, fg_color="transparent")
        self.content_frame.pack(side="top", fill="both", expand=True)

        # --- Left Panel: Layers & Tileset ---
        self.left_panel = ctk.CTkFrame(self.content_frame, width=220, corner_radius=0)
        self.left_panel.pack(side="left", fill="y", padx=(0, 5))
        self.left_panel.pack_propagate(False)

        ctk.CTkLabel(self.left_panel, text="Layers", font=ctk.CTkFont(weight="bold")).pack(pady=(10, 5))
        self.layer_combo = ctk.CTkComboBox(self.left_panel, values=["Background", "Details", "Collision", "Events"])
        self.layer_combo.pack(padx=10, pady=5, fill="x")

        ctk.CTkLabel(self.left_panel, text="Drawing Tools", font=ctk.CTkFont(weight="bold")).pack(pady=(20, 5))
        self.create_tool_btn("Pencil (Draw)")
        self.create_tool_btn("Eraser")
        self.create_tool_btn("Fill Bucket")

        ctk.CTkLabel(self.left_panel, text="Tileset Assets", font=ctk.CTkFont(weight="bold")).pack(pady=(20, 5))
        self.create_tile_btn("Grass", "#4CAF50")
        self.create_tile_btn("Water", "#2196F3")
        self.create_tile_btn("Stone Wall", "#9E9E9E")
        self.create_tile_btn("Dirt Path", "#795548")

        # --- Right Panel: Property Inspector ---
        self.right_panel = ctk.CTkFrame(self.content_frame, width=250, corner_radius=0)
        self.right_panel.pack(side="right", fill="y", padx=(5, 0))
        self.right_panel.pack_propagate(False)

        ctk.CTkLabel(self.right_panel, text="Inspector", font=ctk.CTkFont(size=16, weight="bold")).pack(pady=(10, 15))
        
        ctk.CTkLabel(self.right_panel, text="Map Name:").pack(anchor="w", padx=10)
        self.map_name_entry = ctk.CTkEntry(self.right_panel, placeholder_text="Town_01")
        self.map_name_entry.pack(fill="x", padx=10, pady=(0, 15))

        ctk.CTkLabel(self.right_panel, text="Map Width (Tiles):").pack(anchor="w", padx=10)
        self.width_entry = ctk.CTkEntry(self.right_panel, placeholder_text=str(self.grid_width))
        self.width_entry.pack(fill="x", padx=10, pady=(0, 15))

        ctk.CTkLabel(self.right_panel, text="Map Height (Tiles):").pack(anchor="w", padx=10)
        self.height_entry = ctk.CTkEntry(self.right_panel, placeholder_text=str(self.grid_height))
        self.height_entry.pack(fill="x", padx=10, pady=(0, 25))
        
        ctk.CTkButton(self.right_panel, text="Apply Resize", command=self.dummy_command).pack(padx=10, fill="x")

        # --- Center Panel: Map Editor Canvas ---
        self.center_panel = ctk.CTkFrame(self.content_frame, corner_radius=0, fg_color="#2b2b2b")
        self.center_panel.pack(side="left", fill="both", expand=True)
        
        # Scrollable container for large maps
        canvas_w = self.tile_size * self.grid_width
        canvas_h = self.tile_size * self.grid_height
        self.canvas = tk.Canvas(self.center_panel, width=canvas_w, height=canvas_h, bg="#1e1e1e", highlightthickness=1, highlightbackground="#444")
        self.canvas.place(relx=0.5, rely=0.5, anchor="center") # Center it in the workspace
        
        self.draw_grid()
        self.canvas.bind("<B1-Motion>", self.paint_tile) # Click and drag support
        self.canvas.bind("<Button-1>", self.paint_tile)

        # --- Bottom Panel: Console Log ---
        self.console_panel = ctk.CTkFrame(self.root, height=120, corner_radius=0)
        self.console_panel.pack(side="bottom", fill="x")
        self.console_panel.pack_propagate(False)
        
        ctk.CTkLabel(self.console_panel, text="Console Output", font=ctk.CTkFont(size=11, weight="bold")).pack(anchor="w", padx=10, pady=2)
        self.console_text = ctk.CTkTextbox(self.console_panel, font=ctk.CTkFont(family="Consolas", size=11), text_color="#a8a8a8", fg_color="#121212")
        self.console_text.pack(fill="both", expand=True, padx=5, pady=(0, 5))
        self.console_text.configure(state="disabled")

    # --- UI Helper Methods ---
    def create_toolbar_btn(self, text, command, fg_color=None, hover_color=None):
        btn = ctk.CTkButton(self.toolbar, text=text, width=100, height=30, command=command)
        if fg_color: btn.configure(fg_color=fg_color)
        if hover_color: btn.configure(hover_color=hover_color)
        btn.pack(side="left", padx=5, pady=10)

    def create_tool_btn(self, text):
        def set_tool():
            self.current_tool = text.split()[0]
            self.log_message(f"Selected tool: {self.current_tool}")
        ctk.CTkButton(self.left_panel, text=text, fg_color="#333333", hover_color="#444444", command=set_tool).pack(pady=3, padx=10, fill="x")

    def create_tile_btn(self, name, color_hex):
        def select_tile():
            self.selected_color = color_hex
            self.current_tool = "Pencil"
            self.log_message(f"Selected tile asset: {name}")
        
        btn_frame = ctk.CTkFrame(self.left_panel, fg_color="transparent")
        btn_frame.pack(fill="x", padx=10, pady=3)
        
        color_swatch = ctk.CTkFrame(btn_frame, width=20, height=20, fg_color=color_hex, corner_radius=2)
        color_swatch.pack(side="left", padx=(0, 10))
        
        ctk.CTkButton(btn_frame, text=name, anchor="w", fg_color="#333333", hover_color="#444444", command=select_tile).pack(side="left", fill="x", expand=True)

    def log_message(self, msg):
        """Prints messages to the bottom console panel."""
        self.console_text.configure(state="normal")
        time_str = datetime.now().strftime("%H:%M:%S")
        self.console_text.insert("end", f"[{time_str}] {msg}\n")
        self.console_text.see("end")
        self.console_text.configure(state="disabled")

    # --- Canvas Drawing Logic ---
    def draw_grid(self):
        """Draws the wireframe grid."""
        for i in range(self.grid_width):
            for j in range(self.grid_height):
                x1, y1 = i * self.tile_size, j * self.tile_size
                self.canvas.create_rectangle(x1, y1, x1+self.tile_size, y1+self.tile_size, outline="#333333", fill="#2b2b2b", tags=f"{i}_{j}")

    def paint_tile(self, event):
        """Paints or erases on the canvas based on the selected tool."""
        grid_x = event.x // self.tile_size
        grid_y = event.y // self.tile_size
        
        if 0 <= grid_x < self.grid_width and 0 <= grid_y < self.grid_height:
            x1, y1 = grid_x * self.tile_size, grid_y * self.tile_size
            
            if self.current_tool == "Eraser":
                self.canvas.create_rectangle(x1, y1, x1+self.tile_size, y1+self.tile_size, outline="#333333", fill="#2b2b2b")
            elif self.current_tool == "Pencil":
                self.canvas.create_rectangle(x1, y1, x1+self.tile_size, y1+self.tile_size, outline="#333333", fill=self.selected_color)

    # --- System Commands ---
    def compile_game(self):
        self.log_message("Initializing OS compilation sequence...")
        current_os = platform.system()
        compiler_folder = os.path.join(self.base_dir, "Game Compiler")
        
        script_map = {"Windows": "Compiler_Windows.py", "Darwin": "Compiler_MacOS.py", "Linux": "Compiler_Linux.py"}
        compiler_script = script_map.get(current_os)
        
        if not compiler_script:
            self.log_message(f"ERROR: Unsupported OS ({current_os})")
            return
            
        script_path = os.path.join(compiler_folder, compiler_script)
        if not os.path.exists(script_path):
            self.log_message(f"ERROR: Missing {compiler_script} in {compiler_folder}")
            return
            
        try:
            self.log_message(f"Running {compiler_script}...")
            subprocess.run(["python", script_path], check=True)
            self.log_message(f"SUCCESS: Game compiled to {self.saved_games_dir}")
        except subprocess.CalledProcessError as e:
            self.log_message(f"COMPILATION FAILED: {e}")

    def dummy_command(self):
        self.log_message("Action triggered: Feature is currently under development.")

if __name__ == "__main__":
    root = ctk.CTk()
    app = RpgCreatorEngine(root)
    root.mainloop()