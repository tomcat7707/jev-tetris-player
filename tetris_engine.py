import random

SHAPES = {
    'I': [[(0, 1), (1, 1), (2, 1), (3, 1)],
          [(2, 0), (2, 1), (2, 2), (2, 3)]],
    'O': [[(1, 0), (2, 0), (1, 1), (2, 1)]],
    'T': [[(1, 0), (0, 1), (1, 1), (2, 1)],
          [(1, 0), (1, 1), (2, 1), (1, 2)],
          [(0, 1), (1, 1), (2, 1), (1, 2)],
          [(1, 0), (0, 1), (1, 1), (1, 2)]],
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

# Pierre Dellacherie / El-Tetris 계열의 대표 6-feature weights.
# 이전 버전은 wells/column-transition 가중치가 뒤섞여 있었고
# row transition / eroded piece cells가 누락되어 있었다.
DELLACHERIE_WEIGHTS = {
    "landing_height": -4.500158825082766,
    "eroded_piece_cells": 3.4181268101392694,
    "row_transitions": -3.2178882868487753,
    "col_transitions": -9.348695305445199,
    "holes": -7.899265427351652,
    "cumulative_wells": -3.3855972247263626,
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
        target = board if board is not None else self.board
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
        target = board if board is not None else self.board
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
        hole_depth = 0
        rows_with_holes = set()

        for c in range(self.width):
            filled_above = 0
            block_found = False
            for r in range(self.height):
                if board[r][c] is not None:
                    block_found = True
                    filled_above += 1
                elif block_found:
                    holes += 1
                    hole_depth += filled_above
                    rows_with_holes.add(r)

        # 좌/우 벽을 filled로 취급하는 표준적인 row transition 계산.
        row_transitions = 0
        for r in range(self.height):
            prev = 1
            for c in range(self.width):
                curr = 1 if board[r][c] is not None else 0
                if curr != prev:
                    row_transitions += 1
                prev = curr
            if prev != 1:
                row_transitions += 1

        # 바닥을 filled로 취급한다. 상단은 empty 상태에서 시작한다.
        col_transitions = 0
        for c in range(self.width):
            prev = 0
            for r in range(self.height):
                curr = 1 if board[r][c] is not None else 0
                if curr != prev:
                    col_transitions += 1
                prev = curr
            if prev != 1:
                col_transitions += 1

        cumulative_wells = 0
        max_well_depth = 0
        for c in range(self.width):
            r = 0
            while r < self.height:
                if board[r][c] is not None:
                    r += 1
                    continue

                left_filled = c == 0 or board[r][c - 1] is not None
                right_filled = c == self.width - 1 or board[r][c + 1] is not None
                if not (left_filled and right_filled):
                    r += 1
                    continue

                # 하나의 연속 well을 한 번만 계산한다.
                depth = 0
                rr = r
                while rr < self.height and board[rr][c] is None:
                    left_ok = c == 0 or board[rr][c - 1] is not None
                    right_ok = c == self.width - 1 or board[rr][c + 1] is not None
                    if not (left_ok and right_ok):
                        break
                    depth += 1
                    rr += 1

                cumulative_wells += depth * (depth + 1) // 2
                max_well_depth = max(max_well_depth, depth)
                r = rr

        bumpiness = sum(abs(heights[i] - heights[i + 1]) for i in range(self.width - 1))
        max_cliff = max(
            (abs(heights[i] - heights[i + 1]) for i in range(self.width - 1)),
            default=0,
        )

        return {
            "heights": heights,
            "aggregate_height": sum(heights),
            "max_height": max(heights) if heights else 0,
            "bumpiness": bumpiness,
            "max_cliff": max_cliff,
            "holes": holes,
            "hole_depth": hole_depth,
            "rows_with_holes": len(rows_with_holes),
            "row_transitions": row_transitions,
            "col_transitions": col_transitions,
            "cumulative_wells": cumulative_wells,
            "max_well_depth": max_well_depth,
        }

    def count_holes(self, board=None):
        target = board if board is not None else self.board
        return self.evaluate_board_metrics(target)["holes"]

    def score_move(self, move):
        w = DELLACHERIE_WEIGHTS
        score = (
            w["landing_height"] * move["landing_height"]
            + w["eroded_piece_cells"] * move["eroded_piece_cells"]
            + w["row_transitions"] * move["row_transitions"]
            + w["col_transitions"] * move["col_transitions"]
            + w["holes"] * move["total_holes_after"]
            + w["cumulative_wells"] * move["cumulative_wells"]
        )

        # Dellacherie 바깥의 safety residual.
        # 새 hole은 이후 선택지를 급격히 줄이므로 "현재보다 악화" 자체에 추가 비용을 둔다.
        if move["delta_holes"] > 0:
            score -= 18.0 * move["delta_holes"]

        return score

    def simulate_drop(self, piece_name, rot_idx, col_offset, board=None):
        source_board = board if board is not None else self.board
        rotations = SHAPES[piece_name]
        shape = rotations[rot_idx % len(rotations)]

        min_x = min(x for x, y in shape)
        max_x = max(x for x, y in shape)
        if col_offset + min_x < 0 or col_offset + max_x >= self.width:
            return None

        drop_y = 0
        while self.can_place(piece_name, rot_idx, col_offset, drop_y, source_board):
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

            if by + 1 >= self.height or source_board[by + 1][bx] is not None:
                contact_edges += 1
            elif (cx, cy + 1) not in shape_set:
                overhangs += 1

            if bx - 1 < 0 or source_board[by][bx - 1] is not None:
                contact_edges += 1
            if bx + 1 >= self.width or source_board[by][bx + 1] is not None:
                contact_edges += 1

        sim_board = [row[:] for row in source_board]
        piece_cells = []
        for x, y in shape:
            nx = col_offset + x
            ny = drop_y + y
            if 0 <= ny < self.height and 0 <= nx < self.width:
                sim_board[ny][nx] = piece_name
                piece_cells.append((nx, ny))

        full_rows = [r for r in range(self.height) if all(cell is not None for cell in sim_board[r])]
        cleared = len(full_rows)
        piece_cells_erased = sum(1 for _, py in piece_cells if py in full_rows)
        eroded_piece_cells = cleared * piece_cells_erased

        new_board = [sim_board[r] for r in range(self.height) if r not in full_rows]
        while len(new_board) < self.height:
            new_board.insert(0, [None for _ in range(self.width)])

        metrics_after = self.evaluate_board_metrics(new_board)
        current_metrics = self.evaluate_board_metrics(source_board)

        rot_label = ORIENTATION_LABELS.get(piece_name, {}).get(rot_idx, f"Rot{rot_idx}")

        move = {
            "rot": rot_idx,
            "rot_label": rot_label,
            "col": col_offset,
            "shape": shape,
            "drop_y": drop_y,
            "landing_height": landing_height,
            "contact_edges": contact_edges,
            "overhangs": overhangs,
            "delta_holes": metrics_after["holes"] - current_metrics["holes"],
            "total_holes_after": metrics_after["holes"],
            "hole_depth": metrics_after["hole_depth"],
            "rows_with_holes": metrics_after["rows_with_holes"],
            "row_transitions": metrics_after["row_transitions"],
            "col_transitions": metrics_after["col_transitions"],
            "cumulative_wells": metrics_after["cumulative_wells"],
            "max_well_depth": metrics_after["max_well_depth"],
            "bumpiness": metrics_after["bumpiness"],
            "max_cliff": metrics_after["max_cliff"],
            "aggregate_height": metrics_after["aggregate_height"],
            "lines_cleared": cleared,
            "eroded_piece_cells": eroded_piece_cells,
            "max_height": metrics_after["max_height"],
            "final_board": new_board,
        }
        move["heuristic_score"] = round(self.score_move(move), 3)
        return move

    def _raw_candidates(self, piece_name, board):
        raw = []
        for rot in range(len(SHAPES[piece_name])):
            for col in range(-2, self.width):
                move = self.simulate_drop(piece_name, rot, col, board)
                if move:
                    move["id"] = f"c{col}_{move['rot_label']}"
                    raw.append(move)
        return raw

    def _ranked_diverse_pool(self, candidates, limit=8):
        """
        v4: hole=0을 절대 규칙으로 강제하지 않는다.

        장기 생존에서는 '지금 hole 0'보다 깊은 canyon, 과도한 높이,
        다음 블록 선택지 고갈이 더 위험할 수 있다. 따라서 holistic score를
        기본으로 하되 서로 다른 장점을 가진 후보를 섞어 JEV에 선택권을 준다.
        """
        if not candidates:
            return []

        selected = []
        seen = set()

        def add(move):
            if move is None:
                return
            if move["id"] not in seen and len(selected) < limit:
                selected.append(move)
                seen.add(move["id"])

        # 1) 전체 2-ply 점수 상위 후보가 주력.
        for move in sorted(
            candidates,
            key=lambda m: m.get("robust_score", m.get("two_ply_score", m["heuristic_score"])),
            reverse=True,
        )[: max(4, limit - 3)]:
            add(move)

        # 2) Pareto-like sentinels: 특정 안전 축에서 가장 좋은 후보를 보존.
        add(min(candidates, key=lambda m: (m["total_holes_after"], m["hole_depth"], -m["lines_cleared"])))
        add(min(candidates, key=lambda m: (m["max_well_depth"], m["cumulative_wells"], m["max_height"])))
        add(min(candidates, key=lambda m: (m["max_height"], m["max_cliff"], m["bumpiness"])))
        add(max(candidates, key=lambda m: (m.get("next_option_count", 0), m.get("next_nonworsening_count", 0))))

        # 아직 자리가 남으면 holistic 순으로 채운다.
        if len(selected) < limit:
            for move in sorted(
                candidates,
                key=lambda m: m.get("robust_score", m.get("two_ply_score", m["heuristic_score"])),
                reverse=True,
            ):
                add(move)
                if len(selected) >= limit:
                    break

        selected.sort(
            key=lambda m: m.get("robust_score", m.get("two_ply_score", m["heuristic_score"])),
            reverse=True,
        )
        return selected

    def generate_candidate_moves(self, piece_name, next_piece=None, limit=8):
        raw_candidates = self._raw_candidates(piece_name, self.board)
        if not raw_candidates:
            self.last_candidate_diagnostics = {
                "raw_count": 0,
                "returned_count": 0,
                "mode": "diverse_holistic",
            }
            return []

        current_metrics = self.evaluate_board_metrics(self.board)

        # v4는 모든 합법 후보를 유지한 상태에서 known NEXT를 한 수 더 본다.
        for move in raw_candidates:
            move["safety_filtered"] = False
            move["candidate_pool_mode"] = "diverse_holistic"
            move["lookahead_piece"] = next_piece
            move["next_best_score"] = None
            move["next_best_holes"] = move["total_holes_after"]
            move["next_best_max_height"] = move["max_height"]
            move["next_best_max_well_depth"] = move["max_well_depth"]
            move["next_option_count"] = 0
            move["next_nonworsening_count"] = 0
            move["two_ply_score"] = move["heuristic_score"]

            if next_piece:
                next_raw = self._raw_candidates(next_piece, move["final_board"])
                move["next_option_count"] = len(next_raw)
                if next_raw:
                    move["next_nonworsening_count"] = sum(
                        1
                        for nxt in next_raw
                        if nxt["total_holes_after"] <= move["total_holes_after"]
                    )
                    next_best = max(next_raw, key=lambda m: m["heuristic_score"])
                    move["next_best_score"] = next_best["heuristic_score"]
                    move["next_best_holes"] = next_best["total_holes_after"]
                    move["next_best_max_height"] = next_best["max_height"]
                    move["next_best_max_well_depth"] = next_best["max_well_depth"]
                    move["next_best_id"] = next_best["id"]
                    move["two_ply_score"] = round(
                        move["heuristic_score"] + 0.35 * next_best["heuristic_score"],
                        3,
                    )

            # 유한한 risk penalty만 둔다. hole을 만든다는 이유로 후보 자체를 삭제하지 않는다.
            new_holes = max(0, move["delta_holes"])
            well_excess = max(0, move["max_well_depth"] - 4)
            next_well_excess = max(0, move["next_best_max_well_depth"] - 5)
            option_shortage = max(0, 4 - move["next_option_count"])

            move["robust_score"] = round(
                move["two_ply_score"]
                - 12.0 * new_holes
                - 7.0 * well_excess
                - 4.0 * next_well_excess
                - 6.0 * option_shortage,
                3,
            )

        pool = self._ranked_diverse_pool(raw_candidates, limit=limit)

        self.last_candidate_diagnostics = {
            "mode": "diverse_holistic",
            "raw_count": len(raw_candidates),
            "returned_count": len(pool),
            "current_holes": current_metrics["holes"],
            "current_max_height": current_metrics["max_height"],
            "current_max_well_depth": current_metrics["max_well_depth"],
            "raw_zero_hole_count": sum(
                1 for m in raw_candidates
                if m["total_holes_after"] <= current_metrics["holes"]
            ),
        }
        return pool

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
