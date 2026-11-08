"""Find a Sudoku grid in a photo and straighten it.

Pipeline (step 2 of the picture import; digit reading comes next):
  1. decode the upload, honouring the phone's EXIF rotation
  2. find the grid's outer border: the largest 4-cornered outline in a
     thresholded copy of the picture
  3. perspective-warp that quadrilateral into a flat square
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
