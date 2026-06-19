import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import tkinter.font as tkfont
import re
import os
import sys
import math
import pymupdf as fitz  # PyMuPDF
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

def get_tesseract_cmd():
    if getattr(sys, 'frozen', False):
        # We are running inside a bundled executable
        if sys.platform == 'win32':
            # Use sys._MEIPASS to dynamically find the _internal data folder
            base_dir = getattr(sys, '_MEIPASS', os.path.dirname(sys.executable))
            tess_dir = os.path.join(base_dir, 'Tesseract-OCR')
            tess_path = os.path.join(tess_dir, 'tesseract.exe')
            
            os.environ["TESSDATA_PREFIX"] = os.path.join(tess_dir, 'tessdata')
            return tess_path
            
        elif sys.platform == 'darwin':
            # macOS: Tesseract is inside the .app/Contents/Resources
            macos_dir = os.path.dirname(sys.executable)
            contents_dir = os.path.dirname(macos_dir) 
            tess_dir = os.path.join(contents_dir, 'Resources', 'Tesseract-OCR')
            tess_path = os.path.join(tess_dir, 'tesseract')
            
            os.environ["TESSDATA_PREFIX"] = os.path.join(tess_dir, 'tessdata')
            return tess_path
    else:
        # We are running locally during development
        if sys.platform == 'win32':
            possible_paths = [
                r'C:\Program Files\Tesseract-OCR\tesseract.exe',
                r'C:\Program Files (x86)\Tesseract-OCR\tesseract.exe'
            ]
        else:
            possible_paths = ['/usr/local/bin/tesseract', '/opt/homebrew/bin/tesseract']
            
        for path in possible_paths:
            if os.path.exists(path):
                return path
        return 'tesseract'

pytesseract.pytesseract.tesseract_cmd = get_tesseract_cmd()

def resource_path(relative_path):
    """ Get absolute path to resource, works for dev and for PyInstaller """
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")

    return os.path.join(base_path, relative_path)

# Update your configuration line to use this function:
LAB_VALUES_PDF_PATH = resource_path("lab_values_reference.pdf")

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
        self.is_test_mode = False
        self.root.title("NBME Self-Assessment Simulator")
        self.root.geometry("1024x768")
        self.root.configure(bg="white")
        
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
        
        self.base_font = tkfont.Font(family="Arial", size=12)
        self.strike_font = tkfont.Font(family="Arial", size=12, overstrike=1)
        
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

        # Added yscrollincrement to enable high-fidelity smooth scrolling
        self.main_canvas = tk.Canvas(self.main_container, bg=self.color_white, highlightthickness=0, yscrollincrement="15")
        self.main_scrollbar = ttk.Scrollbar(self.main_container, orient="vertical", command=self.main_canvas.yview)

        self.scrollable_main_frame = tk.Frame(self.main_canvas, bg=self.color_white)
        
        self.canvas_window = self.main_canvas.create_window((0, 0), window=self.scrollable_main_frame, anchor="nw")
        
        # Replaced lambda binds with explicit methods to enforce full height constraints
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
        
        # Configure columns and ENFORCE row stretch so the right panel touches the bottom
        self.content_frame.columnconfigure(0, weight=70, uniform="panels")
        self.content_frame.columnconfigure(1, weight=30, uniform="panels")
        self.content_frame.rowconfigure(0, weight=1) 
        
        self.left_panel = tk.Frame(self.content_frame, bg=self.color_white)
        self.left_panel.grid(row=0, column=0, sticky="nsew")
        self._bind_mousewheel(self.left_panel)
        
        # Dynamically adjust text wrapping for radio buttons when layout changes
        self.left_panel.bind("<Configure>", self.on_left_panel_configure)
        
        self.right_panel = tk.Frame(self.content_frame, bg=self.color_white)
        self.right_panel.grid(row=0, column=1, sticky="nsew", padx=(20, 20))
        self._bind_mousewheel(self.right_panel)
        
        # Upper Text Box 
        self.text_question = tk.Text(self.left_panel, bg=self.color_white, fg=self.color_black, font=("Arial", 12), 
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
        self.text_question_bottom = tk.Text(self.left_panel, bg=self.color_white, fg=self.color_black, font=("Arial", 12), 
                                            wrap=tk.WORD, borderwidth=0, highlightthickness=0)
        self.text_question_bottom.tag_config("highlight", background="yellow")
        self.text_question_bottom.bind("<ButtonRelease-1>", self.apply_highlight)
        self.text_question_bottom.tag_bind("highlight", "<Button-1>", self.remove_highlight)
        self._bind_mousewheel(self.text_question_bottom)

        tk.Label(self.right_panel, text="Reference Image\n(Click to Enlarge)", bg=self.color_white, fg="gray", font=("Arial", 9)).pack(side=tk.TOP, pady=(0, 5))
        self.lbl_preview = tk.Label(self.right_panel, bg=self.color_white, cursor="hand2", relief=tk.RIDGE, bd=2)
        self.lbl_preview.pack(side=tk.TOP)
        self.lbl_preview.bind("<Button-1>", self.show_full_image)
        self._bind_mousewheel(self.lbl_preview)

        # --- Lab Values Embed Container ---
        self.lab_values_container = tk.Frame(self.right_panel, bg=self.color_white)
        # It is hidden initially, will be packed in open_lab_values()
        
        tk.Label(self.lab_values_container, text="Lab Values Reference", bg=self.color_blue, fg=self.color_white, font=("Arial", 10, "bold")).pack(side=tk.TOP, fill=tk.X)
        
        # Added yscrollincrement to enable high-fidelity smooth scrolling
        self.lab_canvas = tk.Canvas(self.lab_values_container, bg=self.color_white, highlightthickness=1, highlightbackground="#cccccc", yscrollincrement="15")
        self.lab_scrollable_frame = tk.Frame(self.lab_canvas, bg=self.color_white)
        
        # Create Vertical Scrollbar to support zoomed-in content
        self.lab_scrollbar = ttk.Scrollbar(self.lab_values_container, orient="vertical", command=self.lab_canvas.yview)
        self.lab_canvas.configure(yscrollcommand=self.lab_scrollbar.set,)

        # Store the window ID so we can dynamically center it later
        self.lab_window_id = self.lab_canvas.create_window((0, 0), window=self.lab_scrollable_frame, anchor="n")
        self.lab_scrollable_frame.bind("<Configure>", lambda e: self.lab_canvas.configure(scrollregion=self.lab_canvas.bbox("all")))

        # Proper packing order to ensure scrollbars map to the edges
        self.lab_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.lab_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        # Bind the canvas resize event to our debounce re-renderer
        self.lab_canvas.bind("<Configure>", self.on_lab_canvas_resize)
        
        # Use dedicated lab mousewheel binding here
        self._bind_lab_mousewheel(self.lab_canvas)
        self._bind_lab_mousewheel(self.lab_scrollable_frame)

        # --- Bottom Bar ---
        self.bottom_frame = tk.Frame(self.root, bg=self.color_blue, height=60)
        self.bottom_frame.pack(side=tk.BOTTOM, fill=tk.X)
        self.bottom_frame.pack_propagate(False)
        
        btn_load = tk.Button(self.bottom_frame, text="Load PDF", command=self.load_pdf, 
                             bg=self.color_white, fg=self.color_black, relief=tk.FLAT, font=("Arial", 10, "bold"))
        btn_load.pack(side=tk.LEFT, padx=20, pady=15)

        controls = ["Next", "Previous", "Review", "Lab Values", "Calculator", "Pause"]
        for ctrl in controls:
            btn = tk.Button(self.bottom_frame, text=ctrl, command=lambda c=ctrl: self.handle_bottom_action(c),
                            bg=self.color_white, fg=self.color_black, relief=tk.FLAT, font=("Arial", 10, "bold"))
            btn.pack(side=tk.RIGHT, padx=10, pady=15)

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

    def on_lab_canvas_resize(self, event):
        """Listens to the canvas resizing and triggers a debounced re-render of the PDF."""
        if not self.lab_values_open:
            return
            
        new_width = event.width
        # Update centering immediately while dragging window
        self.lab_canvas.coords(self.lab_window_id, new_width / 2, 0)
        
        # Ignore minor pixel fluctuations to prevent endless loops
        if abs(self.last_canvas_width - event.width) < 15:
            return
            
        self.last_canvas_width = event.width
        
        # Cancel the previous pending render job if the user is still dragging the window
        if self.lab_resize_job is not None:
            self.root.after_cancel(self.lab_resize_job)
            
        # Schedule a new render job 400ms after the user stops dragging
        self.lab_resize_job = self.root.after(400, self.reload_lab_values_pdf)

    def reload_lab_values_pdf(self):
        """Clears the existing images and forces a fresh render at the new width."""
        if not self.lab_values_open:
            return
            
        # Destroy the old labels to prevent memory bloat
        for widget in self.lab_scrollable_frame.winfo_children():
            widget.destroy()
            
        self.lab_values_images.clear()
        self.load_lab_values_pdf()
        self.lab_resize_job = None

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
        self.lbl_time_remaining.config(fg=self.color_white) # Reset color on start
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
            
            # Prompt the user to continue or end
            end_exam = messagebox.askyesno("Time's Up", "The exam time has expired.\n\nWould you like to end the exam?")
            if end_exam:
                self.enter_review_mode()
            else:
                self.timer_running = True
                self.time_left -= 1
                self.timer_job = self.root.after(1000, self.update_timer)
                
        else: # Overtime (Negative Time)
            abs_time = abs(self.time_left)
            hrs, remainder = divmod(abs_time, 3600)
            mins, secs = divmod(remainder, 60)
            
            # Prepend the minus sign and color it red to indicate overtime
            self.lbl_time_remaining.config(text=f"- {hrs} hr {mins:02d} min {secs:02d} sec", fg="#ff4444")
            self.time_left -= 1
            self.timer_job = self.root.after(1000, self.update_timer)

    def toggle_pause(self):
        if not self.timer_running or self.review_mode:
            return 
        self.timer_running = False 
        self.pause_window = tk.Toplevel(self.root)
        self.pause_window.title("Exam Paused")
        self.pause_window.geometry("400x200")
        self.pause_window.configure(bg=self.color_blue)
        self.pause_window.transient(self.root)
        self.pause_window.grab_set() 
        tk.Label(self.pause_window, text="Exam Paused", bg=self.color_blue, fg=self.color_white, 
                 font=("Arial", 18, "bold")).pack(pady=(50, 20))
        tk.Button(self.pause_window, text="Resume", command=self.resume_timer, 
                  bg="white", font=("Arial", 12)).pack()

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
                self.save_current_state() # Add here
                self.current_index += 1
                self.update_ui()
            else:
                if not self.review_mode:
                    if messagebox.askyesno("End of Exam", "You have reached the end of the exam. Do you want to end the block and enter Review Mode?"):
                        self.enter_review_mode()
        elif action == "Previous":
            if self.current_index > 0:
                self.save_current_state() # Add here
                self.current_index -= 1
                self.update_ui()
        elif action == "Pause":
            self.toggle_pause()
        elif action == "Lab Values":
            self.open_lab_values()
        elif action == "Review":
            self.open_review_window()

    def open_lab_values(self):
        """Toggles the inline Lab Values PDF Panel"""
        if not os.path.exists(LAB_VALUES_PDF_PATH):
            messagebox.showerror("File Not Found", f"Could not locate Lab Values at:\n{LAB_VALUES_PDF_PATH}")
            return

        if self.lab_values_open:
            # Hide the panel
            self.lab_values_container.pack_forget()
            self.lab_values_open = False
            # Revert to 70/30 split
            self.content_frame.columnconfigure(0, weight=70, uniform="panels")
            self.content_frame.columnconfigure(1, weight=30, uniform="panels")
        else:
            # Show the panel
            self.lab_values_container.pack(side=tk.TOP, fill=tk.BOTH, expand=True, pady=(15, 0))
            self.lab_values_open = True
            # Update to 50/50 split
            self.content_frame.columnconfigure(0, weight=40, uniform="panels")
            self.content_frame.columnconfigure(1, weight=60, uniform="panels")
            
            # Force Tkinter to recalculate the GUI layout to physically reflect the split 
            self.root.update_idletasks() 
            
            # Establish baseline width
            self.last_canvas_width = self.lab_canvas.winfo_width()
            
            # Load the PDF images if they haven't been loaded yet
            if not self.lab_values_images:
                self.load_lab_values_pdf()

    def load_lab_values_pdf(self):
        """Renders the PDF pages to ImageTk objects to display in the Lab Values panel."""
        try:
            doc = fitz.open(LAB_VALUES_PDF_PATH)
            
            # Dynamically fetch the real width of the canvas, subtracting ~25px for the scrollbar
            canvas_width = self.lab_canvas.winfo_width()
            target_width = max(200, canvas_width - 25) 
            
            # Dynamically recenter the frame inside the canvas
            self.lab_canvas.coords(self.lab_window_id, canvas_width / 2, 0)
            self.lab_canvas.itemconfig(self.lab_window_id, anchor="n")
            
            for page_num in range(len(doc)):
                page = doc.load_page(page_num)
                
                # Apply zoom factor
                zoom = (target_width / page.rect.width) * 1.15
                mat = fitz.Matrix(zoom, zoom)
                pix = page.get_pixmap(matrix=mat)
                
                mode = "RGBA" if pix.alpha else "RGB"
                img = Image.frombytes(mode, [pix.width, pix.height], pix.samples)
                
                photo = ImageTk.PhotoImage(img)
                self.lab_values_images.append(photo) # Keep reference to avoid garbage collection
                
                lbl = tk.Label(self.lab_scrollable_frame, image=photo, bg="white")
                lbl.pack(pady=5)
                # Apply dedicated scroll binding to the rendered images
                self._bind_lab_mousewheel(lbl)
                
        except Exception as e:
            messagebox.showerror("Error", f"Failed to load inline Lab Values PDF:\n{e}")

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

        self.review_window = tk.Toplevel(self.root)
        self.review_window.title("Review Options")
        self.review_window.geometry("700x500")
        self.review_window.configure(bg=self.color_white)
        self.review_window.transient(self.root)
        
        mode_text = "[REVIEW MODE ACTIVE]" if self.review_mode else "Click a question to navigate. Green = Answered, Red = Unanswered."
        tk.Label(self.review_window, text=mode_text, bg=self.color_white, font=("Arial", 12, "bold" if self.review_mode else "normal")).pack(pady=10)
        
        export_btn = tk.Button(self.review_window, text="Export Exam (PDF)", 
                               command=self.export_to_pdf, bg=self.color_white, fg=self.color_blue, 
                               font=("Arial", 10, "bold"), cursor="hand2", relief=tk.FLAT)
        export_btn.pack(pady=(0, 10))

        # --- Add "End Test" button during active exam ---
        if not self.review_mode:
            end_btn = tk.Button(self.review_window, text="End Test", 
                                command=self.confirm_end_test, bg=self.color_white, fg=self.color_blue, 
                                font=("Arial", 10, "bold"), cursor="hand2", relief=tk.FLAT)
            end_btn.pack(pady=(0, 10))
        # -----------------------------------------------------

        canvas = tk.Canvas(self.review_window, bg=self.color_white, borderwidth=0)
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
            
            lbl_btn = tk.Label(scrollable_frame, text=btn_text, bg=bg_color, font=("Arial", 10, "bold"), width=10, height=2, relief=tk.RAISED, cursor="hand2")
            lbl_btn.bind("<Button-1>", lambda e, idx=i: self.goto_question(idx, self.review_window))
            lbl_btn.grid(row=row, column=col, padx=8, pady=8)

    def goto_question(self, index, review_window):
        self.save_current_state() # Add this at the top
        self.current_index = index
        self.update_ui()
        review_window.destroy()
        self.review_window = None

    def _get_formatted_text(self, raw_text, highlight_ranges):
        """Helper to safely map Tkinter highlight indices to ReportLab HTML-like tags."""
        temp_text = tk.Text(self.root)
        temp_text.insert("1.0", raw_text)
        
        # Apply the saved highlight indices
        if highlight_ranges:
            for i in range(0, len(highlight_ranges), 2):
                temp_text.tag_add("highlight", highlight_ranges[i], highlight_ranges[i+1])

        parts = []
        # Dump the text and tags sequentially
        for key, value, index in temp_text.dump("1.0", "end"):
            if key == "tagon" and value == "highlight":
                parts.append('<font backColor="yellow">')
            elif key == "tagoff" and value == "highlight":
                parts.append('</font>')
            elif key == "text":
                # Escape special HTML characters to prevent ReportLab crashes
                clean_text = value.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
                clean_text = clean_text.replace('\n', '<br/>')
                parts.append(clean_text)

        temp_text.destroy()
        
        res = "".join(parts)
        # Strip trailing newline artifact from Tkinter dump
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

        # Ensure the current question's state is saved before exporting
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

            # Custom Styles
            title_style = styles['Title']
            header_style = ParagraphStyle('HeaderStyle', parent=styles['Heading2'], textColor=colors.HexColor("#0a2240"))
            flagged_style = ParagraphStyle('FlaggedStyle', parent=styles['Heading2'], textColor=colors.red)
            body_style = ParagraphStyle('BodyStyle', parent=styles['Normal'], fontSize=11, leading=14, spaceAfter=10)
            
            story.append(Paragraph("<b>NBME Self-Assessment Review Report</b>", title_style))
            story.append(Spacer(1, 20))

            for i, q in enumerate(self.questions):
                # 1. Title & Flag Status
                is_flagged = i in self.marked_questions
                h_style = flagged_style if is_flagged else header_style
                title_text = f"Question {i + 1} [FLAGGED]" if is_flagged else f"Question {i + 1}"
                story.append(Paragraph(f"<b>{title_text}</b>", h_style))
                
                # 2. Extract and format text with highlights
                if q.inverted:
                    inst_formatted = self._get_formatted_text(q.instructions, q.highlights_top)
                    q_formatted = self._get_formatted_text(q.text, q.highlights_bottom)
                    story.append(Paragraph(inst_formatted, body_style))
                    story.append(Paragraph(q_formatted, body_style))
                else:
                    q_formatted = self._get_formatted_text(q.text, q.highlights_top)
                    story.append(Paragraph(q_formatted, body_style))
                    
                story.append(Spacer(1, 5))

                # 3. Process Options
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
                # Add a light separator line between questions
                story.append(Paragraph("<font color='#cccccc'>________________________________________________________________________</font>", body_style))
                story.append(Spacer(1, 15))

            # Build PDF
            doc.build(story)
            messagebox.showinfo("Success", f"Report successfully exported to:\n{file_path}")

        except Exception as e:
            messagebox.showerror("Export Error", f"Failed to generate PDF:\n{e}")

    def update_ui(self):
        # 1. Handle empty state
        if not self.questions:
            self.lbl_item_count.config(text="Exam Section : Item 0 of 0")
            self.text_question.pack_forget()
            self.options_frame.pack_forget()
            self.text_question_bottom.pack_forget() 
            for rb in self.radio_buttons: rb.destroy()
            self.radio_buttons.clear()
            self.lbl_preview.config(image="", text="No Preview\nAvailable")
            return
            
        # 2. Setup Question
        q = self.questions[self.current_index]
        self.lbl_item_count.config(text=f"Exam Section : Item {self.current_index + 1} of {len(self.questions)}")
        self.chk_mark.config(state=tk.DISABLED if self.review_mode else tk.NORMAL)
        self.mark_var.set(self.current_index in self.marked_questions)
        
        # Reset Widgets
        self.text_question.pack_forget()
        self.options_frame.pack_forget()
        self.text_question_bottom.pack_forget()
        
        self.text_question.config(state=tk.NORMAL)
        self.text_question.delete("1.0", tk.END)
        self.text_question_bottom.config(state=tk.NORMAL)
        self.text_question_bottom.delete("1.0", tk.END)
        
        # 3. Layout Question/Inverted Content
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
            
        # --- Restore Text Highlights ---
        if hasattr(q, 'highlights_top') and q.highlights_top:
            for i in range(0, len(q.highlights_top), 2):
                self.text_question.tag_add("highlight", q.highlights_top[i], q.highlights_top[i+1])

        if q.inverted and hasattr(q, 'highlights_bottom') and q.highlights_bottom:
            for i in range(0, len(q.highlights_bottom), 2):
                self.text_question_bottom.tag_add("highlight", q.highlights_bottom[i], q.highlights_bottom[i+1])
        
        # 4. Finalize text sizing
        self.root.update_idletasks() 
        lines_top = self.text_question.count("1.0", "end", "displaylines")
        self.text_question.config(height=(lines_top[0] + 1) if lines_top else 2, state=tk.DISABLED)
        
        if q.inverted:
            lines_bottom = self.text_question_bottom.count("1.0", "end", "displaylines")
            self.text_question_bottom.config(height=(lines_bottom[0] + 1) if lines_bottom else 2, state=tk.DISABLED)
        else:
            self.text_question_bottom.config(state=tk.DISABLED)
        
        # 5. Handle Image Preview
        if q.image:
            thumb = q.image.copy()
            thumb.thumbnail((300, 450), Image.Resampling.LANCZOS)
            self.thumb_photo = ImageTk.PhotoImage(thumb) 
            self.lbl_preview.config(image=self.thumb_photo, text="")
        else:
            self.lbl_preview.config(image="", text="No Preview\nAvailable")

        # 6. Rebuild Radio Buttons
        for rb in self.radio_buttons: rb.destroy()
        self.radio_buttons.clear()
        rb_state = tk.DISABLED if self.review_mode else tk.NORMAL
        
        # Calculate initial wraplength based on current left_panel size
        initial_wrap_width = max(100, self.left_panel.winfo_width() - 20)
        
        for i, opt in enumerate(q.options):
            rb = tk.Radiobutton(self.options_frame, text=opt, 
                                variable=q.selected_option, value=opt,
                                bg=self.color_white, fg="black", font=self.base_font, 
                                disabledforeground="black", # Prevents text from graying out
                                activebackground=self.color_white, highlightthickness=0, 
                                state=rb_state, justify=tk.LEFT, wraplength=initial_wrap_width)
            
            # Restore strikeout state
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
            
        # Reset scroll to top
        self.main_canvas.yview_moveto(0)

    def parse_text_to_questions(self, raw_pages):
        parsed_questions = []
        pages_with_questions = set()
        inverted_q_remaining = 0

        for page_data in raw_pages:
            page_text = page_data["text"]
            page_image = page_data["image"]
            page_num = page_data["page_num"]
            clean_text = page_text.strip()
            
            # Reset options for each page to avoid carrying over previous options
            options = []

            # Correct common OCR mistake
            clean_text = re.sub(r'[1|lI]\)', 'I)', clean_text)
            
            # Detect Inverted Format
            inv_trigger = re.search(r'The\s+response\s+options\s+for\s+the\s+next\s+(\d+)', clean_text, re.IGNORECASE)
            if inv_trigger:
                inverted_q_remaining = int(inv_trigger.group(1))

            # --- Inverted Format Path ---
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

                    if options:
                        parsed_questions.append(Question(self.root, q_text, options, image=page_image, inverted=True, instructions=instructions))
                        pages_with_questions.add(page_num)
                
                inverted_q_remaining -= 1
                continue
            
            # --- Standard Format Path ---
            match = re.search(r'^(\d+)\.', clean_text, re.DOTALL)
            
            # Split point: The first instance of "A)"
            split_point = re.search(r'A\)', clean_text)
            if split_point:
                q_text = clean_text[:split_point.start()]
                q_text = q_text.replace('\n', ' ')

                answers_block = clean_text[split_point.start():]
                options_messy = re.split(r'(?=[A-Z]\))', answers_block)
                options = [re.split(r'\n|\t| {2,}', item.strip())[0] for item in options_messy[1:]]
                options.sort()

            if options:
                parsed_questions.append(Question(self.root,q_text, options, image=page_image, inverted=False))
                pages_with_questions.add(page_num)
                
        # Calculate which pages didn't yield any questions
        all_pages = [p["page_num"] for p in raw_pages]
        unparsed_pages = [p for p in all_pages if p not in pages_with_questions]
                
        return parsed_questions, unparsed_pages

    def preprocess_for_ocr(self, img, page_num=None):
        """
        1. Dynamically crops out blue headers/footers.
        2. Redacts large photos/charts using a Mid-Tone mask to prevent OCR artifacts.
        3. Washes out light gray backgrounds for clean text reading.
        """
        # ==========================================
        # STEP 1: DYNAMIC CROPPING (Remove Headers)
        # ==========================================
        img_array = np.array(img.convert('RGB'))
        gray_crop = cv2.cvtColor(img_array, cv2.COLOR_RGB2GRAY)
        
        # Threshold: White stays white, dark blue becomes black
        _, thresh_crop = cv2.threshold(gray_crop, 200, 255, cv2.THRESH_BINARY)
        contours_crop, _ = cv2.findContours(thresh_crop, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        if contours_crop:
            largest_contour = max(contours_crop, key=cv2.contourArea)
            x, y, w, h = cv2.boundingRect(largest_contour)
            width, height = img.size
            img = img.crop((0, y, width, y + h))

        # ==========================================
        # STEP 2: DYNAMIC CHART REDACTION (Updated)
        # ==========================================

        crop_array = np.array(img.convert('RGB'))
        img_bgr = cv2.cvtColor(crop_array, cv2.COLOR_RGB2BGR)
        
        # Convert to grayscale for detection
        gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
        
        # 1. Apply a Gaussian blur to smooth out text and minor noise
        blurred = cv2.GaussianBlur(gray, (5, 5), 0)
        
        # 2. Canny Edge Detection
        # Finds boundaries based on gradients. (30, 100) are low thresholds to catch faint edges.
        edges = cv2.Canny(blurred, 20, 80)
        
        # 3. Dilation
        # Thicken the detected edges to close gaps, creating a solid boundary for the contour
        kernel = np.ones((5, 5), np.uint8)
        connected_edges = cv2.dilate(edges, kernel, iterations=2)
        
        # Find contours using the connected edges
        contours, _ = cv2.findContours(connected_edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        # Get image dimensions to calculate the max size of the page
        h_img, w_img = img_bgr.shape[:2]
        page_area = h_img * w_img

        # Don't redact anything that covers more than 80% or less than 30% of the page 
        min_chart_area = page_area * 0.1
        max_chart_area = page_area * 0.8
        
        for cnt in contours:
            x, y, w, h = cv2.boundingRect(cnt)
            area = w * h
            if min_chart_area < area < max_chart_area:
                cv2.rectangle(img_bgr, (x-1, y-1), (x+w+2, y+h+2), (255, 255, 255), -1)

        # ==========================================
        # STEP 2.5: DEBUG SAVE (Post-Redaction Snapshot)
        # ==========================================
        # Convert the modified BGR array back to an RGB PIL Image for saving
        # debug_pil = Image.fromarray(cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB))
        
        # try:
        #     debug_dir = "debug_output"
        #     if not os.path.exists(debug_dir):
        #         os.makedirs(debug_dir)
        #     p_str = f"page_{page_num}" if page_num is not None else "test"
        #     # Saved as _redacted to distinguish it clearly
        #     debug_pil.save(os.path.join(debug_dir, f"{p_str}_redacted.png")) 
        # except Exception as e:
        #     print(f"Debug save failed: {e}")

        # ==========================================
        # STEP 3: CONTRAST ENHANCEMENT FOR OCR
        # ==========================================
        final_pil = Image.fromarray(cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)).convert("L")
        
        # Wash out faint artifacts to pure white, keep text dark
        final_pil = final_pil.point(lambda p: 255 if p > 120 else p)
        processed_rgb = final_pil.convert("RGB")
            
        return processed_rgb

    def load_pdf(self, file_path=None): # Added optional parameter
        if not file_path:
            # Only open the dialog if no path was provided via CLI
            file_path = filedialog.askopenfilename(filetypes=[("PDF files", "*.pdf"), ("Text files", "*.txt")])
        if not file_path: return
            
        try:
            # Initialize PDF and Progress Window
            doc = fitz.open(file_path)
            total_pages = len(doc)
            
            # Create Progress Window
            progress_win = tk.Toplevel(self.root)
            progress_win.title("Processing")
            progress_win.geometry("300x130")
            progress_win.transient(self.root)
            progress_win.grab_set() # Block interaction with main window while loading
            
            # --- FEATURE 2: Handle OCR Cancellation ---
            self.cancel_ocr = False
            def on_close_progress():
                self.cancel_ocr = True
                progress_win.destroy()
                
            progress_win.protocol("WM_DELETE_WINDOW", on_close_progress)
            # ----------------------------------------
            
            tk.Label(progress_win, text="Reading and OCRing pages...").pack(pady=10)
            progress_bar = ttk.Progressbar(progress_win, orient=tk.HORIZONTAL, length=250, mode='determinate', maximum=total_pages)
            progress_bar.pack(pady=10)
            progress_lbl = tk.Label(progress_win, text=f"Page 0 of {total_pages}")
            progress_lbl.pack()

            raw_pages = []
            
            for page_num in range(total_pages):
                # --- Halt execution if window was closed ---
                if self.cancel_ocr:
                    messagebox.showinfo("Cancelled", "PDF processing was cancelled.")
                    return
                # -------------------------------------------
                
                # --- Update UI ---
                progress_bar['value'] = page_num + 1
                progress_lbl.config(text=f"Processing page {page_num + 1} of {total_pages}")
                self.root.update() # Force the GUI to redraw/refresh
                # -----------------

                # Generate original pixmap (Keep this for the GUI/Display)
                mat = fitz.Matrix(2.0, 2.0)
                page = doc.load_page(page_num)
                pix = page.get_pixmap(matrix=mat)
                mode = "RGBA" if pix.alpha else "RGB"
                raw_img = Image.frombytes(mode, [pix.width, pix.height], pix.samples)

                # 1. PREPROCESS & REDACT FOR OCR
                final_img = self.preprocess_for_ocr(raw_img, page_num)
                
                # 2. RUN OCR
                config = '--psm 6'
                text = pytesseract.image_to_string(final_img, config=config)

                # 3. STORE BOTH
                raw_pages.append({
                    "text": text, 
                    "image": raw_img, 
                    "page_num": page_num + 1
                })

            # Safely close the progress window if it wasn't cancelled
            if not self.cancel_ocr and progress_win.winfo_exists():
                progress_win.destroy()

            # Trigger the parsing pipeline
            new_questions, unparsed_pages = self.parse_text_to_questions(raw_pages)
            
            # UI Updates
            if new_questions:
                self.questions = new_questions
                self.current_index = 0
                self.marked_questions.clear()
                self.review_mode = False
                
                if self.timer_job: self.root.after_cancel(self.timer_job)
                
                self.lbl_subtitle_center.config(text="PRACTICE Self-Assessment", fg=self.color_white)
                self.time_left = len(self.questions) * 90
                self.update_ui()
                
                # --- FEATURE 1: Post-processing Summary & Start Prompt ---
                unparsed_str = f"Pages with no new questions detected:\n{', '.join(map(str, unparsed_pages))}" if unparsed_pages else ""
                msg = f"Successfully processed {len(self.questions)} questions.\n{unparsed_str}\n\nWould you like to start the exam timer?"
                
                if self.is_test_mode:
                    start_exam = False 
                else:
                    start_exam = messagebox.askyesno("Processing Complete", msg)
                
                if start_exam:
                    self.start_timer()
                else:
                    # Format time visually without starting the loop
                    hrs, remainder = divmod(self.time_left, 3600)
                    mins, secs = divmod(remainder, 60)
                    self.lbl_time_remaining.config(text=f"{hrs} hr {mins:02d} min {secs:02d} sec (Paused)")
                # ---------------------------------------------------------
            else:
                messagebox.showwarning("Warning", "Could not parse any questions.")

        except Exception as e:
            if 'progress_win' in locals() and progress_win.winfo_exists(): 
                progress_win.destroy()
            messagebox.showerror("Error", f"Failed to read file: {e}")

if __name__ == "__main__":
    root = tk.Tk()
    app = NBMESimulatorApp(root)
    
    # Check for CLI arguments for CI/CD testing
    if len(sys.argv) > 1:
        pdf_args = [arg for arg in sys.argv if arg.lower().endswith('.pdf')]
        is_test_mode = "--test" in sys.argv
        
        # Pass the test mode state to the app
        app.is_test_mode = is_test_mode 

        if pdf_args:
            test_pdf_path = pdf_args[0]
            
            def run_automated_test():
                print(f"Loading test file: {test_pdf_path}")
                app.load_pdf(test_pdf_path)
                
                # If we successfully parsed questions, Tesseract is working
                if app.questions:
                    print(f"SUCCESS: Parsed {len(app.questions)} questions using Tesseract.")
                    if is_test_mode:
                        print("Test complete. Exiting normally.")
                        root.destroy() # Closes the app, allowing GitHub Actions to pass
                else:
                    print("FAILURE: No questions parsed. Tesseract integration may have failed.")
                    if is_test_mode:
                        sys.exit(1) # Forces GitHub Actions to fail the workflow
            
            # Delay execution slightly to ensure the GUI has initialized
            root.after(500, run_automated_test)

    root.mainloop()