import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import tkinter.font as tkfont
import re
import os
import sys
import subprocess
import math

# Import image handling libraries
try:
    import fitz  # PyMuPDF
    from PIL import Image, ImageTk
except ImportError:
    messagebox.showerror("Missing Libraries", "Please install required libraries:\npip install PyMuPDF Pillow")
    sys.exit(1)

# ==========================================
# CODER CONFIGURATION: Set Lab Values Path
# ==========================================
LAB_VALUES_PDF_PATH = "lab_values_reference.pdf"  # Update this to your local file path
# ==========================================

class Question:
    def __init__(self, root, number, text, options, image=None):
        self.number = number
        self.text = text
        self.options = options
        self.selected_option = tk.StringVar(master=root, value="")
        self.image = image  # Stores the full-size PIL Image of the PDF page

class NBMESimulatorApp:
    def __init__(self, root):
        self.root = root
        self.root.title("NBME Self-Assessment Simulator")
        self.root.geometry("1024x768")
        self.root.configure(bg="white")
        
        self.questions = []
        self.current_index = 0
        self.marked_questions = set()
        
        # Mode & Timer variables
        self.review_mode = False
        self.time_left = 0
        self.timer_running = False
        self.timer_job = None
        
        # Window trackers
        self.review_window = None
        self.full_img_win = None
        
        # Colors
        self.bg_blue = "#0a2240"
        self.text_white = "#ffffff"
        self.text_blue = "#0a2240"  
        self.bg_white = "#ffffff"
        
        self.base_font = tkfont.Font(family="Arial", size=12)
        self.strike_font = tkfont.Font(family="Arial", size=12, overstrike=1)
        
        self.create_widgets()
        self.update_ui()

    def create_widgets(self):
        # --- Top Bar ---
        self.top_frame = tk.Frame(self.root, bg=self.bg_blue, height=60)
        self.top_frame.pack(side=tk.TOP, fill=tk.X)
        self.top_frame.pack_propagate(False)
        
        self.left_top_frame = tk.Frame(self.top_frame, bg=self.bg_blue)
        self.left_top_frame.pack(side=tk.LEFT, padx=10, pady=5)
        
        self.lbl_item_count = tk.Label(self.left_top_frame, text="Exam Section : Item 0 of 0", 
                                       bg=self.bg_blue, fg=self.text_white, font=("Arial", 10, "bold"))
        self.lbl_item_count.pack(anchor="w")
        
        self.mark_var = tk.BooleanVar()
        self.chk_mark = tk.Checkbutton(self.left_top_frame, text="Mark", variable=self.mark_var, 
                                       command=self.toggle_mark, bg=self.bg_blue, fg=self.text_white, 
                                       selectcolor=self.bg_blue, activebackground=self.bg_blue, activeforeground=self.text_white, font=("Arial", 10, "bold"))
        self.chk_mark.pack(anchor="w")

        self.center_top_frame = tk.Frame(self.top_frame, bg=self.bg_blue)
        self.center_top_frame.pack(side=tk.LEFT, expand=True)
        
        self.lbl_title_center = tk.Label(self.center_top_frame, text="National Board of Medical Examiners", 
                 bg=self.bg_blue, fg=self.text_white, font=("Arial", 10))
        self.lbl_title_center.pack()
        self.lbl_subtitle_center = tk.Label(self.center_top_frame, text="PRACTICE Self-Assessment", 
                 bg=self.bg_blue, fg=self.text_white, font=("Arial", 10, "bold"))
        self.lbl_subtitle_center.pack()

        self.right_top_frame = tk.Frame(self.top_frame, bg=self.bg_blue)
        self.right_top_frame.pack(side=tk.RIGHT, padx=10, pady=5)
        
        tk.Label(self.right_top_frame, text="Time Remaining:", 
                 bg=self.bg_blue, fg=self.text_white, font=("Arial", 10)).pack(anchor="e")
        self.lbl_time_remaining = tk.Label(self.right_top_frame, text="0 hr 00 min 00 sec", 
                 bg=self.bg_blue, fg=self.text_white, font=("Arial", 10, "bold"))
        self.lbl_time_remaining.pack(anchor="e")

        # --- Main Content Area ---
        self.main_frame = tk.Frame(self.root, bg=self.bg_white)
        self.main_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=40, pady=30)
        
        self.content_frame = tk.Frame(self.main_frame, bg=self.bg_white)
        self.content_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True)
        
        self.left_panel = tk.Frame(self.content_frame, bg=self.bg_white)
        self.left_panel.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        self.right_panel = tk.Frame(self.content_frame, bg=self.bg_white, width=320)
        self.right_panel.pack(side=tk.RIGHT, fill=tk.Y, padx=(20, 0))
        
        self.text_question = tk.Text(self.left_panel, bg=self.bg_white, font=("Arial", 12), 
                                     wrap=tk.WORD, borderwidth=0, highlightthickness=0, height=8)
        self.text_question.pack(anchor="w", fill=tk.X, pady=(0, 20))
        
        self.text_question.tag_config("highlight", background="yellow")
        self.text_question.bind("<ButtonRelease-1>", self.apply_highlight)
        self.text_question.tag_bind("highlight", "<Button-1>", self.remove_highlight)
        
        self.options_frame = tk.Frame(self.left_panel, bg=self.bg_white)
        self.options_frame.pack(anchor="w", fill=tk.X)
        self.radio_buttons = []

        tk.Label(self.right_panel, text="Reference Image\n(Click to Enlarge)", bg=self.bg_white, fg="gray", font=("Arial", 9)).pack(side=tk.TOP, pady=(0, 5))
        self.lbl_preview = tk.Label(self.right_panel, bg="#f0f0f0", cursor="hand2", relief=tk.RIDGE, bd=2)
        self.lbl_preview.pack(side=tk.TOP)
        self.lbl_preview.bind("<Button-1>", self.show_full_image)

        # --- Bottom Bar ---
        self.bottom_frame = tk.Frame(self.root, bg=self.bg_blue, height=60)
        self.bottom_frame.pack(side=tk.BOTTOM, fill=tk.X)
        self.bottom_frame.pack_propagate(False)
        
        btn_load = tk.Button(self.bottom_frame, text="Load PDF", command=self.load_pdf, 
                             bg="#2c4b75", fg=self.text_blue, relief=tk.FLAT, font=("Arial", 10, "bold"))
        btn_load.pack(side=tk.LEFT, padx=20, pady=15)

        controls = ["Next", "Previous", "Review", "Lab Values", "Calculator", "Pause"]
        for ctrl in controls:
            btn = tk.Button(self.bottom_frame, text=ctrl, command=lambda c=ctrl: self.handle_bottom_action(c),
                            bg=self.bg_blue, fg=self.text_blue, relief=tk.FLAT, font=("Arial", 10, "bold"))
            btn.pack(side=tk.RIGHT, padx=10, pady=15)

    # --- Image Handling Logic ---
    
    def show_full_image(self, event):
        if not self.questions: return
        q = self.questions[self.current_index]
        if not q.image: return
        
        if self.full_img_win and self.full_img_win.winfo_exists():
            self.full_img_win.destroy()
            
        self.full_img_win = tk.Toplevel(self.root)
        self.full_img_win.title("Full Size Reference (Click to Close)")
        self.full_img_win.configure(bg="black")
        
        # Dynamically scale the image to fit within the main window's bounds
        max_w = self.root.winfo_width() - 80   # 80px margin
        max_h = self.root.winfo_height() - 80  
        
        img_w, img_h = q.image.size
        
        # Calculate scaling ratio (only scale down, don't scale up small images)
        scale = min(1.0, max_w / img_w, max_h / img_h)
        
        new_w = int(img_w * scale)
        new_h = int(img_h * scale)
        
        # Resize using LANCZOS for high quality downsampling
        resized_img = q.image.resize((new_w, new_h), Image.Resampling.LANCZOS)
        full_photo = ImageTk.PhotoImage(resized_img)
        
        lbl_full = tk.Label(self.full_img_win, image=full_photo, cursor="hand2", bg="black")
        lbl_full.image = full_photo  
        lbl_full.pack(fill=tk.BOTH, expand=True)
        
        # Center the popup window over the main application window
        root_x = self.root.winfo_rootx()
        root_y = self.root.winfo_rooty()
        win_x = root_x + (self.root.winfo_width() - new_w) // 2
        win_y = root_y + (self.root.winfo_height() - new_h) // 2
        
        self.full_img_win.geometry(f"{new_w}x{new_h}+{win_x}+{win_y}")
        self.full_img_win.overrideredirect(True) 
        
        lbl_full.bind("<Button-1>", lambda e: self.full_img_win.destroy())

    # --- Timer & Modes ---
    
    def start_timer(self):
        self.timer_running = True
        self.update_timer()

    def update_timer(self):
        if self.timer_running and self.time_left > 0:
            hrs, remainder = divmod(self.time_left, 3600)
            mins, secs = divmod(remainder, 60)
            self.lbl_time_remaining.config(text=f"{hrs} hr {mins:02d} min {secs:02d} sec")
            
            self.time_left -= 1
            self.timer_job = self.root.after(1000, self.update_timer)
        elif self.time_left <= 0 and self.timer_running:
            self.timer_running = False
            self.lbl_time_remaining.config(text="0 hr 00 min 00 sec")
            messagebox.showinfo("Time's Up", "The exam time has expired. Entering Review Mode.")
            self.enter_review_mode()

    def toggle_pause(self):
        if not self.timer_running or self.review_mode:
            return 

        self.timer_running = False 
        
        self.pause_window = tk.Toplevel(self.root)
        self.pause_window.title("Exam Paused")
        self.pause_window.geometry("400x200")
        self.pause_window.configure(bg=self.bg_blue)
        self.pause_window.transient(self.root)
        self.pause_window.grab_set() 
        
        tk.Label(self.pause_window, text="Exam Paused", bg=self.bg_blue, fg=self.text_white, 
                 font=("Arial", 18, "bold")).pack(pady=(50, 20))
        tk.Button(self.pause_window, text="Resume", command=self.resume_timer, 
                  bg="white", font=("Arial", 12)).pack()

    def resume_timer(self):
        self.pause_window.destroy()
        self.start_timer()

    def enter_review_mode(self):
        self.review_mode = True
        self.timer_running = False
        if self.timer_job:
            self.root.after_cancel(self.timer_job)
        
        self.lbl_subtitle_center.config(text="PRACTICE Self-Assessment [REVIEW MODE]", fg="yellow")
        self.update_ui()
        self.open_review_window()

    # --- Feature Logic ---

    def apply_highlight(self, event):
        if self.review_mode: return
        try:
            if self.text_question.tag_ranges(tk.SEL):
                self.text_question.tag_add("highlight", tk.SEL_FIRST, tk.SEL_LAST)
                self.text_question.tag_remove(tk.SEL, tk.SEL_FIRST, tk.SEL_LAST)
        except tk.TclError:
            pass

    def remove_highlight(self, event):
        if self.review_mode: return
        index = self.text_question.index(f"@{event.x},{event.y}")
        ranges = self.text_question.tag_ranges("highlight")
        for i in range(0, len(ranges), 2):
            start = ranges[i]
            end = ranges[i+1]
            if self.text_question.compare(start, "<=", index) and self.text_question.compare(index, "<=", end):
                self.text_question.tag_remove("highlight", start, end)
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
        if not self.questions:
            return
            
        if action == "Next":
            if self.current_index < len(self.questions) - 1:
                self.current_index += 1
                self.update_ui()
            else:
                if not self.review_mode:
                    response = messagebox.askyesno("End of Exam", "You have reached the end of the exam. Do you want to end the block and enter Review Mode?")
                    if response:
                        self.enter_review_mode()
        elif action == "Previous":
            if self.current_index > 0:
                self.current_index -= 1
                self.update_ui()
        elif action == "Pause":
            self.toggle_pause()
        elif action == "Lab Values":
            self.open_lab_values()
        elif action == "Review":
            self.open_review_window()
        else:
            messagebox.showinfo("Feature Not Implemented", f"The '{action}' feature is a placeholder.")

    def open_lab_values(self):
        if os.path.exists(LAB_VALUES_PDF_PATH):
            try:
                if sys.platform == "win32":
                    os.startfile(LAB_VALUES_PDF_PATH)
                elif sys.platform == "darwin": 
                    subprocess.call(["open", LAB_VALUES_PDF_PATH])
                else: 
                    subprocess.call(["xdg-open", LAB_VALUES_PDF_PATH])
            except Exception as e:
                messagebox.showerror("Error", f"Could not open file: {e}")
        else:
            messagebox.showerror("File Not Found", f"Could not locate Lab Values at:\n{LAB_VALUES_PDF_PATH}\n\nPlease update LAB_VALUES_PDF_PATH in the script.")

    def open_review_window(self):
        if self.review_window and self.review_window.winfo_exists():
            self.review_window.destroy()
            self.review_window = None
            return

        self.review_window = tk.Toplevel(self.root)
        self.review_window.title("Review Options")
        self.review_window.geometry("700x500")
        self.review_window.configure(bg=self.bg_white)
        self.review_window.transient(self.root)
        
        mode_text = "[REVIEW MODE ACTIVE]" if self.review_mode else "Click a question to navigate. Green = Answered, Red = Unanswered."
        tk.Label(self.review_window, text=mode_text, bg=self.bg_white, font=("Arial", 12, "bold" if self.review_mode else "normal")).pack(pady=10)
        
        canvas = tk.Canvas(self.review_window, bg=self.bg_white, borderwidth=0)
        scrollbar = ttk.Scrollbar(self.review_window, orient="vertical", command=canvas.yview)
        scrollable_frame = tk.Frame(canvas, bg=self.bg_white)

        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )

        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side="left", fill="both", expand=True, padx=20)
        scrollbar.pack(side="right", fill="y")
        
        cols = 5
        rows_per_col = math.ceil(len(self.questions) / cols) if self.questions else 1
        
        for i, q in enumerate(self.questions):
            is_answered = q.selected_option.get() != ""
            bg_color = "#d4edda" if is_answered else "#f8d7da" # Green if answered, red if not
            
            flag = " 🚩" if i in self.marked_questions else ""
            btn_text = f"#{i + 1}{flag}" # Added hashtag format
            
            # Math to calculate vertical columns instead of horizontal rows
            row = i % rows_per_col
            col = i // rows_per_col
            
            # Use tk.Label simulating a button to bypass macOS styling limitations that prevent custom 'bg' colors on tk.Buttons
            lbl_btn = tk.Label(scrollable_frame, text=btn_text, bg=bg_color, font=("Arial", 10, "bold"),
                               width=10, height=2, relief=tk.RAISED, cursor="hand2")
            lbl_btn.bind("<Button-1>", lambda e, idx=i: self.goto_question(idx, self.review_window))
            lbl_btn.grid(row=row, column=col, padx=8, pady=8)

    def goto_question(self, index, review_window):
        self.current_index = index
        self.update_ui()
        review_window.destroy()
        self.review_window = None

    def update_ui(self):
        if not self.questions:
            self.lbl_item_count.config(text="Exam Section : Item 0 of 0")
            self.text_question.config(state=tk.NORMAL)
            self.text_question.delete("1.0", tk.END)
            self.text_question.config(state=tk.DISABLED)
            for rb in self.radio_buttons:
                rb.destroy()
            self.radio_buttons.clear()
            self.lbl_preview.config(image="", text="No Preview\nAvailable")
            return
            
        q = self.questions[self.current_index]
        
        self.lbl_item_count.config(text=f"Exam Section : Item {self.current_index + 1} of {len(self.questions)}")
        
        self.chk_mark.config(state=tk.DISABLED if self.review_mode else tk.NORMAL)
        self.mark_var.set(self.current_index in self.marked_questions)
        
        self.text_question.config(state=tk.NORMAL)
        self.text_question.delete("1.0", tk.END)
        self.text_question.insert("1.0", f"{q.number}. {q.text}")
        self.text_question.config(state=tk.DISABLED)
        
        if q.image:
            thumb = q.image.copy()
            thumb.thumbnail((300, 450), Image.Resampling.LANCZOS)
            self.thumb_photo = ImageTk.PhotoImage(thumb) 
            self.lbl_preview.config(image=self.thumb_photo, text="")
        else:
            self.lbl_preview.config(image="", text="No Preview\nAvailable")

        for rb in self.radio_buttons:
            rb.destroy()
        self.radio_buttons.clear()
        
        rb_state = tk.DISABLED if self.review_mode else tk.NORMAL
        
        for opt_letter, opt_text in q.options:
            rb = tk.Radiobutton(self.options_frame, text=f"{opt_letter})  {opt_text}", 
                                variable=q.selected_option, value=opt_letter,
                                bg=self.bg_white, font=self.base_font, 
                                activebackground=self.bg_white, highlightthickness=0,
                                state=rb_state)
            rb.pack(anchor="w", pady=5)
            
            rb.is_crossed_out = False 
            rb.bind("<Alt-Button-1>", self.toggle_strikeout)
            rb.bind("<Option-Button-1>", self.toggle_strikeout)
            
            self.radio_buttons.append(rb)

    def parse_text_to_questions(self, raw_pages):
        parsed_questions = []
        
        for page_data in raw_pages:
            page_text = page_data["text"]
            page_image = page_data["image"]
            
            clean_text = re.sub(r'\\s*', '', page_text)
            
            noise_pattern = r'(Exam Section:.*?|Time Remaining:.*?\d+\s*sec|Clinical Neurology Self-Assessment|National Board of Medical Examiners|Please Wait|Mark|Previous|Next|https://t\.me/USMLENBME2CK|Lab Values|Calculator|Review|Help|Pause)'
            clean_text = re.sub(noise_pattern, '', clean_text, flags=re.IGNORECASE|re.DOTALL)
            
            q_matches = list(re.finditer(r'(\d+)\s*\.\s*(.*?\?)', clean_text, re.DOTALL))
            
            for i, q_match in enumerate(q_matches):
                q_num = q_match.group(1).strip()
                q_text = q_match.group(2).strip().replace('\n', ' ')
                
                start_idx = q_match.end()
                end_idx = q_matches[i+1].start() if i + 1 < len(q_matches) else len(clean_text)
                options_chunk = clean_text[start_idx:end_idx]
                
                options = []
                opt_matches = re.finditer(r'([A-Z])\)\s*([^\n]+)', options_chunk)
                
                for m in opt_matches:
                    letter = m.group(1).upper()
                    opt_text = m.group(2).strip()
                    
                    if opt_text:
                        options.append((letter, opt_text))
                
                if options:
                    parsed_questions.append(Question(self.root, q_num, q_text, options, image=page_image))
                
        return parsed_questions

    def load_pdf(self):
        file_path = filedialog.askopenfilename(filetypes=[("PDF files", "*.pdf"), ("Text files", "*.txt")])
        if not file_path:
            return
            
        try:
            raw_pages = []
            if file_path.endswith('.pdf'):
                doc = fitz.open(file_path)
                for page_num in range(len(doc)):
                    page = doc.load_page(page_num)
                    text = page.get_text("text") or ""
                    
                    mat = fitz.Matrix(2.0, 2.0)  
                    pix = page.get_pixmap(matrix=mat)
                    mode = "RGBA" if pix.alpha else "RGB"
                    img = Image.frombytes(mode, [pix.width, pix.height], pix.samples)
                    
                    raw_pages.append({"text": text, "image": img})
            else:
                with open(file_path, 'r', encoding='utf-8') as file:
                    chunks = file.read().split('--- PAGE')
                    for chunk in chunks:
                        raw_pages.append({"text": chunk, "image": None})
                    
            new_questions = self.parse_text_to_questions(raw_pages)
            
            if new_questions:
                self.questions = new_questions
                self.current_index = 0
                self.marked_questions.clear()
                self.review_mode = False
                
                if self.timer_job:
                    self.root.after_cancel(self.timer_job)
                
                self.lbl_subtitle_center.config(text="PRACTICE Self-Assessment", fg=self.text_white)
                
                self.time_left = len(self.questions) * 90
                self.start_timer()
                
                self.update_ui()
                messagebox.showinfo("Success", f"Loaded {len(self.questions)} questions successfully.\nTimer set for {len(self.questions) * 90} seconds.")
            else:
                messagebox.showwarning("Warning", "Could not parse any questions. Ensure the file contains strict question formats ('1. ... ?' and 'A) ...').")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to read file: {e}")

if __name__ == "__main__":
    root = tk.Tk()
    app = NBMESimulatorApp(root)
    root.mainloop()