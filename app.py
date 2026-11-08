import streamlit as st
import numpy as np
import random
import re
import base64
import html

import sudoku_vision


# ============================================================================
# CORE SUDOKU FUNCTIONS
# ============================================================================

def is_valid(board, row, col, num):
    """Check if placing num at board[row][col] is valid"""
    if num in board[row]:
        return False
    if num in board[:, col]:
        return False
    start_row, start_col = 3 * (row // 3), 3 * (col // 3)
    if num in board[start_row:start_row+3, start_col:start_col+3]:
        return False
    return True


def solve_sudoku_optimized(board):
    """Solve sudoku using backtracking with optimized candidate selection"""
    empty_cells = [(i, j) for i in range(9) for j in range(9) if board[i, j] == 0]

    def candidates(row, col):
        nums = set(range(1, 10))
        nums -= set(board[row, :])
        nums -= set(board[:, col])
        start_row, start_col = 3*(row//3), 3*(col//3)
        nums -= set(board[start_row:start_row+3, start_col:start_col+3].flatten())
        return list(nums)

    def backtrack():
        if not empty_cells:
            return True

        empty_cells.sort(key=lambda pos: len(candidates(*pos)))
        row, col = empty_cells.pop(0)

        for num in candidates(row, col):
            board[row, col] = num
            if backtrack():
                return True
            board[row, col] = 0

        empty_cells.insert(0, (row, col))
        return False

    return backtrack()


def count_solutions(board, limit=2):
    """Count solutions up to limit (for checking uniqueness)"""
    board_copy = board.copy()
    empty_cells = [(i, j) for i in range(9) for j in range(9) if board_copy[i, j] == 0]
    solutions = [0]

    def candidates(row, col):
        nums = set(range(1, 10))
        nums -= set(board_copy[row, :])
        nums -= set(board_copy[:, col])
        start_row, start_col = 3*(row//3), 3*(col//3)
        nums -= set(board_copy[start_row:start_row+3, start_col:start_col+3].flatten())
        return list(nums)

    def backtrack(idx):
        if solutions[0] >= limit:
            return

        if idx == len(empty_cells):
            solutions[0] += 1
            return

        row, col = empty_cells[idx]
        for num in candidates(row, col):
            board_copy[row, col] = num
            backtrack(idx + 1)
            board_copy[row, col] = 0

    backtrack(0)
    return solutions[0]


def generate_complete_sudoku():
    """Generate a complete valid sudoku board"""
    board = np.zeros((9, 9), dtype=int)

    # Fill diagonal 3x3 boxes first (they don't affect each other)
    for box in range(3):
        nums = list(range(1, 10))
        random.shuffle(nums)
        for i in range(3):
            for j in range(3):
                board[box*3 + i][box*3 + j] = nums[i*3 + j]

    # Solve the rest
    solve_sudoku_optimized(board)
    return board


def generate_sudoku_puzzle(difficulty='medium'):
    """Generate a sudoku puzzle with a unique solution

    Args:
        difficulty: 'easy' (40-45 clues), 'medium' (30-35 clues), 'hard' (25-30 clues)

    Returns:
        9x9 numpy array with the puzzle
    """
    board = generate_complete_sudoku()
    puzzle = board.copy()

    # Determine number of cells to remove based on difficulty
    if difficulty == 'easy':
        cells_to_remove = random.randint(36, 41)
    elif difficulty == 'medium':
        cells_to_remove = random.randint(46, 51)
    else:  # hard
        cells_to_remove = random.randint(51, 56)

    # Get all cell positions and shuffle
    cells = [(i, j) for i in range(9) for j in range(9)]
    random.shuffle(cells)

    removed = 0
    for row, col in cells:
        if removed >= cells_to_remove:
            break

        backup = puzzle[row, col]
        puzzle[row, col] = 0

        # Check if puzzle still has unique solution
        if count_solutions(puzzle, limit=2) == 1:
            removed += 1
        else:
            puzzle[row, col] = backup

    return puzzle


def parse_sudoku_text(pasted_text):
    """Parse sudoku text from various formats

    Supports:
    - Tabs or spaces (Excel-style), preserves empty cells
    - Compact 9-digit rows (0 = empty)
    - Sparse grids with multiple empty columns

    Returns:
        9x9 numpy array
    """
    if not pasted_text:
        return None

    try:
        lines = pasted_text.splitlines()
        grid = []

        for r in lines:
            if not r.strip():
                continue

            r = r.rstrip("\r\n")

            # Compact 9-digit row (0 = empty)
            if re.fullmatch(r"[0-9]{9}", r.strip()):
                row = [int(c) for c in r.strip()]
            else:
                # Split by tabs first
                parts = r.split("\t")
                row = []
                for part in parts:
                    subparts = re.split(r" ", part)
                    for sp in subparts:
                        sp = sp.strip()
                        if sp == "":
                            row.append(0)
                        else:
                            try:
                                row.append(int(re.search(r"\d+", sp).group()))
                            except:
                                row.append(0)
                # Pad to 9 columns
                if len(row) < 9:
                    row += [0] * (9 - len(row))
                row = row[:9]

            grid.append(row)

        # Pad to 9 rows
        while len(grid) < 9:
            grid.append([0]*9)
        grid = grid[:9]

        board = np.array(grid, dtype=int)
    except Exception:
        return None

    # Reject values outside the valid Sudoku range (e.g. a stray "12")
    if not ((board >= 0) & (board <= 9)).all():
        return None

    # Non-empty input that yielded no clues at all is unparseable garbage
    if not board.any():
        return None

    return board


# ============================================================================
# STREAMLIT UI
# ============================================================================

def count_conflicts(board):
    """Number of filled cells whose value repeats in their row, column or box."""
    clashing = set()
    for i in range(9):
        for j in range(9):
            v = board[i, j]
            if v == 0:
                continue
            br, bc = 3 * (i // 3), 3 * (j // 3)
            peers = [(i, k) for k in range(9)] + [(k, j) for k in range(9)] + [
                (br + a, bc + b) for a in range(3) for b in range(3)]
            if any(board[p] == v for p in peers if p != (i, j)):
                clashing.add((i, j))
    return len(clashing)


def is_board_solved(board):
    """Check if the board is completely filled and valid"""
    # Check if board is full
    if np.count_nonzero(board) != 81:
        return False

    # Check all rows, columns, and boxes for validity
    for i in range(9):
        # Check row
        if len(set(board[i, :])) != 9 or 0 in board[i, :]:
            return False
        # Check column
        if len(set(board[:, i])) != 9 or 0 in board[:, i]:
            return False

    # Check all 3x3 boxes
    for box_row in range(3):
        for box_col in range(3):
            box = board[box_row*3:(box_row+1)*3, box_col*3:(box_col+1)*3].flatten()
            if len(set(box)) != 9 or 0 in box:
                return False

    return True


def render_editable_grid(board, initial_clues, is_empty=False):
    """Render an editable Sudoku grid using HTML/JavaScript component

    Args:
        board: 9x9 NumPy array with the current board state
        initial_clues: 9x9 NumPy boolean array marking which cells are initial clues
        is_empty: If True, disable all editing (no puzzle loaded)

    Returns:
        Updated board as nested list (or None on first render)
    """
    # Read HTML template from file
    import os
    template_path = os.path.join(os.path.dirname(__file__), 'sudoku_grid.html')
    with open(template_path, 'r', encoding='utf-8') as f:
        html_template = f.read()

    # Convert data to JavaScript format
    board_json = str(board.tolist())
    clues_json = str(initial_clues.tolist()).replace('True', 'true').replace('False', 'false')
    is_empty_js = 'true' if is_empty else 'false'

    # Inject data into template
    html_content = html_template.replace('{{BOARD_DATA}}', board_json)
    html_content = html_content.replace('{{CLUES_DATA}}', clues_json)
    html_content = html_content.replace('{{IS_EMPTY}}', is_empty_js)

    # Render component
    result = st.components.v1.html(html_content, height=420, scrolling=False)
    return result


# Page configuration
st.set_page_config(page_title="Sudoku Solver", layout="wide")

# Custom CSS to reduce top padding
st.markdown("""
    <style>
        .block-container {
            padding-top: 2rem;
        }
        /* Hide the "Press Ctrl+Enter to apply" hint (no keyboard on mobile) */
        [data-testid="InputInstructions"] {
            display: none;
        }
        /* Picture input: a box the same size as the paste text area with a
           centered "Picture" button that opens the native picker. Once a
           picture is picked, the app keeps it and shows a preview in the
           same box instead of the uploader. */
        .st-key-image_box [data-testid="stFileUploaderDropzone"] {
            height: 125px;
            padding: 0;
            justify-content: center;
            align-items: center;
        }
        .st-key-image_box [data-testid="stFileUploaderDropzoneInstructions"] {
            display: none;
        }
        /* Replace the button's own text ("Upload" / "Browse files" depending
           on the Streamlit version) with "Picture" */
        .st-key-image_box [data-testid="stFileUploaderDropzone"] button {
            font-size: 0;
        }
        .st-key-image_box [data-testid="stFileUploaderDropzone"] button * {
            display: none;
        }
        .st-key-image_box [data-testid="stFileUploaderDropzone"] button::after {
            content: "Picture";
            /* match st.button labels, which render in a 14px <p> */
            font-size: 0.875rem;
            line-height: 1.6;
        }
        /* Fixed sizes use !important: Streamlit's own element styles (auto
           heights, negative margins under text) would otherwise win */
        .st-key-image_box {
            height: 125px !important;
            min-height: 125px !important;
        }
        .image-preview {
            height: 125px;
            display: flex;
            align-items: center;
            justify-content: center;
            box-sizing: border-box;
            /* same box as the paste text area and the empty dropzone.
               light-dark() follows the color-scheme Streamlit sets for the
               active theme, so this switches with it (Streamlit 1.67's
               default light / dark theme colours) */
            border-radius: 8px;
            border: 1px solid light-dark(rgb(220, 216, 212), rgb(74, 71, 66));
            background: light-dark(rgb(248, 248, 247), rgb(45, 43, 39));
            overflow: hidden;
        }
        .image-preview img {
            max-width: 100%;
            max-height: 100%;
            object-fit: contain;
        }
        /* Fixed-height line under the picture box: file name + Remove, or a
           hint when empty, so picking a picture doesn't move anything */
        .st-key-picture_row {
            height: 2.5rem !important;
            min-height: 2.5rem !important;
            flex-wrap: nowrap;
            overflow: hidden;
        }
        .st-key-picture_row {
            margin-top: -0.75rem;  /* sit just under the box */
        }
        .st-key-picture_row > div:first-child {
            flex: 1 1 auto;
            min-width: 0;
        }
        /* Streamlit gives text blocks a bottom margin, which pushes the
           name below the Remove button's centre line */
        .st-key-picture_row [data-testid="stMarkdownContainer"],
        .st-key-picture_row [data-testid="stMarkdownContainer"] > div {
            margin: 0 !important;
        }
        .picture-name {
            font-size: 0.875rem;
            color: inherit;  /* the theme's text colour, faded */
            opacity: 0.6;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }
        /* Reserved space under Import for its messages (and the "Reading..."
           spinner), so they don't push the rest of the page down */
        .st-key-import_notice {
            min-height: 4.2rem !important;
        }
        .import-notice {
            font-size: 0.875rem;
            line-height: 1.4;
        }
        .import-notice.success { color: light-dark(#2e7d32, #7dd38b); }
        .import-notice.warning { color: light-dark(#a15c00, #f0b45a); }
        .import-notice.error { color: light-dark(#c62828, #ff8a80); }
    </style>
""", unsafe_allow_html=True)

st.title("🧩 Sudoku Solver & Generator")

# Session state initialization
if "board" not in st.session_state:
    st.session_state.board = np.zeros((9, 9), dtype=int)
if "pasted" not in st.session_state:
    st.session_state.pasted = ""
if "board_parsed" not in st.session_state:
    st.session_state.board_parsed = False
if "initial_clues" not in st.session_state:
    st.session_state.initial_clues = np.zeros((9, 9), dtype=bool)
if "import_notice" not in st.session_state:
    # (kind, message) shown under Import: "success" / "warning" / "error"
    st.session_state.import_notice = None
if "picture" not in st.session_state:
    # The picked picture: {"name", "type", "data"} or None
    st.session_state.picture = None
if "image_upload_nonce" not in st.session_state:
    # Bumped to reset the uploader once its file has been taken over
    st.session_state.image_upload_nonce = 0

board = st.session_state.board

# ============================================================================
# TOP SECTION: Generate or Import
# ============================================================================

top_left, spacer, top_right = st.columns([1, 0.1, 1])

with top_left:
    st.markdown("### 📋 Import Puzzle")

    st.markdown(
        "Paste a 9x9 grid (0s or blanks for empty cells) or add a picture of it:"
    )
    text_col, image_col = st.columns(2)

    with text_col:
        pasted = st.text_area(
            "Pasted grid",
            value=st.session_state.pasted,
            height=125,
            placeholder="Paste grid here...",
            label_visibility="collapsed",
        )
        st.session_state.pasted = pasted

    with image_col:
        picture = st.session_state.picture
        with st.container(key="image_box"):
            if picture is None:
                # A file input opens the device's native picker (camera /
                # photo library / files on mobile, file dialog on desktop).
                uploaded = st.file_uploader(
                    "Picture",
                    type=["png", "jpg", "jpeg", "webp"],
                    key=f"image_upload_{st.session_state.image_upload_nonce}",
                    label_visibility="collapsed",
                )
                if uploaded is not None:
                    # Keep the picture ourselves and drop the uploader, so the
                    # preview can take the uploader's place in the box.
                    st.session_state.picture = {
                        "name": uploaded.name,
                        "type": uploaded.type or "image/png",
                        "data": uploaded.getvalue(),
                    }
                    st.session_state.image_upload_nonce += 1
                    st.rerun()
            else:
                data = base64.b64encode(picture["data"]).decode()
                st.markdown(
                    f'<div class="image-preview"><img src="data:{picture["type"]};'
                    f'base64,{data}" alt="{html.escape(picture["name"])}"></div>',
                    unsafe_allow_html=True,
                )
        with st.container(key="picture_row", horizontal=True, vertical_alignment="center"):
            if picture is None:
                st.markdown('<div class="picture-name">Photo or screenshot of the grid</div>',
                            unsafe_allow_html=True)
            else:
                st.markdown(f'<div class="picture-name">{html.escape(picture["name"])}</div>',
                            unsafe_allow_html=True)
                if st.button("✕ Remove", type="tertiary"):
                    st.session_state.picture = None
                    st.rerun()

    import_clicked = st.button("Import", use_container_width=True)
    notice_slot = st.container(key="import_notice")
    if import_clicked:
        st.session_state.import_notice = None
        if picture is not None:
            # A loaded picture takes precedence over pasted text.
            with notice_slot, st.spinner("Reading the numbers from the picture..."):
                read_board = sudoku_vision.read_sudoku(picture["data"])
            if read_board is None:
                st.session_state.import_notice = (
                    "error",
                    "Couldn't find a Sudoku grid in that picture. Try a closer, "
                    "straighter photo with the whole grid visible.")
            elif not read_board.any():
                st.session_state.import_notice = (
                    "error",
                    "Found a grid but couldn't read any numbers in it. Try a "
                    "sharper, better-lit photo.")
            else:
                st.session_state.board = read_board
                st.session_state.initial_clues = (read_board != 0)
                st.session_state.board_parsed = True
                clashes = count_conflicts(read_board)
                st.session_state.import_notice = (
                    ("warning",
                     f"Read {np.count_nonzero(read_board)} numbers, but {clashes} "
                     "clash (same number twice in a row, column or box), so some "
                     "were misread. Compare with the picture.")
                    if clashes else
                    ("success",
                     f"Read {np.count_nonzero(read_board)} numbers from the "
                     "picture. Check them against it before solving.")
                )
                st.rerun()
        else:
            parsed_board = parse_sudoku_text(pasted)
            if parsed_board is not None:
                st.session_state.board = parsed_board
                st.session_state.initial_clues = (parsed_board != 0)
                st.session_state.board_parsed = True
                st.rerun()
            st.session_state.import_notice = (
                "error",
                "Couldn't read that as a Sudoku grid. Paste 9 rows of digits "
                "(0 or blank for empty cells), or add a picture.")

    # Always render the slot (Streamlit drops empty containers, which would
    # make the page jump when a message appears)
    kind, message = st.session_state.import_notice or ("", " ")
    notice_slot.markdown(
        f'<div class="import-notice {kind}">{html.escape(message)}</div>',
        unsafe_allow_html=True,
    )

with spacer:
    st.markdown("<div style='text-align: center; padding-top: 80px; font-size: 18px; font-weight: bold;'>OR</div>", unsafe_allow_html=True)

with top_right:
    st.markdown("### 🎲 Generate Puzzle")

    difficulty = st.radio(
        "Select difficulty:",
        options=["Easy", "Medium", "Hard"],
        horizontal=True,
        index=1,
        help="Easy: 40-45 clues | Medium: 30-35 clues | Hard: 25-30 clues"
    )

    if st.button("Generate", use_container_width=True):
        with st.spinner(f"Generating {difficulty} puzzle..."):
            new_puzzle = generate_sudoku_puzzle(difficulty=difficulty.lower())
            st.session_state.board = new_puzzle
            st.session_state.initial_clues = (new_puzzle != 0)
            st.session_state.pasted = ""
            st.session_state.picture = None
            st.session_state.import_notice = None
            st.session_state.board_parsed = False
            st.rerun()

st.markdown("---")

# ============================================================================
# BOTTOM SECTION: Grid, Info, and Actions
# ============================================================================

left_col, center_col = st.columns([0.7, 2.3])

# Left column: Actions
with left_col:
    st.markdown("### 🔧 Actions")

    is_board_empty = np.count_nonzero(board) == 0
    is_solved = is_board_solved(board)

    if st.button("🧮 Solve", use_container_width=True, type="primary", disabled=(is_board_empty or is_solved)):
        board_copy = st.session_state.board.copy()
        if solve_sudoku_optimized(board_copy):
            st.session_state.board = board_copy
            st.success("✅ Solved!")
            st.rerun()
        else:
            st.error("❌ No solution.")

    if st.button("🧹 Clear", use_container_width=True):
        st.session_state.board = np.zeros((9, 9), dtype=int)
        st.session_state.initial_clues = np.zeros((9, 9), dtype=bool)
        st.session_state.pasted = ""
        st.session_state.picture = None
        st.session_state.import_notice = None
        st.session_state.board_parsed = False
        st.rerun()

    # Show "Solved!" message when puzzle is complete and valid
    if is_solved:
        st.markdown("<p style='color: #2e7d32; font-weight: bold; font-size: 18px; text-align: center; margin-top: 20px;'>✅ Solved!</p>", unsafe_allow_html=True)

# Center column: Grid
with center_col:
    st.markdown("<h3 style='text-align: center;'>📊 Current Puzzle</h3>", unsafe_allow_html=True)

    # Render editable grid component
    is_board_empty = np.count_nonzero(st.session_state.board) == 0
    updated_board = render_editable_grid(
        st.session_state.board,
        st.session_state.initial_clues,
        is_empty=is_board_empty
    )

    # Info panel is now rendered inside the HTML component for real-time updates
