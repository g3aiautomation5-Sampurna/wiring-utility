import cv2
import numpy as np
import os
import shutil
import tkinter as tk
from tkinter import filedialog, messagebox
try:
    from PIL import Image, ImageTk
except ImportError:
    os.system("pip install Pillow")
    from PIL import Image, ImageTk

from detect_origin import check_origin
from detect_origin2 import check_origin2_grommet, check_origin2_image

# Color Palette matching modern dark theme
BG_DARK = "#0d1117"
CARD_BG = "#161f30"
CARD_BORDER = "#253248"
ACCENT_BLUE = "#3b82f6"
ACCENT_HOVER = "#2563eb"
ACCENT_PURPLE = "#8b5cf6"
ACCENT_PURPLE_HOVER = "#7c3aed"
ACCENT_GREEN = "#10b981"
ACCENT_GREEN_HOVER = "#059669"
TEXT_WHITE = "#f8fafc"
TEXT_MUTED = "#94a3b8"
COLOR_PASS = "#10b981"
COLOR_FAIL = "#ef4444"

class ModernWiringDetectorApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Dual-View Wiring & Origin Inspection System")
        self.root.geometry("1360x880")
        self.root.minsize(1220, 780)
        self.root.configure(bg=BG_DARK)

        # Image state
        self.top_image_path = None
        self.top_wires_annotated = None
        self.top_origins_annotated = None
        self.orig2_image_path = None
        self.orig2_image_annotated = None

        self.current_view_tab = "top_wires" # "top_wires", "top_origins", or "orig2"
        self.img_tk = None

        # Camera state
        self.cap = None
        self.camera_active = False
        self.camera_target = None # "top" or "orig2"
        self.consecutive_failed_frames = 0

        # Build UI Layout
        self.create_widgets()

    def create_widgets(self):
        # Main container: Left (Preview & Actions), Right (Status Sidebar)
        main_frame = tk.Frame(self.root, bg=BG_DARK)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=16)

        # ----------------- LEFT COLUMN -----------------
        left_col = tk.Frame(main_frame, bg=BG_DARK)
        left_col.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 18))

        # Title & Subtitle
        title_lbl = tk.Label(
            left_col, 
            text="Dual-View Wiring & Origin Inspection", 
            font=("Segoe UI", 18, "bold"), 
            fg=TEXT_WHITE, 
            bg=BG_DARK
        )
        title_lbl.pack(anchor=tk.W)

        subtitle_lbl = tk.Label(
            left_col, 
            text="Upload or capture Top View (Image 1) & Origin 2 View (Image 2) for combined verification", 
            font=("Segoe UI", 10), 
            fg=TEXT_MUTED, 
            bg=BG_DARK
        )
        subtitle_lbl.pack(anchor=tk.W, pady=(2, 8))

        # View Switcher Tabs (3 Tabs: Top Wires, Top Origins, Origin 2 Grommet)
        tab_row = tk.Frame(left_col, bg=BG_DARK)
        tab_row.pack(fill=tk.X, pady=(0, 6))

        self.tab_top_wires_btn = tk.Button(
            tab_row,
            text="🔌  1. Top View: Wires",
            command=lambda: self.switch_view_tab("top_wires"),
            font=("Segoe UI", 9, "bold"),
            bg=CARD_BG,
            fg=ACCENT_BLUE,
            activebackground=CARD_BORDER,
            activeforeground=TEXT_WHITE,
            relief=tk.FLAT,
            padx=12,
            pady=5,
            cursor="hand2",
            bd=1,
            highlightthickness=1,
            highlightbackground=ACCENT_BLUE
        )
        self.tab_top_wires_btn.pack(side=tk.LEFT, padx=(0, 6))

        self.tab_top_origins_btn = tk.Button(
            tab_row,
            text="📍  1. Top View: Origins",
            command=lambda: self.switch_view_tab("top_origins"),
            font=("Segoe UI", 9, "bold"),
            bg=CARD_BG,
            fg=TEXT_MUTED,
            activebackground=CARD_BORDER,
            activeforeground=TEXT_WHITE,
            relief=tk.FLAT,
            padx=12,
            pady=5,
            cursor="hand2",
            bd=0
        )
        self.tab_top_origins_btn.pack(side=tk.LEFT, padx=(0, 6))

        self.tab_orig2_btn = tk.Button(
            tab_row,
            text="🔍  2. Origin 2: Grommet",
            command=lambda: self.switch_view_tab("orig2"),
            font=("Segoe UI", 9, "bold"),
            bg=CARD_BG,
            fg=TEXT_MUTED,
            activebackground=CARD_BORDER,
            activeforeground=TEXT_WHITE,
            relief=tk.FLAT,
            padx=12,
            pady=5,
            cursor="hand2",
            bd=0
        )
        self.tab_orig2_btn.pack(side=tk.LEFT)

        # Image Display Card
        self.image_card = tk.Frame(left_col, bg=CARD_BG, highlightbackground=CARD_BORDER, highlightthickness=1)
        self.image_card.pack(fill=tk.BOTH, expand=True)

        self.canvas_w, self.canvas_h = 800, 460
        self.canvas = tk.Canvas(
            self.image_card, 
            width=self.canvas_w, 
            height=self.canvas_h, 
            bg=CARD_BG, 
            highlightthickness=0,
            cursor="hand2"
        )
        self.canvas.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)
        self.canvas.bind("<Button-1>", lambda e: self.browse_current_view())

        # Placeholder text & icon on Canvas
        self.draw_placeholder()

        # Action Buttons Section
        btn_grid = tk.Frame(left_col, bg=BG_DARK)
        btn_grid.pack(fill=tk.X, pady=(10, 0))

        # Row 1: Image 1 Controls (Top View)
        row1 = tk.Frame(btn_grid, bg=BG_DARK)
        row1.pack(fill=tk.X, pady=(0, 6))

        r1_lbl = tk.Label(row1, text="1. Top View:", font=("Segoe UI", 10, "bold"), fg=TEXT_WHITE, bg=BG_DARK, width=12, anchor="w")
        r1_lbl.pack(side=tk.LEFT)

        self.browse_top_btn = tk.Button(
            row1,
            text="📁  Browse Top View",
            command=self.browse_top_image,
            font=("Segoe UI", 9, "bold"),
            bg=ACCENT_BLUE,
            fg=TEXT_WHITE,
            activebackground=ACCENT_HOVER,
            activeforeground=TEXT_WHITE,
            relief=tk.FLAT,
            padx=10,
            pady=6,
            cursor="hand2",
            bd=0
        )
        self.browse_top_btn.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 6))

        self.cam_top_btn = tk.Button(
            row1,
            text="📷  Camera Top View",
            command=lambda: self.start_camera_for("top"),
            font=("Segoe UI", 9, "bold"),
            bg="#059669",
            fg=TEXT_WHITE,
            activebackground="#047857",
            activeforeground=TEXT_WHITE,
            relief=tk.FLAT,
            padx=10,
            pady=6,
            cursor="hand2",
            bd=0
        )
        self.cam_top_btn.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 6))

        self.detect_top_origins_btn = tk.Button(
            row1,
            text="📍  Detect Origins",
            command=self.run_top_origins_only,
            font=("Segoe UI", 9, "bold"),
            bg=ACCENT_PURPLE,
            fg=TEXT_WHITE,
            activebackground=ACCENT_PURPLE_HOVER,
            activeforeground=TEXT_WHITE,
            relief=tk.FLAT,
            padx=10,
            pady=6,
            cursor="hand2",
            bd=0
        )
        self.detect_top_origins_btn.pack(side=tk.LEFT, fill=tk.X, expand=True)

        # Row 2: Image 2 Controls (Origin 2 Dedicated)
        row2 = tk.Frame(btn_grid, bg=BG_DARK)
        row2.pack(fill=tk.X, pady=(0, 8))

        r2_lbl = tk.Label(row2, text="2. Origin 2:", font=("Segoe UI", 10, "bold"), fg=TEXT_WHITE, bg=BG_DARK, width=12, anchor="w")
        r2_lbl.pack(side=tk.LEFT)

        self.browse_orig2_btn = tk.Button(
            row2,
            text="📁  Browse Origin 2",
            command=self.browse_orig2_image,
            font=("Segoe UI", 9, "bold"),
            bg=ACCENT_PURPLE,
            fg=TEXT_WHITE,
            activebackground=ACCENT_PURPLE_HOVER,
            activeforeground=TEXT_WHITE,
            relief=tk.FLAT,
            padx=10,
            pady=6,
            cursor="hand2",
            bd=0
        )
        self.browse_orig2_btn.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 6))

        self.cam_orig2_btn = tk.Button(
            row2,
            text="📷  Camera Origin 2",
            command=lambda: self.start_camera_for("orig2"),
            font=("Segoe UI", 9, "bold"),
            bg="#059669",
            fg=TEXT_WHITE,
            activebackground="#047857",
            activeforeground=TEXT_WHITE,
            relief=tk.FLAT,
            padx=10,
            pady=6,
            cursor="hand2",
            bd=0
        )
        self.cam_orig2_btn.pack(side=tk.LEFT, fill=tk.X, expand=True)

        # Row 3: Run Combined Inspection Button
        self.run_all_btn = tk.Button(
            btn_grid,
            text="🔍  Run Combined Dual-View Inspection",
            command=self.run_combined_detection,
            font=("Segoe UI", 11, "bold"),
            bg="#1e293b",
            fg=TEXT_MUTED,
            activebackground="#334155",
            activeforeground=TEXT_WHITE,
            relief=tk.FLAT,
            padx=12,
            pady=8,
            cursor="hand2",
            bd=0
        )
        self.run_all_btn.pack(fill=tk.X)

        # ----------------- RIGHT COLUMN (SIDEBAR) -----------------
        right_col = tk.Frame(main_frame, bg=BG_DARK, width=430)
        right_col.pack(side=tk.RIGHT, fill=tk.BOTH, padx=(0, 0))
        right_col.pack_propagate(False)

        # Header
        sb_title = tk.Label(
            right_col,
            text="Inspection Results",
            font=("Segoe UI", 15, "bold"),
            fg=TEXT_WHITE,
            bg=BG_DARK
        )
        sb_title.pack(anchor=tk.W, pady=(0, 6))

        # Card 1: Combined Overall Status Banner
        self.status_card = tk.Frame(right_col, bg=CARD_BG, highlightbackground=CARD_BORDER, highlightthickness=1)
        self.status_card.pack(fill=tk.X, pady=(0, 6))

        self.status_dash = tk.Label(self.status_card, text="——", font=("Segoe UI", 15, "bold"), fg=TEXT_MUTED, bg=CARD_BG)
        self.status_dash.pack(pady=(6, 2))

        self.status_text = tk.Label(self.status_card, text="Awaiting images...", font=("Segoe UI", 11, "bold"), fg=TEXT_MUTED, bg=CARD_BG)
        self.status_text.pack(pady=(0, 6))

        # Card 2: Dedicated Origin 2 Grommet Verification
        orig2_card = tk.Frame(right_col, bg=CARD_BG, highlightbackground=CARD_BORDER, highlightthickness=1)
        orig2_card.pack(fill=tk.X, pady=(0, 6), ipady=2)

        orig2_hdr = tk.Label(orig2_card, text="🎯 Origin 2 Dedicated Check (Image 2)", font=("Segoe UI", 10, "bold"), fg=TEXT_WHITE, bg=CARD_BG)
        orig2_hdr.pack(anchor=tk.W, padx=12, pady=(4, 2))

        self.orig2_grommet_var = tk.BooleanVar(value=False)
        o2_frame = tk.Frame(orig2_card, bg=CARD_BG)
        o2_frame.pack(fill=tk.X, padx=12, pady=1)
        self.orig2_grommet_chk = tk.Checkbutton(
            o2_frame, text="Origin 2 Grommet (Red in front / on Right)", 
            variable=self.orig2_grommet_var, state=tk.DISABLED,
            font=("Segoe UI", 9, "bold"), fg=TEXT_WHITE, bg=CARD_BG, selectcolor=CARD_BG,
            activebackground=CARD_BG, activeforeground=TEXT_WHITE, disabledforeground=TEXT_MUTED
        )
        self.orig2_grommet_chk.pack(side=tk.LEFT)
        self.orig2_grommet_badge = tk.Label(o2_frame, text="—", font=("Segoe UI", 9, "bold"), fg=TEXT_MUTED, bg=CARD_BG)
        self.orig2_grommet_badge.pack(side=tk.RIGHT)

        # Card 3: Wire Origins Verification (Top View)
        origins_card = tk.Frame(right_col, bg=CARD_BG, highlightbackground=CARD_BORDER, highlightthickness=1)
        origins_card.pack(fill=tk.X, pady=(0, 6), ipady=2)

        origins_hdr = tk.Label(origins_card, text="📍 Top View Origins Verification (Image 1)", font=("Segoe UI", 10, "bold"), fg=TEXT_WHITE, bg=CARD_BG)
        origins_hdr.pack(anchor=tk.W, padx=12, pady=(4, 2))

        # Origin Row 1: Bottom Left
        self.orig_bl_var = tk.BooleanVar(value=False)
        obl_frame = tk.Frame(origins_card, bg=CARD_BG)
        obl_frame.pack(fill=tk.X, padx=12, pady=1)
        self.orig_bl_chk = tk.Checkbutton(
            obl_frame, text="Origin 1: Bottom Left (Black Above Red)", 
            variable=self.orig_bl_var, state=tk.DISABLED,
            font=("Segoe UI", 9), fg=TEXT_WHITE, bg=CARD_BG, selectcolor=CARD_BG,
            activebackground=CARD_BG, activeforeground=TEXT_WHITE, disabledforeground=TEXT_MUTED
        )
        self.orig_bl_chk.pack(side=tk.LEFT)
        self.orig_bl_badge = tk.Label(obl_frame, text="—", font=("Segoe UI", 9, "bold"), fg=TEXT_MUTED, bg=CARD_BG)
        self.orig_bl_badge.pack(side=tk.RIGHT)

        # Origin Row 2: Upper Middle
        self.orig_um_var = tk.BooleanVar(value=False)
        oum_frame = tk.Frame(origins_card, bg=CARD_BG)
        oum_frame.pack(fill=tk.X, padx=12, pady=1)
        self.orig_um_chk = tk.Checkbutton(
            oum_frame, text="Origin 2: Upper Middle (Red Mid, Black Right)", 
            variable=self.orig_um_var, state=tk.DISABLED,
            font=("Segoe UI", 9), fg=TEXT_WHITE, bg=CARD_BG, selectcolor=CARD_BG,
            activebackground=CARD_BG, activeforeground=TEXT_WHITE, disabledforeground=TEXT_MUTED
        )
        self.orig_um_chk.pack(side=tk.LEFT)
        self.orig_um_badge = tk.Label(oum_frame, text="—", font=("Segoe UI", 9, "bold"), fg=TEXT_MUTED, bg=CARD_BG)
        self.orig_um_badge.pack(side=tk.RIGHT)

        # Origin Row 3: Bottom Right
        self.orig_br_var = tk.BooleanVar(value=False)
        obr_frame = tk.Frame(origins_card, bg=CARD_BG)
        obr_frame.pack(fill=tk.X, padx=12, pady=1)
        self.orig_br_chk = tk.Checkbutton(
            obr_frame, text="Origin 3: Bottom Right (Black Below Red)", 
            variable=self.orig_br_var, state=tk.DISABLED,
            font=("Segoe UI", 9), fg=TEXT_WHITE, bg=CARD_BG, selectcolor=CARD_BG,
            activebackground=CARD_BG, activeforeground=TEXT_WHITE, disabledforeground=TEXT_MUTED
        )
        self.orig_br_chk.pack(side=tk.LEFT)
        self.orig_br_badge = tk.Label(obr_frame, text="—", font=("Segoe UI", 9, "bold"), fg=TEXT_MUTED, bg=CARD_BG)
        self.orig_br_badge.pack(side=tk.RIGHT)

        # Card 4: Wiring Path Verification (Top View)
        cases_card = tk.Frame(right_col, bg=CARD_BG, highlightbackground=CARD_BORDER, highlightthickness=1)
        cases_card.pack(fill=tk.X, pady=(0, 6), ipady=2)

        cases_hdr = tk.Label(cases_card, text="🔌 Top View Wiring Paths (Image 1)", font=("Segoe UI", 10, "bold"), fg=TEXT_WHITE, bg=CARD_BG)
        cases_hdr.pack(anchor=tk.W, padx=12, pady=(4, 2))

        # Checkbox Row 1: Case 1
        self.c1_var = tk.BooleanVar(value=False)
        c1_frame = tk.Frame(cases_card, bg=CARD_BG)
        c1_frame.pack(fill=tk.X, padx=12, pady=1)
        self.c1_chk = tk.Checkbutton(
            c1_frame, text="Case 1: Bottom Left (Red on Left)", 
            variable=self.c1_var, state=tk.DISABLED,
            font=("Segoe UI", 9), fg=TEXT_WHITE, bg=CARD_BG, selectcolor=CARD_BG,
            activebackground=CARD_BG, activeforeground=TEXT_WHITE, disabledforeground=TEXT_MUTED
        )
        self.c1_chk.pack(side=tk.LEFT)
        self.c1_badge = tk.Label(c1_frame, text="—", font=("Segoe UI", 9, "bold"), fg=TEXT_MUTED, bg=CARD_BG)
        self.c1_badge.pack(side=tk.RIGHT)

        # Checkbox Row 2: Case 2
        self.c2_var = tk.BooleanVar(value=False)
        c2_frame = tk.Frame(cases_card, bg=CARD_BG)
        c2_frame.pack(fill=tk.X, padx=12, pady=1)
        self.c2_chk = tk.Checkbutton(
            c2_frame, text="Case 2: Upper Middle (Red on Right)", 
            variable=self.c2_var, state=tk.DISABLED,
            font=("Segoe UI", 9), fg=TEXT_WHITE, bg=CARD_BG, selectcolor=CARD_BG,
            activebackground=CARD_BG, activeforeground=TEXT_WHITE, disabledforeground=TEXT_MUTED
        )
        self.c2_chk.pack(side=tk.LEFT)
        self.c2_badge = tk.Label(c2_frame, text="—", font=("Segoe UI", 9, "bold"), fg=TEXT_MUTED, bg=CARD_BG)
        self.c2_badge.pack(side=tk.RIGHT)

        # Checkbox Row 3: Case 3
        self.c3_var = tk.BooleanVar(value=False)
        c3_frame = tk.Frame(cases_card, bg=CARD_BG)
        c3_frame.pack(fill=tk.X, padx=12, pady=1)
        self.c3_chk = tk.Checkbutton(
            c3_frame, text="Case 3: Bottom Right (Red on Left)", 
            variable=self.c3_var, state=tk.DISABLED,
            font=("Segoe UI", 9), fg=TEXT_WHITE, bg=CARD_BG, selectcolor=CARD_BG,
            activebackground=CARD_BG, activeforeground=TEXT_WHITE, disabledforeground=TEXT_MUTED
        )
        self.c3_chk.pack(side=tk.LEFT)
        self.c3_badge = tk.Label(c3_frame, text="—", font=("Segoe UI", 9, "bold"), fg=TEXT_MUTED, bg=CARD_BG)
        self.c3_badge.pack(side=tk.RIGHT)

        # Card 5: Diagnostic Notes & Rules
        zones_card = tk.Frame(right_col, bg=CARD_BG, highlightbackground=CARD_BORDER, highlightthickness=1)
        zones_card.pack(fill=tk.BOTH, expand=True, pady=(0, 4))

        zones_hdr = tk.Label(zones_card, text="📋 Diagnostic Notes & Rules", font=("Segoe UI", 10, "bold"), fg=TEXT_WHITE, bg=CARD_BG)
        zones_hdr.pack(anchor=tk.W, padx=12, pady=(4, 2))

        # Text widget with scrollbar for notes
        notes_frame = tk.Frame(zones_card, bg=CARD_BG)
        notes_frame.pack(fill=tk.BOTH, expand=True, padx=8, pady=(0, 6))

        self.notes_text = tk.Text(
            notes_frame,
            font=("Segoe UI", 8),
            bg=CARD_BG,
            fg=TEXT_WHITE,
            wrap=tk.WORD,
            bd=0,
            highlightthickness=0,
            height=9
        )
        self.notes_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.notes_text.insert(tk.END, "Please provide Image 1 (Top View) and Image 2 (Origin 2).")
        self.notes_text.config(state=tk.DISABLED)

        # Footer status bar
        self.footer_lbl = tk.Label(right_col, text="Ready. Browse or capture images to begin.", font=("Segoe UI", 8), fg=TEXT_MUTED, bg=BG_DARK)
        self.footer_lbl.pack(anchor=tk.W, pady=(2, 0))

    def set_notes_content(self, text_content):
        self.notes_text.config(state=tk.NORMAL)
        self.notes_text.delete("1.0", tk.END)
        self.notes_text.insert(tk.END, text_content)
        self.notes_text.config(state=tk.DISABLED)

    def draw_placeholder(self):
        self.canvas.delete("all")
        w, h = self.canvas_w, self.canvas_h
        if self.current_view_tab == "top_wires":
            name = "Top View: Wires (Image 1)"
        elif self.current_view_tab == "top_origins":
            name = "Top View: Origins (Image 1)"
        else:
            name = "Origin 2: Grommet (Image 2)"

        self.canvas.create_text(
            w / 2, h / 2 - 15,
            text=f"Click to select {name}",
            font=("Segoe UI", 14),
            fill=TEXT_MUTED
        )
        self.canvas.create_text(
            w / 2, h / 2 + 20,
            text="+",
            font=("Segoe UI", 28),
            fill=TEXT_MUTED
        )

    def switch_view_tab(self, tab):
        self.current_view_tab = tab
        
        # Reset tab styles
        self.tab_top_wires_btn.config(fg=TEXT_MUTED, highlightthickness=0)
        self.tab_top_origins_btn.config(fg=TEXT_MUTED, highlightthickness=0)
        self.tab_orig2_btn.config(fg=TEXT_MUTED, highlightthickness=0)

        if tab == "top_wires":
            self.tab_top_wires_btn.config(fg=ACCENT_BLUE, highlightthickness=1, highlightbackground=ACCENT_BLUE)
            if self.top_wires_annotated is not None:
                self.render_image_on_canvas(self.top_wires_annotated)
            elif self.top_image_path:
                img = cv2.imread(self.top_image_path)
                if img is not None:
                    self.render_image_on_canvas(img)
            else:
                self.draw_placeholder()
        elif tab == "top_origins":
            self.tab_top_origins_btn.config(fg=ACCENT_PURPLE, highlightthickness=1, highlightbackground=ACCENT_PURPLE)
            if self.top_origins_annotated is not None:
                self.render_image_on_canvas(self.top_origins_annotated)
            elif self.top_image_path:
                img = cv2.imread(self.top_image_path)
                if img is not None:
                    self.render_image_on_canvas(img)
            else:
                self.draw_placeholder()
        else:
            self.tab_orig2_btn.config(fg=ACCENT_PURPLE, highlightthickness=1, highlightbackground=ACCENT_PURPLE)
            if self.orig2_image_annotated is not None:
                self.render_image_on_canvas(self.orig2_image_annotated)
            elif self.orig2_image_path:
                img = cv2.imread(self.orig2_image_path)
                if img is not None:
                    self.render_image_on_canvas(img)
            else:
                self.draw_placeholder()

    def browse_current_view(self):
        if self.current_view_tab in ["top_wires", "top_origins"]:
            self.browse_top_image()
        else:
            self.browse_orig2_image()

    def browse_top_image(self):
        if self.camera_active:
            self.stop_camera()
        file_path = filedialog.askopenfilename(
            title="Select Top View Image (Image 1)",
            filetypes=[("Image files", "*.jpg *.jpeg *.png *.bmp *.webp")]
        )
        if not file_path:
            return
            
        self.top_image_path = file_path
        self.tab_top_wires_btn.config(text=f"🔌 Top: Wires ({os.path.basename(file_path)[:12]})")
        self.tab_top_origins_btn.config(text=f"📍 Top: Origins ({os.path.basename(file_path)[:12]})")
        self.switch_view_tab("top_wires")
        self.update_run_button_state()
        if self.orig2_image_path:
            self.run_combined_detection()
        else:
            self.run_top_inspection()

    def browse_orig2_image(self):
        if self.camera_active:
            self.stop_camera()
        file_path = filedialog.askopenfilename(
            title="Select Origin 2 Image (Image 2)",
            filetypes=[("Image files", "*.jpg *.jpeg *.png *.bmp *.webp")]
        )
        if not file_path:
            return
            
        self.orig2_image_path = file_path
        self.tab_orig2_btn.config(text=f"🔍 Origin 2 ({os.path.basename(file_path)[:12]})")
        self.switch_view_tab("orig2")
        self.update_run_button_state()
        if self.top_image_path:
            self.run_combined_detection()
        else:
            self.run_orig2_inspection()

    def update_run_button_state(self):
        if self.top_image_path and self.orig2_image_path:
            self.run_all_btn.config(bg=ACCENT_BLUE, fg=TEXT_WHITE)
        elif self.top_image_path or self.orig2_image_path:
            self.run_all_btn.config(bg="#1e293b", fg=TEXT_WHITE)
        else:
            self.run_all_btn.config(bg="#1e293b", fg=TEXT_MUTED)

    def start_camera_for(self, target):
        if self.camera_active:
            self.stop_camera()
            if self.camera_target == target:
                return

        self.camera_target = target
        self.switch_view_tab("top_wires" if target == "top" else "orig2")

        self.cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
        if not self.cap.isOpened():
            self.cap = cv2.VideoCapture(0)
            if not self.cap.isOpened():
                messagebox.showerror("Error", "Could not open camera. Ensure no other application is using it.")
                return

        self.camera_active = True
        btn_to_update = self.cam_top_btn if target == "top" else self.cam_orig2_btn
        btn_to_update.config(text="⏹ Stop Camera", bg="#ef4444", activebackground="#dc2626")
        
        self.run_all_btn.config(text="📸 Capture Image", command=self.capture_current_frame, bg=ACCENT_GREEN, fg=TEXT_WHITE)
        self.status_text.config(text=f"Align {target.upper()} view in camera...")
        self.consecutive_failed_frames = 0
        self.update_camera_frame()

    def stop_camera(self):
        self.camera_active = False
        if self.cap:
            self.cap.release()
            self.cap = None
        self.cam_top_btn.config(text="📷  Camera Top View", bg="#059669", activebackground="#047857")
        self.cam_orig2_btn.config(text="📷  Camera Origin 2", bg="#059669", activebackground="#047857")
        self.run_all_btn.config(text="🔍  Run Combined Dual-View Inspection", command=self.run_combined_detection)
        self.update_run_button_state()

    def draw_dotted_rect(self, img, pt1, pt2, color, dot_spacing=8, label=""):
        x1, y1 = pt1
        x2, y2 = pt2
        for x in range(x1, x2, dot_spacing):
            cv2.circle(img, (x, y1), 2, color, -1)
            cv2.circle(img, (x, y2), 2, color, -1)
        for y in range(y1, y2, dot_spacing):
            cv2.circle(img, (x1, y), 2, color, -1)
            cv2.circle(img, (x2, y), 2, color, -1)
            
        if label:
            (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.45, 1)
            cv2.rectangle(img, (x1, y1 - th - 6), (x1 + tw + 6, y1), (15, 20, 30), -1)
            cv2.putText(img, label, (x1 + 3, y1 - 3), cv2.FONT_HERSHEY_SIMPLEX, 0.45, color, 1, cv2.LINE_AA)

    def draw_labeled_box(self, img, pt1, pt2, is_pass, label):
        """Draws bounding box with clear colored badge banner."""
        x1, y1 = pt1
        x2, y2 = pt2
        border_color = (0, 220, 0) if is_pass else (0, 0, 240)
        cv2.rectangle(img, (x1, y1), (x2, y2), border_color, 3)

        badge_text = f" {label}: {'PASS' if is_pass else 'FAIL'} "
        badge_bg = (0, 180, 0) if is_pass else (0, 0, 220)
        
        badge_y = y1 - 8 if y1 > 25 else y1 + 24
        text_size = cv2.getTextSize(badge_text, cv2.FONT_HERSHEY_SIMPLEX, 0.52, 2)[0]
        cv2.rectangle(img, (x1, badge_y - 18), (x1 + text_size[0], badge_y + 4), badge_bg, -1)
        cv2.putText(img, badge_text, (x1, badge_y), cv2.FONT_HERSHEY_SIMPLEX, 0.52, (255, 255, 255), 2)

    def update_camera_frame(self):
        if not self.camera_active or not self.cap:
            return
            
        ret, frame = self.cap.read()
        if ret and frame is not None:
            self.consecutive_failed_frames = 0
            frame = cv2.resize(frame, (1024, 576))
            
            if self.camera_target == "top":
                # 1. Main PCB Box Outline
                self.draw_dotted_rect(frame, (250, 10), (780, 570), (0, 255, 255), dot_spacing=12, label="PCB Box")

                # 2. Wire Origin Positions
                self.draw_dotted_rect(frame, (470, 15), (690, 100), (0, 255, 255), dot_spacing=8, label="Top Middle (Coils)")
                self.draw_dotted_rect(frame, (370, 410), (470, 565), (0, 255, 255), dot_spacing=8, label="Bottom Left (Origin 1)")
                self.draw_dotted_rect(frame, (620, 435), (720, 570), (0, 255, 255), dot_spacing=8, label="Bottom Right (Origin 3)")

                # 3. Wire Path Zones
                self.draw_dotted_rect(frame, (310, 260), (470, 555), (255, 140, 0), dot_spacing=10, label="Wires (Case 1: BL)")
                self.draw_dotted_rect(frame, (470, 0), (710, 200), (255, 140, 0), dot_spacing=10, label="Wires (Case 2: UM)")
                self.draw_dotted_rect(frame, (600, 385), (730, 565), (255, 140, 0), dot_spacing=10, label="Wires (Case 3: BR)")

            else:
                # Origin 2 Grommet Alignment
                self.draw_dotted_rect(frame, (80, 260), (280, 490), (0, 255, 255), dot_spacing=10, label="Origin 2 Grommet")

            self.render_image_on_canvas(frame)
            self.last_frame = frame
        else:
            self.consecutive_failed_frames += 1
            if self.consecutive_failed_frames > 30:
                self.stop_camera()
                messagebox.showerror("Camera Error", "Lost connection to the camera.")
                return
            
        self.root.after(30, self.update_camera_frame)

    def capture_current_frame(self):
        if not self.camera_active or not hasattr(self, 'last_frame'):
            return
            
        target = self.camera_target
        temp_path = os.path.join(os.getcwd(), f"temp_{target}_camera.jpg")
        cv2.imwrite(temp_path, self.last_frame)
        
        self.stop_camera()

        if target == "top":
            self.top_image_path = temp_path
            self.tab_top_wires_btn.config(text="🔌 Top: Wires (Captured)")
            self.tab_top_origins_btn.config(text="📍 Top: Origins (Captured)")
            self.switch_view_tab("top_wires")
        else:
            self.orig2_image_path = temp_path
            self.tab_orig2_btn.config(text="🔍 Origin 2 (Captured)")
            self.switch_view_tab("orig2")

        self.update_run_button_state()
        if self.top_image_path and self.orig2_image_path:
            self.run_combined_detection()
        elif target == "top":
            self.run_top_inspection()
        else:
            self.run_orig2_inspection()

    def run_top_origins_only(self):
        """Dedicated action to run origin detection on Top View and switch view to Origins."""
        if not self.top_image_path:
            messagebox.showinfo("Top View Image Required", "Please select or capture Image 1 (Top View) first.")
            return
        self.run_top_inspection()
        self.switch_view_tab("top_origins")

    def run_top_inspection(self):
        if not self.top_image_path or not os.path.exists(self.top_image_path):
            return
        img_raw = cv2.imread(self.top_image_path)
        if img_raw is None:
            return

        img_top = cv2.resize(img_raw, (1024, 576))
        hsv_top = cv2.cvtColor(img_top, cv2.COLOR_BGR2HSV)

        # 1. ORIGINS EVALUATION & ANNOTATION
        origin_pass, top_failed_origins, origin_details = check_origin(img_top)
        obl_pass = origin_details.get('case1_bl', {}).get('pass', False)
        oum_pass = origin_details.get('case2_um', {}).get('pass', False)
        obr_pass = origin_details.get('case3_br', {}).get('pass', False)

        img_origins = img_top.copy()
        self.draw_labeled_box(img_origins, (370, 410), (470, 565), obl_pass, "Origin 1 (BL)")
        self.draw_labeled_box(img_origins, (470, 15), (690, 100), oum_pass, "Origin 2 (UM)")
        self.draw_labeled_box(img_origins, (620, 435), (720, 570), obr_pass, "Origin 3 (BR)")
        self.top_origins_annotated = img_origins

        # 2. WIRES EVALUATION & ANNOTATION
        mask_r = cv2.inRange(hsv_top, (0, 100, 50), (12, 255, 255)) + cv2.inRange(hsv_top, (160, 100, 50), (180, 255, 255))
        mask_b = cv2.inRange(hsv_top, (0, 0, 0), (180, 255, 45))

        # Case 1 (BL)
        bl_r = mask_r[270:330, 310:470]
        bl_b = mask_b[270:330, 310:470]
        xr_bl = np.where(bl_r > 0)[1]
        xb_bl = np.where(bl_b > 0)[1]
        rx_bl = np.median(xr_bl) if len(xr_bl) else -1
        bx_bl = np.median(xb_bl) if len(xb_bl) else -1
        bl_wire_pass = bool(rx_bl < bx_bl) if (rx_bl != -1 and bx_bl != -1) else True

        # Case 2 (UM) - Detect only origins; if origins pass, wiring passes
        um_wire_pass = bool(oum_pass)

        # Case 3 (BR)
        br_r = mask_r[410:455, 600:730]
        br_b = mask_b[410:455, 600:730]
        xr_br = np.where(br_r > 0)[1]
        xb_br = np.where(br_b > 0)[1]
        rx_br = np.median(xr_br) if len(xr_br) else -1
        bx_br = np.median(xb_br) if len(xb_br) else -1
        br_wire_pass = bool(rx_br < bx_br) if (rx_br != -1 and bx_br != -1) else True

        img_wires = img_top.copy()
        self.draw_labeled_box(img_wires, (310, 260), (470, 555), bl_wire_pass, "Case 1 (BL)")
        self.draw_labeled_box(img_wires, (470, 0), (710, 200), um_wire_pass, "Case 2 (UM)")
        self.draw_labeled_box(img_wires, (600, 385), (730, 565), br_wire_pass, "Case 3 (BR)")
        self.top_wires_annotated = img_wires

        # Update Checkboxes
        self.orig_bl_var.set(obl_pass)
        self.orig_bl_chk.config(fg=COLOR_PASS if obl_pass else COLOR_FAIL)
        self.orig_bl_badge.config(text="✔ PASS" if obl_pass else "✖ FAIL", fg=COLOR_PASS if obl_pass else COLOR_FAIL)

        self.orig_um_var.set(oum_pass)
        self.orig_um_chk.config(fg=COLOR_PASS if oum_pass else COLOR_FAIL)
        self.orig_um_badge.config(text="✔ PASS" if oum_pass else "✖ FAIL", fg=COLOR_PASS if oum_pass else COLOR_FAIL)

        self.orig_br_var.set(obr_pass)
        self.orig_br_chk.config(fg=COLOR_PASS if obr_pass else COLOR_FAIL)
        self.orig_br_badge.config(text="✔ PASS" if obr_pass else "✖ FAIL", fg=COLOR_PASS if obr_pass else COLOR_FAIL)

        self.c1_var.set(bl_wire_pass)
        self.c1_chk.config(fg=COLOR_PASS if bl_wire_pass else COLOR_FAIL)
        self.c1_badge.config(text="✔ PASS" if bl_wire_pass else "✖ FAIL", fg=COLOR_PASS if bl_wire_pass else COLOR_FAIL)

        self.c2_var.set(um_wire_pass)
        self.c2_chk.config(fg=COLOR_PASS if um_wire_pass else COLOR_FAIL)
        self.c2_badge.config(text="✔ PASS" if um_wire_pass else "✖ FAIL", fg=COLOR_PASS if um_wire_pass else COLOR_FAIL)

        self.c3_var.set(br_wire_pass)
        self.c3_chk.config(fg=COLOR_PASS if br_wire_pass else COLOR_FAIL)
        self.c3_badge.config(text="✔ PASS" if br_wire_pass else "✖ FAIL", fg=COLOR_PASS if br_wire_pass else COLOR_FAIL)

        if self.current_view_tab == "top_wires":
            self.render_image_on_canvas(self.top_wires_annotated)
        elif self.current_view_tab == "top_origins":
            self.render_image_on_canvas(self.top_origins_annotated)

    def run_orig2_inspection(self):
        if not self.orig2_image_path or not os.path.exists(self.orig2_image_path):
            return
        is_p, img_o2, failed_o2, details_o2 = check_origin2_image(self.orig2_image_path, save_result=False)
        self.orig2_image_annotated = img_o2

        self.orig2_grommet_var.set(is_p)
        self.orig2_grommet_chk.config(fg=COLOR_PASS if is_p else COLOR_FAIL)
        self.orig2_grommet_badge.config(text="✔ PASS" if is_p else "✖ FAIL", fg=COLOR_PASS if is_p else COLOR_FAIL)

        if self.current_view_tab == "orig2":
            self.render_image_on_canvas(self.orig2_image_annotated)

    def run_combined_detection(self):
        """Runs Dual-View Inspection with explicit rule conventions and labeled overlays."""
        if not self.top_image_path and not self.orig2_image_path:
            messagebox.showinfo("Images Required", "Please upload or capture Image 1 (Top View) and Image 2 (Origin 2).")
            return

        self.run_top_inspection()
        self.run_orig2_inspection()

        # Check values
        obl_pass = self.orig_bl_var.get()
        oum_pass = self.orig_um_var.get()
        obr_pass = self.orig_br_var.get()
        bl_wire_pass = self.c1_var.get()
        um_wire_pass = self.c2_var.get()
        br_wire_pass = self.c3_var.get()
        orig2_pass = self.orig2_grommet_var.get()

        # Override rule: Origin 2 passes if dedicated Origin 2 image passes OR top view check passed
        effective_origin2_pass = oum_pass or orig2_pass
        self.orig_um_var.set(effective_origin2_pass)
        self.orig_um_chk.config(fg=COLOR_PASS if effective_origin2_pass else COLOR_FAIL)
        self.orig_um_badge.config(
            text="✔ PASS (Img 2)" if (orig2_pass and not oum_pass) else ("✔ PASS" if effective_origin2_pass else "✖ FAIL"), 
            fg=COLOR_PASS if effective_origin2_pass else COLOR_FAIL
        )

        # Upper Middle wiring follows origin verification
        um_wire_pass = effective_origin2_pass
        self.c2_var.set(um_wire_pass)
        self.c2_chk.config(fg=COLOR_PASS if um_wire_pass else COLOR_FAIL)
        self.c2_badge.config(text="✔ PASS" if um_wire_pass else "✖ FAIL", fg=COLOR_PASS if um_wire_pass else COLOR_FAIL)
        if self.top_wires_annotated is not None:
            self.draw_labeled_box(self.top_wires_annotated, (470, 0), (710, 200), um_wire_pass, "Case 2 (UM)")

        wire_all_pass = bl_wire_pass and um_wire_pass and br_wire_pass
        origins_all_pass = obl_pass and obr_pass and effective_origin2_pass
        combined_pass = wire_all_pass and origins_all_pass

        # Build Comprehensive Diagnostic Notes with Rule Conventions
        notes_lines = []
        notes_lines.append("═════════════ DIAGNOSTIC BREAKDOWN & RULES ═════════════\n")

        # 1. Wire Paths
        notes_lines.append("🔌 WIRE ROUTING PATHS (Top View):")
        notes_lines.append(f" • Case 1 (Bottom Left):  {'✔ PASS' if bl_wire_pass else '✖ FAIL (Red is on Right)'}")
        notes_lines.append("   👉 Correct Rule: Red wire MUST be on LEFT of Black wire.\n")

        notes_lines.append(f" • Case 2 (Upper Middle): {'✔ PASS' if um_wire_pass else '✖ FAIL (Origin Failed)'}")
        notes_lines.append("   👉 Correct Rule: Red wire MUST originate at Middle Coil (wiring verified via origin).\n")

        notes_lines.append(f" • Case 3 (Bottom Right): {'✔ PASS' if br_wire_pass else '✖ FAIL (Red is on Right)'}")
        notes_lines.append("   👉 Correct Rule: Red wire MUST be on LEFT of Black wire.\n")

        # 2. Origins
        notes_lines.append("📍 WIRE ORIGIN CONNECTIONS:")
        notes_lines.append(f" • Origin 1 (Bottom Left):  {'✔ PASS' if obl_pass else '✖ FAIL'}")
        notes_lines.append("   👉 Correct Rule: Black wire enters Upper Socket, Red enters Lower Socket (Black above Red).\n")

        notes_lines.append(f" • Origin 2 (Top Middle):   {'✔ PASS' if effective_origin2_pass else '✖ FAIL'}" + 
                           (" [Verified via Image 2 Dedicated View]" if (orig2_pass and not oum_pass) else ""))
        notes_lines.append("   👉 Correct Rule: Red wire connects to Middle Coil, Black wire to Rightmost Coil.\n")

        notes_lines.append(f" • Origin 3 (Bottom Right): {'✔ PASS' if obr_pass else '✖ FAIL'}")
        notes_lines.append("   👉 Correct Rule: Red wire origin MUST be ABOVE Black wire origin.\n")

        # 3. Dedicated Origin 2
        notes_lines.append("🎯 DEDICATED ORIGIN 2 GROMMET (Image 2):")
        notes_lines.append(f" • Grommet Wire Order:     {'✔ PASS' if orig2_pass else '✖ FAIL (Red is on Left/Behind)'}")
        notes_lines.append("   👉 Correct Rule: Red wire MUST ALWAYS be in front / on RIGHT of Black wire.\n")

        self.set_notes_content("\n".join(notes_lines))

        # Update Active Canvas View
        if self.current_view_tab == "top_wires" and self.top_wires_annotated is not None:
            self.render_image_on_canvas(self.top_wires_annotated)
        elif self.current_view_tab == "top_origins" and self.top_origins_annotated is not None:
            self.render_image_on_canvas(self.top_origins_annotated)
        elif self.current_view_tab == "orig2" and self.orig2_image_annotated is not None:
            self.render_image_on_canvas(self.orig2_image_annotated)

        # Status Banner
        target_folder = "Pass" if combined_pass else "Fail"
        result_dir = os.path.join(os.getcwd(), "Result", target_folder)
        os.makedirs(result_dir, exist_ok=True)

        # Save Selec PMS JSON output (PASS or FAIL)
        try:
            import json
            from pms_json_manager import build_report_store, save_payload_to_file
            verdict = "PASS" if combined_pass else "FAIL"
            _, pms_payload = build_report_store(
                device_serial_no=None,
                wire_origin_pass=origins_all_pass,
                vi_test_pass=combined_pass
            )
            save_payload_to_file(pms_payload, f"{verdict}_report_gui")
            with open(os.path.join(result_dir, f"{verdict}_pms_report.json"), "w", encoding="utf-8") as f:
                json.dump(pms_payload, f, indent=4)
            with open(os.path.join(result_dir, "latest_pms_report.json"), "w", encoding="utf-8") as f:
                json.dump(pms_payload, f, indent=4)
        except Exception as e:
            print(f"[PMS GUI] Warning: Could not generate PMS report: {e}")

        if combined_pass:
            self.status_dash.config(text="✔", fg=COLOR_PASS)
            self.status_text.config(text="COMBINED RESULT: PASS", fg=COLOR_PASS)
        else:
            self.status_dash.config(text="✖", fg=COLOR_FAIL)
            self.status_text.config(text="COMBINED RESULT: FAIL", fg=COLOR_FAIL)

        self.footer_lbl.config(text=f"Inspection complete. Results & PMS JSON saved to Result/")

    def render_image_on_canvas(self, img):
        card_w = self.canvas.winfo_width() or self.canvas_w
        card_h = self.canvas.winfo_height() or self.canvas_h
        img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        img_resized = cv2.resize(img_rgb, (card_w, card_h))
        img_pil = Image.fromarray(img_resized)
        self.img_tk = ImageTk.PhotoImage(image=img_pil)

        self.canvas.delete("all")
        self.canvas.create_image(0, 0, anchor=tk.NW, image=self.img_tk)

if __name__ == "__main__":
    root = tk.Tk()
    app = ModernWiringDetectorApp(root)
    root.mainloop()
