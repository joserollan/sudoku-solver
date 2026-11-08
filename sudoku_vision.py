"""Read a Sudoku from a photo.

Pipeline (read_sudoku does all of it):
  1. decode the upload, honouring the phone's EXIF rotation
  2. find the grid's outer border: the largest 4-cornered outline in a
     thresholded copy of the picture
  3. perspective-warp that quadrilateral into a flat square
  4. turn it upright if the photo was sideways / upside down
  5. split into 81 cells, cut out the digit in each non-empty one, and
     read the digits with Tesseract (3 readings per digit, majority vote)
"""

import io

import cv2
import numpy as np
from PIL import Image, ImageOps

# Detection runs on a downscaled copy; corners are scaled back afterwards.
_WORK_SIZE = 1000


def load_image(data: bytes) -> np.ndarray:
    """Decode image bytes into a BGR array, applying EXIF orientation.

    Phones often store photos sideways plus an EXIF "rotate me" flag;
    without exif_transpose the grid would be detected rotated.
    """
    img = ImageOps.exif_transpose(Image.open(io.BytesIO(data))).convert("RGB")
    return cv2.cvtColor(np.asarray(img), cv2.COLOR_RGB2BGR)


def order_corners(pts: np.ndarray) -> np.ndarray:
    """Return 4 points ordered top-left, top-right, bottom-right, bottom-left."""
    pts = np.asarray(pts, dtype=np.float32).reshape(4, 2)
    s = pts.sum(axis=1)             # x + y: smallest at TL, largest at BR
    d = np.diff(pts, axis=1).ravel()  # y - x: smallest at TR, largest at BL
    return np.array(
        [pts[np.argmin(s)], pts[np.argmin(d)], pts[np.argmax(s)], pts[np.argmax(d)]],
        dtype=np.float32,
    )


def find_grid_corners(img: np.ndarray):
    """Locate the Sudoku's outer border.

    Returns a (4, 2) float32 array of corners (TL, TR, BR, BL) in the
    coordinates of `img`, or None if no plausible grid was found.
    """
    h, w = img.shape[:2]
    scale = _WORK_SIZE / max(h, w)
    small = cv2.resize(img, (round(w * scale), round(h * scale)), interpolation=cv2.INTER_AREA)

    gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
    gray = cv2.GaussianBlur(gray, (7, 7), 0)
    # Adaptive threshold copes with uneven lighting / shadows on paper.
    # Window of 51px (at the 1000px working size): smaller windows break
    # the blurry outer border into pieces. Tuned on a 200-photo newspaper
    # dataset; 41-71 all score the same (~99% of grids within half a cell).
    binary = cv2.adaptiveThreshold(
        gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 51, 5
    )
    # Close small gaps so the border is one connected outline.
    binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))

    contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    min_area = 0.05 * small.shape[0] * small.shape[1]

    for contour in sorted(contours, key=cv2.contourArea, reverse=True)[:5]:
        if cv2.contourArea(contour) < min_area:
            break
        hull = cv2.convexHull(contour)
        perimeter = cv2.arcLength(hull, True)
        # Loosen the polygon fit until the outline collapses to 4 corners.
        for eps in (0.01, 0.02, 0.03, 0.05):
            approx = cv2.approxPolyDP(hull, eps * perimeter, True)
            if len(approx) == 4:
                corners = order_corners(approx)
                if _looks_like_grid(corners):
                    return corners / scale
                break
    return None


def _looks_like_grid(corners: np.ndarray) -> bool:
    """Reject quadrilaterals far from a square (seen at an angle)."""
    tl, tr, br, bl = corners
    sides = [np.linalg.norm(a - b) for a, b in ((tl, tr), (tr, br), (br, bl), (bl, tl))]
    return min(sides) > 0 and max(sides) / min(sides) < 2.5


def warp_grid(img: np.ndarray, corners: np.ndarray, size: int = 450) -> np.ndarray:
    """Perspective-warp the grid inside `corners` into a size x size square."""
    dst = np.array([[0, 0], [size - 1, 0], [size - 1, size - 1], [0, size - 1]], dtype=np.float32)
    matrix = cv2.getPerspectiveTransform(np.asarray(corners, dtype=np.float32), dst)
    return cv2.warpPerspective(img, matrix, (size, size))


# ---------------------------------------------------------------------------
# Reading the digits
# ---------------------------------------------------------------------------

_CELL = 50  # px per cell in the straightened grid (warp size 450 / 9)


def _configure_tesseract():
    """Point pytesseract at the Windows install when it isn't on PATH."""
    import os
    import shutil

    import pytesseract

    default = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
    if shutil.which("tesseract") is None and os.path.exists(default):
        pytesseract.pytesseract.tesseract_cmd = default
    return pytesseract


def _binarize_grid(grid: np.ndarray) -> np.ndarray:
    """Ink -> white, paper -> black. Window 35px / offset 7 keeps faint,
    blurry digits while ignoring paper texture (tuned on the dataset)."""
    gray = cv2.cvtColor(grid, cv2.COLOR_BGR2GRAY)
    return cv2.adaptiveThreshold(
        gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 35, 7
    )


def extract_digits(grid: np.ndarray):
    """Split a straightened 450x450 grid into 81 cells and cut out each digit.

    Returns (cells, binary, gray): the (row, col) of every non-empty cell
    and, for each, the digit cut from the black/white image and from the
    contrast-stretched grey image (ink bright on dark in both). The grey cut
    keeps the shape of blurry digits that thresholding turns into blobs (an
    8's holes close up); reading both and voting beats either alone.
    """
    binary = _binarize_grid(grid)
    ink = 255 - cv2.cvtColor(grid, cv2.COLOR_BGR2GRAY)
    cells, bin_cuts, gray_cuts = [], [], []
    for r in range(9):
        for c in range(9):
            ys, xs = slice(r * _CELL, (r + 1) * _CELL), slice(c * _CELL, (c + 1) * _CELL)
            box = _digit_box(binary[ys, xs])
            if box is None:
                continue
            x, y, w, h = box
            crop = ink[ys, xs][y:y + h, x:x + w].astype(np.float32)
            lo, hi = np.percentile(crop, 5), crop.max()
            cells.append((r, c))
            bin_cuts.append(binary[ys, xs][y:y + h, x:x + w])
            gray_cuts.append(np.clip((crop - lo) * 255 / max(hi - lo, 1), 0, 255).astype(np.uint8))
    return cells, bin_cuts, gray_cuts


def _digit_box(cell: np.ndarray):
    """Return the digit's bounding box (x, y, w, h) in a binary cell, or None
    if the cell is empty.

    Grid lines touch the cell's edges, digits sit near its centre: keep the
    largest blob whose centre is in the middle of the cell and whose height
    is digit-like.
    """
    n, labels, stats, centroids = cv2.connectedComponentsWithStats(cell, connectivity=8)
    size = cell.shape[0]
    best, best_area = None, 0
    for i in range(1, n):
        x, y, w, h, area = stats[i]
        cx, cy = centroids[i]
        if not (0.25 * size < cx < 0.75 * size and 0.25 * size < cy < 0.75 * size):
            continue
        if not (0.3 * size <= h <= 0.9 * size) or w > 0.8 * size:
            continue
        if area > best_area:
            best, best_area = i, area
    if best is None:
        return None
    x, y, w, h, _ = stats[best]
    return int(x), int(y), int(w), int(h)


_DIGIT_H = 40  # digit height fed to Tesseract
_WHITELIST = "tessedit_char_whitelist=123456789"

# Each digit is read 3 ways and the majority wins (ties go to the first).
# (cut, Tesseract page-segmentation mode); 10 = single character,
# 13 = raw line. Chosen on the 200-photo dataset: this trio got the most
# puzzles fully right of all combinations of {binary, grey} x {8, 10, 13}.
_VOTERS = (("binary", 10), ("gray", 10), ("gray", 13))


def _digit_page(cut: np.ndarray) -> Image.Image:
    """Black digit on white, _DIGIT_H tall, with a margin: what Tesseract likes."""
    h, w = cut.shape
    # Width capped at 50px: a cut that is wider than a digit (a smudge or a
    # bit of grid line attached) gets squeezed rather than dominating.
    new_w = min(50, max(1, round(w * _DIGIT_H / h)))
    digit = cv2.resize(cut, (new_w, _DIGIT_H), interpolation=cv2.INTER_CUBIC)
    canvas = np.zeros((_DIGIT_H + 40, 110), np.uint8)
    x0 = (canvas.shape[1] - digit.shape[1]) // 2
    canvas[20:20 + _DIGIT_H, x0:x0 + digit.shape[1]] = digit
    return Image.fromarray(255 - canvas)


def _read_pages(cuts, psm: int) -> list:
    """Read many digit cuts in ONE Tesseract run; 0 where nothing was read.

    Starting Tesseract costs ~0.1-0.3 s, so one run per cell would take
    several seconds per puzzle. Instead every digit becomes a page of a
    multi-page TIFF: Tesseract still reads each page on its own (as
    accurate as one run per cell) and separates the pages' text with a
    form feed, which maps the answers back to their cells.
    """
    if not cuts:
        return []
    import os
    import subprocess
    import tempfile

    exe = _configure_tesseract().pytesseract.tesseract_cmd
    pages = [_digit_page(cut) for cut in cuts]
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "digits.tif")
        pages[0].save(path, save_all=True, append_images=pages[1:])
        out = subprocess.run(
            [exe, path, "stdout", "--psm", str(psm), "-c", _WHITELIST],
            capture_output=True, text=True, check=True,
        ).stdout
    texts = out.split("")
    digits = []
    for i in range(len(cuts)):
        found = [ch for ch in (texts[i] if i < len(texts) else "") if ch in "123456789"]
        digits.append(int(found[0]) if found else 0)
    return digits


def orient_grid(grid: np.ndarray, sample: int = 15) -> np.ndarray:
    """Rotate a straightened grid so its digits are upright.

    Photos without an EXIF rotation flag (screenshots, forwarded images,
    shots taken looking straight down) can arrive sideways or upside down.
    Tesseract recognises far fewer digits when they're rotated, so read a
    sample of digits in each of the 4 rotations and keep the best one.
    """
    best_grid, best_score = grid, -1.0
    for k in range(4):
        candidate = np.ascontiguousarray(np.rot90(grid, k))
        _, bin_cuts, _ = extract_digits(candidate)
        bin_cuts = bin_cuts[:sample]
        if not bin_cuts:
            continue
        score = sum(d != 0 for d in _read_pages(bin_cuts, 10)) / len(bin_cuts)
        if score > best_score:
            best_grid, best_score = candidate, score
        if k == 0 and score >= 0.8:
            break  # clearly upright: the usual case, skip the other rotations
    return best_grid


def read_board(grid: np.ndarray) -> np.ndarray:
    """Read all 81 cells of an upright, straightened grid (0 = empty)."""
    cells, bin_cuts, gray_cuts = extract_digits(grid)
    cuts = {"binary": bin_cuts, "gray": gray_cuts}
    readings = [_read_pages(cuts[kind], psm) for kind, psm in _VOTERS]
    board = np.zeros((9, 9), dtype=int)
    for i, (r, c) in enumerate(cells):
        votes = [reading[i] for reading in readings if reading[i]]
        if votes:
            board[r, c] = max(votes, key=votes.count)  # ties: first voter wins
    return board


def read_sudoku(data: bytes):
    """Picture bytes -> 9x9 board (0 = empty), or None if no grid was found."""
    photo = load_image(data)
    corners = find_grid_corners(photo)
    if corners is None:
        return None
    return read_board(orient_grid(warp_grid(photo, corners)))
