import streamlit as st
import numpy as np
import re

# ---- Sudoku Solver ----
def is_valid(board, row, col, num):
    if num in board[row]:
        return False
    if num in board[:, col]:
        return False
    start_row, start_col = 3 * (row // 3), 3 * (col // 3)
    if num in board[start_row:start_row+3, start_col:start_col+3]:
        return False
    return True

def solve_sudoku_optimized(board):
    # Precompute empty cells
    empty_cells = [(i, j) for i in range(9) for j in range(9) if board[i, j] == 0]

    def candidates(row, col):
        nums = set(range(1, 10))
        nums -= set(board[row, :])       # remove row numbers
        nums -= set(board[:, col])       # remove column numbers
        start_row, start_col = 3*(row//3), 3*(col//3)
        nums -= set(board[start_row:start_row+3, start_col:start_col+3].flatten())  # remove block numbers
        return list(nums)

    def backtrack():
        if not empty_cells:
            return True

        # Choose the empty cell with the fewest candidates
        empty_cells.sort(key=lambda pos: len(candidates(*pos)))
        row, col = empty_cells.pop(0)

        for num in candidates(row, col):
            board[row, col] = num
            if backtrack():
                return True
            board[row, col] = 0

        # Backtrack failed, put cell back
        empty_cells.insert(0, (row, col))
        return False

    return backtrack()

# ---- Streamlit UI ----
st.set_page_config(page_title="Sudoku Solver", layout="centered")
st.title("🧩 Sudoku Solver")

st.write("Enter numbers manually, or paste your Sudoku grid from Excel below (0 or blank for empty cells).")

# ---- Session state ----
if "board" not in st.session_state:
    st.session_state.board = np.zeros((9, 9), dtype=int)
if "pasted" not in st.session_state:
    st.session_state.pasted = ""
if "board_parsed" not in st.session_state:
    st.session_state.board_parsed = False

# ---- Paste input area ----
pasted = st.text_area(
    "Paste your Sudoku grid (9x9 numbers separated by spaces or tabs):",
    value=st.session_state.pasted,
    height=150
)
st.session_state.pasted = pasted

#---- Improved Parser ----
def parse_sudoku_text(pasted_text):
    """
    Robust parser for all Sudoku paste formats:
    - Tabs or spaces (Excel-style), preserves empty cells
    - Compact 9-digit rows (0 = empty)
    - Sparse grids with multiple empty columns
    Returns a 9x9 numpy array
    """
    if not pasted_text:
        return None

    lines = pasted_text.splitlines()
    grid = []

    for r in lines:
        if not r.strip():
            continue  # skip empty lines

        r = r.rstrip("\r\n")

        # Compact 9-digit row (0 = empty)
        if re.fullmatch(r"[0-9]{9}", r.strip()):
            row = [int(c) for c in r.strip()]
        else:
            # Split by tabs first
            parts = r.split("\t")
            row = []
            for part in parts:
                # Split remaining spaces inside part
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

# ---- Load pasted board only once ----
if st.session_state.pasted.strip() != "" and not st.session_state.board_parsed:
    parsed_board = parse_sudoku_text(st.session_state.pasted)
    if parsed_board is not None:
        st.session_state.board = parsed_board
        st.session_state.board_parsed = True

board = st.session_state.board

# ---- Display HTML grid ----
st.markdown("### Sudoku Grid")
grid_html = "<table style='border-collapse: collapse; margin:auto;'>"
for i in range(9):
    grid_html += "<tr>"
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
        grid_html += f"<td style='width:30px; height:30px; text-align:center; border:{border_style}; font-size:18px;'>{val}</td>"
    grid_html += "</tr>"
grid_html += "</table>"
st.markdown(grid_html, unsafe_allow_html=True)

# ---- Buttons ----
if st.button("🧮 Solve Sudoku"):
    board_copy = st.session_state.board.copy()
    if solve_sudoku_optimized(board_copy):
        st.session_state.board = board_copy
        st.success("✅ Sudoku solved!")
        st.rerun()
    else:
        st.error("❌ No valid solution found.")

if st.button("🧹 Clear Grid"):
    st.session_state.board = np.zeros((9, 9), dtype=int)
    st.session_state.pasted = ""
    st.session_state.board_parsed = False
    st.rerun()
