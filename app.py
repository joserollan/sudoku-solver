import streamlit as st
import numpy as np
import re
import random


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

    return np.array(grid, dtype=int)


# ============================================================================
# STREAMLIT UI
# ============================================================================

# Page configuration
st.set_page_config(page_title="Sudoku Solver", layout="wide")

# Custom CSS to reduce top padding
st.markdown("""
    <style>
        .block-container {
            padding-top: 2rem;
        }
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

# Load pasted board
if st.session_state.pasted.strip() != "" and not st.session_state.board_parsed:
    parsed_board = parse_sudoku_text(st.session_state.pasted)
    if parsed_board is not None:
        st.session_state.board = parsed_board
        st.session_state.board_parsed = True

board = st.session_state.board

# ============================================================================
# TOP SECTION: Generate or Import
# ============================================================================

top_left, spacer, top_right = st.columns([1, 0.1, 1])

with top_left:
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
            st.session_state.pasted = ""
            st.session_state.board_parsed = False
            st.rerun()

with spacer:
    st.markdown("<div style='text-align: center; padding-top: 80px; font-size: 18px; font-weight: bold;'>OR</div>", unsafe_allow_html=True)

with top_right:
    st.markdown("### 📋 Import Puzzle")

    pasted = st.text_area(
        "Paste your Sudoku grid (9x9, with 0s or blanks for empty cells):",
        value=st.session_state.pasted,
        height=125,
        placeholder="Paste grid here..."
    )
    st.session_state.pasted = pasted

st.markdown("---")

# ============================================================================
# BOTTOM SECTION: Grid, Info, and Actions
# ============================================================================

left_col, center_col, right_col = st.columns([0.7, 1.6, 0.7])

# Left column: Actions
with left_col:
    st.markdown("### 🔧 Actions")

    is_board_empty = np.count_nonzero(board) == 0

    if st.button("🧮 Solve", use_container_width=True, type="primary", disabled=is_board_empty):
        board_copy = st.session_state.board.copy()
        if solve_sudoku_optimized(board_copy):
            st.session_state.board = board_copy
            st.success("✅ Solved!")
            st.rerun()
        else:
            st.error("❌ No solution.")

    if st.button("🧹 Clear", use_container_width=True):
        st.session_state.board = np.zeros((9, 9), dtype=int)
        st.session_state.pasted = ""
        st.session_state.board_parsed = False
        st.rerun()

# Center column: Grid
with center_col:
    st.markdown("<h3 style='text-align: center;'>📊 Current Puzzle</h3>", unsafe_allow_html=True)

    # Build HTML grid
    grid_html = "<table style='border-collapse: collapse; margin:10px auto; table-layout: fixed;'>"
    for i in range(9):
        grid_html += "<tr style='height:40px;'>"
        for j in range(9):
            val = int(board[i, j]) if board[i, j] != 0 else ""
            border_style = "1px solid #999;"
            if j % 3 == 0:
                border_style += "border-left: 3px solid black;"
            if i % 3 == 0:
                border_style += "border-top: 3px solid black;"
            if j == 8:
                border_style += "border-right: 3px solid black;"
            if i == 8:
                border_style += "border-bottom: 3px solid black;"
            grid_html += f"<td style='width:40px; height:40px; min-height:40px; max-height:40px; text-align:center; vertical-align:middle; border:{border_style}; font-size:20px; font-weight:bold; padding:0;'>{val}</td>"
        grid_html += "</tr>"
    grid_html += "</table>"
    st.markdown(grid_html, unsafe_allow_html=True)

# Right column: Info
with right_col:
    st.markdown("### 📈 Info")

    filled_cells = np.count_nonzero(board)
    empty_cells = 81 - filled_cells
    progress = (filled_cells / 81) * 100

    st.metric("Filled", f"{filled_cells}/81")
    st.metric("Empty", empty_cells)
    st.metric("Progress", f"{progress:.0f}%")
