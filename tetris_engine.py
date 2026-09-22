import random

SHAPES = {
    'I': [[(0, 1), (1, 1), (2, 1), (3, 1)],
          [(2, 0), (2, 1), (2, 2), (2, 3)]],
    'O': [[(1, 0), (2, 0), (1, 1), (2, 1)]],
    'T': [[(1, 0), (0, 1), (1, 1), (2, 1)],  # 0: ㅜ (바닥평탄)
          [(1, 0), (1, 1), (2, 1), (1, 2)],  # 1: ㅏ (세로우측)
          [(0, 1), (1, 1), (2, 1), (1, 2)],  # 2: ㅗ (홈/웅덩이 메우기)
          [(1, 0), (0, 1), (1, 1), (1, 2)]], # 3: ㅓ (세로좌측)
    'S': [[(1, 0), (2, 0), (0, 1), (1, 1)],
          [(1, 0), (1, 1), (2, 1), (2, 2)]],
    'Z': [[(0, 0), (1, 0), (1, 1), (2, 1)],
          [(2, 0), (1, 1), (2, 1), (1, 2)]],
    'J': [[(0, 0), (0, 1), (1, 1), (2, 1)],
          [(1, 0), (2, 0), (1, 1), (1, 2)],
          [(0, 1), (1, 1), (2, 1), (2, 2)],
          [(1, 0), (1, 1), (0, 2), (1, 2)]],
    'L': [[(2, 0), (0, 1), (1, 1), (2, 1)],
          [(1, 0), (1, 1), (1, 2), (2, 2)],
          [(0, 1), (1, 1), (2, 1), (0, 2)],
          [(0, 0), (1, 0), (1, 1), (1, 2)]]
}

ORIENTATION_LABELS = {
    'T': {0: 'ㅜ(바닥평탄)', 1: 'ㅏ(세로우측)', 2: 'ㅗ(홈메우기)', 3: 'ㅓ(세로좌측)'},
    'I': {0: 'ㅡ(가로안착)', 1: 'ㅣ(세로꽂기)'},
    'O': {0: '■(정사각형)'},
    'S': {0: 'S(가로형)', 1: 'S(세로형)'},
    'Z': {0: 'Z(가로형)', 1: 'Z(세로형)'},
    'J': {0: 'J(ㄴ자형)', 1: 'J(세로형)', 2: 'J(ㄱ뒤집힘)', 3: 'J(세로형)'},
    'L': {0: 'L(역ㄴ자)', 1: 'L(세로형)', 2: 'L(역ㄱ형)', 3: 'L(세로형)'}
}

PIECE_COLORS = {
    'I': (0, 240, 240),
    'O': (240, 240, 0),
    'T': (160, 0, 240),
    'S': (0, 240, 0),
    'Z': (240, 0, 0),
    'J': (0, 100, 240),
    'L': (240, 140, 0)
}


class TetrisGame:
    def __init__(self, width=10, height=20, randomizer_mode="7bag", seed=None):
        self.width = width
        self.height = height
        self.board = [[None for _ in range(width)] for _ in range(height)]
        self.score = 0
        self.lines_cleared_total = 0
        self.game_over = False

        self.randomizer_mode = randomizer_mode if randomizer_mode in {"7bag", "iid"} else "7bag"
        self.rng = random.Random(seed)
        self.bag = []

        self.current_piece = self._draw_piece()
        self.next_piece = self._draw_piece()

    def _draw_piece(self):
        pieces = list(SHAPES.keys())

        if self.randomizer_mode == "iid":
            return self.rng.choice(pieces)

        if not self.bag:
            self.bag = pieces[:]
            self.rng.shuffle(self.bag)
        return self.bag.pop()

    def advance_piece(self):
        self.current_piece = self.next_piece
        self.next_piece = self._draw_piece()

    def can_place(self, piece_name, rot_idx, col, row, board=None):
        """현재 보드에서 실제 이동/회전/낙하가 가능한지 검사한다."""
        target = board or self.board
        shape = SHAPES[piece_name][rot_idx % len(SHAPES[piece_name])]

        for x, y in shape:
            nx = col + x
            ny = row + y

            if nx < 0 or nx >= self.width or ny >= self.height:
                return False
            if ny >= 0 and target[ny][nx] is not None:
                return False

        return True

    def get_column_heights(self, board=None):
        target = board or self.board
        heights = []
        for c in range(self.width):
            h = 0
            for r in range(self.height):
                if target[r][c] is not None:
                    h = self.height - r
                    break
            heights.append(h)
        return heights

    def evaluate_board_metrics(self, board):
        heights = self.get_column_heights(board)

        holes = 0
        for c in range(self.width):
            block_found = False
            for r in range(self.height):
                if board[r][c] is not None:
                    block_found = True
                elif block_found and board[r][c] is None:
                    holes += 1

        col_transitions = 0
        for c in range(self.width):
            prev = 1
            for r in range(self.height - 1, -1, -1):
                curr = 1 if board[r][c] is not None else 0
                if curr != prev:
                    col_transitions += 1
                prev = curr
            if prev != 0:
                col_transitions += 1

        cumulative_wells = 0
        for c in range(self.width):
            left_h = self.height if c == 0 else heights[c - 1]
            right_h = self.height if c == self.width - 1 else heights[c + 1]
            min_adj = min(left_h, right_h)
            if min_adj > heights[c]:
                depth = min_adj - heights[c]
                cumulative_wells += (depth * (depth + 1)) // 2

        return holes, col_transitions, cumulative_wells

    def count_holes(self, board=None):
        h, _, _ = self.evaluate_board_metrics(board or self.board)
        return h

    def simulate_drop(self, piece_name, rot_idx, col_offset):
        rotations = SHAPES[piece_name]
        shape = rotations[rot_idx % len(rotations)]

        min_x = min(x for x, y in shape)
        max_x = max(x for x, y in shape)
        if col_offset + min_x < 0 or col_offset + max_x >= self.width:
            return None

        drop_y = 0
        while self.can_place(piece_name, rot_idx, col_offset, drop_y):
            drop_y += 1
        drop_y -= 1

        if drop_y < 0:
            return None

        min_y = min(drop_y + y for x, y in shape)
        landing_height = self.height - min_y

        shape_set = set(shape)
        contact_edges = 0
        overhangs = 0

        for cx, cy in shape:
            bx = col_offset + cx
            by = drop_y + cy

            if by + 1 >= self.height or self.board[by + 1][bx] is not None:
                contact_edges += 1
            elif (cx, cy + 1) not in shape_set:
                overhangs += 1

            if bx - 1 < 0 or (by < self.height and self.board[by][bx - 1] is not None):
                contact_edges += 1
            if bx + 1 >= self.width or (by < self.height and self.board[by][bx + 1] is not None):
                contact_edges += 1

        sim_board = [row[:] for row in self.board]
        for x, y in shape:
            nx = col_offset + x
            ny = drop_y + y
            if 0 <= ny < self.height and 0 <= nx < self.width:
                sim_board[ny][nx] = piece_name

        cleared = sum(1 for row in sim_board if all(cell is not None for cell in row))
        new_board = [row for row in sim_board if not all(cell is not None for cell in row)]
        while len(new_board) < self.height:
            new_board.insert(0, [None for _ in range(self.width)])

        new_heights = self.get_column_heights(new_board)
        holes, col_trans, wells = self.evaluate_board_metrics(new_board)
        curr_holes, _, _ = self.evaluate_board_metrics(self.board)

        rot_label = ORIENTATION_LABELS.get(piece_name, {}).get(rot_idx, f"Rot{rot_idx}")

        return {
            "rot": rot_idx,
            "rot_label": rot_label,
            "col": col_offset,
            "shape": shape,
            "drop_y": drop_y,
            "landing_height": landing_height,
            "contact_edges": contact_edges,
            "overhangs": overhangs,
            "delta_holes": holes - curr_holes,
            "total_holes_after": holes,
            "col_transitions": col_trans,
            "cumulative_wells": wells,
            "lines_cleared": cleared,
            "max_height": max(new_heights),
            "final_board": new_board
        }

    def generate_candidate_moves(self, piece_name):
        raw_candidates = []
        rotations = SHAPES[piece_name]
        for rot in range(len(rotations)):
            for col in range(-2, self.width):
                res = self.simulate_drop(piece_name, rot, col)
                if res:
                    res["id"] = f"c{col}_{res['rot_label']}"
                    raw_candidates.append(res)

        if not raw_candidates:
            return []

        surviving_moves = [m for m in raw_candidates if m["landing_height"] < 19]
        valid_pool = surviving_moves if surviving_moves else raw_candidates

        def score_move(m):
            score = (
                - 4.5 * m["landing_height"]
                + 3.4 * (m["lines_cleared"] * 4)
                - 8.0 * m["total_holes_after"]
                - 3.2 * m["cumulative_wells"]
                - 3.8 * m["col_transitions"]
                + 2.5 * m["contact_edges"]
                - 6.0 * m["overhangs"]
            )
            if m["landing_height"] <= 8:
                score += 15.0
            return score

        valid_pool.sort(key=score_move, reverse=True)
        return valid_pool[:5]

    def lock_blocks_to_board(self, shape, col, drop_y, piece_name):
        for x, y in shape:
            nx = col + x
            ny = drop_y + y
            if 0 <= ny < self.height and 0 <= nx < self.width:
                self.board[ny][nx] = piece_name

        full_rows = [r for r in range(self.height) if all(cell is not None for cell in self.board[r])]
        if any(self.board[0][c] is not None for c in range(self.width)):
            self.game_over = True
        return full_rows

    def clear_full_lines(self, full_rows):
        if not full_rows:
            return
        cleared = len(full_rows)
        self.lines_cleared_total += cleared
        self.score += (cleared ** 2) * 100 + 10

        new_board = [self.board[r] for r in range(self.height) if r not in full_rows]
        while len(new_board) < self.height:
            new_board.insert(0, [None for _ in range(self.width)])
        self.board = new_board
