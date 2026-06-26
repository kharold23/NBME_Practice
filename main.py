import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import customtkinter as ctk
import tkinter.font as tkfont
import re
import os
import sys
import math
import fitz  # PyMuPDF
import pytesseract
from PIL import Image, ImageTk
import cv2
import numpy as np
try:
    from reportlab.lib.pagesizes import letter
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib import colors
    REPORTLAB_AVAILABLE = True
except ImportError:
    REPORTLAB_AVAILABLE = False

# Configure CustomTkinter default global styling
ctk.set_appearance_mode("light")
ctk.set_default_color_theme("blue")

class Question:
    def __init__(self, root, text, options, image=None, inverted=False, instructions=""):
        self.text = text
        self.options = options
        self.selected_option = tk.StringVar(master=root, value="")
        self.image = image
        self.inverted = inverted
        self.instructions = instructions
        
        # Track visual state
        self.highlights_top = []
        self.highlights_bottom = []
        self.crossed_out_options = set()

class NBMESimulatorApp:
    def __init__(self, root):
        self.root = root
        self.root.title("NBME Self-Assessment Simulator")
        self.root.geometry("1024x768")
        self.root.configure(fg_color="white")
        
        self.questions = []
        self.current_index = 0
        self.marked_questions = set()
        
        self.review_mode = False
        self.time_left = 0
        self.timer_running = False
        self.timer_job = None
        
        self.review_window = None
        self.full_img_win = None
        
        # New State for Lab Values
        self.lab_values_open = False
        self.lab_values_images = []
        self.lab_resize_job = None      
        self.last_canvas_width = 0      
        
        self.color_blue = "#0a2240"
        self.color_white = "#ffffff"
        self.color_black = "#000000"
        
        self.base_font = tkfont.Font(family="Arial", size=14)
        self.strike_font = tkfont.Font(family="Arial", size=14, overstrike=1)
        
        self.create_widgets()
        self.update_ui()

    def save_current_state(self):
        """Saves highlights and strike-outs to the current question object before navigating away."""
        if not self.questions: return
        q = self.questions[self.current_index]

        # Save Text Highlights (Convert Tkinter index objects to strings)
        q.highlights_top = [str(idx) for idx in self.text_question.tag_ranges("highlight")]
        q.highlights_bottom = [str(idx) for idx in self.text_question_bottom.tag_ranges("highlight")]

        # Save Radiobutton Strike-outs
        q.crossed_out_options.clear()
        for i, rb in enumerate(self.radio_buttons):
            if getattr(rb, 'is_crossed_out', False):
                q.crossed_out_options.add(i)

    def create_widgets(self):
        # --- Top Bar ---
        self.top_frame = tk.Frame(self.root, bg=self.color_blue, height=60)
        self.top_frame.pack(side=tk.TOP, fill=tk.X)
        self.top_frame.pack_propagate(False)
        
        self.left_top_frame = tk.Frame(self.top_frame, bg=self.color_blue)
        self.left_top_frame.pack(side=tk.LEFT, padx=10, pady=5)
        
        self.lbl_item_count = tk.Label(self.left_top_frame, text="Exam Section : Item 0 of 0", 
                                       bg=self.color_blue, fg=self.color_white, font=("Arial", 10, "bold"))
        self.lbl_item_count.pack(anchor="w")
        
        self.mark_var = tk.BooleanVar()
        self.chk_mark = tk.Checkbutton(self.left_top_frame, text="Mark", variable=self.mark_var, 
                                       command=self.toggle_mark, bg=self.color_blue, fg=self.color_white, 
                                       selectcolor=self.color_blue, activebackground=self.color_blue, activeforeground=self.color_white, font=("Arial", 10, "bold"))
        self.chk_mark.pack(anchor="w")

        self.center_top_frame = tk.Frame(self.top_frame, bg=self.color_blue)
        self.center_top_frame.pack(side=tk.LEFT, expand=True)
        
        self.lbl_title_center = tk.Label(self.center_top_frame, text="National Board of Medical Examiners", 
                 bg=self.color_blue, fg=self.color_white, font=("Arial", 10))
        self.lbl_title_center.pack()
        
        self.lbl_subtitle_center = tk.Label(self.center_top_frame, text="PRACTICE Self-Assessment", 
                 bg=self.color_blue, fg=self.color_white, font=("Arial", 10, "bold"))
        self.lbl_subtitle_center.pack()

        self.right_top_frame = tk.Frame(self.top_frame, bg=self.color_blue)
        self.right_top_frame.pack(side=tk.RIGHT, padx=10, pady=5)
        
        tk.Label(self.right_top_frame, text="Time Remaining:", 
                 bg=self.color_blue, fg=self.color_white, font=("Arial", 10)).pack(anchor="e")
        self.lbl_time_remaining = tk.Label(self.right_top_frame, text="0 hr 00 min 00 sec", 
                 bg=self.color_blue, fg=self.color_white, font=("Arial", 10, "bold"))
        self.lbl_time_remaining.pack(anchor="e")

        # --- Main Content Area (Strictly Bounded Scrollable) ---
        self.main_container = tk.Frame(self.root, bg=self.color_white)
        self.main_container.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        self.main_canvas = tk.Canvas(self.main_container, bg=self.color_white, highlightthickness=0, yscrollincrement="15")
        self.main_scrollbar = ttk.Scrollbar(self.main_container, orient="vertical", command=self.main_canvas.yview)

        self.scrollable_main_frame = tk.Frame(self.main_canvas, bg=self.color_white)
        self.canvas_window = self.main_canvas.create_window((0, 0), window=self.scrollable_main_frame, anchor="nw")
        
        self.scrollable_main_frame.bind("<Configure>", self._on_scrollable_frame_configure)
        self.main_canvas.bind('<Configure>', self._on_main_canvas_configure)
        self.main_canvas.configure(yscrollcommand=self.main_scrollbar.set)

        self.main_canvas.pack(side="left", fill="both", expand=True, padx=(40, 0), pady=30)
        self.main_scrollbar.pack(side="right", fill="y")
        
        self._bind_mousewheel(self.main_canvas)
        self._bind_mousewheel(self.scrollable_main_frame)

        # --- Grid Layout Configuration ---
        self.content_frame = tk.Frame(self.scrollable_main_frame, bg=self.color_white)
        self.content_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True)
        self._bind_mousewheel(self.content_frame)
        
        self.content_frame.columnconfigure(0, weight=80, uniform="panels")
        self.content_frame.columnconfigure(1, weight=20, uniform="panels")
        self.content_frame.rowconfigure(0, weight=1) 
        
        self.left_panel = tk.Frame(self.content_frame, bg=self.color_white)
        self.left_panel.grid(row=0, column=0, sticky="nsew")
        self._bind_mousewheel(self.left_panel)
        
        self.left_panel.bind("<Configure>", self.on_left_panel_configure)
        
        self.right_panel = tk.Frame(self.content_frame, bg=self.color_white)
        self.right_panel.grid(row=0, column=1, sticky="nsew", padx=(20, 20))
        self._bind_mousewheel(self.right_panel)
        
        # Upper Text Box 
        self.text_question = tk.Text(self.left_panel, bg=self.color_white, fg=self.color_black, font=("Arial", 14), 
                                     wrap=tk.WORD, borderwidth=0, highlightthickness=0)
        self.text_question.tag_config("highlight", background="yellow")
        self.text_question.bind("<ButtonRelease-1>", self.apply_highlight)
        self.text_question.tag_bind("highlight", "<Button-1>", self.remove_highlight)
        self._bind_mousewheel(self.text_question)
        
        # Options Frame
        self.options_frame = tk.Frame(self.left_panel, bg=self.color_white)
        self._bind_mousewheel(self.options_frame)
        self.radio_buttons = []

        # Lower Text Box (Used for inverted questions)
        self.text_question_bottom = tk.Text(self.left_panel, bg=self.color_white, fg=self.color_black, font=("Arial", 14), 
                                            wrap=tk.WORD, borderwidth=0, highlightthickness=0)
        self.text_question_bottom.tag_config("highlight", background="yellow")
        self.text_question_bottom.bind("<ButtonRelease-1>", self.apply_highlight)
        self.text_question_bottom.tag_bind("highlight", "<Button-1>", self.remove_highlight)
        self._bind_mousewheel(self.text_question_bottom)

        tk.Label(self.right_panel, text="Reference Image\n(Click to Enlarge)", bg=self.color_white, fg="gray", font=("Arial", 10)).pack(side=tk.TOP, pady=(0, 5))
        self.lbl_preview = tk.Label(self.right_panel, bg=self.color_white, cursor="hand2", relief=tk.RIDGE, bd=2)
        self.lbl_preview.pack(side=tk.TOP)
        self.lbl_preview.bind("<Button-1>", self.show_full_image)
        self._bind_mousewheel(self.lbl_preview)

        # --- Lab Values Embed Container ---
        self.lab_values_container = tk.Frame(self.right_panel, bg=self.color_white)
        
        tk.Label(self.lab_values_container, text="Lab Values Reference", bg=self.color_blue, fg=self.color_white, font=("Arial", 10, "bold")).pack(side=tk.TOP, fill=tk.X)
        
        self.lab_tree_frame = tk.Frame(self.lab_values_container, bg=self.color_white)
        self.lab_tree_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        # Style the Treeview
        style = ttk.Style()
        style.configure("Treeview", font=("Arial", 10), rowheight=25)
        style.configure("Treeview.Heading", font=("Arial", 10, "bold"))

        # Setup Table Columns
        columns = ("Lab Test", "Reference Range", "SI Interval")
        self.lab_tree = ttk.Treeview(self.lab_tree_frame, columns=columns, show="headings", selectmode="none")
        
        self.lab_tree.heading("Lab Test", text="Lab Test")
        self.lab_tree.heading("Reference Range", text="Reference Range")
        self.lab_tree.heading("SI Interval", text="SI Interval")
        
        self.lab_tree.column("Lab Test", width=100, anchor=tk.W)
        self.lab_tree.column("Reference Range", width=120, anchor=tk.W)
        self.lab_tree.column("SI Interval", width=120, anchor=tk.W)

        # Setup Scrollbar
        self.lab_tree_scrollbar = ttk.Scrollbar(self.lab_tree_frame, orient=tk.VERTICAL, command=self.lab_tree.yview)
        self.lab_tree.configure(yscrollcommand=self.lab_tree_scrollbar.set)

        self.lab_tree_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.lab_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        header_font = tkfont.Font(family="Arial", size=10, weight="bold", underline=True)
        self.lab_tree.tag_configure("header_row", font=header_font)

        # Insert Filler Data
        lab_values_data = [
            ("General Chemistry", "", ""),
            ("Sodium (Na+)", "136-146 mEq/L", "136-146 mmol/L"), 
            ("Potassium (K+)", "3.5-5.0 mEq/L", "3.5-5.0 mmol/L"), 
            ("Chloride (Cl-)", "95-105 mEq/L", "95-105 mmol/L"), 
            ("Bicarbonate (HCO3-)", "22-28 mEq/L", "22-28 mmol/L"), 
            ("Urea nitrogen", "7-18 mg/dL", "2.5-6.4 mmol/L"), 
            ("Creatinine", "0.6-1.2 mg/dL", "53-106 µmol/L"), 
            ("Glucose (Fasting)", "70-100 mg/dL", "3.8-5.6 mmol/L"), 
            ("Glucose (Random)", "<140 mg/dL", "<7.77 mmol/L"), 
            ("Calcium", "8.4-10.2 mg/dL", "2.1-2.6 mmol/L"), 
            ("Magnesium (Mg2+)", "1.5-2.0 mg/dL", "0.75-1.0 mmol/L"), 
            ("Phosphorus (inorganic)", "3.0-4.5 mg/dL", "1.0-1.5 mmol/L"), 
            
            ("", "", ""),
            ("Hepatic", "", ""),
            ("ALT", "10-40 U/L", "10-40 U/L"), 
            ("AST", "12-38 U/L", "12-38 U/L"), 
            ("Alkaline phosphatase", "25-100 U/L", "25-100 U/L"), 
            ("Bilirubin, total", "0.1-1.0 mg/dL", "2-17 µmol/L"), 
            ("Bilirubin, direct", "0.0-0.3 mg/dL", "0-5 µmol/L"), 
            ("Proteins, total", "6.0-7.8 g/dL", "60-78 g/L"), 
            ("Albumin", "3.5-5.5 g/dL", "35-55 g/L"), 
            ("Globulin", "2.3-3.5 g/dL", "23-35 g/L"), 
            
            ("", "", ""),
            ("Other, serum", "", ""),
            ("Amylase", "25-125 U/L", "25-125 U/L"), 
            ("Lipase", "13-60 U/L", "13-60 U/L"), 
            ("Creatinine clearance", "Male: 97-137 mL/min", "Female: 88-128 mL/min"), 
            ("", "Female: 88-128 mL/min", "Female: 88-128 mL/min"), 
            ("Creatine kinase", "Male: 25-90 U/L", "Male: 25-90 U/L"), 
            ("", "Female: 10-70 U/L", "Female: 10-70 U/L"), 
            ("Lactate dehydrogenase", "45-200 U/L", "45-200 U/L"), 
            ("Osmolality", "275-295 mOsmol/kg H2O", "275-295 mOsmol/kg H2O"), 
            ("Troponin I", "≤0.04 ng/mL", "≤0.04 µg/L"), 
            ("Uric acid", "3.0-8.2 mg/dL", "0.18-0.48 mmol/L"), 

            ("", "", ""),
            ("Lipids", "", ""),
            ("Cholesterol, Total (Normal)", "<200 mg/dL", "<5.2 mmol/L"), 
            ("Cholesterol, Total (High)", ">240 mg/dL", ">6.2 mmol/L"), 
            ("Cholesterol, HDL", "40-60 mg/dL", "1.0-1.6 mmol/L"), 
            ("Cholesterol, LDL", "<160 mg/dL", "<4.2 mmol/L"), 
            ("Triglycerides (Normal)", "<150 mg/dL", "<1.70 mmol/L"), 
            ("Triglycerides (Borderline)", "151-199 mg/dL", "1.71-2.25 mmol/L"), 

            ("", "", ""),
            ("Iron Studies", "", ""),
            ("Ferritin", "Male: 20-250 ng/mL", "Male: 20-250 µg/L"), 
            ("", "Female: 10-120 ng/mL", "Female: 10-120 µg/L"), 
            ("Iron", "Male: 65-175 µg/dL", "Male: 11.6-31.3 µmol/L"), 
            ("", "Female: 50-170 µg/dL", "Female: 9.0-30.4 μmol/L"), 
            ("Total iron-binding capacity", "250-400 µg/dL", "44.8-71.6 µmol/L"), 
            ("Transferrin", "200-360 mg/dL", "2.0-3.6 g/L"), 

            ("", "", ""),
            ("Endocrine", "", ""),
            ("FSH", "Male: 4-25 mIU/mL", "Male: 4-25 IU/L"), 
            ("", "Female: premenopause 4-30 mIU/mL", "Female: premenopause 4-30 IU/L"), 
            ("", "midcycle peak 10-90 mIU/mL", "midcycle peak 10-90 IU/L"), 
            ("", "postmenopause 40-250 mIU/mL", "postmenopause 40-250 IU/L"), 
            ("Luteinizing hormone", "Male: 6-23 mIU/mL", "Male: 6-23 IU/L"), 
            ("", "Female: follicular phase 5-30 mIU/mL", "Female: follicular phase 5-30 IU/L"), 
            ("", "midcycle 75-150 mIU/mL", "midcycle 75-150 IU/L"), 
            ("", "postmenopause 30-200 mIU/mL", "postmenopause 30-200 IU/L"), 
            ("Growth hormone", "Fasting: <5 ng/mL", "Fasting: <5 µg/L"), 
            ("", "Provocative stimuli: >7 ng/mL", "Provocative stimuli: >7 µg/L"), 
            ("Prolactin (hPRL)", "Male: <17 ng/mL", "Male: <17 µg/L"), 
            ("", "Female: <25 ng/mL", "Female: <25 µg/L"), 
            ("Cortisol (0800 h)", "5-23 µg/dL", "138-635 nmol/L"), 
            ("Cortisol (1600 h)", "3-15 µg/dL", "82-413 nmol/L"), 
            ("Cortisol (2000 h)", "<50% of 0800 h", "Fraction of 0800 h: <0.50"), 
            ("TSH", "0.4-4.0 μU/mL", "0.4-4.0 mIU/L"), 
            ("Triiodothyronine (T3) (RIA)", "100-200 ng/dL", "1.5-3.1 nmol/L"), 
            ("T3 resin uptake", "25%-35%", "0.25-0.35"), 
            ("Thyroxine (T4)", "5-12 µg/dL", "64-155 nmol/L"), 
            ("Free T4", "0.9-1.7 ng/dL", "12.0-21.9 pmol/L"), 
            ("123I uptake", "8%-30% of dose/24 h", "0.08-0.30/24 h"), 
            ("Intact PTH", "10-60 pg/mL", "10-60 ng/L"), 
            ("17-Hydroxycorticosteroids", "Male: 3.0-10.0 mg/24 h", "Male: 8.2-27.6 µmol/24 h"), 
            ("", "Female: 2.0-8.0 mg/24 h", "Female: 5.5-22.0 µmol/24 h"), 
            ("17-Ketosteroids, total", "Male: 8-20 mg/24 h", "Male: 28-70 μmol/24 h"), 
            ("", "Female: 6-15 mg/24 h", "Female: 21-52 µmol/24 h"), 

            ("", "", ""),
            ("Immunoglobulins", "", ""),
            ("IgA", "76-390 mg/dL", "0.76-3.90 g/L"), 
            ("IgE", "0-380 IU/mL", "0-380 KIU/L"), 
            ("IgG", "650-1500 mg/dL", "6.5-15.0 g/L"), 
            ("IgM", "50-300 mg/dL", "0.5-3.0 g/L"), 

            ("", "", ""),
            ("Gases, Arterial Blood", "", ""),
            ("PO2", "75-105 mm Hg", "10.0-14.0 kPa"), 
            ("PCO2", "33-45 mm Hg", "4.4-5.9 kPa"), 
            ("pH", "7.35-7.45", "[H+] 36-44 nmol/L"), 

            ("", "", ""),
            ("Cerebrospinal Fluid", "", ""),
            ("Cell count", "0-5/mm³", "0-5 x 10^6/L"), 
            ("Chloride", "118-132 mEq/L", "118-132 mmol/L"), 
            ("Gamma globulin", "3%-12% total proteins", "0.03-0.12"), 
            ("Glucose", "40-70 mg/dL", "2.2-3.9 mmol/L"), 
            ("Pressure", "70-180 mm H2O", "70-180 mm H2O"), 
            ("Proteins, total", "<40 mg/dL", "<0.40 g/L"), 

            ("", "", ""),
            ("Hematologic", "", ""),
            ("Hematocrit", "Male: 41%-53%", "Male: 0.41-0.53"), 
            ("", "Female: 36%-46%", "Female: 0.36-0.46"), 
            ("Hemoglobin, blood", "Male: 13.5-17.5 g/dL", "Male: 135-175 g/L"), 
            ("", "Female: 12.0-16.0 g/dL", "Female: 120-160 g/L"), 
            ("MCH", "25-35 pg/cell", "0.39-0.54 fmol/cell"), 
            ("MCHC", "31%-36% Hb/cell", "4.8-5.6 mmol Hb/L"), 
            ("MCV", "80-100 μm³", "80-100 fL"), 
            ("Volume, Plasma", "Male: 25-43 mL/kg", "Male: 0.025-0.043 L/kg"), 
            ("", "Female: 28-45 mL/kg", "Female: 0.028-0.045 L/kg"), 
            ("Volume, Red cell", "Male: 20-36 mL/kg", "Male: 0.020-0.036 L/kg"), 
            ("", "Female: 19-31 mL/kg", "Female: 0.019-0.031 L/kg"), 
            ("Leukocyte count (WBC)", "4500-11,000/mm³", "4.5-11.0 x 10^9/L"), 
            ("Neutrophils, segmented", "54%-62%", "0.54-0.62"), 
            ("Neutrophils, bands", "3%-5%", "0.03-0.05"), 
            ("Lymphocytes", "25%-33%", "0.25-0.33"), 
            ("Monocytes", "3%-7%", "0.03-0.07"), 
            ("Eosinophils", "1%-3%", "0.01-0.03"), 
            ("Basophils", "0%-0.75%", "0.00-0.0075"), 
            ("Platelet count", "150,000-400,000/mm³", "150-400 x 10^9/L"), 

            ("", "", ""),
            ("Coagulation", "", ""),
            ("Partial thromboplastin time", "25-40 seconds", "25-40 seconds"), 
            ("Prothrombin time (PT)", "11-15 seconds", "11-15 seconds"), 
            ("D-dimer", "≤250 ng/mL", "≤1.4 nmol/L"), 

            ("", "", ""),
            ("Other, Hematologic", "", ""),
            ("Reticulocyte count", "0.5%-1.5%", "0.005-0.015"), 
            ("Erythrocyte count (RBC)", "Male: 4.3-5.9 million/mm³", "Male: 4.3-5.9 x 10^12/L"), 
            ("", "Female: 3.5-5.5 million/mm³", "Female: 3.5-5.5 x 10^12/L"), 
            ("ESR (Westergren)", "Male: 0-15 mm/h", "Male: 0-15 mm/h"), 
            ("", "Female: 0-20 mm/h", "Female: 0-20 mm/h"), 
            ("CD4+ T-lymphocyte count", "≥500/mm³", "≥0.5 x 10^9/L"), 
            
            ("", "", ""),
            ("Endocrine (Hemoglobin)", "", ""),
            ("Hemoglobin A1c", "≤6%", "≤42 mmol/mol"), 

            ("", "", ""),
            ("Urine", "", ""),
            ("Calcium", "100-300 mg/24 h", "2.5-7.5 mmol/24 h"), 
            ("Osmolality", "50-1200 mOsmol/kg H2O", "50-1200 mOsmol/kg H2O"), 
            ("Oxalate", "8-40 µg/mL", "90-445 µmol/L"), 
            ("Proteins, total", "<150 mg/24 h", "<0.15 g/24 h"), 

            ("", "", ""),
            ("Body Mass Index (BMI)", "", ""),
            ("Adult BMI", "19-25 kg/m²", "") 
        ]
        
        for item in lab_values_data:
            # Check if the 2nd and 3rd columns (Reference Range and SI Interval) are empty
            if item[1] == "" and item[2] == "":
                self.lab_tree.insert("", tk.END, values=item, tags=("header_row",))
            else:
                self.lab_tree.insert("", tk.END, values=item)

        # --- Bottom Bar ---
        self.bottom_frame = tk.Frame(self.root, bg="#0a2240", height=65)
        self.bottom_frame.pack(side=tk.BOTTOM, fill=tk.X)
        self.bottom_frame.pack_propagate(False)

        self.footer_images = {}

        def load_btn_image(filename, size=(26, 26)):
            """Helper to load and map a PNG icon into a CTkImage for auto-scaling scaling on macOS."""
            path = os.path.join("assets", filename)
            if os.path.exists(path):
                try:
                    img = Image.open(path)
                    photo = ctk.CTkImage(light_image=img, dark_image=img, size=size)
                    self.footer_images[filename] = photo  
                    return photo
                except Exception as e:
                    print(f"Warning: Could not load image {filename}: {e}")
            return None
        
        # Center: Native CustomTkinter load button
        img_load = load_btn_image("load.png")
        btn_load = ctk.CTkButton(self.bottom_frame, text="Load PDF", command=self.load_pdf, 
                                 fg_color=self.color_white, text_color=self.color_blue, 
                                 hover_color="#1a3b61", font=("Arial", 9, "bold"), 
                                 width=70, height=30, compound="top")
        if img_load:
            btn_load.configure(image=img_load)
        btn_load.place(relx=0.5, rely=0.5, anchor=tk.CENTER)

        # Left-Side Controls (CustomTkinter)
        left_controls = [
            ("Previous", "Previous", "previous.png"), 
            ("Next", "Next", "next.png")
        ]
        for text, action, icon_file in left_controls:
            img = load_btn_image(icon_file)
            btn = ctk.CTkButton(self.bottom_frame, text=text, command=lambda a=action: self.handle_bottom_action(a),
                                fg_color=self.color_blue, text_color=self.color_white, 
                                hover_color="#1a3b61", font=("Arial", 9, "bold"), 
                                width=50, height=55, compound="top")
            if img:
                btn.configure(image=img)
            btn.pack(side=tk.LEFT, padx=5, pady=5)

        # Right-Side Controls (CustomTkinter)
        right_controls = [
            ("Pause", "Pause", "pause.png"),
            ("Help", "Help", "help.png"),
            ("Review", "Review", "review.png"),
            ("Lab Values", "Lab Values", "lab_values.png")
        ]
        for text, action, icon_file in right_controls:
            img = load_btn_image(icon_file)
            btn = ctk.CTkButton(self.bottom_frame, text=text, command=lambda a=action: self.handle_bottom_action(a),
                                fg_color=self.color_blue, text_color=self.color_white, 
                                hover_color="#1a3b61", font=("Arial", 9, "bold"), 
                                width=50, height=55, compound="top")
            if img:
                btn.configure(image=img)
            btn.pack(side=tk.RIGHT, padx=5, pady=5)

    def _on_main_canvas_configure(self, event):
        """Forces the content window to stretch to the bottom if it's shorter than the visible canvas."""
        self.main_canvas.itemconfig(self.canvas_window, width=event.width)
        req_height = self.scrollable_main_frame.winfo_reqheight()
        if req_height < event.height:
            self.main_canvas.itemconfig(self.canvas_window, height=event.height)
        else:
            self.main_canvas.itemconfig(self.canvas_window, height="")

    def _on_scrollable_frame_configure(self, event):
        """Updates scroll region and enforces height constraints dynamically."""
        self.main_canvas.configure(scrollregion=self.main_canvas.bbox("all"))
        canvas_height = self.main_canvas.winfo_height()
        if event.height < canvas_height:
            self.main_canvas.itemconfig(self.canvas_window, height=canvas_height)
        else:
            self.main_canvas.itemconfig(self.canvas_window, height=event.height)

    def on_left_panel_configure(self, event):
        """Dynamically adjusts the text wrapping length of radio buttons to prevent overlap."""
        wrap_width = event.width - 20 
        if wrap_width > 50:
            for rb in self.radio_buttons:
                try:
                    rb.config(wraplength=wrap_width)
                except tk.TclError:
                    pass

    def _get_scroll_delta(self, event):
        """Helper to calculate smooth scroll delta across Mac, Windows, and Linux."""
        if event.num == 4:
            return -4
        elif event.num == 5:
            return 4
        elif sys.platform == "darwin":
            return int(-event.delta)
        else:
            return int(-event.delta / 120) * 4

    def _bind_mousewheel(self, widget):
        widget.bind("<MouseWheel>", self._on_mousewheel)
        widget.bind("<Button-4>", self._on_mousewheel)
        widget.bind("<Button-5>", self._on_mousewheel)

    def _on_mousewheel(self, event):
        bbox = self.main_canvas.bbox("all")
        if not bbox or bbox[3] <= self.main_canvas.winfo_height():
            return "break"
            
        self.main_canvas.yview_scroll(self._get_scroll_delta(event), "units")
        return "break" 

    def _bind_lab_mousewheel(self, widget):
        widget.bind("<MouseWheel>", self._on_lab_mousewheel)
        widget.bind("<Button-4>", self._on_lab_mousewheel)
        widget.bind("<Button-5>", self._on_lab_mousewheel)

    def _on_lab_mousewheel(self, event):
        bbox = self.lab_canvas.bbox("all")
        if not bbox or bbox[3] <= self.lab_canvas.winfo_height():
            return "break"
            
        self.lab_canvas.yview_scroll(self._get_scroll_delta(event), "units")
        return "break" 
    
    def show_full_image(self, event):
        if not self.questions: return
        q = self.questions[self.current_index]
        if not q.image: return
        
        if self.full_img_win and self.full_img_win.winfo_exists():
            self.full_img_win.destroy()
            
        self.full_img_win = tk.Toplevel(self.root)
        self.full_img_win.title("Full Size Reference (Click to Close)")
        self.full_img_win.configure(bg="black")
        
        max_w = self.root.winfo_width() - 80   
        max_h = self.root.winfo_height() - 80  
        
        img_w, img_h = q.image.size
        scale = min(1.0, max_w / img_w, max_h / img_h)
        
        new_w = int(img_w * scale)
        new_h = int(img_h * scale)
        
        resized_img = q.image.resize((new_w, new_h), Image.Resampling.LANCZOS)
        full_photo = ImageTk.PhotoImage(resized_img)
        
        lbl_full = tk.Label(self.full_img_win, image=full_photo, cursor="hand2", bg="black")
        lbl_full.image = full_photo  
        lbl_full.pack(fill=tk.BOTH, expand=True)
        
        root_x = self.root.winfo_rootx()
        root_y = self.root.winfo_rooty()
        win_x = root_x + (self.root.winfo_width() - new_w) // 2
        win_y = root_y + (self.root.winfo_height() - new_h) // 2
        
        self.full_img_win.geometry(f"{new_w}x{new_h}+{win_x}+{win_y}")
        self.full_img_win.overrideredirect(True) 
        
        lbl_full.bind("<Button-1>", lambda e: self.full_img_win.destroy())

    def start_timer(self):
        self.lbl_time_remaining.config(fg=self.color_white) 
        self.timer_running = True
        self.update_timer()

    def update_timer(self):
        if not self.timer_running:
            return

        if self.time_left > 0:
            hrs, remainder = divmod(self.time_left, 3600)
            mins, secs = divmod(remainder, 60)
            self.lbl_time_remaining.config(text=f"{hrs} hr {mins:02d} min {secs:02d} sec")
            self.time_left -= 1
            self.timer_job = self.root.after(1000, self.update_timer)
            
        elif self.time_left == 0:
            self.timer_running = False
            self.lbl_time_remaining.config(text="0 hr 00 min 00 sec", fg="#ff4444")
            
            end_exam = messagebox.askyesno("Time's Up", "The exam time has expired.\n\nWould you like to end the exam?")
            if end_exam:
                self.enter_review_mode()
            else:
                self.timer_running = True
                self.time_left -= 1
                self.timer_job = self.root.after(1000, self.update_timer)
                
        else: 
            abs_time = abs(self.time_left)
            hrs, remainder = divmod(abs_time, 3600)
            mins, secs = divmod(remainder, 60)
            
            self.lbl_time_remaining.config(text=f"- {hrs} hr {mins:02d} min {secs:02d} sec", fg="#ff4444")
            self.time_left -= 1
            self.timer_job = self.root.after(1000, self.update_timer)

    def toggle_pause(self):
        # Allow opening if timer isn't running, but prevent in review mode
        if self.review_mode:
            return 
            
        # Prevent opening multiple pause windows if one already exists
        if hasattr(self, 'pause_window') and self.pause_window and self.pause_window.winfo_exists():
            return

        self.timer_running = False 
        self.pause_window = ctk.CTkToplevel(self.root)
        self.pause_window.title("Exam Paused")
        
        # --- Center the pause window relative to the app window ---
        window_width = 400
        window_height = 200
        
        # Get parent window position and size
        root_x = self.root.winfo_rootx()
        root_y = self.root.winfo_rooty()
        root_width = self.root.winfo_width()
        root_height = self.root.winfo_height()
        
        # Calculate center coordinates
        pos_x = root_x + (root_width // 2) - (window_width // 2)
        pos_y = root_y + (root_height // 2) - (window_height // 2)
        
        self.pause_window.geometry(f"{window_width}x{window_height}+{pos_x}+{pos_y}")
        # ----------------------------------------------------------
        
        self.pause_window.configure(fg_color=self.color_blue)
        self.pause_window.transient(self.root)
        self.pause_window.grab_set() 
        
        ctk.CTkLabel(self.pause_window, text="Exam Paused", text_color=self.color_white, 
                     font=("Arial", 18, "bold")).pack(pady=(50, 20))
        ctk.CTkButton(self.pause_window, text="Resume", command=self.resume_timer, 
                     fg_color="white", text_color=self.color_blue, hover_color="#e0e0e0", font=("Arial", 12)).pack()

    def resume_timer(self):
        self.pause_window.destroy()
        self.start_timer()

    def enter_review_mode(self):
        self.save_current_state()
        self.review_mode = True
        self.timer_running = False
        if self.timer_job:
            self.root.after_cancel(self.timer_job)
        self.lbl_subtitle_center.config(text="PRACTICE Self-Assessment [REVIEW MODE]", fg="yellow")
        self.update_ui()
        self.open_review_window()

    def apply_highlight(self, event):
        if self.review_mode: return
        widget = event.widget
        try:
            if widget.tag_ranges(tk.SEL):
                widget.tag_add("highlight", tk.SEL_FIRST, tk.SEL_LAST)
                widget.tag_remove(tk.SEL, tk.SEL_FIRST, tk.SEL_LAST)
        except tk.TclError:
            pass

    def remove_highlight(self, event):
        if self.review_mode: return
        widget = event.widget
        index = widget.index(f"@{event.x},{event.y}")
        ranges = widget.tag_ranges("highlight")
        for i in range(0, len(ranges), 2):
            start = ranges[i]
            end = ranges[i+1]
            if widget.compare(start, "<=", index) and widget.compare(index, "<=", end):
                widget.tag_remove("highlight", start, end)
                break

    def toggle_strikeout(self, event):
        if self.review_mode: return
        widget = event.widget
        if widget.is_crossed_out:
            widget.configure(font=self.base_font)
            widget.is_crossed_out = False
        else:
            widget.configure(font=self.strike_font)
            widget.is_crossed_out = True

    def toggle_mark(self):
        if self.review_mode: return
        if self.questions:
            if self.mark_var.get():
                self.marked_questions.add(self.current_index)
            else:
                self.marked_questions.discard(self.current_index)

    def handle_bottom_action(self, action):
        if not self.questions: return
        if action == "Next":
            if self.current_index < len(self.questions) - 1:
                self.save_current_state()
                self.current_index += 1
                self.update_ui()
            else:
                if not self.review_mode:
                    if messagebox.askyesno("End of Exam", "You have reached the end of the exam. Do you want to end the block and enter Review Mode?"):
                        self.enter_review_mode()
        elif action == "Previous":
            if self.current_index > 0:
                self.save_current_state()
                self.current_index -= 1
                self.update_ui()
        elif action == "Pause":
            self.toggle_pause()
        elif action == "Lab Values":
            self.open_lab_values()
        elif action == "Review":
            self.open_review_window()
        elif action == "Help":
            messagebox.showinfo("Help", "NBME Interface Simulator\n\n- Text Highlighting: Select text with mouse.\n- Strikeout Options: Alt + Click option text.")
        elif action == "Calculator":
            messagebox.showinfo("Calculator", "System Calculator integration placeholder.")

    def open_lab_values(self):
        """Toggles the inline Lab Values Table Panel"""
        if self.lab_values_open:
            self.lab_values_container.pack_forget()
            self.lab_values_open = False
            self.content_frame.columnconfigure(0, weight=80, uniform="panels")
            self.content_frame.columnconfigure(1, weight=20, uniform="panels")
        else:
            self.lab_values_container.pack(side=tk.TOP, fill=tk.BOTH, expand=True, pady=(15, 0))
            self.lab_values_open = True
            self.content_frame.columnconfigure(0, weight=50, uniform="panels")
            self.content_frame.columnconfigure(1, weight=50, uniform="panels")
            
        # Recalculate text box heights after layout changes
        self.root.update_idletasks() 
        if self.questions:
            q = self.questions[self.current_index]
            
            lines_top = self.text_question.count("1.0", "end", "displaylines")
            if lines_top:
                self.text_question.config(height=lines_top[0] + 1)
                
            if q.inverted:
                lines_bottom = self.text_question_bottom.count("1.0", "end", "displaylines")
                if lines_bottom:
                    self.text_question_bottom.config(height=lines_bottom[0] + 1)

    def confirm_end_test(self):
        if messagebox.askyesno("End Exam", "Are you sure you want to end the exam and enter Review Mode?"):
            if self.review_window and self.review_window.winfo_exists():
                self.review_window.destroy()
            self.enter_review_mode()

    def open_review_window(self):
        if self.review_window and self.review_window.winfo_exists():
            self.review_window.destroy()
            self.review_window = None
            return

        self.review_window = ctk.CTkToplevel(self.root)
        self.review_window.title("Review Options")
        self.review_window.geometry("700x500")
        self.review_window.configure(fg_color=self.color_white)
        self.review_window.transient(self.root)
        
        mode_text = "[REVIEW MODE ACTIVE]" if self.review_mode else "Click a question to navigate. Green = Answered, Red = Unanswered."
        ctk.CTkLabel(self.review_window, text=mode_text, text_color=self.color_black, 
                     font=("Arial", 12, "bold" if self.review_mode else "normal")).pack(pady=10)
        
        export_btn = ctk.CTkButton(self.review_window, text="Export Exam (PDF)", 
                                   command=self.export_to_pdf, fg_color="white", text_color=self.color_blue, 
                                   hover_color="#e0e0e0", font=("Arial", 10, "bold"))
        export_btn.pack(pady=(0, 10))

        if not self.review_mode:
            end_btn = ctk.CTkButton(self.review_window, text="End Test", 
                                    command=self.confirm_end_test, fg_color="white", text_color=self.color_blue, 
                                    hover_color="#e0e0e0", font=("Arial", 10, "bold"))
            end_btn.pack(pady=(0, 10))

        canvas = tk.Canvas(self.review_window, bg=self.color_white, borderwidth=0, highlightthickness=0)
        scrollbar = ttk.Scrollbar(self.review_window, orient="vertical", command=canvas.yview)
        scrollable_frame = tk.Frame(canvas, bg=self.color_white)

        scrollable_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True, padx=20)
        scrollbar.pack(side="right", fill="y")
        
        cols = 5
        rows_per_col = math.ceil(len(self.questions) / cols) if self.questions else 1
        
        for i, q in enumerate(self.questions):
            is_answered = q.selected_option.get() != ""
            bg_color = "#90ffab" if is_answered else "#ff808b" 
            flag = " 🚩" if i in self.marked_questions else ""
            btn_text = f"#{i + 1}{flag}" 
            
            row = i % rows_per_col
            col = i // rows_per_col
            
            # Using CustomTkinter CTkButton matrix for full macOS background rendering
            lbl_btn = ctk.CTkButton(scrollable_frame, text=btn_text, fg_color=bg_color, text_color="black",
                                    hover_color="#7ae694" if is_answered else "#e66e78",
                                    font=("Arial", 10, "bold"), width=70, height=35,
                                    command=lambda idx=i: self.goto_question(idx, self.review_window))
            lbl_btn.grid(row=row, column=col, padx=8, pady=8)

    def goto_question(self, index, review_window):
        self.save_current_state()
        self.current_index = index
        self.update_ui()
        review_window.destroy()
        self.review_window = None

    def _get_formatted_text(self, raw_text, highlight_ranges):
        """Helper to safely map Tkinter highlight indices to ReportLab HTML-like tags."""
        temp_text = tk.Text(self.root)
        temp_text.insert("1.0", raw_text)
        
        if highlight_ranges:
            for i in range(0, len(highlight_ranges), 2):
                temp_text.tag_add("highlight", highlight_ranges[i], highlight_ranges[i+1])

        parts = []
        for key, value, index in temp_text.dump("1.0", "end"):
            if key == "tagon" and value == "highlight":
                parts.append('<font backColor="yellow">')
            elif key == "tagoff" and value == "highlight":
                parts.append('</font>')
            elif key == "text":
                clean_text = value.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
                clean_text = clean_text.replace('\n', '<br/>')
                parts.append(clean_text)

        temp_text.destroy()
        
        res = "".join(parts)
        if res.endswith("<br/>"): res = res[:-5] 
        return res

    def export_to_pdf(self):
        """Generates a comprehensive PDF report of the current exam state."""
        if not self.questions:
            messagebox.showwarning("Empty", "No questions to export.")
            return
            
        if not REPORTLAB_AVAILABLE:
            messagebox.showerror("Missing Dependency", "ReportLab is required for this feature.\nPlease run: pip install reportlab")
            return

        self.save_current_state()

        file_path = filedialog.asksaveasfilename(
            defaultextension=".pdf",
            filetypes=[("PDF files", "*.pdf")],
            title="Save Exam Report"
        )
        if not file_path: return

        try:
            doc = SimpleDocTemplate(file_path, pagesize=letter, rightMargin=40, leftMargin=40, topMargin=40, bottomMargin=40)
            styles = getSampleStyleSheet()
            story = []

            title_style = styles['Title']
            header_style = ParagraphStyle('HeaderStyle', parent=styles['Heading2'], textColor=colors.HexColor("#0a2240"))
            flagged_style = ParagraphStyle('FlaggedStyle', parent=styles['Heading2'], textColor=colors.red)
            body_style = ParagraphStyle('BodyStyle', parent=styles['Normal'], fontSize=11, leading=14, spaceAfter=10)
            
            story.append(Paragraph("<b>NBME Self-Assessment Review Report</b>", title_style))
            story.append(Spacer(1, 20))

            for i, q in enumerate(self.questions):
                is_flagged = i in self.marked_questions
                h_style = flagged_style if is_flagged else header_style
                title_text = f"Question {i + 1} [FLAGGED]" if is_flagged else f"Question {i + 1}"
                story.append(Paragraph(f"<b>{title_text}</b>", h_style))
                
                if q.inverted:
                    inst_formatted = self._get_formatted_text(q.instructions, q.highlights_top)
                    q_formatted = self._get_formatted_text(q.text, q.highlights_bottom)
                    story.append(Paragraph(inst_formatted, body_style))
                    story.append(Paragraph(q_formatted, body_style))
                else:
                    q_formatted = self._get_formatted_text(q.text, q.highlights_top)
                    story.append(Paragraph(q_formatted, body_style))
                    
                story.append(Spacer(1, 5))

                selected_val = q.selected_option.get()
                for j, opt in enumerate(q.options):
                    opt_clean = opt.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
                    
                    is_selected = (selected_val == opt)
                    is_crossed = j in getattr(q, 'crossed_out_options', set())
                    
                    prefix = "[ X ]" if is_selected else "[   ]"
                    if is_crossed:
                        opt_clean = f"<strike>{opt_clean}</strike>"
                        
                    color_tag = "green" if is_selected else "gray" if is_crossed else "black"
                    
                    option_line = f"<font color='{color_tag}'><b>{prefix}</b> {opt_clean}</font>"
                    story.append(Paragraph(option_line, body_style))

                story.append(Spacer(1, 15))
                story.append(Paragraph("<font color='#cccccc'>________________________________________________________________________</font>", body_style))
                story.append(Spacer(1, 15))

            doc.build(story)
            messagebox.showinfo("Success", f"Report successfully exported to:\n{file_path}")

        except Exception as e:
            messagebox.showerror("Export Error", f"Failed to generate PDF:\n{e}")

    def update_ui(self):
        if not self.questions:
            self.lbl_item_count.config(text="Exam Section : Item 0 of 0")
            self.text_question.pack_forget()
            self.options_frame.pack_forget()
            self.text_question_bottom.pack_forget() 
            for rb in self.radio_buttons: rb.destroy()
            self.radio_buttons.clear()
            self.lbl_preview.config(image="", text="No Preview\nAvailable")
            return
            
        q = self.questions[self.current_index]
        self.lbl_item_count.config(text=f"Exam Section : Item {self.current_index + 1} of {len(self.questions)}")
        self.chk_mark.config(state=tk.DISABLED if self.review_mode else tk.NORMAL)
        self.mark_var.set(self.current_index in self.marked_questions)
        
        self.text_question.pack_forget()
        self.options_frame.pack_forget()
        self.text_question_bottom.pack_forget()
        
        self.text_question.config(state=tk.NORMAL)
        self.text_question.delete("1.0", tk.END)
        self.text_question_bottom.config(state=tk.NORMAL)
        self.text_question_bottom.delete("1.0", tk.END)
        
        if q.inverted:
            self.text_question.insert("1.0", q.instructions)
            self.text_question_bottom.insert("1.0", q.text)
            
            self.text_question.pack(anchor="w", fill=tk.X, pady=(0, 20))
            self.options_frame.pack(anchor="w", fill=tk.X)
            self.text_question_bottom.pack(anchor="w", fill=tk.X, pady=(20, 0)) 
        else:
            self.text_question.insert("1.0", q.text)
            self.text_question.pack(anchor="w", fill=tk.X, pady=(0, 20))
            self.options_frame.pack(anchor="w", fill=tk.X)
            
        if hasattr(q, 'highlights_top') and q.highlights_top:
            for i in range(0, len(q.highlights_top), 2):
                self.text_question.tag_add("highlight", q.highlights_top[i], q.highlights_top[i+1])

        if q.inverted and hasattr(q, 'highlights_bottom') and q.highlights_bottom:
            for i in range(0, len(q.highlights_bottom), 2):
                self.text_question_bottom.tag_add("highlight", q.highlights_bottom[i], q.highlights_bottom[i+1])
        
        self.root.update_idletasks() 
        lines_top = self.text_question.count("1.0", "end", "displaylines")
        self.text_question.config(height=(lines_top[0] + 1) if lines_top else 2, state=tk.DISABLED)
        
        if q.inverted:
            lines_bottom = self.text_question_bottom.count("1.0", "end", "displaylines")
            self.text_question_bottom.config(height=(lines_bottom[0] + 1) if lines_bottom else 2, state=tk.DISABLED)
        else:
            self.text_question_bottom.config(state=tk.DISABLED)
        
        if q.image:
            thumb = q.image.copy()
            thumb.thumbnail((100, 150), Image.Resampling.LANCZOS)
            self.thumb_photo = ImageTk.PhotoImage(thumb) 
            self.lbl_preview.config(image=self.thumb_photo, text="")
        else:
            self.lbl_preview.config(image="", text="No Preview\nAvailable")

        for rb in self.radio_buttons: rb.destroy()
        self.radio_buttons.clear()
        rb_state = tk.DISABLED if self.review_mode else tk.NORMAL
        
        initial_wrap_width = max(100, self.left_panel.winfo_width() - 20)
        
        for i, opt in enumerate(q.options):
            rb = tk.Radiobutton(self.options_frame, text=opt, 
                                variable=q.selected_option, value=opt,
                                bg=self.color_white, fg="black", font=self.base_font, 
                                disabledforeground="black", 
                                activebackground=self.color_white, highlightthickness=0, 
                                state=rb_state, justify=tk.LEFT, wraplength=initial_wrap_width)
            
            if hasattr(q, 'crossed_out_options') and i in q.crossed_out_options:
                rb.is_crossed_out = True
                rb.configure(font=self.strike_font)
            else:
                rb.is_crossed_out = False 
            
            rb.pack(anchor="w", pady=5)
            self._bind_mousewheel(rb)
            rb.bind("<Alt-Button-1>", self.toggle_strikeout)
            rb.bind("<Option-Button-1>", self.toggle_strikeout)
            self.radio_buttons.append(rb)
            
        self.main_canvas.yview_moveto(0)

    def _fill_missing_options(self, options):
        """
        Evaluates a list of options (e.g., ['A) text', 'C) text']) and fills in 
        missing letters up to the highest detected option with an error placeholder.
        """
        if not options:
            return []
            
        letters_found = []
        for opt in options:
            match = re.match(r'^([A-Z])\)', opt.strip())
            if match:
                letters_found.append(match.group(1))
                
        if not letters_found:
            return options
            
        max_letter = max(letters_found)
        complete_options = []
        
        # Iterate from 'A' up to the highest letter found
        for i in range(ord('A'), ord(max_letter) + 1):
            expected_letter = chr(i)
            
            # Search for an existing option that matches the expected letter
            found_opt = next((opt for opt in options if opt.strip().startswith(f"{expected_letter})")), None)
            
            if found_opt:
                complete_options.append(found_opt)
            else:
                # Inject fallback if the OCR missed this letter
                complete_options.append(f"{expected_letter}) [OCR error, see reference]")
                
        return complete_options

    def parse_text_to_questions(self, raw_pages):
        parsed_questions = []
        unparsed_pages = []
        pages_with_questions = set()
        inverted_q_remaining = 0

        for page_data in raw_pages:
            page_text = page_data["text"]
            page_image = page_data["image"]
            page_num = page_data["page_num"]
            clean_text = page_text.strip()
            
            options = []
            parsed_successfully = False
            
            clean_text = re.sub(r'[1|lI]\)', 'I)', clean_text)
            
            inv_trigger = re.search(r'The\s+response\s+options\s+for\s+the\s+next\s+(\d+)', clean_text, re.IGNORECASE)
            if inv_trigger:
                inverted_q_remaining = int(inv_trigger.group(1))

            # Handle "Inverted" questions (where options appear before the prompt)
            if inverted_q_remaining > 0:
                split_point = re.search(r'A\)', clean_text)
                if split_point:
                    i_text = clean_text[:split_point.start()]
                    instructions = i_text.replace('\n', ' ')
                    match = re.search(r'^(\d+)\.', clean_text, re.MULTILINE)
                    if match:
                        q_text = clean_text[match.start():]
                        q_text = q_text.replace('\n', ' ')

                    answers_block = clean_text[split_point.start():match.start()]
                    options_messy = re.split(r'(?=[A-Z]\))', answers_block)
                    options = [re.split(r'\n|\t| {2,}', item.strip())[0] for item in options_messy[1:]]
                    options.sort()
                    
                    # Fill in missing answer choices
                    options = self._fill_missing_options(options)

                    if options:
                        parsed_questions.append(Question(self.root, q_text, options, image=page_image, inverted=True, instructions=instructions))
                        pages_with_questions.add(page_num)
                        parsed_successfully = True
                
                inverted_q_remaining -= 1
            
            # Handle Standard questions
            else:
                match = re.search(r'^(\d+)\.', clean_text, re.DOTALL)
                split_point = re.search(r'A\)', clean_text)
                if split_point:
                    q_text = clean_text[:split_point.start()]
                    q_text = q_text.replace('\n', ' ')

                    answers_block = clean_text[split_point.start():]
                    options_messy = re.split(r'(?=[A-Z]\))', answers_block)
                    options = [re.split(r'\n|\t| {2,}', item.strip())[0] for item in options_messy[1:]]
                    options.sort()
                    
                    # Fill in missing answer choices
                    options = self._fill_missing_options(options)

                if options:
                    parsed_questions.append(Question(self.root, q_text, options, image=page_image, inverted=False))
                    pages_with_questions.add(page_num)
                    parsed_successfully = True

            # Fallback for unparsed pages: 1-to-1 page/question matching
            if not parsed_successfully:
                fallback_text = "[OCR unable to process this question, please see reference image]"
                # Generate options A through Z
                fallback_options = [f"{chr(i)})" for i in range(65, 91)] 
                unparsed_pages.append(page_num)
                parsed_questions.append(Question(self.root, fallback_text, fallback_options, image=page_image, inverted=False))
                pages_with_questions.add(page_num)
                
        return parsed_questions, unparsed_pages

    def preprocess_for_ocr(self, img, page_num=None):
        img_array = np.array(img.convert('RGB'))
        gray_crop = cv2.cvtColor(img_array, cv2.COLOR_RGB2GRAY)
        
        _, thresh_crop = cv2.threshold(gray_crop, 200, 255, cv2.THRESH_BINARY)
        contours_crop, _ = cv2.findContours(thresh_crop, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        if contours_crop:
            largest_contour = max(contours_crop, key=cv2.contourArea)
            x, y, w, h = cv2.boundingRect(largest_contour)
            width, height = img.size
            img = img.crop((0, y, width, y + h))

        crop_array = np.array(img.convert('RGB'))
        img_bgr = cv2.cvtColor(crop_array, cv2.COLOR_RGB2BGR)
        gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
        
        blurred = cv2.GaussianBlur(gray, (5, 5), 0)
        edges = cv2.Canny(blurred, 20, 80)
        
        kernel = np.ones((5, 5), np.uint8)
        connected_edges = cv2.dilate(edges, kernel, iterations=2)
        contours, _ = cv2.findContours(connected_edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        h_img, w_img = img_bgr.shape[:2]
        page_area = h_img * w_img

        min_chart_area = page_area * 0.1
        max_chart_area = page_area * 0.8
        
        for cnt in contours:
            x, y, w, h = cv2.boundingRect(cnt)
            area = w * h
            if min_chart_area < area < max_chart_area:
                roi_gray = gray[y:y+h, x:x+w]
                
                # --- CHECK 1: Adaptive Pixel Density (Catches Photos, CTs, Smears) ---
                # Otsu automatically finds the optimal threshold to separate foreground from background
                _, otsu_roi = cv2.threshold(roi_gray, 0, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)
                
                # Text paragraphs typically have 5-15% dark pixels. Photos and scans are much denser.
                fg_ratio = cv2.countNonZero(otsu_roi) / area
                is_image = fg_ratio > 0.22
                
                # --- CHECK 2: Structural Morphology (Catches Line Graphs, Visual Fields) ---
                # If it's sparse (like a line graph), we check the size of the shapes inside.
                if not is_image:
                    _, binary_roi = cv2.threshold(roi_gray, 200, 255, cv2.THRESH_BINARY_INV)
                    internal_contours, _ = cv2.findContours(binary_roi, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
                    
                    for ic in internal_contours:
                        _, _, iw, ih = cv2.boundingRect(ic)
                        # If a single connected shape (like a circle or curve) spans >40% of both the width and height.
                        # Text letters never span this much of a full paragraph block.
                        if iw > w * 0.4 and ih > h * 0.4:
                            is_image = True
                            break
                            
                if is_image:
                    pad = 15
                    cv2.rectangle(img_bgr, 
                                  (max(0, x - pad), max(0, y - pad)), 
                                  (min(w_img, x + w + pad), min(h_img, y + h + pad)), 
                                  (255, 255, 255), -1)

        final_pil = Image.fromarray(cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)).convert("L")
        final_pil = final_pil.point(lambda p: 255 if p > 120 else p)
        processed_rgb = final_pil.convert("RGB")
            
        return processed_rgb

    def load_pdf(self):
        file_path = filedialog.askopenfilename(filetypes=[("PDF files", "*.pdf"), ("Text files", "*.txt")])
        if not file_path: return
            
        try:
            doc = fitz.open(file_path)
            total_pages = len(doc)
            
            progress_win = ctk.CTkToplevel(self.root)
            progress_win.title("Processing")
            progress_win.geometry("300x130")
            progress_win.transient(self.root)
            progress_win.grab_set() 
            
            self.cancel_ocr = False
            def on_close_progress():
                self.cancel_ocr = True
                progress_win.destroy()
                
            progress_win.protocol("WM_DELETE_WINDOW", on_close_progress)
            
            tk.Label(progress_win, text="Reading and OCRing pages...").pack(pady=10)
            progress_bar = ttk.Progressbar(progress_win, orient=tk.HORIZONTAL, length=250, mode='determinate', maximum=total_pages)
            progress_bar.pack(pady=10)
            progress_lbl = tk.Label(progress_win, text=f"Page 0 of {total_pages}")
            progress_lbl.pack()

            raw_pages = []
            
            for page_num in range(total_pages):
                if self.cancel_ocr:
                    messagebox.showinfo("Cancelled", "PDF processing was cancelled.")
                    return
                
                progress_bar['value'] = page_num + 1
                progress_lbl.config(text=f"Processing page {page_num + 1} of {total_pages}")
                self.root.update() 

                mat = fitz.Matrix(2.0, 2.0)
                page = doc.load_page(page_num)
                pix = page.get_pixmap(matrix=mat)
                mode = "RGBA" if pix.alpha else "RGB"
                raw_img = Image.frombytes(mode, [pix.width, pix.height], pix.samples)

                final_img = self.preprocess_for_ocr(raw_img, page_num)
                final_img.save(f"extracted_images/debug_page_{page_num + 1}.png")
                config = '--psm 6'
                text = pytesseract.image_to_string(final_img, config=config)

                raw_pages.append({
                    "text": text, 
                    "image": raw_img, 
                    "page_num": page_num + 1
                })

            if not self.cancel_ocr and progress_win.winfo_exists():
                progress_win.destroy()

            new_questions, unparsed_pages = self.parse_text_to_questions(raw_pages)
            
            if new_questions:
                self.questions = new_questions
                self.current_index = 0
                self.marked_questions.clear()
                self.review_mode = False
                
                if self.timer_job: self.root.after_cancel(self.timer_job)
                
                self.lbl_subtitle_center.config(text="PRACTICE Self-Assessment", fg=self.color_white)
                self.time_left = len(self.questions) * 90
                self.update_ui()
                
                unparsed_str = f"Pages with no questions detected:\n{', '.join(map(str, unparsed_pages))}" if unparsed_pages else ""
                msg = f"Successfully processed {len(self.questions)} questions.\n{unparsed_str}\n\nWould you like to start the exam timer?"
                
                start_exam = messagebox.askyesno("Processing Complete", msg)
                if start_exam:
                    self.start_timer()
                else:
                    hrs, remainder = divmod(self.time_left, 3600)
                    mins, secs = divmod(remainder, 60)
                    self.lbl_time_remaining.config(text=f"{hrs} hr {mins:02d} min {secs:02d} sec (Paused)")
                    self.toggle_pause()
            else:
                messagebox.showwarning("Warning", "Could not parse any questions.")

        except Exception as e:
            if 'progress_win' in locals() and progress_win.winfo_exists(): 
                progress_win.destroy()
            messagebox.showerror("Error", f"Failed to read file: {e}")

if __name__ == "__main__":
    root = ctk.CTk()
    app = NBMESimulatorApp(root)
    root.mainloop()