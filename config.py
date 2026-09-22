import os
from dotenv import load_dotenv

# .env 파일에서 환경변수 로드
load_dotenv()

TYPESAFE_API_KEY = os.getenv("TYPESAFE_API_KEY", "")
TYPESAFE_API_URL = "https://api.typesafe.ai/v1/systemone"

# 테트리스 규격 및 화면 설정
BLOCK_SIZE = 30
BOARD_WIDTH = 10
BOARD_HEIGHT = 20
SCREEN_WIDTH = BOARD_WIDTH * BLOCK_SIZE + 480
SCREEN_HEIGHT = BOARD_HEIGHT * BLOCK_SIZE
FPS = 60

# 실시간 스트레스 테스트 설정
# - iid: 매 블록을 독립적으로 1/7 확률로 추첨 (패턴/보정 없는 스트레스 테스트)
# - 7bag: 현대 테트리스에서 흔히 쓰는 7-bag 방식
PIECE_RANDOMIZER = os.getenv("PIECE_RANDOMIZER", "iid").strip().lower()
if PIECE_RANDOMIZER not in {"iid", "7bag"}:
    PIECE_RANDOMIZER = "iid"

_seed_raw = os.getenv("TETRIS_RANDOM_SEED", "").strip()
TETRIS_RANDOM_SEED = int(_seed_raw) if _seed_raw else None

# 블록은 JEV 응답을 기다리지 않고 즉시 낙하한다.
# 이 시간 안에 JEV가 도착하지 않으면 휴리스틱 1위 후보로 계속 진행한다.
JEV_DECISION_DEADLINE_MS = int(os.getenv("JEV_DECISION_DEADLINE_MS", "1600"))
