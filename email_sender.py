import json
import mimetypes
import os
import smtplib
import threading
import time
import tkinter as tk
from email.message import EmailMessage
from tkinter import filedialog, font, messagebox, ttk
import urllib.request
import urllib.error
import xml.etree.ElementTree as ET
from datetime import datetime


# =========================================================================
# DEFAULT FILES / SETTINGS
# =========================================================================

APP_SETTINGS_FILE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "settings.json"
)

DEFAULT_DATA_FOLDER = os.path.dirname(os.path.abspath(__file__))


# =========================================================================
# MAIN APPLICATION
# =========================================================================

class EmailApp:

    def __init__(self, root):
        self.root = root
        self.root.title("Email Suite & Feed Monitor")
        self.root.geometry("920x700")
        self.root.minsize(820, 600)

        # ---------------------------------------------------------------
        # Application settings
        # ---------------------------------------------------------------

        self.app_settings = self.load_app_settings()

        self.data_folder = self.app_settings.get(
            "data_folder",
            DEFAULT_DATA_FOLDER
        )

        self.theme = self.app_settings.get(
            "theme",
            "System"
        )

        self.update_file_paths()

        # ---------------------------------------------------------------
        # Application state
        # ---------------------------------------------------------------

        self.attached_files = []
        self.feeds = self.load_feeds()
        self.seen_entries = self.load_seen_entries()
        self.server_cfg = self.load_server_cfg()

        self.auto_check_enabled = tk.BooleanVar(value=True)
        self.status_var = tk.StringVar(value="Ready")

        self._bold_active = False
        self._italic_active = False

        self._editing_feed_index = None

        # ---------------------------------------------------------------
        # Setup
        # ---------------------------------------------------------------

        self.setup_styles()
        self.create_menu()

        self.create_notebook()
        self.create_send_email_tab()
        self.create_email_feed_tab()
        self.create_server_tab()
        self.create_settings_tab()
        self.create_instructions_tab()
        self.create_footer()

        self.apply_theme()

        # Local background feed checker
        threading.Thread(
            target=self.background_feed_checker,
            daemon=True
        ).start()

    # =========================================================================
    # APPLICATION SETTINGS
    # =========================================================================

    def load_app_settings(self):
        if os.path.exists(APP_SETTINGS_FILE):
            try:
                with open(APP_SETTINGS_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass

        return {
            "data_folder": DEFAULT_DATA_FOLDER,
            "theme": "System"
        }

    def save_app_settings(self):
        try:
            with open(APP_SETTINGS_FILE, "w", encoding="utf-8") as f:
                json.dump(self.app_settings, f, indent=4)
        except Exception as ex:
            messagebox.showerror(
                "Error",
                f"Could not save application settings:\n{ex}"
            )

    def update_file_paths(self):
        self.config_file = os.path.join(
            self.data_folder,
            "feeds_config.json"
        )

        self.seen_file = os.path.join(
            self.data_folder,
            "seen_entries.json"
        )

        self.server_file = os.path.join(
            self.data_folder,
            "server_config.json"
        )

    # =========================================================================
    # TAB — SETTINGS
    # =========================================================================

    def create_settings_tab(self):
        frame = ttk.Frame(self.tab_settings, padding=15)
        frame.pack(fill="both", expand=True)

        # ---------------------------------------------------------------
        # Data folder
        # ---------------------------------------------------------------

        folder_frame = ttk.LabelFrame(
            frame,
            text=" File Save Location ",
            padding=10
        )
        folder_frame.pack(fill="x", pady=(0, 12))

        ttk.Label(
            folder_frame,
            text="Feed/configuration files are saved in:"
        ).pack(anchor="w")

        folder_row = ttk.Frame(folder_frame)
        folder_row.pack(fill="x", pady=(8, 0))

        self.settings_folder_var = tk.StringVar(value=self.data_folder)

        folder_entry = ttk.Entry(
            folder_row,
            textvariable=self.settings_folder_var
        )
        folder_entry.pack(
            side="left",
            fill="x",
            expand=True
        )

        def choose_folder():
            selected = filedialog.askdirectory(
                title="Choose Data Save Folder",
                initialdir=self.data_folder
            )

            if selected:
                self.settings_folder_var.set(selected)

        ttk.Button(
            folder_row,
            text="Browse...",
            command=choose_folder
        ).pack(side="left", padx=(8, 0))

        ttk.Button(
            folder_frame,
            text="Reset to App Folder",
            command=lambda: self.settings_folder_var.set(DEFAULT_DATA_FOLDER)
        ).pack(anchor="w", pady=(8, 0))

        # ---------------------------------------------------------------
        # Theme
        # ---------------------------------------------------------------

        theme_frame = ttk.LabelFrame(
            frame,
            text=" Application Theme ",
            padding=10
        )
        theme_frame.pack(fill="x", pady=(0, 12))

        ttk.Label(
            theme_frame,
            text="Choose the appearance used throughout the application:"
        ).pack(anchor="w")

        self.settings_theme_var = tk.StringVar(value=self.theme)

        theme_combo = ttk.Combobox(
            theme_frame,
            textvariable=self.settings_theme_var,
            values=["System", "Light", "Dark"],
            state="readonly",
            width=18
        )
        theme_combo.pack(anchor="w", pady=(8, 0))

        # ---------------------------------------------------------------
        # Buttons
        # ---------------------------------------------------------------

        button_frame = ttk.Frame(frame)
        button_frame.pack(fill="x", side="bottom")

        ttk.Button(
            button_frame,
            text="Revert Changes",
            command=self.revert_settings_tab
        ).pack(side="right", padx=(5, 0))

        ttk.Button(
            button_frame,
            text="Save Settings",
            command=self.save_settings_tab,
            style="Accent.TButton"
        ).pack(side="right")

    def revert_settings_tab(self):
        self.settings_folder_var.set(self.data_folder)
        self.settings_theme_var.set(self.theme)

        self.set_status(
            "Settings changes reverted."
        )

    def save_settings_tab(self):
        selected_folder = self.settings_folder_var.get().strip()

        if not selected_folder:
            messagebox.showerror(
                "Invalid Folder",
                "Please choose a folder."
            )
            return

        if not os.path.isdir(selected_folder):
            try:
                os.makedirs(selected_folder, exist_ok=True)
            except Exception as ex:
                messagebox.showerror(
                    "Folder Error",
                    f"Could not create the folder:\n{ex}"
                )
                return

        self.data_folder = selected_folder
        self.theme = self.settings_theme_var.get()

        self.app_settings["data_folder"] = self.data_folder
        self.app_settings["theme"] = self.theme

        self.update_file_paths()
        self.save_app_settings()

        self.apply_theme()

        self.set_status(
            "Application settings saved."
        )

    # =========================================================================
    # STYLES / THEME
    # =========================================================================

    def setup_styles(self):
        self.style = ttk.Style()

        try:
            self.style.theme_use("clam")
        except Exception:
            pass

        self.style.configure(
            "Accent.TButton",
            foreground="white",
            background="#2563EB"
        )

        self.style.map(
            "Accent.TButton",
            background=[
                ("active", "#1D4ED8")
            ]
        )

        self.style.configure(
            "Danger.TButton",
            foreground="white",
            background="#DC2626"
        )

        self.style.map(
            "Danger.TButton",
            background=[
                ("active", "#B91C1C")
            ]
        )

    def detect_system_theme(self):
        """
        Attempts to detect the operating system theme.

        Windows:
            Uses the Windows registry.

        macOS:
            Uses defaults.

        Linux:
            Attempts common desktop settings.

        Falls back to Light.
        """

        # Windows
        if os.name == "nt":
            try:
                import winreg

                key = winreg.OpenKey(
                    winreg.HKEY_CURRENT_USER,
                    r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"
                )

                value, _ = winreg.QueryValueEx(
                    key,
                    "AppsUseLightTheme"
                )

                winreg.CloseKey(key)

                return "Light" if value else "Dark"

            except Exception:
                return "Light"

        # macOS
        if os.uname().sysname == "Darwin":
            try:
                import subprocess

                result = subprocess.run(
                    [
                        "defaults",
                        "read",
                        "-g",
                        "AppleInterfaceStyle"
                    ],
                    capture_output=True,
                    text=True
                )

                if "Dark" in result.stdout:
                    return "Dark"

            except Exception:
                pass

            return "Light"

        # Linux
        try:
            import subprocess

            result = subprocess.run(
                [
                    "gsettings",
                    "get",
                    "org.gnome.desktop.interface",
                    "color-scheme"
                ],
                capture_output=True,
                text=True
            )

            if "dark" in result.stdout.lower():
                return "Dark"

        except Exception:
            pass

        return "Light"

    def apply_theme(self):
        if self.theme == "System":
            actual_theme = self.detect_system_theme()
        else:
            actual_theme = self.theme

        if actual_theme == "Dark":
            self.apply_dark_theme()
        else:
            self.apply_light_theme()

        self.apply_theme_to_window(self.root)

    def apply_light_theme(self):
        self.root.configure(bg="#F2F2F2")

        self.style.configure(
            ".",
            background="#F2F2F2",
            foreground="#111111"
        )

        self.style.configure(
            "TFrame",
            background="#F2F2F2"
        )

        self.style.configure(
            "TLabel",
            background="#F2F2F2",
            foreground="#111111"
        )

        self.style.configure(
            "TLabelframe",
            background="#F2F2F2",
            foreground="#111111"
        )

        self.style.configure(
            "TLabelframe.Label",
            background="#F2F2F2",
            foreground="#111111"
        )

        self.style.configure(
            "TCheckbutton",
            background="#F2F2F2",
            foreground="#111111"
        )

        self.style.configure(
            "TNotebook",
            background="#F2F2F2"
        )

        self.style.configure(
            "TNotebook.Tab",
            background="#E5E7EB",
            foreground="#111111"
        )

        self.style.map(
            "TNotebook.Tab",
            background=[
                ("selected", "#FFFFFF")
            ],
            foreground=[
                ("selected", "#111111")
            ]
        )

        self.style.configure(
            "TEntry",
            fieldbackground="#FFFFFF",
            foreground="#111111"
        )

        self.style.configure(
            "TCombobox",
            fieldbackground="#FFFFFF",
            foreground="#111111"
        )

        self.style.configure(
            "Treeview",
            background="#FFFFFF",
            foreground="#111111",
            fieldbackground="#FFFFFF"
        )

        self.style.configure(
            "Treeview.Heading",
            background="#E5E7EB",
            foreground="#111111"
        )

        self.style.configure(
            "TScrollbar",
            background="#D1D5DB"
        )

        if hasattr(self, "text_editor"):
            self.text_editor.configure(
                bg="#FFFFFF",
                fg="#111111",
                insertbackground="#111111",
                selectbackground="#2563EB",
                selectforeground="#FFFFFF"
            )

        if hasattr(self, "feed_text"):
            self.feed_text.configure(
                bg="#FFFFFF",
                fg="#111111",
                insertbackground="#111111",
                selectbackground="#2563EB",
                selectforeground="#FFFFFF"
            )

        if hasattr(self, "srv_log"):
            self.srv_log.configure(
                bg="#FFFFFF",
                fg="#111111",
                insertbackground="#111111",
                selectbackground="#2563EB",
                selectforeground="#FFFFFF"
            )

    def apply_dark_theme(self):
        bg = "#1E1E1E"
        panel = "#252525"
        entry_bg = "#303030"
        fg = "#F5F5F5"
        secondary = "#BDBDBD"

        self.root.configure(bg=bg)

        self.style.configure(
            ".",
            background=bg,
            foreground=fg
        )

        self.style.configure(
            "TFrame",
            background=bg
        )

        self.style.configure(
            "TLabel",
            background=bg,
            foreground=fg
        )

        self.style.configure(
            "TLabelframe",
            background=bg,
            foreground=fg
        )

        self.style.configure(
            "TLabelframe.Label",
            background=bg,
            foreground=fg
        )

        self.style.configure(
            "TCheckbutton",
            background=bg,
            foreground=fg
        )

        self.style.configure(
            "TNotebook",
            background=bg
        )

        self.style.configure(
            "TNotebook.Tab",
            background=panel,
            foreground=fg
        )

        self.style.map(
            "TNotebook.Tab",
            background=[
                ("selected", "#3A3A3A")
            ],
            foreground=[
                ("selected", "#FFFFFF")
            ]
        )

        self.style.configure(
            "TEntry",
            fieldbackground=entry_bg,
            foreground=fg
        )

        self.style.configure(
            "TCombobox",
            fieldbackground=entry_bg,
            foreground=fg
        )

        self.style.map(
            "TCombobox",
            fieldbackground=[
                ("readonly", entry_bg)
            ],
            foreground=[
                ("readonly", fg)
            ]
        )

        self.style.configure(
            "Treeview",
            background=entry_bg,
            foreground=fg,
            fieldbackground=entry_bg
        )

        self.style.map(
            "Treeview",
            background=[
                ("selected", "#2563EB")
            ],
            foreground=[
                ("selected", "#FFFFFF")
            ]
        )

        self.style.configure(
            "Treeview.Heading",
            background="#3A3A3A",
            foreground=fg
        )

        self.style.configure(
            "TScrollbar",
            background="#404040"
        )

        if hasattr(self, "text_editor"):
            self.text_editor.configure(
                bg=entry_bg,
                fg=fg,
                insertbackground=fg,
                selectbackground="#2563EB",
                selectforeground="#FFFFFF"
            )

        if hasattr(self, "feed_text"):
            self.feed_text.configure(
                bg=entry_bg,
                fg=fg,
                insertbackground=fg,
                selectbackground="#2563EB",
                selectforeground="#FFFFFF"
            )

        if hasattr(self, "srv_log"):
            self.srv_log.configure(
                bg=entry_bg,
                fg=fg,
                insertbackground=fg,
                selectbackground="#2563EB",
                selectforeground="#FFFFFF"
            )

    def apply_theme_to_window(self, window):
        try:
            actual_theme = (
                self.detect_system_theme()
                if self.theme == "System"
                else self.theme
            )

            if actual_theme == "Dark":
                window.configure(bg="#1E1E1E")
            else:
                window.configure(bg="#F2F2F2")

        except Exception:
            pass

    # =========================================================================
    # MENU
    # =========================================================================

    def create_menu(self):
        self.menu_bar = tk.Menu(self.root)

        file_menu = tk.Menu(
            self.menu_bar,
            tearoff=0
        )

        file_menu.add_command(
            label="Settings",
            command=lambda: self.notebook.select(self.tab_settings)
        )

        file_menu.add_separator()

        file_menu.add_command(
            label="Exit",
            command=self.root.destroy
        )

        self.menu_bar.add_cascade(
            label="File",
            menu=file_menu
        )

        self.root.config(menu=self.menu_bar)

    # =========================================================================
    # NOTEBOOK
    # =========================================================================

    def create_notebook(self):
        self.notebook = ttk.Notebook(self.root)

        self.notebook.pack(
            fill="both",
            expand=True,
            padx=10,
            pady=5
        )

        self.tab_send = ttk.Frame(self.notebook)
        self.tab_feed = ttk.Frame(self.notebook)
        self.tab_server = ttk.Frame(self.notebook)
        self.tab_settings = ttk.Frame(self.notebook)
        self.tab_instructions = ttk.Frame(self.notebook)

        self.notebook.add(
            self.tab_send,
            text="  📧 Send Email  "
        )

        self.notebook.add(
            self.tab_feed,
            text="  📡 Feed Monitor  "
        )

        self.notebook.add(
            self.tab_server,
            text="  🖥 Server  "
        )

        self.notebook.add(
            self.tab_settings,
            text="  ⚙️ Settings  "
        )

        self.notebook.add(
            self.tab_instructions,
            text="  📖 Instructions  "
        )

    # =========================================================================
    # TAB 1 — SEND EMAIL
    # =========================================================================

    def create_send_email_tab(self):

        sf = ttk.LabelFrame(
            self.tab_send,
            text=" SMTP Configuration ",
            padding=10
        )

        sf.pack(
            fill="x",
            padx=10,
            pady=5
        )

        ttk.Label(
            sf,
            text="SMTP Server:"
        ).grid(
            row=0,
            column=0,
            sticky="e",
            padx=4
        )

        self.entry_smtp_host = ttk.Entry(
            sf,
            width=22
        )

        self.entry_smtp_host.insert(
            0,
            "smtp.gmail.com"
        )

        self.entry_smtp_host.grid(
            row=0,
            column=1,
            padx=5,
            pady=3
        )

        ttk.Label(
            sf,
            text="Port:"
        ).grid(
            row=0,
            column=2,
            sticky="e",
            padx=4
        )

        self.entry_smtp_port = ttk.Entry(
            sf,
            width=8
        )

        self.entry_smtp_port.insert(
            0,
            "587"
        )

        self.entry_smtp_port.grid(
            row=0,
            column=3,
            padx=5,
            pady=3
        )

        ttk.Label(
            sf,
            text="From Email:"
        ).grid(
            row=0,
            column=4,
            sticky="e",
            padx=4
        )

        self.entry_smtp_user = ttk.Entry(
            sf,
            width=22
        )

        self.entry_smtp_user.grid(
            row=0,
            column=5,
            padx=5,
            pady=3
        )

        ttk.Label(
            sf,
            text="App Password:"
        ).grid(
            row=1,
            column=0,
            sticky="e",
            padx=4
        )

        self.entry_smtp_pass = ttk.Entry(
            sf,
            show="*",
            width=22
        )

        self.entry_smtp_pass.grid(
            row=1,
            column=1,
            padx=5,
            pady=3
        )

        self.smtp_tls_var = tk.BooleanVar(
            value=True
        )

        ttk.Checkbutton(
            sf,
            text="Use TLS (port 587)",
            variable=self.smtp_tls_var
        ).grid(
            row=1,
            column=2,
            columnspan=2,
            sticky="w",
            padx=5
        )

        ttk.Button(
            sf,
            text="Test Connection",
            command=self.test_smtp_connection
        ).grid(
            row=1,
            column=4,
            columnspan=2,
            sticky="e",
            padx=5
        )

        # ---------------------------------------------------------------
        # Email headers
        # ---------------------------------------------------------------

        df = ttk.LabelFrame(
            self.tab_send,
            text=" Email Headers ",
            padding=10
        )

        df.pack(
            fill="x",
            padx=10,
            pady=5
        )

        for idx, (lbl, attr) in enumerate([
            ("To:", "entry_to"),
            ("CC:", "entry_cc"),
            ("BCC:", "entry_bcc"),
            ("Subject:", "entry_subject"),
        ]):

            ttk.Label(
                df,
                text=lbl
            ).grid(
                row=idx,
                column=0,
                sticky="e",
                pady=2,
                padx=4
            )

            e = ttk.Entry(
                df,
                width=74
            )

            e.grid(
                row=idx,
                column=1,
                sticky="w",
                padx=5,
                pady=2
            )

            setattr(
                self,
                attr,
                e
            )

        # ---------------------------------------------------------------
        # Formatting toolbar
        # ---------------------------------------------------------------

        tb = ttk.Frame(
            self.tab_send
        )

        tb.pack(
            fill="x",
            padx=10,
            pady=(5, 0)
        )

        self.btn_bold = ttk.Button(
            tb,
            text="B",
            width=3,
            command=self.toggle_bold
        )

        self.btn_bold.pack(
            side="left",
            padx=2
        )

        self.btn_italic = ttk.Button(
            tb,
            text="I",
            width=3,
            command=self.toggle_italic
        )

        self.btn_italic.pack(
            side="left",
            padx=2
        )

        ttk.Separator(
            tb,
            orient="vertical"
        ).pack(
            side="left",
            fill="y",
            padx=4
        )

        ttk.Label(
            tb,
            text="Font:"
        ).pack(
            side="left"
        )

        self.font_family = ttk.Combobox(
            tb,
            values=sorted(font.families()),
            state="readonly",
            width=16
        )

        self.font_family.set("Arial")

        self.font_family.pack(
            side="left",
            padx=2
        )

        self.font_family.bind(
            "<<ComboboxSelected>>",
            self.change_font
        )

        ttk.Label(
            tb,
            text="Size:"
        ).pack(
            side="left",
            padx=(4, 0)
        )

        self.font_size = ttk.Combobox(
            tb,
            values=[
                8, 9, 10, 11, 12, 14,
                16, 18, 20, 24, 28, 36
            ],
            state="readonly",
            width=5
        )

        self.font_size.set("12")

        self.font_size.pack(
            side="left",
            padx=2
        )

        self.font_size.bind(
            "<<ComboboxSelected>>",
            self.change_font_size
        )

        ttk.Separator(
            tb,
            orient="vertical"
        ).pack(
            side="left",
            fill="y",
            padx=4
        )

        ttk.Button(
            tb,
            text="📎 Attach File",
            command=self.attach_file
        ).pack(
            side="left",
            padx=2
        )

        self.attachment_label = ttk.Label(
            tb,
            text="No attachments"
        )

        self.attachment_label.pack(
            side="left",
            padx=4
        )

        # ---------------------------------------------------------------
        # Body
        # ---------------------------------------------------------------

        ef = ttk.Frame(
            self.tab_send
        )

        ef.pack(
            fill="both",
            expand=True,
            padx=10,
            pady=5
        )

        self._cur_family = "Arial"
        self._cur_size = 12

        self.text_editor = tk.Text(
            ef,
            wrap="word",
            height=10,
            font=(
                self._cur_family,
                self._cur_size
            ),
            undo=True,
            relief="flat",
            bd=1
        )

        self.text_editor.pack(
            side="left",
            fill="both",
            expand=True
        )

        self._rebuild_tags()

        sb = ttk.Scrollbar(
            ef,
            orient="vertical",
            command=self.text_editor.yview
        )

        sb.pack(
            side="right",
            fill="y"
        )

        self.text_editor.configure(
            yscrollcommand=sb.set
        )

        # ---------------------------------------------------------------
        # Send row
        # ---------------------------------------------------------------

        br = ttk.Frame(
            self.tab_send
        )

        br.pack(
            fill="x",
            padx=10,
            pady=(0, 8)
        )

        ttk.Button(
            br,
            text="Clear",
            command=self.clear_compose
        ).pack(
            side="left",
            padx=2
        )

        ttk.Button(
            br,
            text="✉ Send Email",
            command=self.send_email,
            style="Accent.TButton"
        ).pack(
            side="right",
            padx=2
        )

    # =========================================================================
    # TEXT FORMATTING
    # =========================================================================

    def _rebuild_tags(self):
        f = self._cur_family
        s = self._cur_size

        self.text_editor.configure(
            font=(f, s)
        )

        self.text_editor.tag_configure(
            "bold",
            font=(f, s, "bold")
        )

        self.text_editor.tag_configure(
            "italic",
            font=(f, s, "italic")
        )

        self.text_editor.tag_configure(
            "bold-italic",
            font=(f, s, "bold italic")
        )

    def toggle_bold(self):
        self._bold_active = not self._bold_active

        self.btn_bold.configure(
            style=(
                "Accent.TButton"
                if self._bold_active
                else "TButton"
            )
        )

        self._apply_format_to_selection()

    def toggle_italic(self):
        self._italic_active = not self._italic_active

        self.btn_italic.configure(
            style=(
                "Accent.TButton"
                if self._italic_active
                else "TButton"
            )
        )

        self._apply_format_to_selection()

    def _apply_format_to_selection(self):
        try:
            s = self.text_editor.index("sel.first")
            e = self.text_editor.index("sel.last")
        except tk.TclError:
            return

        for tag in (
            "bold",
            "italic",
            "bold-italic"
        ):
            self.text_editor.tag_remove(
                tag,
                s,
                e
            )

        if self._bold_active and self._italic_active:
            self.text_editor.tag_add(
                "bold-italic",
                s,
                e
            )

        elif self._bold_active:
            self.text_editor.tag_add(
                "bold",
                s,
                e
            )

        elif self._italic_active:
            self.text_editor.tag_add(
                "italic",
                s,
                e
            )

    def change_font(self, _=None):
        self._cur_family = self.font_family.get()
        self._rebuild_tags()

    def change_font_size(self, _=None):
        try:
            self._cur_size = int(
                self.font_size.get()
            )
        except ValueError:
            pass

        self._rebuild_tags()

    # =========================================================================
    # ATTACHMENTS
    # =========================================================================

    def attach_file(self):
        files = filedialog.askopenfilenames(
            title="Select files to attach"
        )

        if files:
            self.attached_files.extend(files)
            self._update_attach_label()

    def _update_attach_label(self):
        n = len(self.attached_files)

        if n == 0:
            self.attachment_label.configure(
                text="No attachments"
            )

        else:
            names = ", ".join(
                os.path.basename(f)
                for f in self.attached_files
            )

            self.attachment_label.configure(
                text=f"{n} file(s): {names}"
            )

    def clear_compose(self):
        self.text_editor.delete(
            "1.0",
            tk.END
        )

        for w in (
            self.entry_to,
            self.entry_cc,
            self.entry_bcc,
            self.entry_subject
        ):
            w.delete(
                0,
                tk.END
            )

        self.attached_files.clear()

        self._update_attach_label()

    # =========================================================================
    # SMTP
    # =========================================================================

    def _build_smtp(self):
        host = self.entry_smtp_host.get().strip()
        port = int(
            self.entry_smtp_port.get().strip()
        )
        user = self.entry_smtp_user.get().strip()
        password = self.entry_smtp_pass.get().strip()
        use_tls = self.smtp_tls_var.get()

        if not host or not user or not password:
            raise ValueError(
                "SMTP Server, From Email, and App Password are all required."
            )

        if use_tls:
            srv = smtplib.SMTP(
                host,
                port,
                timeout=10
            )

            srv.ehlo()
            srv.starttls()
            srv.ehlo()

        else:
            srv = smtplib.SMTP_SSL(
                host,
                port,
                timeout=10
            )

        srv.login(
            user,
            password
        )

        return srv, user

    def test_smtp_connection(self):
        self.set_status(
            "Testing SMTP connection…"
        )

        def _t():
            try:
                srv, _ = self._build_smtp()

                srv.quit()

                self.root.after(
                    0,
                    lambda: messagebox.showinfo(
                        "Success",
                        "SMTP connection successful!"
                    )
                )

                self.root.after(
                    0,
                    lambda: self.set_status(
                        "SMTP OK"
                    )
                )

            except Exception as ex:
                self.root.after(
                    0,
                    lambda: messagebox.showerror(
                        "Connection Failed",
                        str(ex)
                    )
                )

                self.root.after(
                    0,
                    lambda: self.set_status(
                        "SMTP test failed"
                    )
                )

        threading.Thread(
            target=_t,
            daemon=True
        ).start()

    def send_email(self):
        to = self.entry_to.get().strip()
        subject = self.entry_subject.get().strip()
        body = self.text_editor.get(
            "1.0",
            tk.END
        ).strip()

        if not to:
            messagebox.showerror(
                "Missing Field",
                "The 'To' field is required."
            )
            return

        if not subject:
            messagebox.showerror(
                "Missing Field",
                "The 'Subject' field is required."
            )
            return

        self.set_status(
            "Sending email…"
        )

        def _send():
            try:
                srv, from_addr = self._build_smtp()

                msg = EmailMessage()

                msg["From"] = from_addr
                msg["To"] = to
                msg["Subject"] = subject

                cc = self.entry_cc.get().strip()
                bcc = self.entry_bcc.get().strip()

                if cc:
                    msg["CC"] = cc

                if bcc:
                    msg["BCC"] = bcc

                msg.set_content(body)

                for fp in self.attached_files:
                    mt, _ = mimetypes.guess_type(fp)

                    main, sub = (
                        mt or "application/octet-stream"
                    ).split("/", 1)

                    with open(fp, "rb") as f:
                        msg.add_attachment(
                            f.read(),
                            maintype=main,
                            subtype=sub,
                            filename=os.path.basename(fp)
                        )

                recipients = [
                    a.strip()
                    for a in to.split(",")
                ]

                if cc:
                    recipients += [
                        a.strip()
                        for a in cc.split(",")
                    ]

                if bcc:
                    recipients += [
                        a.strip()
                        for a in bcc.split(",")
                    ]

                srv.send_message(
                    msg,
                    to_addrs=recipients
                )

                srv.quit()

                self.root.after(
                    0,
                    lambda: messagebox.showinfo(
                        "Sent",
                        "Email sent successfully!"
                    )
                )

                self.root.after(
                    0,
                    lambda: self.set_status(
                        "Email sent"
                    )
                )

                self.root.after(
                    0,
                    self.clear_compose
                )

            except Exception as ex:
                self.root.after(
                    0,
                    lambda: messagebox.showerror(
                        "Send Failed",
                        str(ex)
                    )
                )

                self.root.after(
                    0,
                    lambda: self.set_status(
                        f"Send failed: {ex}"
                    )
                )

        threading.Thread(
            target=_send,
            daemon=True
        ).start()

    # =========================================================================
    # TAB 2 — FEED MONITOR
    # =========================================================================

    def create_email_feed_tab(self):

        ff = ttk.LabelFrame(
            self.tab_feed,
            text=" Add New Feed Automation ",
            padding=10
        )

        ff.pack(
            fill="x",
            padx=10,
            pady=5
        )

        for row, (lbl, attr, default) in enumerate([
            (
                "RSS Feed URL:",
                "feed_source",
                ""
            ),
            (
                "Send To (Email):",
                "feed_to",
                ""
            ),
            (
                "Email Subject:",
                "feed_subject",
                "New item from feed: {title}"
            ),
        ]):

            ttk.Label(
                ff,
                text=lbl
            ).grid(
                row=row,
                column=0,
                sticky="e",
                pady=2,
                padx=4
            )

            e = ttk.Entry(
                ff,
                width=57
            )

            if default:
                e.insert(
                    0,
                    default
                )

            e.grid(
                row=row,
                column=1,
                sticky="w",
                padx=5,
                pady=2
            )

            setattr(
                self,
                attr,
                e
            )

        ttk.Label(
            ff,
            text="Email Body Template:"
        ).grid(
            row=3,
            column=0,
            sticky="ne",
            pady=2,
            padx=4
        )

        self.feed_text = tk.Text(
            ff,
            width=57,
            height=4,
            wrap="word"
        )

        self.feed_text.insert(
            "1.0",
            "New item detected!\n\n"
            "Title: {title}\n"
            "Link: {link}\n"
            "Published: {published}"
        )

        self.feed_text.grid(
            row=3,
            column=1,
            sticky="w",
            padx=5,
            pady=2
        )

        ttk.Label(
            ff,
            text="Placeholders: {title} {link} {published} {summary}"
        ).grid(
            row=4,
            column=1,
            sticky="w",
            padx=5
        )

        ttk.Label(
            ff,
            text="Check interval (min):"
        ).grid(
            row=5,
            column=0,
            sticky="e",
            pady=2,
            padx=4
        )

        self.feed_interval = ttk.Entry(
            ff,
            width=8
        )

        self.feed_interval.insert(
            0,
            "15"
        )

        self.feed_interval.grid(
            row=5,
            column=1,
            sticky="w",
            padx=5,
            pady=2
        )

        br = ttk.Frame(ff)

        br.grid(
            row=6,
            column=1,
            sticky="e",
            pady=5
        )

        ttk.Button(
            br,
            text="🔍 Test Feed",
            command=self.test_feed
        ).pack(
            side="left",
            padx=4
        )

        self.feed_save_button = ttk.Button(
            br,
            text="💾 Save Feed",
            command=self.save_new_feed,
            style="Accent.TButton"
        )

        self.feed_save_button.pack(
            side="left"
        )

        # ---------------------------------------------------------------
        # Controls
        # ---------------------------------------------------------------

        cf = ttk.Frame(
            self.tab_feed
        )

        cf.pack(
            fill="x",
            padx=10,
            pady=(0, 4)
        )

        ttk.Checkbutton(
            cf,
            text="Auto-check feeds in background",
            variable=self.auto_check_enabled
        ).pack(
            side="left"
        )

        ttk.Button(
            cf,
            text="▶ Check All Feeds Now",
            command=self.manual_check_feeds
        ).pack(
            side="right"
        )

        # ---------------------------------------------------------------
        # Feed list
        # ---------------------------------------------------------------

        lf = ttk.LabelFrame(
            self.tab_feed,
            text=" Active Feeds ",
            padding=8
        )

        lf.pack(
            fill="both",
            expand=True,
            padx=10,
            pady=5
        )

        cols = (
            "source",
            "to",
            "interval",
            "last_checked"
        )

        self.feed_tree = ttk.Treeview(
            lf,
            columns=cols,
            show="headings",
            height=7
        )

        for col, hdr, w in [
            (
                "source",
                "RSS URL",
                270
            ),
            (
                "to",
                "Send To",
                160
            ),
            (
                "interval",
                "Interval (min)",
                100
            ),
            (
                "last_checked",
                "Last Checked",
                150
            ),
        ]:

            self.feed_tree.heading(
                col,
                text=hdr
            )

            self.feed_tree.column(
                col,
                width=w
            )

        self.feed_tree.pack(
            side="left",
            fill="both",
            expand=True
        )

        sb = ttk.Scrollbar(
            lf,
            orient="vertical",
            command=self.feed_tree.yview
        )

        sb.pack(
            side="right",
            fill="y"
        )

        self.feed_tree.configure(
            yscrollcommand=sb.set
        )

        # ---------------------------------------------------------------
        # Feed buttons
        # ---------------------------------------------------------------

        button_row = ttk.Frame(
            self.tab_feed
        )

        button_row.pack(
            fill="x",
            padx=10,
            pady=4
        )

        ttk.Button(
            button_row,
            text="✏️ Edit Selected Feed",
            command=self.edit_feed
        ).pack(
            side="left",
            padx=2
        )

        ttk.Button(
            button_row,
            text="🗑 Delete Selected Feed",
            command=self.delete_feed
        ).pack(
            side="left",
            padx=2
        )

        self.refresh_feed_table()

    # =========================================================================
    # FEED TEST
    # =========================================================================

    def test_feed(self):
        url = self.feed_source.get().strip()

        if not url:
            messagebox.showerror(
                "Error",
                "Enter an RSS feed URL first."
            )
            return

        self.set_status(
            f"Testing feed: {url}"
        )

        def _t():
            try:
                items = self.fetch_rss_items(url)

                if items:
                    s = items[0]

                    msg = (
                        f"Feed OK — {len(items)} item(s) found.\n\n"
                        f"Latest:\n"
                        f"  Title: {s.get('title', 'N/A')}\n"
                        f"  Link: {s.get('link', 'N/A')}\n"
                        f"  Published: {s.get('published', 'N/A')}"
                    )

                    self.root.after(
                        0,
                        lambda: messagebox.showinfo(
                            "Feed Test OK",
                            msg
                        )
                    )

                    self.root.after(
                        0,
                        lambda: self.set_status(
                            "Feed test OK"
                        )
                    )

                else:
                    self.root.after(
                        0,
                        lambda: messagebox.showwarning(
                            "Feed Empty",
                            "Feed parsed but contains no items."
                        )
                    )

            except Exception as ex:
                self.root.after(
                    0,
                    lambda: messagebox.showerror(
                        "Feed Error",
                        str(ex)
                    )
                )

                self.root.after(
                    0,
                    lambda: self.set_status(
                        "Feed test failed"
                    )
                )

        threading.Thread(
            target=_t,
            daemon=True
        ).start()

    # =========================================================================
    # ADD / EDIT FEEDS
    # =========================================================================

    def save_new_feed(self):
        source = self.feed_source.get().strip()
        to_addr = self.feed_to.get().strip()
        subject = self.feed_subject.get().strip()
        body = self.feed_text.get(
            "1.0",
            tk.END
        ).strip()

        try:
            interval = int(
                self.feed_interval.get().strip()
            )
        except ValueError:
            messagebox.showerror(
                "Error",
                "Interval must be a whole number of minutes."
            )
            return

        if interval <= 0:
            messagebox.showerror(
                "Error",
                "Interval must be greater than 0."
            )
            return

        if not source or not to_addr:
            messagebox.showerror(
                "Error",
                "RSS Feed URL and Send To are required."
            )
            return

        feed_data = {
            "source": source,
            "to": to_addr,
            "subject": subject,
            "text": body,
            "interval": interval,
            "last_checked": None,
            "next_check": 0,
        }

        # ---------------------------------------------------------------
        # EDIT EXISTING FEED
        # ---------------------------------------------------------------

        if self._editing_feed_index is not None:

            index = self._editing_feed_index

            old_feed = self.feeds[index]

            # Preserve existing check information when editing.
            feed_data["last_checked"] = old_feed.get(
                "last_checked"
            )

            feed_data["next_check"] = old_feed.get(
                "next_check",
                0
            )

            self.feeds[index] = feed_data

            self._editing_feed_index = None

            self.feed_save_button.configure(
                text="💾 Save Feed"
            )

            self.save_feeds_to_file()
            self.refresh_feed_table()
            self.clear_feed_editor()

            messagebox.showinfo(
                "Updated",
                "Feed automation updated!"
            )

            return

        # ---------------------------------------------------------------
        # NEW FEED
        # ---------------------------------------------------------------

        self.feeds.append(
            feed_data
        )

        self.save_feeds_to_file()
        self.refresh_feed_table()
        self.clear_feed_editor()

        messagebox.showinfo(
            "Saved",
            "Feed automation saved!"
        )

    def edit_feed(self):
        sel = self.feed_tree.selection()

        if not sel:
            messagebox.showwarning(
                "Warning",
                "Select a feed to edit."
            )
            return

        item = sel[0]

        index = self.feed_tree.index(
            item
        )

        if index < 0 or index >= len(self.feeds):
            return

        feed = self.feeds[index]

        # ---------------------------------------------------------------
        # Load feed into editor
        # ---------------------------------------------------------------

        self.feed_source.delete(
            0,
            tk.END
        )

        self.feed_source.insert(
            0,
            feed.get("source", "")
        )

        self.feed_to.delete(
            0,
            tk.END
        )

        self.feed_to.insert(
            0,
            feed.get("to", "")
        )

        self.feed_subject.delete(
            0,
            tk.END
        )

        self.feed_subject.insert(
            0,
            feed.get(
                "subject",
                "New item from feed: {title}"
            )
        )

        self.feed_text.delete(
            "1.0",
            tk.END
        )

        self.feed_text.insert(
            "1.0",
            feed.get(
                "text",
                "New item detected!\n\n"
                "Title: {title}\n"
                "Link: {link}\n"
                "Published: {published}"
            )
        )

        self.feed_interval.delete(
            0,
            tk.END
        )

        self.feed_interval.insert(
            0,
            str(
                feed.get(
                    "interval",
                    15
                )
            )
        )

        self._editing_feed_index = index

        self.feed_save_button.configure(
            text="💾 Update Feed"
        )

        self.notebook.select(
            self.tab_feed
        )

        self.set_status(
            f"Editing feed #{index + 1}"
        )

    def clear_feed_editor(self):
        self.feed_source.delete(
            0,
            tk.END
        )

        self.feed_to.delete(
            0,
            tk.END
        )

        self.feed_subject.delete(
            0,
            tk.END
        )

        self.feed_subject.insert(
            0,
            "New item from feed: {title}"
        )

        self.feed_text.delete(
            "1.0",
            tk.END
        )

        self.feed_text.insert(
            "1.0",
            "New item detected!\n\n"
            "Title: {title}\n"
            "Link: {link}\n"
            "Published: {published}"
        )

        self.feed_interval.delete(
            0,
            tk.END
        )

        self.feed_interval.insert(
            0,
            "15"
        )

        self._editing_feed_index = None

        self.feed_save_button.configure(
            text="💾 Save Feed"
        )

    # =========================================================================
    # FEED TABLE
    # =========================================================================

    def refresh_feed_table(self):
        for item in self.feed_tree.get_children():
            self.feed_tree.delete(
                item
            )

        for f in self.feeds:
            self.feed_tree.insert(
                "",
                tk.END,
                values=(
                    f["source"],
                    f["to"],
                    f.get(
                        "interval",
                        15
                    ),
                    f.get(
                        "last_checked"
                    ) or "Never",
                )
            )

    def delete_feed(self):
        sel = self.feed_tree.selection()

        if not sel:
            messagebox.showwarning(
                "Warning",
                "Select a feed to delete."
            )
            return

        if not messagebox.askyesno(
            "Delete Feed",
            "Are you sure you want to delete the selected feed?"
        ):
            return

        indices = sorted(
            [
                self.feed_tree.index(i)
                for i in sel
            ],
            reverse=True
        )

        for idx in indices:
            del self.feeds[idx]

        self.save_feeds_to_file()
        self.refresh_feed_table()

        if self._editing_feed_index is not None:
            self.clear_feed_editor()

    def save_feeds_to_file(self):
        try:
            os.makedirs(
                self.data_folder,
                exist_ok=True
            )

            with open(
                self.config_file,
                "w",
                encoding="utf-8"
            ) as f:
                json.dump(
                    self.feeds,
                    f,
                    indent=4
                )

        except Exception as ex:
            messagebox.showerror(
                "Error",
                f"Could not save feeds:\n{ex}"
            )

    # =========================================================================
    # RSS FETCHING
    # =========================================================================

    def fetch_rss_items(
        self,
        url: str
    ) -> list:

        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "EmailSuite/1.0"
            }
        )

        with urllib.request.urlopen(
            req,
            timeout=15
        ) as resp:
            data = resp.read()

        root = ET.fromstring(data)

        items = []

        tag = root.tag

        # ---------------------------------------------------------------
        # Atom
        # ---------------------------------------------------------------

        if "feed" in tag.lower():

            ns = (
                tag[1:tag.index("}")]
                if "}" in tag
                else ""
            )

            p = (
                f"{{{ns}}}"
                if ns
                else ""
            )

            for entry in root.findall(
                f"{p}entry"
            ):

                te = entry.find(
                    f"{p}title"
                )

                le = entry.find(
                    f"{p}link"
                )

                pe = entry.find(
                    f"{p}published"
                )

                if pe is None:
                    pe = entry.find(
                        f"{p}updated"
                    )

                se = entry.find(
                    f"{p}summary"
                )

                if se is None:
                    se = entry.find(
                        f"{p}content"
                    )

                ide = entry.find(
                    f"{p}id"
                )

                link = (
                    le.get(
                        "href",
                        le.text or ""
                    )
                    if le is not None
                    else ""
                )

                eid = (
                    ide.text
                    if ide is not None
                    else None
                ) or link

                items.append({
                    "id": eid,
                    "title": (
                        te.text
                        if te is not None
                        else "No title"
                    ),
                    "link": link,
                    "published": (
                        pe.text
                        if pe is not None
                        else ""
                    ),
                    "summary": (
                        se.text
                        if se is not None
                        else ""
                    ),
                })

        # ---------------------------------------------------------------
        # RSS 2.0
        # ---------------------------------------------------------------

        else:

            ch = root.find(
                "channel"
            )

            if ch is None:
                ch = root

            for item in ch.findall(
                "item"
            ):

                te = item.find(
                    "title"
                )

                le = item.find(
                    "link"
                )

                pe = item.find(
                    "pubDate"
                )

                de = item.find(
                    "description"
                )

                ge = item.find(
                    "guid"
                )

                link = (
                    le.text
                    if le is not None
                    else ""
                )

                eid = (
                    ge.text
                    if ge is not None
                    else None
                ) or link

                items.append({
                    "id": eid,
                    "title": (
                        te.text
                        if te is not None
                        else "No title"
                    ),
                    "link": link,
                    "published": (
                        pe.text
                        if pe is not None
                        else ""
                    ),
                    "summary": (
                        de.text
                        if de is not None
                        else ""
                    ),
                })

        return items

    # =========================================================================
    # FEED EMAIL
    # =========================================================================

    def send_feed_email(
        self,
        feed: dict,
        item: dict
    ) -> bool:

        def r(t):
            return (
                t.replace(
                    "{title}",
                    item.get(
                        "title",
                        ""
                    )
                )
                .replace(
                    "{link}",
                    item.get(
                        "link",
                        ""
                    )
                )
                .replace(
                    "{published}",
                    item.get(
                        "published",
                        ""
                    )
                )
                .replace(
                    "{summary}",
                    item.get(
                        "summary",
                        ""
                    )
                )
            )

        try:
            srv, from_addr = self._build_smtp()

            msg = EmailMessage()

            msg["From"] = from_addr
            msg["To"] = feed["to"]
            msg["Subject"] = r(
                feed.get(
                    "subject",
                    "New feed item: {title}"
                )
            )

            msg.set_content(
                r(
                    feed.get(
                        "text",
                        "New item: {link}"
                    )
                )
            )

            srv.send_message(
                msg
            )

            srv.quit()

            return True

        except Exception as ex:
            self.root.after(
                0,
                lambda: self.set_status(
                    f"Feed email failed: {ex}"
                )
            )

            return False

    # =========================================================================
    # FEED CHECKING
    # =========================================================================

    def check_single_feed(
        self,
        feed: dict
    ):

        url = feed["source"]

        try:
            items = self.fetch_rss_items(
                url
            )

        except Exception as ex:
            self.root.after(
                0,
                lambda: self.set_status(
                    f"Feed fetch error: {ex}"
                )
            )

            return

        key = url

        if key not in self.seen_entries:
            self.seen_entries[key] = [
                i["id"]
                for i in items
            ]

            self.save_seen_entries()

            return

        known = set(
            self.seen_entries[key]
        )

        new_ones = [
            i
            for i in items
            if i["id"] not in known
        ]

        changed = False

        for item in new_ones:

            sent = self.send_feed_email(
                feed,
                item
            )

            if sent:

                self.seen_entries[key].append(
                    item["id"]
                )

                changed = True

                self.root.after(
                    0,
                    lambda t=item["title"]:
                    self.set_status(
                        f"Feed email sent: {t[:50]}"
                    )
                )

            else:

                self.root.after(
                    0,
                    lambda t=item["title"]:
                    self.set_status(
                        f"Email failed; will retry: {t[:50]}"
                    )
                )

        if changed:
            self.save_seen_entries()

        feed["last_checked"] = (
            datetime.now().strftime(
                "%Y-%m-%d %H:%M"
            )
        )

        feed["next_check"] = (
            time.time()
            + feed.get(
                "interval",
                15
            ) * 60
        )

        self.save_feeds_to_file()

        self.root.after(
            0,
            self.refresh_feed_table
        )

    def manual_check_feeds(self):
        if not self.feeds:
            messagebox.showinfo(
                "No Feeds",
                "No feeds configured."
            )
            return

        self.set_status(
            "Checking all feeds…"
        )

        def _c():

            if not self.entry_smtp_host.get().strip():
                self.root.after(
                    0,
                    lambda: self.set_status(
                        "Set SMTP credentials first."
                    )
                )
                return

            for feed in self.feeds:
                self.check_single_feed(
                    feed
                )

            self.root.after(
                0,
                lambda: self.set_status(
                    "Feed check complete."
                )
            )

        threading.Thread(
            target=_c,
            daemon=True
        ).start()

    def background_feed_checker(self):

        while True:

            time.sleep(30)

            if not self.auto_check_enabled.get():
                continue

            if not self.entry_smtp_host.get().strip():
                continue

            now = time.time()

            for feed in list(
                self.feeds
            ):

                if now >= feed.get(
                    "next_check",
                    0
                ):

                    self.check_single_feed(
                        feed
                    )

    # =========================================================================
    # TAB 3 — REMOTE SERVER
    # =========================================================================

    def create_server_tab(self):

        cf = ttk.LabelFrame(
            self.tab_server,
            text=" Remote Server Connection ",
            padding=10
        )

        cf.pack(
            fill="x",
            padx=10,
            pady=5
        )

        ttk.Label(
            cf,
            text="Server URL:"
        ).grid(
            row=0,
            column=0,
            sticky="e",
            padx=4
        )

        self.srv_url = ttk.Entry(
            cf,
            width=40
        )

        self.srv_url.insert(
            0,
            self.server_cfg.get(
                "url",
                "http://your-server-ip:8642"
            )
        )

        self.srv_url.grid(
            row=0,
            column=1,
            sticky="w",
            padx=5,
            pady=3
        )

        ttk.Label(
            cf,
            text="API Key:"
        ).grid(
            row=0,
            column=2,
            sticky="e",
            padx=4
        )

        self.srv_key = ttk.Entry(
            cf,
            show="*",
            width=22
        )

        self.srv_key.insert(
            0,
            self.server_cfg.get(
                "api_key",
                ""
            )
        )

        self.srv_key.grid(
            row=0,
            column=3,
            sticky="w",
            padx=5,
            pady=3
        )

        btn_row = ttk.Frame(
            cf
        )

        btn_row.grid(
            row=1,
            column=0,
            columnspan=4,
            sticky="e",
            pady=5
        )

        ttk.Button(
            btn_row,
            text="💾 Save Connection",
            command=self.save_server_cfg
        ).pack(
            side="left",
            padx=3
        )

        ttk.Button(
            btn_row,
            text="🔌 Ping Server",
            command=self.ping_server
        ).pack(
            side="left",
            padx=3
        )

        # ---------------------------------------------------------------
        # Status
        # ---------------------------------------------------------------

        sf = ttk.LabelFrame(
            self.tab_server,
            text=" Server Status ",
            padding=10
        )

        sf.pack(
            fill="x",
            padx=10,
            pady=5
        )

        self.srv_status_var = tk.StringVar(
            value="Not connected"
        )

        ttk.Label(
            sf,
            textvariable=self.srv_status_var
        ).pack(
            anchor="w"
        )

        # ---------------------------------------------------------------
        # SMTP push
        # ---------------------------------------------------------------

        mf = ttk.LabelFrame(
            self.tab_server,
            text=" Push SMTP Config to Server ",
            padding=10
        )

        mf.pack(
            fill="x",
            padx=10,
            pady=5
        )

        ttk.Label(
            mf,
            text=(
                "Pushes the SMTP credentials from the 'Send Email' tab to the server.\n"
                "The server uses these to send feed notification emails independently."
            ),
            justify="left"
        ).pack(
            anchor="w",
            pady=(0, 6)
        )

        ttk.Button(
            mf,
            text="⬆ Push SMTP Config to Server",
            command=self.push_smtp_to_server,
            style="Accent.TButton"
        ).pack(
            anchor="w"
        )

        # ---------------------------------------------------------------
        # Feeds sync
        # ---------------------------------------------------------------

        feeds_frame = ttk.LabelFrame(
            self.tab_server,
            text=" Sync Feeds ",
            padding=10
        )

        feeds_frame.pack(
            fill="x",
            padx=10,
            pady=5
        )

        ttk.Label(
            feeds_frame,
            text=(
                "Push your local feeds list to the server (overwrites server copy),\n"
                "or pull the server's feeds list back to the local app."
            ),
            justify="left"
        ).pack(
            anchor="w",
            pady=(0, 6)
        )

        sync_btn_row = ttk.Frame(
            feeds_frame
        )

        sync_btn_row.pack(
            anchor="w"
        )

        ttk.Button(
            sync_btn_row,
            text="⬆ Push Feeds to Server",
            command=self.push_feeds_to_server,
            style="Accent.TButton"
        ).pack(
            side="left",
            padx=(0, 6)
        )

        ttk.Button(
            sync_btn_row,
            text="⬇ Pull Feeds from Server",
            command=self.pull_feeds_from_server
        ).pack(
            side="left",
            padx=(0, 6)
        )

        ttk.Button(
            sync_btn_row,
            text="▶ Trigger Check on Server",
            command=self.trigger_server_check
        ).pack(
            side="left"
        )

        # ---------------------------------------------------------------
        # Server log
        # ---------------------------------------------------------------

        lf = ttk.LabelFrame(
            self.tab_server,
            text=" Server Log ",
            padding=8
        )

        lf.pack(
            fill="both",
            expand=True,
            padx=10,
            pady=5
        )

        log_inner = ttk.Frame(
            lf
        )

        log_inner.pack(
            fill="both",
            expand=True
        )

        self.srv_log = tk.Text(
            log_inner,
            height=10,
            wrap="word",
            state="disabled",
            font=("Courier", 9),
            relief="flat"
        )

        self.srv_log.pack(
            side="left",
            fill="both",
            expand=True
        )

        sb = ttk.Scrollbar(
            log_inner,
            orient="vertical",
            command=self.srv_log.yview
        )

        sb.pack(
            side="right",
            fill="y"
        )

        self.srv_log.configure(
            yscrollcommand=sb.set
        )

        ttk.Button(
            self.tab_server,
            text="🔄 Refresh Log",
            command=self.fetch_server_log
        ).pack(
            anchor="e",
            padx=10,
            pady=(0, 6)
        )

    # =========================================================================
    # SERVER API
    # =========================================================================

    def _srv_request(
        self,
        method: str,
        endpoint: str,
        body=None
    ):

        url = (
            self.srv_url.get().strip().rstrip("/")
            + endpoint
        )

        key = self.srv_key.get().strip()

        data = (
            json.dumps(body).encode()
            if body is not None
            else None
        )

        req = urllib.request.Request(
            url,
            data=data,
            method=method
        )

        req.add_header(
            "X-API-Key",
            key
        )

        req.add_header(
            "Content-Type",
            "application/json"
        )

        with urllib.request.urlopen(
            req,
            timeout=10
        ) as resp:

            return json.loads(
                resp.read().decode()
            )

    def _srv_bg(
        self,
        method: str,
        endpoint: str,
        body=None,
        on_success=None,
        on_error=None
    ):

        def _run():

            try:
                result = self._srv_request(
                    method,
                    endpoint,
                    body
                )

                if on_success:
                    self.root.after(
                        0,
                        lambda: on_success(
                            result
                        )
                    )

            except Exception as ex:

                if on_error:
                    self.root.after(
                        0,
                        lambda: on_error(
                            ex
                        )
                    )

                else:
                    self.root.after(
                        0,
                        lambda: self.set_status(
                            f"Server error: {ex}"
                        )
                    )

        threading.Thread(
            target=_run,
            daemon=True
        ).start()

    def save_server_cfg(self):
        self.server_cfg = {
            "url": self.srv_url.get().strip(),
            "api_key": self.srv_key.get().strip(),
        }

        try:
            os.makedirs(
                self.data_folder,
                exist_ok=True
            )

            with open(
                self.server_file,
                "w",
                encoding="utf-8"
            ) as f:

                json.dump(
                    self.server_cfg,
                    f,
                    indent=4
                )

            self.set_status(
                "Server connection config saved."
            )

        except Exception as ex:
            messagebox.showerror(
                "Error",
                f"Could not save server config: {ex}"
            )

    def ping_server(self):
        self.set_status(
            "Pinging server…"
        )

        self.srv_status_var.set(
            "Connecting…"
        )

        def ok(data):

            lines = [
                f"✅  Connected  —  Feed Server v{data.get('version', '?')}",
                f"Uptime: {data.get('uptime', '?')}",
                f"Feeds on server: {data.get('feed_count', '?')}",
                f"Server time: {data.get('time', '?')}",
            ]

            summary = data.get(
                "feeds_summary",
                []
            )

            if summary:

                lines.append(
                    "\nFeed last-check times:"
                )

                for f in summary:

                    lines.append(
                        f"  • {f['source'][:50]}  →  {f['last_checked']}"
                    )

            self.srv_status_var.set(
                "\n".join(lines)
            )

            self.set_status(
                "Server ping OK."
            )

        def err(ex):

            self.srv_status_var.set(
                f"❌  Could not reach server:\n{ex}"
            )

            self.set_status(
                "Server ping failed."
            )

        self._srv_bg(
            "GET",
            "/status",
            on_success=ok,
            on_error=err
        )

    def push_smtp_to_server(self):

        host = self.entry_smtp_host.get().strip()
        port_str = self.entry_smtp_port.get().strip()
        user = self.entry_smtp_user.get().strip()
        password = self.entry_smtp_pass.get().strip()
        tls = self.smtp_tls_var.get()

        if not host or not user or not password:

            messagebox.showerror(
                "Error",
                "Fill in SMTP Server, From Email, and App Password in the 'Send Email' tab first."
            )

            return

        try:
            port = int(
                port_str
            )

        except ValueError:

            messagebox.showerror(
                "Error",
                "Port must be a number."
            )

            return

        payload = {
            "host": host,
            "port": port,
            "user": user,
            "password": password,
            "tls": tls
        }

        self.set_status(
            "Pushing SMTP config to server…"
        )

        def ok(_):

            messagebox.showinfo(
                "Success",
                "SMTP config pushed to server successfully."
            )

            self.set_status(
                "SMTP config pushed."
            )

        def err(ex):

            messagebox.showerror(
                "Push Failed",
                str(ex)
            )

            self.set_status(
                f"SMTP push failed: {ex}"
            )

        self._srv_bg(
            "POST",
            "/smtp",
            body=payload,
            on_success=ok,
            on_error=err
        )

    def push_feeds_to_server(self):

        if not self.feeds:

            messagebox.showwarning(
                "No Feeds",
                "No local feeds to push."
            )

            return

        if not messagebox.askyesno(
            "Confirm Push",
            f"Push {len(self.feeds)} local feed(s) to the server?\n"
            "This will overwrite the server's current feeds list."
        ):
            return

        self.set_status(
            "Pushing feeds to server…"
        )

        def ok(data):

            messagebox.showinfo(
                "Success",
                f"{data.get('count', '?')} feed(s) pushed to server successfully."
            )

            self.set_status(
                "Feeds pushed to server."
            )

        def err(ex):

            messagebox.showerror(
                "Push Failed",
                str(ex)
            )

            self.set_status(
                f"Feed push failed: {ex}"
            )

        self._srv_bg(
            "POST",
            "/feeds",
            body=self.feeds,
            on_success=ok,
            on_error=err
        )

    def pull_feeds_from_server(self):

        if not messagebox.askyesno(
            "Confirm Pull",
            "Pull feeds from the server?\n"
            "This will overwrite your local feeds list."
        ):
            return

        self.set_status(
            "Pulling feeds from server…"
        )

        def ok(data):

            if not isinstance(
                data,
                list
            ):

                messagebox.showerror(
                    "Error",
                    "Server returned unexpected data."
                )

                return

            self.feeds = data

            self.save_feeds_to_file()

            self.refresh_feed_table()

            messagebox.showinfo(
                "Success",
                f"{len(self.feeds)} feed(s) pulled from server."
            )

            self.set_status(
                "Feeds pulled from server."
            )

        def err(ex):

            messagebox.showerror(
                "Pull Failed",
                str(ex)
            )

            self.set_status(
                f"Feed pull failed: {ex}"
            )

        self._srv_bg(
            "GET",
            "/feeds",
            on_success=ok,
            on_error=err
        )

    def trigger_server_check(self):

        self.set_status(
            "Triggering feed check on server…"
        )

        def ok(data):

            self.set_status(
                f"Server check triggered: "
                f"{data.get('message', 'started')}"
            )

            messagebox.showinfo(
                "Check Triggered",
                "The server has started checking all feeds now."
            )

        def err(ex):

            messagebox.showerror(
                "Error",
                str(ex)
            )

            self.set_status(
                f"Trigger failed: {ex}"
            )

        self._srv_bg(
            "POST",
            "/check",
            on_success=ok,
            on_error=err
        )

    def fetch_server_log(self):

        self.set_status(
            "Fetching server log…"
        )

        def ok(data):

            lines = data.get(
                "logs",
                []
            )

            self.srv_log.configure(
                state="normal"
            )

            self.srv_log.delete(
                "1.0",
                tk.END
            )

            self.srv_log.insert(
                tk.END,
                "\n".join(lines)
            )

            self.srv_log.see(
                tk.END
            )

            self.srv_log.configure(
                state="disabled"
            )

            self.set_status(
                f"Server log fetched — {len(lines)} line(s)."
            )

        def err(ex):

            self.srv_log.configure(
                state="normal"
            )

            self.srv_log.delete(
                "1.0",
                tk.END
            )

            self.srv_log.insert(
                tk.END,
                f"Could not fetch log:\n{ex}"
            )

            self.srv_log.configure(
                state="disabled"
            )

            self.set_status(
                f"Log fetch failed: {ex}"
            )

        self._srv_bg(
            "GET",
            "/logs",
            on_success=ok,
            on_error=err
        )

    # =========================================================================
    # TAB 4 — INSTRUCTIONS
    # =========================================================================

    def create_instructions_tab(self):

        canvas = tk.Canvas(
            self.tab_instructions,
            highlightthickness=0
        )

        vsb = ttk.Scrollbar(
            self.tab_instructions,
            orient="vertical",
            command=canvas.yview
        )

        canvas.configure(
            yscrollcommand=vsb.set
        )

        vsb.pack(
            side="right",
            fill="y"
        )

        canvas.pack(
            side="left",
            fill="both",
            expand=True
        )

        inner = ttk.Frame(
            canvas
        )

        win = canvas.create_window(
            (0, 0),
            window=inner,
            anchor="nw"
        )

        def _on_frame(e):
            canvas.configure(
                scrollregion=canvas.bbox("all")
            )

        def _on_canvas(e):
            canvas.itemconfig(
                win,
                width=e.width
            )

        inner.bind(
            "<Configure>",
            _on_frame
        )

        canvas.bind(
            "<Configure>",
            _on_canvas
        )

        sections = [

            (
                "📧 Sending Emails",
                (
                    "1. Fill in SMTP Server, Port, From Email, and App Password in the Send Email tab.\n"
                    "   • Gmail:   smtp.gmail.com  port 587  TLS on  (use a Google App Password)\n"
                    "   • Outlook: smtp.office365.com  port 587  TLS on\n"
                    "2. Click 'Test Connection' to verify.\n"
                    "3. Fill To, optional CC/BCC, Subject, then compose your body.\n"
                    "4. Use the toolbar to format text, attach files, then click 'Send Email'."
                )
            ),

            (
                "📡 Local Feed Monitor",
                (
                    "Runs while the desktop app is open.\n"
                    "1. Enter an RSS/Atom URL, recipient email, subject, and body template.\n"
                    "2. Placeholders: {title} {link} {published} {summary}\n"
                    "3. Set check interval in minutes (e.g. 15).\n"
                    "4. Click 'Test Feed' to verify the URL, then 'Save Feed' to activate.\n"
                    "5. On first check, existing items are recorded — no emails sent.\n"
                    "   Only items that appear AFTER saving trigger emails.\n\n"
                    "EDITING FEEDS:\n"
                    "   Select a feed in the list and click 'Edit Selected Feed'.\n"
                    "   Change the settings and click 'Update Feed'."
                )
            ),

            (
                "⚙️ Application Settings",
                (
                    "Open the ⚙️ Settings tab (or File → Settings) to change application settings.\n\n"
                    "FILE SAVE LOCATION:\n"
                    "   Choose the folder where feeds_config.json,\n"
                    "   seen_entries.json, and server_config.json are saved.\n\n"
                    "THEME:\n"
                    "   System — follows your operating system where supported.\n"
                    "   Light  — light application appearance.\n"
                    "   Dark   — dark application appearance.\n\n"
                    "The selected settings are remembered when the application is restarted."
                )
            ),

            (
                "🖥 Remote Server (feed_server.py)",
                (
                    "Run feed_server.py on a VPS or always-on machine so feeds are checked\n"
                    "24/7 even when the desktop app is closed.\n\n"
                    "SETUP ON SERVER:\n"
                    "  1. Copy feed_server.py to your server.\n"
                    "  2. Install Python 3.8+  (no extra packages needed).\n"
                    "  3. Start it:\n"
                    "       python feed_server.py --api-key YOUR_SECRET_KEY --port 8642\n"
                    "  4. To keep it running permanently, use systemd, screen, or tmux:\n"
                    "       screen -S feedserver python feed_server.py --api-key KEY\n\n"
                    "CONFIGURE IN THE APP (Server tab):\n"
                    "  1. Enter the server URL  e.g.  http://123.45.67.89:8642\n"
                    "  2. Enter the same API key you used when starting the server.\n"
                    "  3. Click 'Save Connection', then 'Ping Server' to verify.\n"
                    "  4. Click 'Push SMTP Config' — sends your email credentials to the server.\n"
                    "  5. Click 'Push Feeds to Server' — uploads your feed list.\n"
                    "  6. The server will now check feeds independently and email on new items.\n\n"
                    "API ENDPOINTS (for advanced use):\n"
                    "  GET  /status   — uptime, version, feed summary\n"
                    "  GET  /feeds    — current feeds list\n"
                    "  POST /feeds    — replace feeds (JSON array)\n"
                    "  GET  /smtp     — current SMTP config (password masked)\n"
                    "  POST /smtp    — replace SMTP config\n"
                    "  GET  /logs     — last 500 log lines\n"
                    "  POST /check    — trigger immediate check\n"
                    "  All requests need header:  X-API-Key: YOUR_SECRET_KEY\n\n"
                    "FIREWALL:\n"
                    "  Open port 8642 (or whichever you chose) in your server firewall.\n"
                    "  For production, put nginx in front with HTTPS."
                )
            ),

            (
                "🔑 Gmail App Passwords",
                (
                    "Gmail requires an App Password (not your regular password):\n"
                    "1. Go to myaccount.google.com → Security.\n"
                    "2. Enable 2-Step Verification if not already on.\n"
                    "3. Search for 'App passwords', create one for Mail.\n"
                    "4. Paste the 16-character code into the App Password field."
                )
            ),
        ]

        for title, body in sections:

            frame = ttk.LabelFrame(
                inner,
                text=f"  {title}  ",
                padding=10
            )

            frame.pack(
                fill="x",
                padx=15,
                pady=6
            )

            ttk.Label(
                frame,
                text=body,
                justify="left",
                font=("Arial", 10),
                wraplength=840
            ).pack(
                anchor="w"
            )

    # =========================================================================
    # FOOTER
    # =========================================================================

    def create_footer(self):

        f = ttk.Frame(
            self.root,
            padding=4
        )

        f.pack(
            fill="x",
            side="bottom"
        )

        ttk.Label(
            f,
            textvariable=self.status_var,
            relief="sunken",
            anchor="w"
        ).pack(
            fill="x"
        )

    def set_status(
        self,
        msg: str
    ):

        ts = datetime.now().strftime(
            "%H:%M:%S"
        )

        self.status_var.set(
            f"[{ts}] {msg}"
        )

    # =========================================================================
    # PERSISTENCE
    # =========================================================================

    def load_feeds(self) -> list:

        if os.path.exists(
            self.config_file
        ):

            try:

                with open(
                    self.config_file,
                    "r",
                    encoding="utf-8"
                ) as f:

                    return json.load(f)

            except Exception:
                pass

        return []

    def load_seen_entries(self) -> dict:

        if os.path.exists(
            self.seen_file
        ):

            try:

                with open(
                    self.seen_file,
                    "r",
                    encoding="utf-8"
                ) as f:

                    return json.load(f)

            except Exception:
                pass

        return {}

    def save_seen_entries(self):

        try:

            os.makedirs(
                self.data_folder,
                exist_ok=True
            )

            with open(
                self.seen_file,
                "w",
                encoding="utf-8"
            ) as f:

                json.dump(
                    self.seen_entries,
                    f,
                    indent=4
                )

        except Exception:
            pass

    def load_server_cfg(self) -> dict:

        if os.path.exists(
            self.server_file
        ):

            try:

                with open(
                    self.server_file,
                    "r",
                    encoding="utf-8"
                ) as f:

                    return json.load(f)

            except Exception:
                pass

        return {}


# =========================================================================
# START APPLICATION
# =========================================================================

if __name__ == "__main__":
    root = tk.Tk()
    app = EmailApp(root)
    root.mainloop()
