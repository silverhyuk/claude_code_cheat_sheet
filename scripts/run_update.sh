#!/bin/bash
# ─────────────────────────────────────────────────────────────
# Claude Code 치트시트 자동 업데이트 쉘 스크립트
# Ubuntu crontab에서 매일 실행
#
# 사용법:
#   1. 이 파일에 실행 권한 부여: chmod +x scripts/run_update.sh
#   2. crontab에 등록: crontab -e
#      매일 오전 9시(KST) 실행 예시:
#      0 0 * * * /home/ubuntu/claude_code_cheat_sheet/scripts/run_update.sh
#      (UTC 00:00 = KST 09:00)
#
# 환경변수 설정:
#   OPENAI_API_KEY를 아래 또는 별도 .env 파일에 설정해야 합니다.
# ─────────────────────────────────────────────────────────────

set -euo pipefail

# ─── 경로 설정 (우분투 서버 기준, 실제 경로에 맞게 수정) ────────
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
LOG_DIR="${PROJECT_DIR}/logs"
LOG_FILE="${LOG_DIR}/auto_update_$(date +%Y%m%d_%H%M%S).log"

# ─── 로그 디렉토리 생성 ─────────────────────────────────────────
mkdir -p "$LOG_DIR"

# ─── 환경변수 로드 (.env 파일이 있으면 사용) ────────────────────
ENV_FILE="${PROJECT_DIR}/.env"
if [ -f "$ENV_FILE" ]; then
    set -a
    source "$ENV_FILE"
    set +a
fi

# ─── OPENAI_API_KEY 확인 ─────────────────────────────────────
if [ -z "${OPENAI_API_KEY:-}" ]; then
    echo "[ERROR] OPENAI_API_KEY가 설정되지 않았습니다." | tee -a "$LOG_FILE"
    echo "  .env 파일에 OPENAI_API_KEY=sk-... 형태로 설정하세요." | tee -a "$LOG_FILE"
    exit 1
fi

# ─── Python 가상환경 활성화 (있으면) ────────────────────────────
VENV_DIR="${PROJECT_DIR}/venv"
if [ -d "$VENV_DIR" ]; then
    source "$VENV_DIR/bin/activate"
elif [ -d "${PROJECT_DIR}/.venv" ]; then
    source "${PROJECT_DIR}/.venv/bin/activate"
fi

# ─── Git 사용자 설정 확인 (cron 환경에서는 없을 수 있음) ────────
cd "$PROJECT_DIR"
if [ -z "$(git config user.email 2>/dev/null || true)" ]; then
    git config user.email "auto-update@cheatsheet.local"
    git config user.name "CheatSheet Auto Updater"
fi

# ─── 최신 코드 pull ─────────────────────────────────────────────
echo "[$(date)] git pull 시작..." | tee -a "$LOG_FILE"
git pull --rebase 2>&1 | tee -a "$LOG_FILE"

# ─── Python 스크립트 실행 ────────────────────────────────────────
echo "[$(date)] auto_update.py 실행 시작..." | tee -a "$LOG_FILE"
python3 "${SCRIPT_DIR}/auto_update.py" 2>&1 | tee -a "$LOG_FILE"
EXIT_CODE=${PIPESTATUS[0]}

# ─── 결과 로깅 ──────────────────────────────────────────────────
if [ $EXIT_CODE -eq 0 ]; then
    echo "[$(date)] 자동 업데이트 성공!" | tee -a "$LOG_FILE"
else
    echo "[$(date)] 자동 업데이트 실패 (exit code: $EXIT_CODE)" | tee -a "$LOG_FILE"
fi

# ─── 오래된 로그 정리 (30일 이상) ───────────────────────────────
find "$LOG_DIR" -name "auto_update_*.log" -mtime +30 -delete 2>/dev/null || true

exit $EXIT_CODE
