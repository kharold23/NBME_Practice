# NBME Self-Assessment Simulator

This application is a desktop-based interactive simulator designed to mimic the National Board of Medical Examiners (NBME) test-taking interface. It allows users to load a PDF of practice questions, tracks time, and provides standard NBME tools like highlighting, answer strike-outs, and a question review screen.

Created by Kaitlin Harold, VP&S c/o 2028, with the help of Google Gemini

For suggestions on how to improve, feel free to send me a GroupMe message or post in Issues!

## 🛠️ Prerequisites & Installation

This application requires **Python 3.x**. To run the code, you will need to install a few third-party Python libraries that handle PDF extraction and image rendering.

<details>
  <summary><b><u>MacOS Users</b></u>
  </summary>
  First install Homebrew. Open your terminal or command prompt and run the following commands:

  ```bash
bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

Then install the required libraries to run the program:

```bash
brew install tesseract
pip3 install -r requirements.txt
```

</details>

<details>
  <summary><b><u>Windows Users</b></u>
  </summary>

Open your terminal or command prompt and run the following commands:

```bash
winget install -e --id UB-Mannheim.TesseractOCR

pip3 install -r requirements.txt
```
<br>

Important Post-Installation Setup:
<div style="margin-left: 30px;">
If you are using Tesseract with Python (e.g., via the pytesseract library), you often need to ensure the system knows where the executable is located if it wasn't added to your PATH automatically.
<br><br>
By default, it usually installs to C:\Program Files\Tesseract-OCR\tesseract.exe.
<br><br>

If the "tesseract --version" command does not work, you must manually add the installation folder to your Windows Environment:
* Search for "Edit the system environment variables" in your Windows Start menu.
* Click Environment Variables > System variables > Path > Edit > New. Then paste the path to your Tesseract folder (e.g., C:\Program Files\Tesseract-OCR).
* Click OK on all windows.
</div>

<b>*Also be sure to uncomment line 21 in main.py*</b>

---
</details>

<br>
<b><u>Libraries:</b></u>

* **PyMuPDF:** Imported as fitz. Used for loading, parsing, and rendering the PDF files.
* **pytesseract:** Used to perform OCR (Optical Character Recognition) on the extracted PDF pages.
* **Pillow:** Imported as PIL. Used for image manipulation, scaling, and handling image data for the Tkinter UI (ImageTk).
opencv-python: Imported as cv2. Used for image preprocessing, thresholding, and dynamic chart redaction before OCR.
* **numpy:** Imported as np. Used alongside OpenCV for matrix and array operations during image processing.
* **reportlab:** Used to generate the PDF export in the review module, translating Tkinter GUI text formatting into a structured document.

---

## 📖 How to Use the Interface

### 1. Loading an Exam

* Launch the application by running the Python script.
* Click the **"Load PDF"** button in the bottom left corner.
* Select your PDF file. The parser specifically looks for questions formatted with a number followed by a period (e.g., `1.`) and ending with a question mark (`?`), with answer options formatted with capital letters and a parenthesis (e.g., `A)`).
    * For best results, the PDF should be screenshots of the NBME exam (like those provided in the shared drive). For example:
![Screenshot of an NBME practice test question](PDF_Example.png "NBME Practice Test")
* Once loaded, the timer will automatically start (calculated at 90 seconds per question).



### 2. Taking the Test

* **Answering:** Standard click on the radio buttons to select an answer.
* **Process of Elimination (Strike-out):** Hold `Alt` (Windows) or `Option` (Mac) and click on an answer text to cross it out. Click again with the modifier key to remove the strike-out.
* **Highlighting:** Click and drag your mouse over any text in the question box to highlight it in yellow. To remove a highlight, simply click anywhere on the existing yellow highlighted text.
* **Marking:** Check the **"Mark"** box in the top-left corner to flag a question for later review.
* **Viewing Images:** If the PDF page contains an image (or is a screenshot), a thumbnail preview will appear on the right side of the screen. Click the thumbnail to open a scaled, full-size view of the image. Click the full-size image to close it.

### 3. Navigation & Tools

* **Next / Previous:** Use these buttons to navigate chronologically through the block.
* **Pause:** Halts the timer and brings up a full-screen block to hide the exam content while you step away.
* **Lab Values:** Attempts to open the local PDF specified in your configuration using your computer's default PDF viewer.
* **Review:** Opens a grid interface showing all questions in the block.
* 🟢 **Green:** Answered
* 🔴 **Red:** Unanswered
* 🚩 **Flag:** Marked for review
* Clicking any button in the review grid will immediately jump you to that question.



### 4. Review Mode

If the timer reaches `0 hr 00 min 00 sec`, or if you manually choose to end the block after the last question, the application enters **Review Mode**.

* The header will turn yellow to indicate you are in Review Mode.
* The timer will stop.
* All answer choices, highlighters, and checkboxes will be locked to prevent further changes while you review your work.