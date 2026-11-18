import customtkinter as ctk
import os
import subprocess
import threading
import sys
import shutil
import platform
from tkinter import messagebox
from datetime import datetime

# Configure the modern look
ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")


class RpgSetupWizard(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("RPG Creator Setup")
        self.geometry("650x520")
        self.resizable(False, False)

        # Resolve root directory whether running as .py or compiled Setup.exe
        if getattr(sys, "frozen", False):
            self.base_dir = os.path.dirname(sys.executable)
        else:
            self.base_dir = os.path.dirname(os.path.abspath(__file__))

        self.log_folder = os.path.join(self.base_dir, "Setup Log")
        self.log_file = os.path.join(self.log_folder, "Setup_log.txt")
        self.backup_folder = os.path.join(self.base_dir, "Old Versions")

        os.makedirs(self.log_folder, exist_ok=True)
        os.makedirs(self.backup_folder, exist_ok=True)

        self.exe_name = "Engine.exe" if os.name == "nt" else "Engine"
        self.exe_path = os.path.join(self.base_dir, self.exe_name)
        self.info_exe_name = "Info.exe" if os.name == "nt" else "Info"
        self.info_exe_path = os.path.join(self.base_dir, self.info_exe_name)
        self.is_update = os.path.exists(self.exe_path)

        # Versioning System
        self.version_file = os.path.join(self.base_dir, "version.txt")
        self.current_version = self.load_current_version()
        self.new_version_var = ctk.StringVar(value="")

        # Page Navigation State Machine
        self.history = []
        self.is_test_mode = False

        # Check architecture silently, then route to the correct starting page
        self.is_supported_arch = self.check_architecture()
        self.current_page = "welcome" if self.is_supported_arch else "unsupported"

        self.install_mode = "full"

        # Variables
        self.maint_action_var = ctk.StringVar(value="reinstall")
        self.install_track_var = ctk.StringVar(value="Test Build")
        self.downgrade_file_var = ctk.StringVar(value="")

        self.comp_core = ctk.BooleanVar(value=True)
        self.comp_physics = ctk.BooleanVar(value=False)
        self.comp_audio = ctk.BooleanVar(value=False)
        self.comp_network = ctk.BooleanVar(value=False)

        self.build_ui_framework()
        self.load_page(self.current_page)

    def check_architecture(self):
        """Returns False if the architecture is 16-bit or ARM16."""
        arch_bits = platform.architecture()[0].lower()
        machine = platform.machine().lower()

        if arch_bits == "16bit" or "arm16" in machine:
            return False
        return True

    def load_current_version(self):
        if os.path.exists(self.version_file):
            try:
                with open(self.version_file, "r") as f:
                    return f.read().strip()
            except Exception:
                return "Unknown"
        return "Unknown"

    def save_new_version(self):
        new_ver = self.new_version_var.get().strip()
        if new_ver:
            try:
                with open(self.version_file, "w") as f:
                    f.write(new_ver)
            except Exception as e:
                self.write_log(f"Warning: Failed to save version file: {e}")

    def write_log(self, message):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        try:
            with open(self.log_file, "a") as f:
                f.write(f"[{timestamp}] {message}\n")
        except Exception:
            pass

    def is_file_locked(self, file_path):
        if not os.path.exists(file_path):
            return False
        try:
            with open(file_path, "a"):
                pass
            return False
        except PermissionError:
            return True

    # ================= NAVIGATION SYSTEM =================

    def build_ui_framework(self):
        self.content_frame = ctk.CTkFrame(self, corner_radius=0, fg_color="transparent")
        self.content_frame.pack(fill="both", expand=True, padx=20, pady=20)

        self.nav_frame = ctk.CTkFrame(self, height=50, corner_radius=0)
        self.nav_frame.pack(fill="x", side="bottom")

        self.btn_back = ctk.CTkButton(
            self.nav_frame, text="< Back", width=80, command=self.prev_step
        )
        self.btn_back.pack(side="left", padx=20, pady=10)

        self.btn_next = ctk.CTkButton(
            self.nav_frame, text="Next >", width=80, command=self.next_step
        )
        self.btn_next.pack(side="right", padx=20, pady=10)

        self.btn_cancel = ctk.CTkButton(
            self.nav_frame,
            text="Cancel",
            width=80,
            fg_color="transparent",
            border_width=1,
            text_color=("gray10", "gray90"),
            command=self.destroy,
        )
        self.btn_cancel.pack(side="right", padx=10, pady=10)

    def clear_content(self):
        for widget in self.content_frame.winfo_children():
            widget.destroy()

    def load_page(self, page_name):
        self.clear_content()
        self.current_page = page_name

        if page_name == "unsupported":
            self.show_unsupported_page()
        elif page_name == "welcome":
            self.show_welcome_page()
        elif page_name == "maintenance":
            self.show_maintenance_page()
        elif page_name == "downgrade":
            self.show_downgrade_page()
        elif page_name == "license":
            self.show_license_page()
        elif page_name == "components":
            self.show_components_page()
        elif page_name == "install":
            self.show_install_page()

    def next_step(self):
        new_ver = self.new_version_var.get().strip()

        next_page = ""
        if self.current_page == "welcome":
            if not new_ver:
                messagebox.showerror("Error", "Please enter/select a target version.")
                return

            if self.is_update and new_ver == self.current_version:
                next_page = "maintenance"
            else:
                selected_track = self.install_track_var.get()
                if selected_track in ["Test Build", "Alpha Build"]:
                    proceed = messagebox.askyesno(
                        "Pre-Release Software",
                        "This version of Rpg Creator hasn't reached beta yet, there might be bugs.\n\nDo you wish to continue?",
                    )
                    if not proceed:
                        return

                self.install_mode = "full"
                next_page = "license"

        elif self.current_page == "maintenance":
            action = self.maint_action_var.get()
            if action == "reinstall":
                self.install_mode = "reinstall"
                next_page = "components"
            elif action == "downgrade":
                self.install_mode = "downgrade"
                next_page = "downgrade"
            elif action == "deps":
                self.install_mode = "deps"
                next_page = "install"

        elif self.current_page == "downgrade":
            if not self.downgrade_file_var.get():
                messagebox.showerror("Error", "Please select a version to downgrade to.")
                return
            next_page = "install"

        elif self.current_page == "license":
            next_page = "components"

        elif self.current_page == "components":
            next_page = "install"

        if next_page:
            self.history.append(self.current_page)
            self.load_page(next_page)

    def prev_step(self):
        if self.history:
            prev_page = self.history.pop()
            self.load_page(prev_page)

    # ================= UI PAGES =================

    def show_unsupported_page(self):
        if self.is_test_mode:
            self.btn_back.configure(state="normal")
            self.btn_cancel.configure(text="Cancel")
        else:
            self.btn_back.configure(state="disabled")
            self.btn_cancel.configure(text="Exit")

        self.btn_next.configure(state="disabled")

        ctk.CTkLabel(self.content_frame, text="⚠️", font=ctk.CTkFont(size=60)).pack(
            pady=(40, 10)
        )

        status_text = (
            "Installation Halted"
            if not self.is_test_mode
            else "Installation Halted (Simulation)"
        )
        ctk.CTkLabel(
            self.content_frame,
            text=status_text,
            font=ctk.CTkFont(size=24, weight="bold"),
            text_color="#FF4444",
        ).pack(pady=(0, 10))

        ctk.CTkLabel(
            self.content_frame,
            text="unsupported arch, please buy a new pc with at least x86",
            font=ctk.CTkFont(size=14),
        ).pack(pady=10)

        if self.is_test_mode:
            sys_info = "Detected System: Simulated OS | Arch: arm16 (16bit) [TEST MODE]"
        else:
            sys_info = f"Detected System: {platform.system()} {platform.release()} | Arch: {platform.machine()} ({platform.architecture()[0]})"

        ctk.CTkLabel(
            self.content_frame,
            text=sys_info,
            font=ctk.CTkFont(size=12),
            text_color="gray",
        ).pack(pady=20)

    def show_welcome_page(self):
        self.is_test_mode = False
        self.btn_back.configure(state="disabled")
        self.btn_next.configure(state="normal", text="Next >")

        title = (
            "Update RPG Creator Engine"
            if self.is_update
            else "Welcome to RPG Creator Setup"
        )
        ctk.CTkLabel(
            self.content_frame, text=title, font=ctk.CTkFont(size=24, weight="bold")
        ).pack(pady=(10, 5), anchor="w")

        if self.is_update:
            ctk.CTkLabel(
                self.content_frame,
                text=f"Current Installed Version: {self.current_version}",
                text_color="#00FF00",
                font=ctk.CTkFont(weight="bold"),
            ).pack(anchor="w", pady=(0, 10))
        else:
            ctk.CTkLabel(
                self.content_frame,
                text="No existing engine detected. Let's configure your new installation.",
                text_color="gray",
            ).pack(anchor="w", pady=(0, 10))

        self.version_frame = ctk.CTkFrame(self.content_frame, fg_color="#1a1a1a")
        self.version_frame.pack(fill="both", expand=True, pady=5, ipadx=10, ipady=10)

        ctk.CTkLabel(
            self.version_frame,
            text="Select Installation Track:",
            font=ctk.CTkFont(weight="bold"),
        ).pack(anchor="w", padx=10, pady=(5, 10))

        modes = [
            ("Install Latest Release (Stable) - Not Available", "Latest Release", "disabled"),
            ("Install Beta Build (Experimental Features) - Not Available", "Beta Build", "disabled"),
            ("Install Alpha Build (Unstable / Bleeding Edge) - Not Available", "Alpha Build", "disabled"),
            ("Install Test Version (Internal Testing)", "Test Build", "normal"),
            ("Standard Install + Extra Dependencies - Not Available", "Standard w/ Extras", "disabled"),
            ("Custom Version Entry - Locked", "custom", "disabled"),
        ]

        for text, val, btn_state in modes:
            ctk.CTkRadioButton(
                self.version_frame,
                text=text,
                variable=self.install_track_var,
                value=val,
                state=btn_state,
                command=self.on_install_track_change,
            ).pack(anchor="w", padx=20, pady=6)

        self.custom_version_entry = ctk.CTkEntry(
            self.version_frame, textvariable=self.new_version_var, width=250
        )
        self.custom_version_entry.pack(anchor="w", padx=20, pady=(10, 0))

        # Test Toggle and Button for Unsupported Architecture Screen
        self.test_frame = ctk.CTkFrame(self.content_frame, fg_color="transparent")
        self.test_frame.pack(fill="x", pady=10)

        self.test_toggle_var = ctk.BooleanVar(value=False)
        self.test_switch = ctk.CTkSwitch(
            self.test_frame,
            text="Enable Unsupported Arch Toggle",
            variable=self.test_toggle_var,
        )
        self.test_switch.pack(side="left", padx=10)

        self.test_btn = ctk.CTkButton(
            self.test_frame,
            text="Test Unsupported Message",
            fg_color="#444444",
            hover_color="#555555",
            command=self.trigger_test_message,
        )
        self.test_btn.pack(side="right", padx=10)

        self.on_install_track_change()

    def trigger_test_message(self):
        if self.test_toggle_var.get():
            self.is_test_mode = True
            self.history.append(self.current_page)
            self.load_page("unsupported")

    def on_install_track_change(self):
        selection = self.install_track_var.get()
        if selection == "custom":
            self.new_version_var.set("")
            self.custom_version_entry.configure(state="normal")
        else:
            self.new_version_var.set(selection)
            self.custom_version_entry.configure(state="disabled")

    def show_maintenance_page(self):
        self.btn_back.configure(state="normal")
        self.btn_next.configure(state="normal", text="Next >")

        ctk.CTkLabel(
            self.content_frame,
            text="Maintenance Mode",
            font=ctk.CTkFont(size=24, weight="bold"),
            text_color="#FFA500",
        ).pack(pady=(20, 10), anchor="w")
        ctk.CTkLabel(
            self.content_frame,
            text="The version number hasn't changed. What would you like to do?",
        ).pack(anchor="w", pady=(0, 20))

        ctk.CTkRadioButton(
            self.content_frame,
            text="Reinstall/Repair Engine & Info Tool (Rebuilds EXEs)",
            variable=self.maint_action_var,
            value="reinstall",
        ).pack(anchor="w", pady=10)
        ctk.CTkRadioButton(
            self.content_frame,
            text="Downgrade (Restore a previous version from Old Versions)",
            variable=self.maint_action_var,
            value="downgrade",
        ).pack(anchor="w", pady=10)
        ctk.CTkRadioButton(
            self.content_frame,
            text="Install/Reset Dependencies (Regenerates DLLs only)",
            variable=self.maint_action_var,
            value="deps",
        ).pack(anchor="w", pady=10)

    def show_downgrade_page(self):
        self.btn_back.configure(state="normal")
        self.btn_next.configure(state="normal", text="Downgrade")

        ctk.CTkLabel(
            self.content_frame,
            text="Select Version to Restore",
            font=ctk.CTkFont(size=20, weight="bold"),
        ).pack(pady=(0, 10), anchor="w")

        files = [
            f
            for f in os.listdir(self.backup_folder)
            if f.startswith("Engine_v_") and f.endswith(".exe")
        ]

        if not files:
            ctk.CTkLabel(
                self.content_frame,
                text="No previous versions found in 'Old Versions' folder.",
                text_color="red",
            ).pack(anchor="w")
            self.btn_next.configure(state="disabled")
        else:
            self.downgrade_file_var.set(files[-1])
            ctk.CTkOptionMenu(
                self.content_frame,
                variable=self.downgrade_file_var,
                values=files,
                width=300,
            ).pack(anchor="w", pady=10)

    def show_license_page(self):
        self.btn_back.configure(state="normal")
        self.btn_next.configure(state="disabled")

        ctk.CTkLabel(
            self.content_frame,
            text="License Agreement",
            font=ctk.CTkFont(size=20, weight="bold"),
        ).pack(pady=(0, 10), anchor="w")

        eula_text = (
            "END USER LICENSE AGREEMENT (EULA)\n\n"
            "1. GRANT OF LICENSE\n"
            "This software is licensed, not sold. We grant you a personal, non-exclusive, non-transferable license to use the RPG Creator Engine for game development purposes.\n\n"
            "2. ANTI-PIRACY & RESTRICTIONS\n"
            "You may not copy, distribute, share, rent, or sell this software, its installation files, or any proprietary modules. Unauthorized redistribution or piracy of the Engine is strictly prohibited.\n\n"
            "3. REVERSE ENGINEERING & CORE MODIFICATIONS\n"
            "You may not reverse engineer, decompile, disassemble, or attempt to extract the source code of the core engine, installer, or any generated dependencies.\n\n"
            "4. USER-CREATED PLUGINS (MODDING)\n"
            "Notwithstanding the restrictions in Section 3, you are explicitly permitted to create, use, and freely distribute your own custom plugins or mods to extend the functionality of the Engine, provided these plugins do not modify or replace the proprietary core engine files.\n\n"
            "5. TERMINATION\n"
            "Failure to comply with any of these terms will result in immediate revocation of your license, removal of your access, and potential legal action."
        )

        eula = ctk.CTkTextbox(self.content_frame, height=180, wrap="word")
        eula.pack(fill="x", pady=(0, 15))
        eula.insert("0.0", eula_text)
        eula.configure(state="disabled")

        self.agree_var = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(
            self.content_frame,
            text="I accept the terms in the License Agreement",
            variable=self.agree_var,
            command=lambda: self.btn_next.configure(
                state="normal" if self.agree_var.get() else "disabled"
            ),
        ).pack(anchor="w")

    def show_components_page(self):
        self.btn_back.configure(state="normal")
        self.btn_next.configure(state="normal", text="Install")

        ctk.CTkLabel(
            self.content_frame,
            text="Select Components",
            font=ctk.CTkFont(size=20, weight="bold"),
        ).pack(pady=(0, 10), anchor="w")

        ctk.CTkCheckBox(
            self.content_frame,
            text="Core Engine DLLs & Info Hub (Required)",
            variable=self.comp_core,
            state="disabled",
        ).pack(anchor="w", pady=5)
        ctk.CTkCheckBox(
            self.content_frame, text="Physics Module", variable=self.comp_physics
        ).pack(anchor="w", pady=5)
        ctk.CTkCheckBox(
            self.content_frame, text="Audio Module", variable=self.comp_audio
        ).pack(anchor="w", pady=5)
        ctk.CTkCheckBox(
            self.content_frame, text="Network Module", variable=self.comp_network
        ).pack(anchor="w", pady=5)

    def show_install_page(self):
        if self.is_file_locked(self.exe_path):
            messagebox.showwarning(
                "Engine is Running",
                "Engine.exe is currently open and running.\nPlease close it before continuing.",
            )
            self.prev_step()
            return

        if self.is_file_locked(self.info_exe_path):
            messagebox.showwarning(
                "Info Hub is Running",
                "Info.exe is currently open and running.\nPlease close it before continuing.",
            )
            self.prev_step()
            return

        self.btn_back.configure(state="disabled")
        self.btn_next.configure(state="disabled")
        self.btn_cancel.configure(state="disabled")

        if self.install_mode == "downgrade":
            action_title = "Downgrading Engine..."
        elif self.install_mode == "deps":
            action_title = "Installing Dependencies..."
        else:
            action_title = f"Installing {self.new_version_var.get().strip()}..."

        self.action_title_label = ctk.CTkLabel(
            self.content_frame,
            text=action_title,
            font=ctk.CTkFont(size=20, weight="bold"),
        )
        self.action_title_label.pack(pady=(0, 10), anchor="w")

        self.progress = ctk.CTkProgressBar(self.content_frame)
        self.progress.pack(fill="x", pady=(10, 5))
        self.progress.set(0)

        self.status_label = ctk.CTkLabel(
            self.content_frame, text="Preparing...", text_color="gray"
        )
        self.status_label.pack(anchor="w")

        self.log_box = ctk.CTkTextbox(
            self.content_frame,
            height=130,
            fg_color="#0c0c0c",
            text_color="#00FF00",
            font=ctk.CTkFont(family="Consolas", size=11),
        )
        self.log_box.pack(fill="both", expand=True, pady=(15, 0))

        threading.Thread(target=self.run_setup_tasks, daemon=True).start()

    # ================= EXECUTION LOGIC =================

    def gui_log(self, text):
        self.log_box.insert("end", text + "\n")
        self.log_box.see("end")
        self.write_log(text)

    def backup_old_engine(self):
        if not os.path.exists(self.exe_path):
            return
        safe_version = self.current_version.replace(" ", "_")
        backup_name = (
            f"{self.exe_name.replace('.exe', '')}_v_{safe_version}.exe"
            if os.name == "nt"
            else f"{self.exe_name}_v_{safe_version}"
        )
        backup_path = os.path.join(self.backup_folder, backup_name)

        if os.path.exists(backup_path):
            backup_name = backup_name.replace(
                ".exe", f"_{datetime.now().strftime('%H%M%S')}.exe"
            )
            backup_path = os.path.join(self.backup_folder, backup_name)

        try:
            shutil.move(self.exe_path, backup_path)
            self.gui_log(f"[BACKUP] Saved to: Old Versions/{backup_name}")
        except Exception as e:
            self.gui_log(f"[WARNING] Backup failed: {e}")

    def run_setup_tasks(self):
        try:
            self.write_log(f"--- SETUP INITIATED [{self.install_mode.upper()}] ---")

            if self.install_mode in ["full", "reinstall"]:
                if self.is_update:
                    self.status_label.configure(text="Archiving old version...")
                    self.backup_old_engine()

                self.progress.set(0.25)
                self.status_label.configure(text="Generating C++ Modules...")
                self.generate_dll_code()

                if (
                    not self.is_update
                    and self.install_track_var.get() == "Standard w/ Extras"
                ):
                    self.gui_log("Fetching Extra Dependencies...")
                    os.makedirs(os.path.join(self.base_dir, "Extras"), exist_ok=True)
                    self.gui_log("Extra Dependencies Unpacked.")

                self.progress.set(0.5)
                self.status_label.configure(text="Compiling Engine & Info Executables...")
                self.build_executables()

                self.save_new_version()

            elif self.install_mode == "deps":
                self.progress.set(0.5)
                self.status_label.configure(text="Generating Dependencies...")
                self.generate_dll_code()
                self.gui_log("Skipping PyInstaller build (Dependency Mode).")

            elif self.install_mode == "downgrade":
                self.status_label.configure(text="Restoring old version...")
                self.backup_old_engine()

                selected_exe = self.downgrade_file_var.get()
                source_path = os.path.join(self.backup_folder, selected_exe)
                shutil.copy(source_path, self.exe_path)
                self.gui_log(f"Restored {selected_exe} to root directory.")

                old_ver = (
                    selected_exe.replace(f"{self.exe_name.replace('.exe', '')}_v_", "")
                    .replace(".exe", "")
                    .replace("_", " ")
                )
                self.new_version_var.set(old_ver)
                self.save_new_version()

            # Success Finish State
            self.progress.set(1.0)
            self.action_title_label.configure(
                text="Thanks For Installing Rpg Creator!", text_color="#00FF00"
            )
            self.status_label.configure(text="Complete!", text_color="#00FF00")
            self.gui_log("Thanks For Installing Rpg Creator!")
            self.gui_log("Process finished successfully.")
            self.write_log("--- SETUP COMPLETED ---")

            self.btn_next.configure(state="normal", text="Finish", command=self.destroy)
            self.btn_cancel.configure(state="normal")

        except Exception as e:
            self.status_label.configure(text="Process Failed.", text_color="#FF0000")
            self.gui_log(f"ERROR: {str(e)}")
            self.write_log("--- ABORTED DUE TO ERROR ---")
            self.btn_cancel.configure(state="normal", text="Close")

    def generate_dll_code(self):
        dll_folder = os.path.join(self.base_dir, "dll")
        os.makedirs(dll_folder, exist_ok=True)
        with open(os.path.join(dll_folder, "Rpg_Core.cpp"), "w") as f:
            f.write("#include <windows.h>\n")
        self.gui_log("DLL source files refreshed.")

    def _compile_script(self, script_path, output_label):
        if getattr(sys, "frozen", False):
            command = [
                "pyinstaller",
                "--noconfirm",
                "--onefile",
                "--windowed",
                f"--distpath={self.base_dir}",
                script_path,
            ]
        else:
            command = [
                sys.executable,
                "-m",
                "PyInstaller",
                "--noconfirm",
                "--onefile",
                "--windowed",
                f"--distpath={self.base_dir}",
                script_path,
            ]

        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )

        for line in process.stdout:
            self.gui_log(line.strip())
        process.wait()

        if process.returncode != 0:
            raise Exception(f"PyInstaller failed while building {output_label}.")
        self.gui_log(f"{output_label} compiled successfully.")

    def build_executables(self):
        engine_script = os.path.join(self.base_dir, "Engine.py")
        if not os.path.exists(engine_script):
            raise FileNotFoundError(f"Missing script: {engine_script}")

        self.gui_log("Compiling Engine.exe...")
        self._compile_script(engine_script, self.exe_name)

        self.progress.set(0.8)
        info_script = os.path.join(self.base_dir, "Info.py")
        if os.path.exists(info_script):
            self.gui_log("Compiling Info.exe...")
            self._compile_script(info_script, self.info_exe_name)
        else:
            self.gui_log("[NOTICE] Info.py not found; skipping Info.exe build.")


if __name__ == "__main__":
    app = RpgSetupWizard()
    app.mainloop()
