import customtkinter as ctk
import tkinter as tk
from tkinter import messagebox, filedialog
import os
import sys
import json
import copy
import ctypes
import subprocess
import traceback
import importlib.util

ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

TILE_SIZE = 34
DEFAULT_MAP_W = 20
DEFAULT_MAP_H = 14

BASE_TILES = {
    "grass": {"label": "Grass", "color": "#2E7D32", "walkable": True},
    "dirt": {"label": "Dirt Path", "color": "#8D6E63", "walkable": True},
    "floor": {"label": "Wood Floor", "color": "#BCAAA4", "walkable": True},
    "water": {"label": "Deep Water", "color": "#1565C0", "walkable": False},
    "wall": {"label": "Stone Wall", "color": "#424242", "walkable": False},
}

SAMPLE_PLUGIN_CODE = '''"""
Sample RPG Creator Plugin (Section 4 EULA Compliant)
Drop any .py plugin file into the 'plugins' folder and reload in Engine.exe.
"""

PLUGIN_NAME = "Lava & Fireball Starter Mod"
PLUGIN_AUTHOR = "RPG Creator SDK"
PLUGIN_VERSION = "1.0.0"
PLUGIN_DESC = "Adds a custom Lava hazard tile and a modded Phoenix Feather item."


def register(api):
    # 1. Register a custom tile into the Map Editor palette
    api.register_tile(
        tile_id="mod_lava",
        label="Lava (Mod)",
        color="#E65100",
        walkable=False,
    )

    # 2. Inject a custom item into the Game Database if not already present
    api.add_database_item(
        name="Phoenix Feather (Mod)",
        item_type="Key / Relic",
        power=100,
        price=250,
    )

    # 3. Hook into Playtest startup
    def on_start(playtest_state):
        api.log(f"Playtest started with hero: {playtest_state['hero']['name']}")

    api.on_playtest_start(on_start)
'''


def ensure_single_instance():
    """Prevents multiple copies of Engine.exe from running simultaneously on Windows."""
    if os.name == "nt":
        mutex_name = "Global\\RpgCreatorEngineSingleInstanceMutex"
        kernel32 = ctypes.windll.kernel32
        mutex = kernel32.CreateMutexW(None, False, mutex_name)
        if kernel32.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
            messagebox.showwarning(
                "Already Running",
                "RPG Creator Engine is already open and running.",
            )
            sys.exit(0)
        return mutex
    return None


class PluginAPI:
    """Safe API exposed to external user-created plugins in the plugins/ directory."""

    def __init__(self, engine_app, plugin_filename):
        self._app = engine_app
        self._plugin_filename = plugin_filename

    def log(self, message):
        self._app.log_plugin(f"[{self._plugin_filename}] {message}")

    def register_tile(self, tile_id, label, color, walkable=True):
        if not tile_id or not isinstance(tile_id, str):
            return
        self._app.tile_registry[tile_id] = {
            "label": str(label),
            "color": str(color),
            "walkable": bool(walkable),
        }
        self.log(f"Registered custom tile '{label}' ({tile_id})")

    def add_database_item(self, name, item_type="Consumable", power=10, price=10):
        items = self._app.project_data["database"]["items"]
        if not any(i["name"] == name for i in items):
            items.append(
                {
                    "name": str(name),
                    "type": str(item_type),
                    "power": int(power),
                    "price": int(price),
                }
            )
            self.log(f"Added item '{name}' to database")

    def on_playtest_start(self, callback):
        if callable(callback):
            self._app.playtest_hooks.append((self._plugin_filename, callback))


class EventEditorDialog(ctk.CTkToplevel):
    """Modal popup for creating or editing an NPC / Event trigger on a map tile."""

    def __init__(self, parent, x, y, existing_event=None):
        super().__init__(parent)
        self.title(f"Event Trigger at ({x}, {y})")
        self.geometry("420x290")
        self.resizable(False, False)
        self.result = None

        self.transient(parent)
        self.grab_set()

        ctk.CTkLabel(
            self,
            text=f"Configure NPC / Event at Tile ({x}, {y})",
            font=ctk.CTkFont(size=15, weight="bold"),
        ).pack(anchor="w", padx=20, pady=(15, 10))

        ctk.CTkLabel(self, text="NPC / Event Name:").pack(anchor="w", padx=20)
        self.name_entry = ctk.CTkEntry(self, placeholder_text="Village Guard")
        self.name_entry.pack(fill="x", padx=20, pady=(2, 10))

        ctk.CTkLabel(self, text="Dialogue Message (shown when player interacts):").pack(
            anchor="w", padx=20
        )
        self.dialogue_box = ctk.CTkTextbox(self, height=95, wrap="word")
        self.dialogue_box.pack(fill="x", padx=20, pady=(2, 12))

        if existing_event:
            self.name_entry.insert(0, existing_event.get("name", ""))
            self.dialogue_box.insert("0.0", existing_event.get("dialogue", ""))
        else:
            self.name_entry.insert(0, "Townsperson")
            self.dialogue_box.insert(
                "0.0", "Greetings, traveler! Welcome to our RPG world."
            )

        btn_row = ctk.CTkFrame(self, fg_color="transparent")
        btn_row.pack(fill="x", padx=20)

        ctk.CTkButton(
            btn_row,
            text="Cancel",
            width=90,
            fg_color="transparent",
            border_width=1,
            command=self.destroy,
        ).pack(side="right", padx=(8, 0))

        ctk.CTkButton(
            btn_row,
            text="Save Event",
            width=110,
            command=self.save,
        ).pack(side="right")

        self.focus_force()

    def save(self):
        name = self.name_entry.get().strip() or "Event"
        dialogue = self.dialogue_box.get("0.0", "end").strip() or "..."
        self.result = {"name": name, "dialogue": dialogue}
        self.destroy()


class PlaytestWindow(ctk.CTkToplevel):
    """Live playable RPG preview window using the active map, database, and plugins."""

    def __init__(self, parent, project_data, tile_registry, playtest_hooks, log_fn):
        super().__init__(parent)
        self.project = copy.deepcopy(project_data)
        self.tile_registry = tile_registry
        self.log_fn = log_fn

        self.title(f"Playtest — {self.project['project_name']}")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        map_data = self.project["map"]
        self.map_w = map_data["width"]
        self.map_h = map_data["height"]
        self.tiles = map_data["tiles"]
        self.events = map_data["events"]
        self.px, self.py = map_data["player_start"]

        actors = self.project["database"]["actors"]
        self.hero = (
            copy.deepcopy(actors[0])
            if actors
            else {
                "name": "Hero",
                "role": "Adventurer",
                "hp": 100,
                "mp": 20,
                "atk": 12,
                "def": 10,
            }
        )
        self.max_hp = self.hero["hp"]
        self.inventory = copy.deepcopy(self.project["database"]["items"])

        # Execute plugin playtest hooks safely
        state_snapshot = {
            "hero": self.hero,
            "player_pos": (self.px, self.py),
            "inventory": self.inventory,
        }
        for plugin_name, hook in playtest_hooks:
            try:
                hook(state_snapshot)
            except Exception as e:
                self.log_fn(f"[PLUGIN ERROR] {plugin_name} playtest hook failed: {e}")

        self.build_ui()
        self.render_map()

        self.bind("<Up>", lambda _: self.move_player(0, -1))
        self.bind("<Down>", lambda _: self.move_player(0, 1))
        self.bind("<Left>", lambda _: self.move_player(-1, 0))
        self.bind("<Right>", lambda _: self.move_player(1, 0))
        self.bind("w", lambda _: self.move_player(0, -1))
        self.bind("s", lambda _: self.move_player(0, 1))
        self.bind("a", lambda _: self.move_player(-1, 0))
        self.bind("d", lambda _: self.move_player(1, 0))
        self.bind("<space>", lambda _: self.interact_facing())
        self.bind("<Return>", lambda _: self.interact_facing())

        self.focus_force()

    def build_ui(self):
        # Top HUD
        hud = ctk.CTkFrame(self, fg_color="#1a1a1a", corner_radius=0)
        hud.pack(fill="x")

        self.hud_label = ctk.CTkLabel(
            hud,
            text="",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color="#00FF00",
        )
        self.hud_label.pack(side="left", padx=15, pady=10)

        ctk.CTkButton(
            hud,
            text="Use Potion (+HP)",
            width=130,
            height=28,
            command=self.use_healing_item,
        ).pack(side="right", padx=15, pady=8)

        # Map Viewport
        canvas_w = self.map_w * TILE_SIZE
        canvas_h = self.map_h * TILE_SIZE
        self.canvas = tk.Canvas(
            self,
            width=canvas_w,
            height=canvas_h,
            bg="#111111",
            highlightthickness=0,
        )
        self.canvas.pack(padx=15, pady=10)

        # Bottom RPG Dialogue Box
        dialogue_frame = ctk.CTkFrame(self, fg_color="#1a1a1a", height=85)
        dialogue_frame.pack(fill="x", padx=15, pady=(0, 15))
        dialogue_frame.pack_propagate(False)

        self.speaker_label = ctk.CTkLabel(
            dialogue_frame,
            text="Controls",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color="#38BDF8",
        )
        self.speaker_label.pack(anchor="w", padx=12, pady=(8, 0))

        self.dialogue_label = ctk.CTkLabel(
            dialogue_frame,
            text="Use WASD or Arrow Keys to move. Step onto or press Space next to an NPC (★) to talk.",
            justify="left",
            wraplength=max(400, canvas_w - 30),
            font=ctk.CTkFont(size=12),
        )
        self.dialogue_label.pack(anchor="w", padx=12, pady=(2, 8))

        self.update_hud()

    def update_hud(self):
        self.hud_label.configure(
            text=(
                f"{self.hero['name']} ({self.hero['role']})   |   "
                f"HP: {self.hero['hp']}/{self.max_hp}   |   "
                f"MP: {self.hero['mp']}   |   "
                f"ATK: {self.hero['atk']}  DEF: {self.hero['def']}   |   "
                f"Bag: {len(self.inventory)} item(s)"
            )
        )

    def use_healing_item(self):
        for idx, item in enumerate(self.inventory):
            if "consumable" in item.get("type", "").lower() or "potion" in item["name"].lower():
                heal = item.get("power", 25)
                self.hero["hp"] = min(self.max_hp, self.hero["hp"] + heal)
                used = self.inventory.pop(idx)
                self.update_hud()
                self.speaker_label.configure(text="Item Used")
                self.dialogue_label.configure(
                    text=f"{self.hero['name']} used {used['name']} and recovered {heal} HP!"
                )
                return
        self.speaker_label.configure(text="Inventory")
        self.dialogue_label.configure(text="No consumable healing items in your bag.")

    def render_map(self):
        self.canvas.delete("all")
        for y in range(self.map_h):
            for x in range(self.map_w):
                tile_id = self.tiles[y][x]
                tile_info = self.tile_registry.get(
                    tile_id, {"color": "#9C27B0", "walkable": True}
                )
                x1, y1 = x * TILE_SIZE, y * TILE_SIZE
                x2, y2 = x1 + TILE_SIZE, y1 + TILE_SIZE
                self.canvas.create_rectangle(
                    x1, y1, x2, y2, fill=tile_info["color"], outline="#222222"
                )

        # Draw Events / NPCs
        for ev in self.events:
            ex, ey = ev["x"], ev["y"]
            cx = ex * TILE_SIZE + TILE_SIZE // 2
            cy = ey * TILE_SIZE + TILE_SIZE // 2
            self.canvas.create_oval(
                ex * TILE_SIZE + 5,
                ey * TILE_SIZE + 5,
                (ex + 1) * TILE_SIZE - 5,
                (ey + 1) * TILE_SIZE - 5,
                fill="#FACC15",
                outline="#000000",
                width=2,
            )
            self.canvas.create_text(
                cx, cy, text="★", fill="#000000", font=("Consolas", 12, "bold")
            )

        # Draw Player
        px1 = self.px * TILE_SIZE + 4
        py1 = self.py * TILE_SIZE + 4
        px2 = (self.px + 1) * TILE_SIZE - 4
        py2 = (self.py + 1) * TILE_SIZE - 4
        self.canvas.create_oval(px1, py1, px2, py2, fill="#EF4444", outline="#FFFFFF", width=2)
        self.canvas.create_text(
            self.px * TILE_SIZE + TILE_SIZE // 2,
            self.py * TILE_SIZE + TILE_SIZE // 2,
            text="P",
            fill="#FFFFFF",
            font=("Consolas", 11, "bold"),
        )

    def move_player(self, dx, dy):
        nx, ny = self.px + dx, self.py + dy
        if not (0 <= nx < self.map_w and 0 <= ny < self.map_h):
            return

        # Check if an NPC is on the target tile -> trigger dialogue instead of walking over
        for ev in self.events:
            if ev["x"] == nx and ev["y"] == ny:
                self.speaker_label.configure(text=ev["name"])
                self.dialogue_label.configure(text=ev["dialogue"])
                return

        tile_id = self.tiles[ny][nx]
        tile_info = self.tile_registry.get(tile_id, {"walkable": True})
        if not tile_info.get("walkable", True):
            return

        self.px, self.py = nx, ny
        self.render_map()

    def interact_facing(self):
        for dx, dy in [(0, -1), (0, 1), (-1, 0), (1, 0), (0, 0)]:
            tx, ty = self.px + dx, self.py + dy
            for ev in self.events:
                if ev["x"] == tx and ev["y"] == ty:
                    self.speaker_label.configure(text=ev["name"])
                    self.dialogue_label.configure(text=ev["dialogue"])
                    return


class RpgCreatorEngine(ctk.CTk):
    def __init__(self):
        super().__init__()

        if getattr(sys, "frozen", False):
            self.base_dir = os.path.dirname(sys.executable)
        else:
            self.base_dir = os.path.dirname(os.path.abspath(__file__))

        self.projects_dir = os.path.join(self.base_dir, "projects")
        self.plugins_dir = os.path.join(self.base_dir, "plugins")
        self.plugin_config_path = os.path.join(self.plugins_dir, "plugins_config.json")

        os.makedirs(self.projects_dir, exist_ok=True)
        os.makedirs(self.plugins_dir, exist_ok=True)

        self.version = self.load_version()
        self.title(f"RPG Creator Engine ({self.version})")
        self.geometry("1160x740")
        self.minsize(1060, 680)

        # Engine State
        self.tile_registry = copy.deepcopy(BASE_TILES)
        self.playtest_hooks = []
        self.plugin_logs = []
        self.current_project_path = None
        self.project_data = self.create_default_project()

        # Editor Tool State
        self.editor_tool_var = ctk.StringVar(value="paint")
        self.selected_tile_var = ctk.StringVar(value="grass")
        self.selected_actor_idx = None
        self.selected_item_idx = None
        self.selected_skill_idx = None

        self.ensure_sample_plugin()
        self.build_ui()
        self.reload_plugins(silent=True)
        self.refresh_all_views()

    def load_version(self):
        version_file = os.path.join(self.base_dir, "version.txt")
        if os.path.exists(version_file):
            try:
                with open(version_file, "r") as f:
                    return f.read().strip()
            except Exception:
                pass
        return "Test Build"

    def create_default_project(self):
        tiles = [
            ["grass" for _ in range(DEFAULT_MAP_W)] for _ in range(DEFAULT_MAP_H)
        ]
        # Border stone walls
        for x in range(DEFAULT_MAP_W):
            tiles[0][x] = "wall"
            tiles[DEFAULT_MAP_H - 1][x] = "wall"
        for y in range(DEFAULT_MAP_H):
            tiles[y][0] = "wall"
            tiles[y][DEFAULT_MAP_W - 1] = "wall"

        # Sample dirt road & pond
        for x in range(2, 12):
            tiles[6][x] = "dirt"
        for y in range(3, 6):
            for x in range(14, 18):
                tiles[y][x] = "water"

        return {
            "project_name": "Starter Quest",
            "map": {
                "width": DEFAULT_MAP_W,
                "height": DEFAULT_MAP_H,
                "player_start": [3, 6],
                "tiles": tiles,
                "events": [
                    {
                        "x": 8,
                        "y": 5,
                        "name": "Village Elder",
                        "dialogue": "Welcome to RPG Creator! Edit this map, add items in the Database, or drop custom .py mods into the plugins folder.",
                    }
                ],
            },
            "database": {
                "actors": [
                    {
                        "name": "Aria",
                        "role": "Vanguard Knight",
                        "hp": 120,
                        "mp": 35,
                        "atk": 18,
                        "def": 14,
                    }
                ],
                "items": [
                    {
                        "name": "Health Potion",
                        "type": "Consumable",
                        "power": 50,
                        "price": 25,
                    },
                    {
                        "name": "Iron Broadsword",
                        "type": "Weapon",
                        "power": 15,
                        "price": 120,
                    },
                ],
                "skills": [
                    {"name": "Flame Slash", "mp_cost": 10, "power": 35},
                    {"name": "Aegis Guard", "mp_cost": 8, "power": 20},
                ],
            },
        }

    # ================= TOP TOOLBAR & MAIN LAYOUT =================

    def build_ui(self):
        top_bar = ctk.CTkFrame(self, height=48, corner_radius=0, fg_color="#1a1a1a")
        top_bar.pack(fill="x")

        self.project_title_label = ctk.CTkLabel(
            top_bar,
            text="",
            font=ctk.CTkFont(size=15, weight="bold"),
        )
        self.project_title_label.pack(side="left", padx=15, pady=10)

        # Right-side action buttons
        ctk.CTkButton(
            top_bar,
            text="Info / Bugs & Suggestions",
            width=185,
            fg_color="#333333",
            hover_color="#444444",
            command=self.open_info_center,
        ).pack(side="right", padx=(6, 15), pady=9)

        ctk.CTkButton(
            top_bar,
            text="▶ Playtest RPG",
            width=130,
            fg_color="#16A34A",
            hover_color="#15803D",
            font=ctk.CTkFont(weight="bold"),
            command=self.launch_playtest,
        ).pack(side="right", padx=6, pady=9)

        ctk.CTkButton(
            top_bar,
            text="Save Project",
            width=105,
            command=self.save_project,
        ).pack(side="right", padx=6, pady=9)

        ctk.CTkButton(
            top_bar,
            text="Load Project",
            width=105,
            fg_color="#2B2B2B",
            hover_color="#3A3A3A",
            command=self.load_project,
        ).pack(side="right", padx=6, pady=9)

        ctk.CTkButton(
            top_bar,
            text="New Project",
            width=100,
            fg_color="#2B2B2B",
            hover_color="#3A3A3A",
            command=self.new_project,
        ).pack(side="right", padx=6, pady=9)

        # Main Editor Tabs
        self.main_tabs = ctk.CTkTabview(self)
        self.main_tabs.pack(fill="both", expand=True, padx=12, pady=(4, 12))

        self.tab_map = self.main_tabs.add("Map & Event Editor")
        self.tab_db = self.main_tabs.add("Game Database")
        self.tab_plugins = self.main_tabs.add("Plugin Manager (Mods)")

        self.build_map_editor_tab()
        self.build_database_tab()
        self.build_plugins_tab()

    # ================= TAB 1: MAP & EVENT EDITOR =================

    def build_map_editor_tab(self):
        container = ctk.CTkFrame(self.tab_map, fg_color="transparent")
        container.pack(fill="both", expand=True)

        # Left Palette Sidebar
        sidebar = ctk.CTkFrame(container, width=270, fg_color="#181818")
        sidebar.pack(side="left", fill="y", padx=(0, 12), pady=4)
        sidebar.pack_propagate(False)

        ctk.CTkLabel(
            sidebar, text="Editor Tool Mode", font=ctk.CTkFont(size=14, weight="bold")
        ).pack(anchor="w", padx=14, pady=(12, 6))

        tools = [
            ("Paint Terrain Tile", "paint"),
            ("Set Player Start (P)", "player_start"),
            ("Place / Edit Event (★)", "event"),
            ("Delete Event", "delete_event"),
        ]
        for label, val in tools:
            ctk.CTkRadioButton(
                sidebar,
                text=label,
                variable=self.editor_tool_var,
                value=val,
            ).pack(anchor="w", padx=18, pady=4)

        ctk.CTkLabel(
            sidebar, text="Terrain Tile Palette", font=ctk.CTkFont(size=14, weight="bold")
        ).pack(anchor="w", padx=14, pady=(16, 6))

        self.palette_scroll = ctk.CTkScrollableFrame(sidebar, height=240, fg_color="#121212")
        self.palette_scroll.pack(fill="x", padx=12, pady=(0, 12))

        ctk.CTkButton(
            sidebar,
            text="Fill Entire Map w/ Tile",
            fg_color="#333333",
            hover_color="#444444",
            command=self.fill_map_with_selected,
        ).pack(fill="x", padx=14, pady=(4, 6))

        ctk.CTkButton(
            sidebar,
            text="Clear All Events",
            fg_color="#7F1D1D",
            hover_color="#991B1B",
            command=self.clear_all_events,
        ).pack(fill="x", padx=14, pady=4)

        # Right Map Canvas Area
        canvas_holder = ctk.CTkFrame(container, fg_color="#121212")
        canvas_holder.pack(side="right", fill="both", expand=True, pady=4)

        self.coord_label = ctk.CTkLabel(
            canvas_holder,
            text="Hover over grid to inspect tiles • Left-click or drag to paint",
            text_color="gray",
            font=ctk.CTkFont(size=12),
        )
        self.coord_label.pack(pady=(10, 6))

        canvas_w = DEFAULT_MAP_W * TILE_SIZE
        canvas_h = DEFAULT_MAP_H * TILE_SIZE
        self.map_canvas = tk.Canvas(
            canvas_holder,
            width=canvas_w,
            height=canvas_h,
            bg="#0e0e0e",
            highlightthickness=1,
            highlightbackground="#333333",
        )
        self.map_canvas.pack(expand=True)

        self.map_canvas.bind("<Button-1>", self.on_map_click)
        self.map_canvas.bind("<B1-Motion>", self.on_map_drag)
        self.map_canvas.bind("<Motion>", self.on_map_hover)

    def rebuild_tile_palette(self):
        for widget in self.palette_scroll.winfo_children():
            widget.destroy()

        if self.selected_tile_var.get() not in self.tile_registry:
            self.selected_tile_var.set("grass")

        for tile_id, info in self.tile_registry.items():
            row = ctk.CTkFrame(self.palette_scroll, fg_color="transparent")
            row.pack(fill="x", pady=3)

            swatch = ctk.CTkFrame(
                row, width=18, height=18, corner_radius=3, fg_color=info["color"]
            )
            swatch.pack(side="left", padx=(4, 8))

            status_tag = "Walk" if info.get("walkable", True) else "Solid"
            ctk.CTkRadioButton(
                row,
                text=f"{info['label']} [{status_tag}]",
                variable=self.selected_tile_var,
                value=tile_id,
                command=lambda: self.editor_tool_var.set("paint"),
            ).pack(side="left")

    def render_editor_map(self):
        self.map_canvas.delete("all")
        map_data = self.project_data["map"]
        w, h = map_data["width"], map_data["height"]
        tiles = map_data["tiles"]

        for y in range(h):
            for x in range(w):
                tile_id = tiles[y][x]
                tile_info = self.tile_registry.get(
                    tile_id, {"color": "#9C27B0", "walkable": True}
                )
                x1, y1 = x * TILE_SIZE, y * TILE_SIZE
                x2, y2 = x1 + TILE_SIZE, y1 + TILE_SIZE
                self.map_canvas.create_rectangle(
                    x1, y1, x2, y2, fill=tile_info["color"], outline="#1e1e1e"
                )

        # Draw Player Start Marker
        px, py = map_data["player_start"]
        self.map_canvas.create_oval(
            px * TILE_SIZE + 5,
            py * TILE_SIZE + 5,
            (px + 1) * TILE_SIZE - 5,
            (py + 1) * TILE_SIZE - 5,
            fill="#EF4444",
            outline="#FFFFFF",
            width=2,
        )
        self.map_canvas.create_text(
            px * TILE_SIZE + TILE_SIZE // 2,
            py * TILE_SIZE + TILE_SIZE // 2,
            text="P",
            fill="#FFFFFF",
            font=("Consolas", 11, "bold"),
        )

        # Draw NPC Events
        for ev in map_data["events"]:
            ex, ey = ev["x"], ev["y"]
            self.map_canvas.create_oval(
                ex * TILE_SIZE + 5,
                ey * TILE_SIZE + 5,
                (ex + 1) * TILE_SIZE - 5,
                (ey + 1) * TILE_SIZE - 5,
                fill="#FACC15",
                outline="#000000",
                width=2,
            )
            self.map_canvas.create_text(
                ex * TILE_SIZE + TILE_SIZE // 2,
                ey * TILE_SIZE + TILE_SIZE // 2,
                text="★",
                fill="#000000",
                font=("Consolas", 12, "bold"),
            )

    def _grid_coords_from_event(self, event):
        gx = event.x // TILE_SIZE
        gy = event.y // TILE_SIZE
        map_data = self.project_data["map"]
        if 0 <= gx < map_data["width"] and 0 <= gy < map_data["height"]:
            return gx, gy
        return None, None

    def on_map_hover(self, event):
        gx, gy = self._grid_coords_from_event(event)
        if gx is None:
            return
        tile_id = self.project_data["map"]["tiles"][gy][gx]
        tile_label = self.tile_registry.get(tile_id, {"label": tile_id})["label"]
        ev_match = next(
            (e["name"] for e in self.project_data["map"]["events"] if e["x"] == gx and e["y"] == gy),
            None,
        )
        ev_str = f"  |  Event: {ev_match}" if ev_match else ""
        self.coord_label.configure(text=f"Tile ({gx}, {gy}) — {tile_label}{ev_str}")

    def on_map_drag(self, event):
        if self.editor_tool_var.get() == "paint":
            self.on_map_click(event)

    def on_map_click(self, event):
        gx, gy = self._grid_coords_from_event(event)
        if gx is None:
            return

        tool = self.editor_tool_var.get()
        map_data = self.project_data["map"]

        if tool == "paint":
            map_data["tiles"][gy][gx] = self.selected_tile_var.get()
            self.render_editor_map()

        elif tool == "player_start":
            map_data["player_start"] = [gx, gy]
            self.render_editor_map()

        elif tool == "event":
            existing = next(
                (e for e in map_data["events"] if e["x"] == gx and e["y"] == gy), None
            )
            dialog = EventEditorDialog(self, gx, gy, existing)
            self.wait_window(dialog)
            if dialog.result:
                if existing:
                    existing["name"] = dialog.result["name"]
                    existing["dialogue"] = dialog.result["dialogue"]
                else:
                    map_data["events"].append(
                        {
                            "x": gx,
                            "y": gy,
                            "name": dialog.result["name"],
                            "dialogue": dialog.result["dialogue"],
                        }
                    )
                self.render_editor_map()

        elif tool == "delete_event":
            map_data["events"] = [
                e for e in map_data["events"] if not (e["x"] == gx and e["y"] == gy)
            ]
            self.render_editor_map()

    def fill_map_with_selected(self):
        tile_id = self.selected_tile_var.get()
        map_data = self.project_data["map"]
        for y in range(map_data["height"]):
            for x in range(map_data["width"]):
                map_data["tiles"][y][x] = tile_id
        self.render_editor_map()

    def clear_all_events(self):
        self.project_data["map"]["events"] = []
        self.render_editor_map()

    # ================= TAB 2: GAME DATABASE =================

    def build_database_tab(self):
        self.db_tabs = ctk.CTkTabview(self.tab_db)
        self.db_tabs.pack(fill="both", expand=True, padx=6, pady=4)

        self.tab_actors = self.db_tabs.add("Actors (Heroes)")
        self.tab_items = self.db_tabs.add("Items & Gear")
        self.tab_skills = self.db_tabs.add("Skills & Magic")

        self.build_actors_subtab()
        self.build_items_subtab()
        self.build_skills_subtab()

    # --- Actors Subtab ---
    def build_actors_subtab(self):
        left = ctk.CTkFrame(self.tab_actors, width=300, fg_color="#181818")
        left.pack(side="left", fill="y", padx=(0, 12), pady=6)
        left.pack_propagate(False)

        ctk.CTkLabel(
            left, text="Party Actors", font=ctk.CTkFont(size=14, weight="bold")
        ).pack(anchor="w", padx=12, pady=(10, 6))

        self.actors_list_scroll = ctk.CTkScrollableFrame(left, fg_color="#121212")
        self.actors_list_scroll.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        right = ctk.CTkFrame(self.tab_actors, fg_color="#181818")
        right.pack(side="right", fill="both", expand=True, pady=6)

        ctk.CTkLabel(
            right, text="Actor Stats Editor", font=ctk.CTkFont(size=15, weight="bold")
        ).pack(anchor="w", padx=20, pady=(14, 12))

        self.actor_name_entry = self._add_labeled_entry(right, "Character Name:")
        self.actor_role_entry = self._add_labeled_entry(right, "Class / Role:")
        self.actor_hp_entry = self._add_labeled_entry(right, "Max HP:")
        self.actor_mp_entry = self._add_labeled_entry(right, "Max MP:")
        self.actor_atk_entry = self._add_labeled_entry(right, "Attack (ATK):")
        self.actor_def_entry = self._add_labeled_entry(right, "Defense (DEF):")

        btn_row = ctk.CTkFrame(right, fg_color="transparent")
        btn_row.pack(fill="x", padx=20, pady=15)

        ctk.CTkButton(btn_row, text="Add New Actor", command=self.add_actor).pack(
            side="left", padx=(0, 8)
        )
        ctk.CTkButton(
            btn_row,
            text="Update Selected",
            fg_color="#2563EB",
            command=self.update_actor,
        ).pack(side="left", padx=8)
        ctk.CTkButton(
            btn_row,
            text="Delete",
            width=80,
            fg_color="#991B1B",
            hover_color="#B91C1C",
            command=self.delete_actor,
        ).pack(side="right")

    def refresh_actors_list(self):
        for w in self.actors_list_scroll.winfo_children():
            w.destroy()
        for idx, actor in enumerate(self.project_data["database"]["actors"]):
            ctk.CTkButton(
                self.actors_list_scroll,
                text=f"{actor['name']} — {actor['role']} (HP {actor['hp']})",
                anchor="w",
                fg_color="#262626" if idx != self.selected_actor_idx else "#1D4ED8",
                hover_color="#333333",
                command=lambda i=idx: self.select_actor(i),
            ).pack(fill="x", pady=3)

    def select_actor(self, idx):
        self.selected_actor_idx = idx
        actor = self.project_data["database"]["actors"][idx]
        self._set_entry(self.actor_name_entry, actor["name"])
        self._set_entry(self.actor_role_entry, actor["role"])
        self._set_entry(self.actor_hp_entry, str(actor["hp"]))
        self._set_entry(self.actor_mp_entry, str(actor["mp"]))
        self._set_entry(self.actor_atk_entry, str(actor["atk"]))
        self._set_entry(self.actor_def_entry, str(actor["def"]))
        self.refresh_actors_list()

    def _read_actor_form(self):
        return {
            "name": self.actor_name_entry.get().strip() or "Unnamed Hero",
            "role": self.actor_role_entry.get().strip() or "Adventurer",
            "hp": int(self.actor_hp_entry.get() or 100),
            "mp": int(self.actor_mp_entry.get() or 20),
            "atk": int(self.actor_atk_entry.get() or 10),
            "def": int(self.actor_def_entry.get() or 10),
        }

    def add_actor(self):
        try:
            self.project_data["database"]["actors"].append(self._read_actor_form())
            self.selected_actor_idx = len(self.project_data["database"]["actors"]) - 1
            self.refresh_actors_list()
        except ValueError:
            messagebox.showerror("Invalid Input", "HP, MP, ATK, and DEF must be numbers.")

    def update_actor(self):
        if self.selected_actor_idx is None:
            return
        try:
            self.project_data["database"]["actors"][
                self.selected_actor_idx
            ] = self._read_actor_form()
            self.refresh_actors_list()
        except ValueError:
            messagebox.showerror("Invalid Input", "HP, MP, ATK, and DEF must be numbers.")

    def delete_actor(self):
        if self.selected_actor_idx is None:
            return
        del self.project_data["database"]["actors"][self.selected_actor_idx]
        self.selected_actor_idx = None
        self.refresh_actors_list()

    # --- Items Subtab ---
    def build_items_subtab(self):
        left = ctk.CTkFrame(self.tab_items, width=300, fg_color="#181818")
        left.pack(side="left", fill="y", padx=(0, 12), pady=6)
        left.pack_propagate(False)

        ctk.CTkLabel(
            left, text="Database Items", font=ctk.CTkFont(size=14, weight="bold")
        ).pack(anchor="w", padx=12, pady=(10, 6))

        self.items_list_scroll = ctk.CTkScrollableFrame(left, fg_color="#121212")
        self.items_list_scroll.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        right = ctk.CTkFrame(self.tab_items, fg_color="#181818")
        right.pack(side="right", fill="both", expand=True, pady=6)

        ctk.CTkLabel(
            right, text="Item Properties", font=ctk.CTkFont(size=15, weight="bold")
        ).pack(anchor="w", padx=20, pady=(14, 12))

        self.item_name_entry = self._add_labeled_entry(right, "Item Name:")
        self.item_type_entry = self._add_labeled_entry(
            right, "Type (Consumable / Weapon / Armor):"
        )
        self.item_power_entry = self._add_labeled_entry(right, "Heal / Stat Power:")
        self.item_price_entry = self._add_labeled_entry(right, "Gold Price:")

        btn_row = ctk.CTkFrame(right, fg_color="transparent")
        btn_row.pack(fill="x", padx=20, pady=15)

        ctk.CTkButton(btn_row, text="Add New Item", command=self.add_item).pack(
            side="left", padx=(0, 8)
        )
        ctk.CTkButton(
            btn_row,
            text="Update Selected",
            fg_color="#2563EB",
            command=self.update_item,
        ).pack(side="left", padx=8)
        ctk.CTkButton(
            btn_row,
            text="Delete",
            width=80,
            fg_color="#991B1B",
            hover_color="#B91C1C",
            command=self.delete_item,
        ).pack(side="right")

    def refresh_items_list(self):
        for w in self.items_list_scroll.winfo_children():
            w.destroy()
        for idx, item in enumerate(self.project_data["database"]["items"]):
            ctk.CTkButton(
                self.items_list_scroll,
                text=f"{item['name']} [{item['type']}] ({item['price']}G)",
                anchor="w",
                fg_color="#262626" if idx != self.selected_item_idx else "#1D4ED8",
                hover_color="#333333",
                command=lambda i=idx: self.select_item(i),
            ).pack(fill="x", pady=3)

    def select_item(self, idx):
        self.selected_item_idx = idx
        item = self.project_data["database"]["items"][idx]
        self._set_entry(self.item_name_entry, item["name"])
        self._set_entry(self.item_type_entry, item["type"])
        self._set_entry(self.item_power_entry, str(item["power"]))
        self._set_entry(self.item_price_entry, str(item["price"]))
        self.refresh_items_list()

    def _read_item_form(self):
        return {
            "name": self.item_name_entry.get().strip() or "New Item",
            "type": self.item_type_entry.get().strip() or "Consumable",
            "power": int(self.item_power_entry.get() or 10),
            "price": int(self.item_price_entry.get() or 10),
        }

    def add_item(self):
        try:
            self.project_data["database"]["items"].append(self._read_item_form())
            self.selected_item_idx = len(self.project_data["database"]["items"]) - 1
            self.refresh_items_list()
        except ValueError:
            messagebox.showerror("Invalid Input", "Power and Price must be numbers.")

    def update_item(self):
        if self.selected_item_idx is None:
            return
        try:
            self.project_data["database"]["items"][
                self.selected_item_idx
            ] = self._read_item_form()
            self.refresh_items_list()
        except ValueError:
            messagebox.showerror("Invalid Input", "Power and Price must be numbers.")

    def delete_item(self):
        if self.selected_item_idx is None:
            return
        del self.project_data["database"]["items"][self.selected_item_idx]
        self.selected_item_idx = None
        self.refresh_items_list()

    # --- Skills Subtab ---
    def build_skills_subtab(self):
        left = ctk.CTkFrame(self.tab_skills, width=300, fg_color="#181818")
        left.pack(side="left", fill="y", padx=(0, 12), pady=6)
        left.pack_propagate(False)

        ctk.CTkLabel(
            left, text="Database Skills", font=ctk.CTkFont(size=14, weight="bold")
        ).pack(anchor="w", padx=12, pady=(10, 6))

        self.skills_list_scroll = ctk.CTkScrollableFrame(left, fg_color="#121212")
        self.skills_list_scroll.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        right = ctk.CTkFrame(self.tab_skills, fg_color="#181818")
        right.pack(side="right", fill="both", expand=True, pady=6)

        ctk.CTkLabel(
            right, text="Skill Properties", font=ctk.CTkFont(size=15, weight="bold")
        ).pack(anchor="w", padx=20, pady=(14, 12))

        self.skill_name_entry = self._add_labeled_entry(right, "Skill Name:")
        self.skill_mp_entry = self._add_labeled_entry(right, "MP Cost:")
        self.skill_power_entry = self._add_labeled_entry(right, "Base Power:")

        btn_row = ctk.CTkFrame(right, fg_color="transparent")
        btn_row.pack(fill="x", padx=20, pady=15)

        ctk.CTkButton(btn_row, text="Add New Skill", command=self.add_skill).pack(
            side="left", padx=(0, 8)
        )
        ctk.CTkButton(
            btn_row,
            text="Update Selected",
            fg_color="#2563EB",
            command=self.update_skill,
        ).pack(side="left", padx=8)
        ctk.CTkButton(
            btn_row,
            text="Delete",
            width=80,
            fg_color="#991B1B",
            hover_color="#B91C1C",
            command=self.delete_skill,
        ).pack(side="right")

    def refresh_skills_list(self):
        for w in self.skills_list_scroll.winfo_children():
            w.destroy()
        for idx, skill in enumerate(self.project_data["database"]["skills"]):
            ctk.CTkButton(
                self.skills_list_scroll,
                text=f"{skill['name']} (MP: {skill['mp_cost']} | Pwr: {skill['power']})",
                anchor="w",
                fg_color="#262626" if idx != self.selected_skill_idx else "#1D4ED8",
                hover_color="#333333",
                command=lambda i=idx: self.select_skill(i),
            ).pack(fill="x", pady=3)

    def select_skill(self, idx):
        self.selected_skill_idx = idx
        skill = self.project_data["database"]["skills"][idx]
        self._set_entry(self.skill_name_entry, skill["name"])
        self._set_entry(self.skill_mp_entry, str(skill["mp_cost"]))
        self._set_entry(self.skill_power_entry, str(skill["power"]))
        self.refresh_skills_list()

    def _read_skill_form(self):
        return {
            "name": self.skill_name_entry.get().strip() or "New Skill",
            "mp_cost": int(self.skill_mp_entry.get() or 5),
            "power": int(self.skill_power_entry.get() or 20),
        }

    def add_skill(self):
        try:
            self.project_data["database"]["skills"].append(self._read_skill_form())
            self.selected_skill_idx = len(self.project_data["database"]["skills"]) - 1
            self.refresh_skills_list()
        except ValueError:
            messagebox.showerror("Invalid Input", "MP Cost and Power must be numbers.")

    def update_skill(self):
        if self.selected_skill_idx is None:
            return
        try:
            self.project_data["database"]["skills"][
                self.selected_skill_idx
            ] = self._read_skill_form()
            self.refresh_skills_list()
        except ValueError:
            messagebox.showerror("Invalid Input", "MP Cost and Power must be numbers.")

    def delete_skill(self):
        if self.selected_skill_idx is None:
            return
        del self.project_data["database"]["skills"][self.selected_skill_idx]
        self.selected_skill_idx = None
        self.refresh_skills_list()

    # ================= TAB 3: PLUGIN MANAGER (MODS) =================

    def build_plugins_tab(self):
        top_info = ctk.CTkFrame(self.tab_plugins, fg_color="#181818")
        top_info.pack(fill="x", padx=6, pady=(6, 10))

        ctk.CTkLabel(
            top_info,
            text="Custom User Plugins (EULA Section 4 — External .py Mods Only)",
            font=ctk.CTkFont(size=14, weight="bold"),
        ).pack(side="left", padx=15, pady=10)

        ctk.CTkButton(
            top_info,
            text="Reload Plugins",
            width=120,
            command=self.reload_plugins,
        ).pack(side="right", padx=(6, 15), pady=8)

        ctk.CTkButton(
            top_info,
            text="Open Plugins Folder",
            width=145,
            fg_color="#333333",
            hover_color="#444444",
            command=self.open_plugins_folder,
        ).pack(side="right", padx=6, pady=8)

        self.plugins_scroll = ctk.CTkScrollableFrame(
            self.tab_plugins, height=260, fg_color="#141414"
        )
        self.plugins_scroll.pack(fill="both", expand=True, padx=6, pady=(0, 10))

        ctk.CTkLabel(
            self.tab_plugins,
            text="Plugin Loader Console:",
            font=ctk.CTkFont(size=12, weight="bold"),
        ).pack(anchor="w", padx=8)

        self.plugin_console = ctk.CTkTextbox(
            self.tab_plugins,
            height=130,
            fg_color="#0c0c0c",
            text_color="#00FF00",
            font=ctk.CTkFont(family="Consolas", size=11),
        )
        self.plugin_console.pack(fill="x", padx=6, pady=(2, 6))

    def ensure_sample_plugin(self):
        existing_py = [f for f in os.listdir(self.plugins_dir) if f.endswith(".py")]
        if not existing_py:
            sample_path = os.path.join(self.plugins_dir, "sample_lava_mod.py")
            try:
                with open(sample_path, "w", encoding="utf-8") as f:
                    f.write(SAMPLE_PLUGIN_CODE)
            except Exception:
                pass

    def load_plugin_config(self):
        if os.path.exists(self.plugin_config_path):
            try:
                with open(self.plugin_config_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {}

    def save_plugin_config(self, config):
        try:
            with open(self.plugin_config_path, "w", encoding="utf-8") as f:
                json.dump(config, f, indent=2)
        except Exception as e:
            self.log_plugin(f"[WARNING] Could not save plugins_config.json: {e}")

    def log_plugin(self, text):
        self.plugin_logs.append(text)
        if hasattr(self, "plugin_console"):
            self.plugin_console.insert("end", text + "\n")
            self.plugin_console.see("end")

    def reload_plugins(self, silent=False):
        self.tile_registry = copy.deepcopy(BASE_TILES)
        self.playtest_hooks = []
        self.plugin_console.delete("0.0", "end")

        for w in self.plugins_scroll.winfo_children():
            w.destroy()

        config = self.load_plugin_config()
        plugin_files = sorted(
            [
                f
                for f in os.listdir(self.plugins_dir)
                if f.endswith(".py") and not f.startswith("_")
            ]
        )

        if not plugin_files:
            ctk.CTkLabel(
                self.plugins_scroll,
                text="No .py plugins found in the 'plugins' folder.",
                text_color="gray",
            ).pack(pady=30)
            self.refresh_all_views()
            return

        for filename in plugin_files:
            full_path = os.path.join(self.plugins_dir, filename)
            enabled = config.get(filename, True)
            config[filename] = enabled

            p_name = filename
            p_author = "Unknown"
            p_ver = "1.0"
            p_desc = "Custom RPG Creator plugin."
            load_status = "Disabled"
            status_color = "gray"

            try:
                spec = importlib.util.spec_from_file_location(
                    f"rpg_mod_{filename[:-3]}", full_path
                )
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)

                p_name = getattr(module, "PLUGIN_NAME", filename)
                p_author = getattr(module, "PLUGIN_AUTHOR", "Unknown")
                p_ver = getattr(module, "PLUGIN_VERSION", "1.0")
                p_desc = getattr(module, "PLUGIN_DESC", p_desc)

                if enabled:
                    if hasattr(module, "register") and callable(module.register):
                        api = PluginAPI(self, filename)
                        module.register(api)
                        load_status = "Active"
                        status_color = "#00FF00"
                    else:
                        load_status = "Missing register(api)"
                        status_color = "#FFA500"
                        self.log_plugin(
                            f"[WARNING] {filename} has no register(api) entry point."
                        )
            except Exception as e:
                load_status = "Error"
                status_color = "#FF4444"
                self.log_plugin(f"[ERROR] Failed loading {filename}: {e}")
                self.log_plugin(traceback.format_exc().strip())

            # Plugin Card UI
            card = ctk.CTkFrame(self.plugins_scroll, fg_color="#1f1f1f", corner_radius=8)
            card.pack(fill="x", padx=6, pady=5)

            top = ctk.CTkFrame(card, fg_color="transparent")
            top.pack(fill="x", padx=12, pady=(8, 2))

            ctk.CTkLabel(
                top,
                text=f"{p_name}  v{p_ver}",
                font=ctk.CTkFont(size=14, weight="bold"),
            ).pack(side="left")

            ctk.CTkLabel(
                top,
                text=f"  [{load_status}]",
                text_color=status_color,
                font=ctk.CTkFont(size=12, weight="bold"),
            ).pack(side="left")

            toggle_var = ctk.BooleanVar(value=enabled)
            ctk.CTkSwitch(
                top,
                text="Enabled",
                variable=toggle_var,
                command=lambda fn=filename, var=toggle_var: self.toggle_plugin(fn, var),
            ).pack(side="right")

            ctk.CTkLabel(
                card,
                text=f"File: plugins/{filename}  |  Author: {p_author}",
                text_color="gray",
                font=ctk.CTkFont(size=11),
            ).pack(anchor="w", padx=12)

            ctk.CTkLabel(
                card,
                text=p_desc,
                font=ctk.CTkFont(size=12),
            ).pack(anchor="w", padx=12, pady=(2, 8))

        self.save_plugin_config(config)
        self.refresh_all_views()
        if not silent:
            self.log_plugin("Plugin reload complete.")

    def toggle_plugin(self, filename, var):
        config = self.load_plugin_config()
        config[filename] = var.get()
        self.save_plugin_config(config)
        self.reload_plugins(silent=True)

    def open_plugins_folder(self):
        if os.name == "nt":
            os.startfile(self.plugins_dir)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", self.plugins_dir])
        else:
            subprocess.Popen(["xdg-open", self.plugins_dir])

    # ================= PROJECT SAVE / LOAD & LAUNCHERS =================

    def new_project(self):
        dialog = ctk.CTkInputDialog(
            text="Enter a name for your new RPG project:", title="New Project"
        )
        name = dialog.get_input()
        if name is None:
            return
        self.project_data = self.create_default_project()
        self.project_data["project_name"] = name.strip() or "Untitled RPG"
        self.current_project_path = None
        self.selected_actor_idx = None
        self.selected_item_idx = None
        self.selected_skill_idx = None
        self.reload_plugins(silent=True)

    def save_project(self):
        if not self.current_project_path:
            safe_name = (
                self.project_data["project_name"].lower().replace(" ", "_") + ".json"
            )
            path = filedialog.asksaveasfilename(
                initialdir=self.projects_dir,
                initialfile=safe_name,
                defaultextension=".json",
                filetypes=[("RPG Project JSON", "*.json")],
            )
            if not path:
                return
            self.current_project_path = path

        try:
            with open(self.current_project_path, "w", encoding="utf-8") as f:
                json.dump(self.project_data, f, indent=2)
            self.update_header_title()
            messagebox.showinfo(
                "Project Saved",
                f"Saved '{self.project_data['project_name']}' successfully.",
            )
        except Exception as e:
            messagebox.showerror("Save Error", f"Could not save project:\n{e}")

    def load_project(self):
        path = filedialog.askopenfilename(
            initialdir=self.projects_dir,
            filetypes=[("RPG Project JSON", "*.json")],
        )
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                loaded = json.load(f)
            if "map" not in loaded or "database" not in loaded:
                raise ValueError("Invalid RPG Creator project file.")
            self.project_data = loaded
            self.current_project_path = path
            self.selected_actor_idx = None
            self.selected_item_idx = None
            self.selected_skill_idx = None
            self.reload_plugins(silent=True)
        except Exception as e:
            messagebox.showerror("Load Error", f"Could not load project:\n{e}")

    def launch_playtest(self):
        PlaytestWindow(
            self,
            self.project_data,
            self.tile_registry,
            self.playtest_hooks,
            self.log_plugin,
        )

    def open_info_center(self):
        info_exe = os.path.join(
            self.base_dir, "Info.exe" if os.name == "nt" else "Info"
        )
        info_py = os.path.join(self.base_dir, "Info.py")

        if os.path.exists(info_exe):
            subprocess.Popen([info_exe], cwd=self.base_dir)
        elif os.path.exists(info_py):
            subprocess.Popen([sys.executable, info_py], cwd=self.base_dir)
        else:
            messagebox.showerror(
                "Missing Tool",
                "Info.exe was not found in the root folder.\nRun Setup.exe in Maintenance Mode to reinstall it.",
            )

    # ================= UI HELPERS =================

    def _add_labeled_entry(self, parent, label_text):
        ctk.CTkLabel(parent, text=label_text).pack(anchor="w", padx=20)
        entry = ctk.CTkEntry(parent)
        entry.pack(fill="x", padx=20, pady=(2, 8))
        return entry

    def _set_entry(self, entry, value):
        entry.delete(0, "end")
        entry.insert(0, value)

    def update_header_title(self):
        proj_name = self.project_data.get("project_name", "Untitled RPG")
        self.project_title_label.configure(
            text=f"RPG Creator ({self.version})  —  Project: {proj_name}"
        )

    def refresh_all_views(self):
        self.update_header_title()
        self.rebuild_tile_palette()
        self.render_editor_map()
        self.refresh_actors_list()
        self.refresh_items_list()
        self.refresh_skills_list()


if __name__ == "__main__":
    _instance_mutex = ensure_single_instance()
    app = RpgCreatorEngine()
    app.mainloop()
