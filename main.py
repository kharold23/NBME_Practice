import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import re
import fitz  # PyMuPDF
import pytesseract
from PIL import Image
import cv2
import numpy as np

# Optional imports for Excel export
try:
    import pandas as pd
    PANDAS_AVAILABLE = True
except ImportError:
    PANDAS_AVAILABLE = False

# If on Windows, uncomment and update the line below to point to your Tesseract installation:
# pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

class EditableQuestion:
    def __init__(self, text, options, inverted=False, instructions=""):
        self.instructions = instructions.strip()
        self.text = text.strip()
        self.options = [opt.strip() for opt in options]  # List of parsed options
        self.image_field = ""  
        self.correct_answer = ""
        self.explanation = ""

class QuestionEditorApp:
    def __init__(self, root):
        self.root = root
        self.root.title("PDF Question Parser & Editor")
        self.root.geometry("900x800")
        self.root.configure(bg="#f4f4f4")
        
        self.questions = []
        self.current_index = 0
        self.cancel_ocr = False
        
        self.create_widgets()

    def create_widgets(self):
        # --- Top Control Bar ---
        self.top_frame = tk.Frame(self.root, bg="#0a2240", height=60)
        self.top_frame.pack(side=tk.TOP, fill=tk.X)
        self.top_frame.pack_propagate(False)
        
        btn_load = tk.Button(self.top_frame, text="Load & OCR PDF", command=self.load_pdf, 
                             bg="white", font=("Arial", 10, "bold"), relief=tk.FLAT)
        btn_load.pack(side=tk.LEFT, padx=20, pady=15)
        
        self.lbl_tracker = tk.Label(self.top_frame, text="No PDF Loaded", 
                                    bg="#0a2240", fg="white", font=("Arial", 12, "bold"))
        self.lbl_tracker.pack(side=tk.LEFT, expand=True)

        # --- EXPORT BUTTON ---
        btn_export = tk.Button(self.top_frame, text="Export to Excel", command=self.export_to_excel, 
                               bg="#28a745", fg="white", font=("Arial", 10, "bold"), relief=tk.FLAT)
        btn_export.pack(side=tk.RIGHT, padx=20, pady=15)

        # --- Main Scrollable Area ---
        self.main_container = tk.Frame(self.root, bg="#f4f4f4")
        self.main_container.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        self.canvas = tk.Canvas(self.main_container, bg="#f4f4f4", highlightthickness=0, yscrollincrement="10")
        self.scrollbar = ttk.Scrollbar(self.main_container, orient="vertical", command=self.canvas.yview)
        
        self.scrollable_frame = tk.Frame(self.canvas, bg="#f4f4f4")
        self.scrollable_frame.bind(
            "<Configure>",
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        )
        
        self.canvas_window = self.canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        self.canvas.bind('<Configure>', lambda e: self.canvas.itemconfig(self.canvas_window, width=e.width))
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        
        self.canvas.pack(side="left", fill="both", expand=True, padx=20, pady=10)
        self.scrollbar.pack(side="right", fill="y")
        
        self._bind_mousewheel(self.canvas)
        self._bind_mousewheel(self.scrollable_frame)

        self.build_editor_form()

        # --- Bottom Navigation Bar ---
        self.bottom_frame = tk.Frame(self.root, bg="#e0e0e0", height=60)
        self.bottom_frame.pack(side=tk.BOTTOM, fill=tk.X)
        self.bottom_frame.pack_propagate(False)

        btn_prev = tk.Button(self.bottom_frame, text="<< Previous", command=self.prev_question, 
                             font=("Arial", 10, "bold"), relief=tk.RAISED)
        btn_prev.pack(side=tk.LEFT, padx=20, pady=15)

        btn_next = tk.Button(self.bottom_frame, text="Next >>", command=self.next_question, 
                             font=("Arial", 10, "bold"), relief=tk.RAISED)
        btn_next.pack(side=tk.RIGHT, padx=20, pady=15)

    def build_editor_form(self):
        """Builds the static layout of text boxes."""
        font_lbl = ("Arial", 10, "bold")
        font_txt = ("Arial", 11)
        
        def create_text_field(parent, label_text, height=4):
            frame = tk.Frame(parent, bg="#f4f4f4")
            frame.pack(fill=tk.X, pady=5)
            tk.Label(frame, text=label_text, bg="#f4f4f4", font=font_lbl).pack(anchor="w")
            txt = tk.Text(frame, height=height, font=font_txt, wrap=tk.WORD, relief=tk.SOLID, bd=1)
            txt.pack(fill=tk.X, pady=2)
            self._bind_mousewheel(txt)
            return txt

        def create_entry_field(parent, label_text):
            frame = tk.Frame(parent, bg="#f4f4f4")
            frame.pack(fill=tk.X, pady=5)
            tk.Label(frame, text=label_text, bg="#f4f4f4", font=font_lbl).pack(side=tk.LEFT)
            entry = tk.Entry(frame, font=font_txt, relief=tk.SOLID, bd=1)
            entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(10, 0))
            return entry

        self.txt_instructions = create_text_field(self.scrollable_frame, "Instructions (Inverted Formats):", height=2)
        self.txt_question = create_text_field(self.scrollable_frame, "Question Text:", height=5)
        self.ent_image = create_entry_field(self.scrollable_frame, "Image Reference/Path:")
        
        # Answer Choices (A through J supported)
        tk.Label(self.scrollable_frame, text="Answer Choices:", bg="#f4f4f4", font=font_lbl).pack(anchor="w", pady=(10, 0))
        self.choice_texts = {}
        choices_frame = tk.Frame(self.scrollable_frame, bg="#f4f4f4")
        choices_frame.pack(fill=tk.X)
        
        for i, char in enumerate("ABCDEFGHIJ"):
            row_frame = tk.Frame(choices_frame, bg="#f4f4f4")
            row_frame.pack(fill=tk.X, pady=2)
            tk.Label(row_frame, text=f"{char})", bg="#f4f4f4", font=font_lbl, width=3).pack(side=tk.LEFT)
            txt = tk.Text(row_frame, height=2, font=font_txt, wrap=tk.WORD, relief=tk.SOLID, bd=1)
            txt.pack(side=tk.LEFT, fill=tk.X, expand=True)
            self._bind_mousewheel(txt)
            self.choice_texts[char] = txt

        self.ent_correct = create_entry_field(self.scrollable_frame, "Correct Answer:")
        self.txt_explanation = create_text_field(self.scrollable_frame, "Explanation:", height=6)

        self.set_fields_state(tk.DISABLED)

    def set_fields_state(self, state):
        for widget in [self.txt_instructions, self.txt_question, self.ent_image, self.ent_correct, self.txt_explanation]:
            widget.config(state=state)
        for txt in self.choice_texts.values():
            txt.config(state=state)

    def clear_form(self):
        self.set_fields_state(tk.NORMAL)
        for txt in [self.txt_instructions, self.txt_question, self.txt_explanation]:
            txt.delete("1.0", tk.END)
        for ent in [self.ent_image, self.ent_correct]:
            ent.delete(0, tk.END)
        for txt in self.choice_texts.values():
            txt.delete("1.0", tk.END)

    def load_question(self):
        if not self.questions: return
        self.clear_form()
        q = self.questions[self.current_index]
        self.lbl_tracker.config(text=f"Editing Question {self.current_index + 1} of {len(self.questions)}")
        
        self.txt_instructions.insert("1.0", q.instructions)
        self.txt_question.insert("1.0", q.text)
        self.ent_image.insert(0, q.image_field)
        
        for i, opt_text in enumerate(q.options):
            if i < len(self.choice_texts):
                char = chr(65 + i) 
                self.choice_texts[char].insert("1.0", opt_text)
                
        self.ent_correct.insert(0, q.correct_answer)
        self.txt_explanation.insert("1.0", q.explanation)
        self.canvas.yview_moveto(0)

    def save_current_question(self):
        if not self.questions: return
        q = self.questions[self.current_index]
        
        q.instructions = self.txt_instructions.get("1.0", tk.END).strip()
        q.text = self.txt_question.get("1.0", tk.END).strip()
        q.image_field = self.ent_image.get().strip()
        q.correct_answer = self.ent_correct.get().strip()
        q.explanation = self.txt_explanation.get("1.0", tk.END).strip()
        
        new_options = []
        for char in "ABCDEFGHIJ":
            opt_text = self.choice_texts[char].get("1.0", tk.END).strip()
            if opt_text:  
                new_options.append(opt_text)
        q.options = new_options

    def next_question(self):
        if self.questions and self.current_index < len(self.questions) - 1:
            self.save_current_question()
            self.current_index += 1
            self.load_question()

    def prev_question(self):
        if self.questions and self.current_index > 0:
            self.save_current_question()
            self.current_index -= 1
            self.load_question()

    # ==========================================
    # EXCEL EXPORT LOGIC 
    # ==========================================
    def export_to_excel(self):
        if not self.questions:
            messagebox.showwarning("Empty", "No questions available to export.")
            return

        if not PANDAS_AVAILABLE:
            messagebox.showerror("Missing Dependency", "The 'pandas' and 'openpyxl' libraries are required for this feature.\n\nPlease run:\npip install pandas openpyxl")
            return

        # Ensure the currently visible question is saved before generating the export
        self.save_current_question()

        file_path = filedialog.asksaveasfilename(
            defaultextension=".xlsx",
            filetypes=[("Excel files", "*.xlsx")],
            title="Export to Excel"
        )
        
        if not file_path: 
            return

        try:
            export_data = []
            
            for i, q in enumerate(self.questions):
                row_dict = {
                    "Question Number": i + 1,
                    "Instructions": q.instructions,
                    "Question Text": q.text,
                    "Image Reference": q.image_field
                }
                
                # Dynamically assign options A through J to their respective columns
                for j in range(10):
                    char = chr(65 + j)  # 'A', 'B', 'C', etc.
                    if j < len(q.options):
                        row_dict[f"Option {char}"] = q.options[j]
                    else:
                        row_dict[f"Option {char}"] = "" 
                
                row_dict["Correct Answer"] = q.correct_answer
                row_dict["Explanation"] = q.explanation
                
                export_data.append(row_dict)

            # Convert to DataFrame and Export
            df = pd.DataFrame(export_data)
            
            # Write to Excel without the DataFrame index
            df.to_excel(file_path, index=False)
            messagebox.showinfo("Export Successful", f"Successfully exported {len(self.questions)} questions to:\n\n{file_path}")

        except Exception as e:
            messagebox.showerror("Export Error", f"An error occurred while exporting to Excel:\n\n{str(e)}")

    # ==========================================
    # PDF & OCR LOGIC 
    # ==========================================
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
                cv2.rectangle(img_bgr, (x-1, y-1), (x+w+2, y+h+2), (255, 255, 255), -1)

        final_pil = Image.fromarray(cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)).convert("L")
        final_pil = final_pil.point(lambda p: 255 if p > 120 else p)
        return final_pil.convert("RGB")

    def parse_text_to_questions(self, raw_pages):
        parsed_questions = []
        inverted_q_remaining = 0

        for page_data in raw_pages:
            clean_text = page_data["text"].strip()
            options = []

            clean_text = re.sub(r'[1|lI]\)', 'I)', clean_text)
            
            inv_trigger = re.search(r'The\s+response\s+options\s+for\s+the\s+next\s+(\d+)', clean_text, re.IGNORECASE)
            if inv_trigger:
                inverted_q_remaining = int(inv_trigger.group(1))

            if inverted_q_remaining > 0:
                split_point = re.search(r'A\)', clean_text)
                if split_point:
                    i_text = clean_text[:split_point.start()]
                    instructions = i_text.replace('\n', ' ')
                    match = re.search(r'^(\d+)\.', clean_text, re.MULTILINE)
                    if match:
                        q_text = clean_text[match.start():].replace('\n', ' ')
                    else:
                        q_text = ""

                    answers_block = clean_text[split_point.start():match.start() if match else len(clean_text)]
                    options_messy = re.split(r'(?=[A-Z]\))', answers_block)
                    options = [re.split(r'\n|\t| {2,}', item.strip())[0] for item in options_messy[1:]]
                    options.sort()

                    if options:
                        parsed_questions.append(EditableQuestion(q_text, options, inverted=True, instructions=instructions))
                
                inverted_q_remaining -= 1
                continue
            
            match = re.search(r'^(\d+)\.', clean_text, re.DOTALL)
            split_point = re.search(r'A\)', clean_text)
            
            if split_point:
                q_text = clean_text[:split_point.start()].replace('\n', ' ')
                answers_block = clean_text[split_point.start():]
                options_messy = re.split(r'(?=[A-Z]\))', answers_block)
                options = [re.split(r'\n|\t| {2,}', item.strip())[0] for item in options_messy[1:]]
                options.sort()

            if options:
                parsed_questions.append(EditableQuestion(q_text, options, inverted=False))
                
        return parsed_questions

    def load_pdf(self):
        file_path = filedialog.askopenfilename(filetypes=[("PDF files", "*.pdf")])
        if not file_path: return
            
        try:
            doc = fitz.open(file_path)
            total_pages = len(doc)
            
            progress_win = tk.Toplevel(self.root)
            progress_win.title("OCRing Document")
            progress_win.geometry("300x130")
            progress_win.transient(self.root)
            progress_win.grab_set() 
            
            self.cancel_ocr = False
            def on_close_progress():
                self.cancel_ocr = True
                progress_win.destroy()
                
            progress_win.protocol("WM_DELETE_WINDOW", on_close_progress)
            
            tk.Label(progress_win, text="Preprocessing and OCRing...").pack(pady=10)
            progress_bar = ttk.Progressbar(progress_win, orient=tk.HORIZONTAL, length=250, mode='determinate', maximum=total_pages)
            progress_bar.pack(pady=10)
            progress_lbl = tk.Label(progress_win, text=f"Page 0 of {total_pages}")
            progress_lbl.pack()

            raw_pages = []
            
            for page_num in range(total_pages):
                if self.cancel_ocr:
                    messagebox.showinfo("Cancelled", "PDF OCR was cancelled.")
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
                text = pytesseract.image_to_string(final_img, config='--psm 6')

                raw_pages.append({
                    "text": text, 
                    "page_num": page_num + 1
                })

            if not self.cancel_ocr and progress_win.winfo_exists():
                progress_win.destroy()

            # Parse and Load
            new_questions = self.parse_text_to_questions(raw_pages)
            
            if new_questions:
                self.questions = new_questions
                self.current_index = 0
                self.load_question()
                messagebox.showinfo("Success", f"Successfully extracted {len(self.questions)} questions ready for editing.")
            else:
                messagebox.showwarning("Warning", "Could not parse any questions.")

        except Exception as e:
            if 'progress_win' in locals() and progress_win.winfo_exists(): 
                progress_win.destroy()
            messagebox.showerror("Error", f"Failed to read file: {e}")

    # ==========================================
    # UTILS
    # ==========================================
    def _bind_mousewheel(self, widget):
        widget.bind("<MouseWheel>", self._on_mousewheel)
        widget.bind("<Button-4>", self._on_mousewheel)
        widget.bind("<Button-5>", self._on_mousewheel)

    def _on_mousewheel(self, event):
        if isinstance(event.widget, tk.Text):
            if event.delta > 0 or event.num == 4:  
                if event.widget.yview()[0] == 0.0:
                    self.canvas.yview_scroll(int(-1 * (event.delta / 120)) if event.delta else -1, "units")
                    return "break"
            else:  
                if event.widget.yview()[1] == 1.0:
                    self.canvas.yview_scroll(int(-1 * (event.delta / 120)) if event.delta else 1, "units")
                    return "break"
            return 
            
        import sys
        if event.num == 4:
            delta = -1
        elif event.num == 5:
            delta = 1
        elif sys.platform == "darwin":
            delta = int(-event.delta)
        else:
            delta = int(-event.delta / 120)
            
        self.canvas.yview_scroll(delta, "units")
        return "break"

if __name__ == "__main__":
    root = tk.Tk()
    app = QuestionEditorApp(root)
    root.mainloop()