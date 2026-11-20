"""
Exhibit Stamper - VS Code / Python version
==========================================

What it does
  * You pick the case folder (e.g. "613_Vishio Watkins-Laurel") and a place to save.
  * Loose PDFs with an exhibit number ("Ex. 1 POLICY.pdf", "EX. 40 ...pdf") are stamped.
  * Exhibit folders ("Ex. 5 Correspondence between counsel") -> only the FIRST PDF,
    in Windows File Explorer order, is stamped (subfolders are searched if the folder
    has no PDFs of its own).
  * Folders with "stamped" in the name (earlier output) are skipped, at any level.
  * Anything without an exhibit number (".PTC Order 10.6.26.pdf") is left alone.
  * The label goes on page 1 only, bottom-right. If that corner has text, it tries the
    other corners; if every corner is busy it still uses bottom-right and tells you.
  * Only the stamped PDFs are saved, in a NEW folder "<case folder> - Stamped",
    keeping each one inside its exhibit folder. Your originals are never changed.

One-time setup (VS Code terminal):
    pip install pymupdf

Run:
    Open this file in VS Code and press the Run button (or F5).
    First choose Petitioner or Plaintiff, then the case folder, then where to save.

    Or from the terminal:
    python stamp_exhibits.py "C:\\path\\to\\613_Vishio Watkins-Laurel" "C:\\path\\to\\save\\here" Plaintiff

For a new case, change only the CASE settings below.
"""

import os
import re
import sys
import time

try:
    import pymupdf as fitz  # PyMuPDF >= 1.24
except ImportError:
    try:
        import fitz
    except ImportError:
        sys.exit("PyMuPDF is missing. In the VS Code terminal run:  pip install pymupdf")

# ---------------------------------------------------------------------------
# CASE SETTINGS - change these for each case
# ---------------------------------------------------------------------------
CASE = {
    # First party: one string per line on the label
    "party1": ["Oxford Pointe at Crown", "Colony Condo Asso Inc."],
    "party2": "American Coastal",
    "case_no": "25-CA-005561",
    "side": "Petitioner",          # default; you're asked each run (see SIDES)
}

# Choices offered when the script starts. Add "Respondent" or "Defendant" here if needed.
SIDES = ["Petitioner", "Plaintiff"]

# Label look (points; 72 points = 1 inch)
FONT = "tiro"          # built-in Times Roman
FONT_SIZE = 7.5
LINE_H = FONT_SIZE * 1.25
BORDER = 2.2           # thick black border like the sample
PAD_X = 6.2
PAD_Y = 4.6
CORNER_MARGIN = 20     # distance from the page edge (0.28 in)

# ---------------------------------------------------------------------------
# Exhibit numbers and File Explorer ordering
# ---------------------------------------------------------------------------
NUM_RE = re.compile(r"^\s*(?:ex(?:hibit|h)?\.?\s*(?:no\.?|#)?\s*)?(\d+(?:\s*[-\u2013]\s*\d+)?)", re.I)
EXHIBIT_FOLDER_RE = re.compile(r"^\s*ex(?:hibit|h)?\b", re.I)
JUNK = {"thumbs.db", "desktop.ini", ".ds_store"}


def is_stamped_folder(name):
    """Folders with 'stamped' in the name are earlier output - always skipped."""
    return "stamped" in name.lower()


def exhibit_number(name):
    m = NUM_RE.match(name)
    return re.sub(r"\s+", "", m.group(1)).replace("\u2013", "-") if m else None


def explorer_key(name):
    """Natural sort like Windows File Explorer: 'Ex. 2' before 'Ex. 10', case-insensitive."""
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", name)]


def is_pdf(name):
    return name.lower().endswith(".pdf")


def first_pdf(folder):
    """First PDF as File Explorer shows it; the folder's own PDFs first, then subfolders."""
    try:
        names = sorted(os.listdir(folder), key=explorer_key)
    except OSError:
        return None
    pdfs = [n for n in names if is_pdf(n) and os.path.isfile(os.path.join(folder, n))]
    if pdfs:
        return os.path.join(folder, pdfs[0])
    for n in names:
        sub = os.path.join(folder, n)
        if os.path.isdir(sub) and not is_stamped_folder(n):
            hit = first_pdf(sub)
            if hit:
                return hit
    return None


def collect_jobs(case_dir):
    """Returns (jobs, notes). jobs = [(number, pdf_path, exhibit_folder_name_or_None)]."""
    root = case_dir
    # If the chosen folder only wraps one non-exhibit folder, look inside it.
    while True:
        kids = [n for n in os.listdir(root) if n.lower() not in JUNK
                and not (is_stamped_folder(n) and os.path.isdir(os.path.join(root, n)))]
        if len(kids) == 1 and os.path.isdir(os.path.join(root, kids[0])) and not EXHIBIT_FOLDER_RE.match(kids[0]):
            root = os.path.join(root, kids[0])
        else:
            break
    jobs, notes = [], []
    for name in sorted(os.listdir(root), key=explorer_key):
        path = os.path.join(root, name)
        if name.lower() in JUNK:
            continue
        num = exhibit_number(name)
        if os.path.isdir(path):
            if is_stamped_folder(name):
                notes.append(f"Folder '{name}' - name has 'stamped', skipped")
                continue
            if num is None:
                notes.append(f"Folder '{name}' - no exhibit number, not stamped")
                continue
            pdf = first_pdf(path)
            if pdf is None:
                notes.append(f"Folder '{name}' - No PDF found, not stamped")
                continue
            jobs.append((num, pdf, name))
        elif is_pdf(name):
            if num is None:
                notes.append(f"'{name}' - no exhibit number, left alone")
                continue
            jobs.append((num, path, None))
    jobs.sort(key=lambda j: (explorer_key(j[0]), explorer_key(j[1])))
    return root, jobs, notes


# ---------------------------------------------------------------------------
# Label drawing
# ---------------------------------------------------------------------------
def tw(text):
    return fitz.get_text_length(text, fontname=FONT, fontsize=FONT_SIZE)


GAP = 12
SLOT_W = tw("00-00") + 3.5  # blank space after "Exhibit #:"


def label_size():
    first = CASE["party1"][0]
    row1 = tw(first) + GAP + tw("Case #: " + CASE["case_no"])
    other = max([tw(t) for t in CASE["party1"][1:]] + [0])
    last = tw(CASE["party2"]) + GAP + tw(CASE["side"]) + GAP * 0.8 + tw("Exhibit #:") + 2 + SLOT_W
    rows = len(CASE["party1"]) + 2  # party1 lines + "vs" + last line
    w = max(row1, other, last) + 2 * PAD_X
    h = rows * LINE_H + 2 * PAD_Y
    return w, h, rows


LABEL_W, LABEL_H, LABEL_ROWS = label_size()


def set_side(side):
    """Switch Petitioner/Plaintiff and resize the label to fit."""
    global LABEL_W, LABEL_H, LABEL_ROWS
    CASE["side"] = side
    LABEL_W, LABEL_H, LABEL_ROWS = label_size()


def pick_side():
    """Small window with one button per side. Returns the chosen side."""
    import tkinter as tk
    choice = {}
    win = tk.Tk()
    win.title("Exhibit Stamper")
    win.attributes("-topmost", True)
    tk.Label(win, text="Which label should be stamped?", font=("Segoe UI", 11), padx=20, pady=12).pack()
    row = tk.Frame(win, padx=20, pady=10)
    row.pack()
    for side in SIDES:
        tk.Button(row, text=side, width=14, font=("Segoe UI", 10),
                  command=lambda s=side: (choice.update(side=s), win.destroy())).pack(side="left", padx=6)
    win.mainloop()
    if "side" not in choice:
        sys.exit("No label chosen.")
    return choice["side"]


def corner_rect(page, corner):
    """Label rectangle in the page's visible (rotated) coordinates."""
    W, H = page.rect.width, page.rect.height
    m = CORNER_MARGIN
    x = W - m - LABEL_W if "right" in corner else m
    y = H - m - LABEL_H if "bottom" in corner else m
    return fitz.Rect(x, y, x + LABEL_W, y + LABEL_H)


def corner_is_clear(page, rect):
    for b in page.get_text("blocks"):
        if fitz.Rect(b[:4]).intersects(rect) and b[4].strip():
            return False
    for img in page.get_image_info():
        r = fitz.Rect(img["bbox"])
        # ignore full-page images (scans) - otherwise nothing would ever be clear
        if r.intersects(rect) and r.get_area() < page.rect.get_area() * 0.8:
            return False
    return True


def already_stamped(page):
    txt = page.get_text()
    return "Case #: " + CASE["case_no"] in txt and "Exhibit #:" in txt


def draw_label(page, rect, number):
    """Draws border + text. rect is in visible coordinates; works on rotated pages too."""
    to_pdf = page.derotation_matrix
    rot = page.rotation
    shape = page.new_shape()
    shape.draw_rect(fitz.Rect(rect) * to_pdf)
    shape.finish(color=(0, 0, 0), fill=(1, 1, 1), width=BORDER)
    shape.commit()

    def put(x, row, text):
        # baseline of the given row, in visible coordinates
        y = rect.y0 + PAD_Y + LINE_H * row + LINE_H * 0.78
        page.insert_text(fitz.Point(x, y) * to_pdf, text, fontname=FONT, fontsize=FONT_SIZE,
                         color=(0, 0, 0), rotate=rot)

    left, right = rect.x0 + PAD_X, rect.x1 - PAD_X
    p1 = CASE["party1"]
    put(left, 0, p1[0])
    case_txt = "Case #: " + CASE["case_no"]
    put(right - tw(case_txt), 0, case_txt)
    for i, line in enumerate(p1[1:], start=1):
        put(left, i, line)
    put(left, len(p1), "vs")
    last = len(p1) + 1
    slot_right = right
    slot_left = slot_right - SLOT_W
    ex_x = slot_left - 2 - tw("Exhibit #:")
    put(ex_x, last, "Exhibit #:")
    put(ex_x - GAP * 0.8 - tw(CASE["side"]), last, CASE["side"])
    put(left, last, CASE["party2"])
    num = str(number)
    put((slot_left + slot_right) / 2 - tw(num) / 2, last, num)


def stamp_pdf(src, dst, number):
    doc = fitz.open(src)
    try:
        if doc.needs_pass:
            return "skipped - password protected"
        page = doc[0]
        if already_stamped(page):
            return "skipped - already has this label"
        status = "ok"
        rect = None
        for corner in ("bottom-right", "bottom-left", "top-left", "top-right"):
            r = corner_rect(page, corner)
            if corner_is_clear(page, r):
                rect = r
                if corner != "bottom-right":
                    status = f"ok - bottom-right had text, placed {corner}"
                break
        if rect is None:
            rect = corner_rect(page, "bottom-right")
            status = "CHECK - no clear corner, placed bottom-right over content"
        draw_label(page, rect, number)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        doc.save(dst, garbage=1, deflate=True)
        return status
    finally:
        doc.close()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def pick_folders():
    import tkinter as tk
    from tkinter import filedialog
    tk_root = tk.Tk()
    tk_root.withdraw()
    tk_root.attributes("-topmost", True)
    src = filedialog.askdirectory(title="1) Choose the CASE folder with the exhibits")
    if not src:
        sys.exit("No case folder chosen.")
    out = filedialog.askdirectory(title="2) Choose WHERE to save the stamped PDFs")
    if not out:
        sys.exit("No save location chosen.")
    tk_root.destroy()
    return src, out


def unique_dir(path):
    if not os.path.exists(path):
        return path
    n = 2
    while os.path.exists(f"{path} ({n})"):
        n += 1
    return f"{path} ({n})"


def fmt(sec):
    sec = max(1, round(sec))
    return f"{sec} s" if sec < 60 else f"{sec // 60} min {sec % 60} s"


def main():
    # Optional 3rd argument: Petitioner or Plaintiff, e.g.
    #   python stamp_exhibits.py "C:\\case folder" "C:\\save here" Plaintiff
    if len(sys.argv) >= 4:
        side = next((s for s in SIDES if s.lower() == sys.argv[3].lower()), None)
        if not side:
            sys.exit(f"Unknown side '{sys.argv[3]}'. Use one of: {', '.join(SIDES)}")
    else:
        side = pick_side()
    set_side(side)
    if len(sys.argv) >= 3:
        src, out_parent = sys.argv[1], sys.argv[2]
    else:
        src, out_parent = pick_folders()
    src, out_parent = os.path.abspath(src), os.path.abspath(out_parent)

    root, jobs, notes = collect_jobs(src)
    if not jobs:
        sys.exit("No numbered exhibits found in " + root)
    out_dir = unique_dir(os.path.join(out_parent, os.path.basename(root) + " - Stamped"))

    print(f"Case folder : {root}")
    print(f"Saving to   : {out_dir}")
    print(f"Label       : {CASE['side']} - {LABEL_W / 72:.2f} in x {LABEL_H / 72:.2f} in")
    print(f"Exhibits    : {len(jobs)} to stamp\n")

    total = sum(os.path.getsize(p) for _, p, _ in jobs) or 1
    done, t0 = 0, time.time()
    report = []
    for i, (num, pdf, folder) in enumerate(jobs, 1):
        rel = os.path.relpath(pdf, root)
        try:
            status = stamp_pdf(pdf, os.path.join(out_dir, rel), num)
        except Exception as e:  # damaged PDF etc.
            status = f"ERROR - {e}"
        done += os.path.getsize(pdf)
        elapsed = time.time() - t0
        left = elapsed / (done / total) - elapsed
        shown = f"[{folder}] {os.path.basename(pdf)}" if folder else os.path.basename(pdf)
        print(f"{i:>3}/{len(jobs)}  Ex. {num:<6} {shown}  ->  {status}   "
              f"({done * 100 // total}% - about {fmt(left)} left)")
        report.append(f"Ex. {num}\t{rel}\t{status}")

    print(f"\nDone in {fmt(time.time() - t0)}.")
    if notes:
        print("\nNot stamped:")
        for n in notes:
            print("  - " + n)
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "stamp report.txt"), "w", encoding="utf-8") as f:
        f.write("Exhibit\tFile\tResult\n" + "\n".join(report))
        if notes:
            f.write("\n\nNot stamped:\n" + "\n".join(notes))
    print(f"\nSaved to: {out_dir}")
    if os.name == "nt":
        os.startfile(out_dir)  # open the folder in File Explorer


if __name__ == "__main__":
    main()
