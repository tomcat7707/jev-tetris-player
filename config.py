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