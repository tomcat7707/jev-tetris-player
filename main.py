import sys
import time
import threading
import pygame
from config import BLOCK_SIZE, BOARD_WIDTH, BOARD_HEIGHT, SCREEN_WIDTH, SCREEN_HEIGHT, FPS
from tetris_engine import TetrisGame, PIECE_COLORS, SHAPES, ORIENTATION_LABELS
from jev_agent import JevTetrisAgent

def draw_block(screen, x, y, color, border_color=(40, 40, 40), width=0):
    rect = pygame.Rect(x, y, BLOCK_SIZE, BLOCK_SIZE)
    if width == 0:
        pygame.draw.rect(screen, color, rect)
        pygame.draw.line(screen, (255, 255, 255, 120), (x, y), (x + BLOCK_SIZE - 1, y), 2)
        pygame.draw.line(screen, (255, 255, 255, 120), (x, y), (x, y + BLOCK_SIZE - 1), 2)
    pygame.draw.rect(screen, border_color, rect, 1 if width == 0 else width)

def draw_piece_preview(screen, x, y, piece_name, label, font):
    box_rect = pygame.Rect(x, y, 95, 75)
    pygame.draw.rect(screen, (20, 22, 28), box_rect, border_radius=4)
    pygame.draw.rect(screen, (55, 60, 75), box_rect, 1, border_radius=4)
    
    lbl_color = (0, 240, 200) if label == "CURRENT" else (160, 170, 185)
    screen.blit(font.render(label, True, lbl_color), (x + 8, y + 4))

    shape = SHAPES[piece_name][0]
    color = PIECE_COLORS.get(piece_name, (200, 200, 200))
    min_x = min(cx for cx, cy in shape)
    max_x = max(cx for cx, cy in shape)
    min_y = min(cy for cx, cy in shape)
    max_y = max(cy for cx, cy in shape)
    p_w = (max_x - min_x + 1) * 14
    p_h = (max_y - min_y + 1) * 14
    start_x = x + (95 - p_w) // 2 - min_x * 14
    start_y = y + 20 + (50 - p_h) // 2 - min_y * 14

    for cx, cy in shape:
        r = pygame.Rect(start_x + cx * 14, start_y + cy * 14, 13, 13)
        pygame.draw.rect(screen, color, r)

def main():
    pygame.init()
    screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
    pygame.display.set_caption("JEV Tetris - Classic G-System & Virtual DAS")
    clock = pygame.time.Clock()
    font = pygame.font.SysFont("malgungothic", 12)
    bold_font = pygame.font.SysFont("malgungothic", 13, bold=True)
    title_font = pygame.font.SysFont("malgungothic", 18, bold=True)

    game = TetrisGame(BOARD_WIDTH, BOARD_HEIGHT)
    agent = JevTetrisAgent()

    running = True
    auto_play = True

    inspector_data = {
        "active_piece": game.current_piece,
        "next_piece": game.next_piece,
        "heights": game.get_column_heights(),
        "terrain_diagnosis": "지형 분석 대기 중...",
        "strategy_goal": "평탄화 및 바닥 안착",
        "chosen_move": None,
        "decision_narrative": "AI 분석 대기 중...",
        "control_action": "대기 중",
        "confidence": 0,
        "latency_ms": 0,
        "evaluated_moves": []
    }

    api_status_text = "준비 완료"
    api_status_color = (100, 255, 120)
    is_network_busy = False
    thread_result = None
    last_request_time = 0

    state = "READY"
    
    # [정통 테트리스 격자 좌표계]
    grid_x = 3
    grid_y = 0
    grid_rot = 0
    
    target_col = 3
    target_rot = 0
    target_drop_y = 0
    chosen_move_data = None

    # [테트리스 표준 타이머 시스템]
    gravity_timer = 0
    das_timer = 0
    gravity_speed = 12       # 12프레임(약 0.2초)마다 정확히 1칸 등속 낙하
    das_speed = 4            # 4프레임마다 회전 또는 좌우 이동 키 입력
    
    lock_timer = 0
    locked_blocks = []
    clearing_rows = []
    line_flash_timer = 0

    def background_api_call(summary, candidates):
        nonlocal is_network_busy, thread_result
        try:
            res = agent.evaluate_best_move(summary, candidates)
            thread_result = (res, summary, candidates)
        finally:
            is_network_busy = False

    while running:
        clock.tick(FPS)

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_SPACE:
                    auto_play = not auto_play
                elif event.key == pygame.K_r and game.game_over:
                    game = TetrisGame(BOARD_WIDTH, BOARD_HEIGHT)
                    state = "READY"
                    thread_result = None
                    is_network_busy = False
                elif event.key == pygame.K_UP:
                    gravity_speed = max(4, gravity_speed - 2)
                elif event.key == pygame.K_DOWN:
                    gravity_speed = min(30, gravity_speed + 2)

        # ----------------- 클래식 G-System 자율 조작 루프 -----------------
        if auto_play and not game.game_over:
            # 1. JEV 목표 연산
            if state == "READY":
                if not is_network_busy and thread_result is None:
                    if time.time() - last_request_time >= 0.8:
                        candidates = game.generate_candidate_moves(game.current_piece)
                        if candidates:
                            summary = {
                                "current_piece": game.current_piece,
                                "next_piece": game.next_piece,
                                "column_heights": game.get_column_heights(),
                                "current_holes": game.count_holes()
                            }
                            is_network_busy = True
                            last_request_time = time.time()
                            api_status_text = f"'{game.current_piece}' 연산 중..."
                            api_status_color = (255, 215, 0)

                            th = threading.Thread(
                                target=background_api_call,
                                args=(summary, candidates),
                                daemon=True
                            )
                            th.start()
                        else:
                            game.game_over = True

                elif thread_result is not None:
                    res, summary, candidates = thread_result
                    thread_result = None

                    if res.get("success"):
                        best_id = res["choice_id"]
                        chosen_move_data = next((c for c in candidates if c["id"] == best_id), candidates[0])
                        m = chosen_move_data

                        target_col = m["col"]
                        target_rot = m["rot"]
                        target_drop_y = m["drop_y"]

                        # 블록 스폰 (상단 중앙 격자 위치)
                        grid_x = 3
                        grid_y = 0
                        grid_rot = 0
                        gravity_timer = 0
                        das_timer = 0

                        h_list = summary["column_heights"]
                        min_h, max_h = min(h_list), max(h_list)
                        diff = max_h - min_h
                        
                        if max_h >= 12:
                            terrain = f"위험 상태: 최고 {max_h}칸 (저지대 유도)"
                            goal = "굴뚝 회피 및 안전 저지대 안착"
                        elif diff >= 5:
                            terrain = f"단차 상태: 높이차 {diff}칸 (최저 {min_h} ~ 최고 {max_h})"
                            goal = "협곡(Well) 메우기를 통한 평탄화"
                        else:
                            terrain = f"안정 상태: 평균 {max_h}칸 고른 분포"
                            goal = "착지점 낮게 유지하며 라인 클리어"

                        lh = m["landing_height"]
                        if m["lines_cleared"] > 0:
                            narrative = f"{m['col']}번 열 안착 (착지 {lh}칸) → 라인 {m['lines_cleared']}줄 삭제 성공"
                        elif lh <= 8:
                            narrative = f"{m['col']}번 열 안착 (착지 {lh}칸) → 굴뚝을 피해 안전 저지대 안착"
                        else:
                            narrative = f"{m['col']}번 열 안착 (착지 {lh}칸) → 협곡 억제 및 안정화 선택"

                        inspector_data = {
                            "active_piece": summary["current_piece"],
                            "next_piece": summary["next_piece"],
                            "heights": h_list,
                            "terrain_diagnosis": terrain,
                            "strategy_goal": goal,
                            "chosen_move": chosen_move_data,
                            "decision_narrative": narrative,
                            "control_action": "스폰 및 정석 조작 시작",
                            "confidence": int(res["confidence"] * 100),
                            "latency_ms": res["latency_ms"],
                            "evaluated_moves": candidates
                        }

                        api_status_text = f"수신 완료 ({res['latency_ms']}ms)"
                        api_status_color = (100, 255, 120)
                        state = "FALLING"
                    else:
                        api_status_text = f"대기: {res.get('error_msg')}"
                        api_status_color = (255, 80, 80)
                        last_request_time = time.time()

            # 2. 정통 테트리스 등속 중력 및 가상 키패드 조작
            elif state == "FALLING":
                das_timer += 1
                gravity_timer += 1

                # [가상 키패드 조작] 4프레임마다 1단계씩 딱-딱 정밀 조작
                if das_timer >= das_speed:
                    das_timer = 0
                    num_rot = len(SHAPES[game.current_piece])
                    
                    # (1) 회전 조작
                    if grid_rot != target_rot:
                        grid_rot = (grid_rot + 1) % num_rot
                        r_lbl = ORIENTATION_LABELS[game.current_piece].get(grid_rot, '')
                        inspector_data["control_action"] = f"회전 키 입력: [{r_lbl}]"
                    
                    # (2) 좌우 이동 조작
                    elif grid_x != target_col:
                        if grid_x < target_col:
                            grid_x += 1
                            inspector_data["control_action"] = "우측 이동 키 입력 (▶)"
                        else:
                            grid_x -= 1
                            inspector_data["control_action"] = "좌측 이동 키 입력 (◀)"

                # [정통 중력 낙하] 정해진 프레임마다 정확히 1칸 등속 하강
                # (열과 회전이 목표와 일치하면 소프트 드롭으로 3배 빠르게 하강)
                is_aligned = (grid_x == target_col and grid_rot == target_rot)
                current_fall_interval = max(2, gravity_speed // 3) if is_aligned else gravity_speed

                if is_aligned:
                    inspector_data["control_action"] = "목표 정렬 완료 → 하강 (Soft Drop)"

                if gravity_timer >= current_fall_interval:
                    gravity_timer = 0
                    grid_y += 1

                    # 착지 지점 도달 시 고정
                    if grid_y >= target_drop_y:
                        grid_y = target_drop_y
                        grid_x = target_col
                        grid_rot = target_rot

                        clearing_rows = game.lock_blocks_to_board(
                            chosen_move_data["shape"],
                            chosen_move_data["col"],
                            chosen_move_data["drop_y"],
                            game.current_piece
                        )
                        locked_blocks = [
                            (chosen_move_data["col"] + cx, chosen_move_data["drop_y"] + cy)
                            for cx, cy in chosen_move_data["shape"]
                        ]
                        lock_timer = 4
                        state = "LOCK_FLASH"

            # 3. 착지 고정 임팩트
            elif state == "LOCK_FLASH":
                lock_timer -= 1
                if lock_timer <= 0:
                    if clearing_rows:
                        line_flash_timer = 10
                        state = "LINE_FLASH"
                    else:
                        game.advance_piece()
                        state = "READY"

            # 4. 라인 삭제 연출
            elif state == "LINE_FLASH":
                line_flash_timer -= 1
                if line_flash_timer <= 0:
                    game.clear_full_lines(clearing_rows)
                    clearing_rows = []
                    game.advance_piece()
                    state = "READY"

        # ----------------- 렌더링 -----------------
        screen.fill((16, 18, 23))

        board_rect = pygame.Rect(0, 0, BOARD_WIDTH * BLOCK_SIZE, BOARD_HEIGHT * BLOCK_SIZE)
        pygame.draw.rect(screen, (10, 11, 15), board_rect)

        for r in range(BOARD_HEIGHT):
            for c in range(BOARD_WIDTH):
                rect = pygame.Rect(c * BLOCK_SIZE, r * BLOCK_SIZE, BLOCK_SIZE, BLOCK_SIZE)
                pygame.draw.rect(screen, (24, 26, 34), rect, 1)

        for r in range(BOARD_HEIGHT):
            for c in range(BOARD_WIDTH):
                cell = game.board[r][c]
                if cell:
                    draw_block(screen, c * BLOCK_SIZE, r * BLOCK_SIZE, PIECE_COLORS.get(cell, (200, 200, 200)))

        # 생각 중일 때 상단 중앙에 대기 블록 펄스 점멸
        if state == "READY" and not game.game_over:
            c_shape = SHAPES[game.current_piece][0]
            c_color = PIECE_COLORS.get(game.current_piece, (200, 200, 200))
            blink = int((time.time() * 4) % 2) if is_network_busy else 1
            if blink == 1:
                for cx, cy in c_shape:
                    draw_block(screen, (3 + cx) * BLOCK_SIZE, cy * BLOCK_SIZE, c_color, width=2)

        # 착지 예상 지점(고스트 피스)
        if state == "FALLING" and chosen_move_data:
            g_color = PIECE_COLORS.get(game.current_piece, (200, 200, 200))
            for cx, cy in chosen_move_data["shape"]:
                gx = (chosen_move_data["col"] + cx) * BLOCK_SIZE
                gy = (chosen_move_data["drop_y"] + cy) * BLOCK_SIZE
                if gy >= 0:
                    draw_block(screen, gx, gy, g_color, border_color=(180, 190, 210), width=1)

        # [클래식 격자 블록] 픽셀 왜곡 없이 정확히 격자 칸을 밟으며 떨어지는 블록
        if state == "FALLING" and chosen_move_data:
            color = PIECE_COLORS.get(game.current_piece, (200, 200, 200))
            active_shape = SHAPES[game.current_piece][grid_rot]
            for cx, cy in active_shape:
                bx = (grid_x + cx) * BLOCK_SIZE
                by = (grid_y + cy) * BLOCK_SIZE
                if by >= 0:
                    draw_block(screen, bx, by, color)

        if state == "LOCK_FLASH":
            for bx, by in locked_blocks:
                rx, ry = bx * BLOCK_SIZE, by * BLOCK_SIZE
                pygame.draw.rect(screen, (255, 255, 255), (rx - 2, ry - 2, BLOCK_SIZE + 4, BLOCK_SIZE + 4), 3)

        if state == "LINE_FLASH":
            for r in clearing_rows:
                flash_col = (255, 255, 255) if (line_flash_timer // 2) % 2 == 0 else (255, 220, 80)
                pygame.draw.rect(screen, flash_col, (0, r * BLOCK_SIZE, BOARD_WIDTH * BLOCK_SIZE, BLOCK_SIZE))

        # ----------------- 우측 AI Inspector 패널 -----------------
        px = BOARD_WIDTH * BLOCK_SIZE + 14

        screen.blit(title_font.render("JEV System 1 Flight Inspector", True, (0, 240, 200)), (px, 10))
        spinner = ["|", "/", "-", "\\"][int(time.time() * 6) % 4] if is_network_busy else ""
        screen.blit(bold_font.render(f"API: {api_status_text} {spinner}", True, api_status_color), (px + 280, 13))

        draw_piece_preview(screen, px, 38, game.current_piece, "CURRENT", bold_font)
        draw_piece_preview(screen, px + 105, 38, game.next_piece, "NEXT", bold_font)

        sx = px + 220
        screen.blit(font.render(f"점수: {game.score:,} 점", True, (240, 240, 240)), (sx, 40))
        screen.blit(font.render(f"클리어한 줄: {game.lines_cleared_total} 줄", True, (240, 240, 240)), (sx, 60))
        screen.blit(font.render(f"보드 내 구멍: {game.count_holes()} 개", True, (255, 180, 100) if game.count_holes() > 0 else (120, 220, 150)), (sx, 80))
        screen.blit(font.render(f"낙하 주기: {gravity_speed}F/칸", True, (180, 180, 240)), (sx, 100))

        pygame.draw.line(screen, (40, 44, 56), (px, 122), (SCREEN_WIDTH - 14, 122), 1)

        # [1] 지형 진단
        screen.blit(bold_font.render("1. 지형 진단 (Dellacherie Feature Analysis)", True, (255, 215, 0)), (px, 130))
        input_box = pygame.Rect(px, 150, SCREEN_WIDTH - px - 14, 65)
        pygame.draw.rect(screen, (22, 25, 33), input_box, border_radius=4)
        pygame.draw.rect(screen, (45, 52, 68), input_box, 1, border_radius=4)

        screen.blit(font.render(f"• 상태 진단: {inspector_data['terrain_diagnosis']}", True, (255, 200, 120)), (px + 10, 156))
        screen.blit(font.render(f"• 열별 높이: {inspector_data['heights']}", True, (180, 190, 210)), (px + 10, 174))
        screen.blit(font.render(f"• 전략 지침: {inspector_data['strategy_goal']}", True, (100, 240, 180)), (px + 10, 192))

        # [2] JEV 판단 결과 및 실시간 조작 상태
        screen.blit(bold_font.render("2. JEV 의사결정 및 격자 조작 (Grid Step Control)", True, (255, 215, 0)), (px, 225))
        dec_box = pygame.Rect(px, 245, SCREEN_WIDTH - px - 14, 65)
        pygame.draw.rect(screen, (22, 25, 33), dec_box, border_radius=4)
        pygame.draw.rect(screen, (45, 52, 68), dec_box, 1, border_radius=4)

        m = inspector_data["chosen_move"]
        if m:
            c_lbl = f"▶ 목표: {m['id']} ({m['col']}번 열) | 착지: {m['landing_height']}칸 | {inspector_data['control_action']}"
            screen.blit(bold_font.render(c_lbl, True, (255, 235, 100)), (px + 10, 252))
            screen.blit(bold_font.render(f"• 선택 근거: {inspector_data['decision_narrative']}", True, (255, 215, 130)), (px + 10, 272))
            
            d_line3 = f"• 확신도: {inspector_data['confidence']}% | 통신: {inspector_data['latency_ms']}ms | 우물패널티: {m['cumulative_wells']}"
            screen.blit(font.render(d_line3, True, (160, 230, 255)), (px + 10, 290))

        # [3] 후보군 비교표
        screen.blit(bold_font.render("3. Evaluated Candidates (블록 형태 및 밀착도 비교)", True, (190, 205, 225)), (px, 320))
        tbl_y = 342
        for idx, cand in enumerate(inspector_data["evaluated_moves"][:5]):
            is_winner = m and (cand["id"] == m["id"])
            tag = "★ [선택]" if is_winner else f"   [후보{idx+1}]"
            tag_col = (100, 255, 120) if is_winner else (160, 165, 180)
            
            fit_str = f"밀착:{cand['contact_edges']}면"
            hang_str = "완전결합" if cand['overhangs'] == 0 else f"걸침({cand['overhangs']}칸)"
            txt = f"{tag} {cand['id']:<10} | 착지:{cand['landing_height']:>2}칸 | {fit_str} | {hang_str} | 줄삭제:{cand['lines_cleared']}줄"
            screen.blit(font.render(txt, True, tag_col), (px + 5, tbl_y + idx * 22))

        # 하단 조작 안내
        guide_box = pygame.Rect(px, SCREEN_HEIGHT - 55, SCREEN_WIDTH - px - 14, 45)
        pygame.draw.rect(screen, (20, 22, 28), guide_box, border_radius=4)
        screen.blit(font.render("[Space] 일시정지  |  [R] 새 게임  |  [↑/↓] 낙하 속도 조절", True, (130, 135, 150)), (px + 12, SCREEN_HEIGHT - 43))

        if game.game_over:
            overlay = pygame.Surface((BOARD_WIDTH * BLOCK_SIZE, BOARD_HEIGHT * BLOCK_SIZE), pygame.SRCALPHA)
            overlay.fill((0, 0, 0, 190))
            screen.blit(overlay, (0, 0))
            screen.blit(title_font.render("GAME OVER", True, (255, 60, 60)), (BOARD_WIDTH * BLOCK_SIZE // 2 - 60, SCREEN_HEIGHT // 2 - 20))

        pygame.display.flip()

    pygame.quit()
    sys.exit()

if __name__ == "__main__":
    main()