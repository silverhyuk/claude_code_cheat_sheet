# Claude Code 치트시트 (한국어)

Claude Code의 모든 키보드 단축키, 슬래시 명령어, CLI 플래그, 설정 등을 한국어로 정리한 치트시트입니다.

## 기능

- Windows / Mac 키보드 단축키 토글 지원
- 8개 섹션: 키보드 단축키, MCP 서버, 슬래시 명령어, 메모리 & 파일, 워크플로우 & 팁, 설정 & 환경변수, 스킬 & 에이전트, CLI & 플래그
- Tailwind CSS 기반 반응형 레이아웃 (데스크탑 4열, 태블릿 2열, 모바일 1열)
- A4 가로 인쇄 최적화
- 단일 HTML 파일 (외부 의존성 없음, CDN만 사용)
- **자동 업데이트**: 공식 체인지로그를 매일 확인하여 새 버전 자동 반영

---

## 자동 업데이트 시스템

[GitHub CHANGELOG.md](https://github.com/anthropics/claude-code/blob/main/CHANGELOG.md)를 매일 확인하여 새로운 릴리스가 있으면 `index.html`을 자동으로 업데이트하고, GitHub에 커밋/푸시합니다.

### 동작 흐름

```
┌─────────────┐    ┌──────────────────┐    ┌──────────────────┐
│  crontab    │───▶│  run_update.sh   │───▶│  auto_update.py  │
│  (매일 1회) │    │  (환경 세팅)      │    │  (메인 로직)      │
└─────────────┘    └──────────────────┘    └──────────────────┘
                                                    │
                    ┌───────────────────────────────┤
                    ▼                               ▼
            ┌──────────────┐              ┌──────────────────┐
            │ VERSION.md   │              │ CHANGELOG.md      │
            │ (현재 버전)   │              │ (GitHub raw)      │
            └──────┬───────┘              └────────┬─────────┘
                   │                               │
                   └───────────┐  ┌────────────────┘
                               ▼  ▼
                      ┌─────────────────┐
                      │ 새 버전 있는가?  │
                      └────────┬────────┘
                               │ Yes
                               ▼
                      ┌─────────────────┐
                      │ o3-mini로       │
                      │ index.html 생성 │
                      └────────┬────────┘
                               │
                    ┌──────────┴──────────┐
                    ▼                     ▼
            ┌──────────────┐    ┌─────────────────┐
            │ index.html   │    │ VERSION.md 갱신  │
            │ 덮어쓰기      │    │ (버전 + 히스토리) │
            └──────────────┘    └─────────────────┘
                    │                     │
                    └──────────┬──────────┘
                               ▼
                      ┌─────────────────┐
                      │ git commit      │
                      │ git push        │
                      └─────────────────┘
```

### 파일 구조

```
claude_code_cheat_sheet/
├── index.html                # 치트시트 본체
├── VERSION.md                # 적용 버전 추적 (applied_version 기준)
├── README.md
├── .env                      # API 키 (git 미추적, 직접 생성)
└── scripts/
    ├── requirements.txt      # Python 의존성
    ├── auto_update.py        # 메인 업데이트 스크립트
    └── run_update.sh         # crontab용 쉘 래퍼
```

### 버전 관리 방식

`VERSION.md` 파일에서 현재 반영된 버전을 추적합니다:

```markdown
- **applied_version**: v2.1.90    ← 이 값과 체인지로그를 비교
- **last_updated**: 2026-04-08

## Applied Versions History
| 버전 | 적용일 | 주요 변경사항 요약 |
|------|--------|-------------------|
| v2.1.90 | 2026-04-08 | 초기 버전 추적 시작 |
| v2.1.95 | 2026-04-15 | v2.1.91~v2.1.95 신규 기능 자동 반영 |  ← 자동 추가
```

---

## 우분투 서버 설정 가이드

### 1. 사전 요구사항

- Ubuntu 20.04+ 
- Python 3.10+
- Git (GitHub 인증 설정 완료)
- OpenAI API 키

### 2. 프로젝트 클론 및 환경 구성

```bash
# 프로젝트 클론
cd /home/ubuntu
git clone https://github.com/silverhyuk/claude_code_cheat_sheet.git
cd claude_code_cheat_sheet

# Python 가상환경 생성 및 패키지 설치
python3 -m venv venv
source venv/bin/activate
pip install -r scripts/requirements.txt
```

### 3. 환경변수 설정

프로젝트 루트에 `.env` 파일을 생성합니다:

```bash
echo "OPENAI_API_KEY=sk-your-openai-api-key-here" > .env
```

> `.env` 파일은 `.gitignore`에 추가하여 원격 저장소에 노출되지 않도록 합니다.

### 4. 쉘 스크립트 실행 권한 부여

```bash
chmod +x scripts/run_update.sh
```

### 5. 수동 테스트

crontab 등록 전에 수동으로 실행하여 정상 동작을 확인합니다:

```bash
./scripts/run_update.sh
```

로그 확인:

```bash
ls logs/
cat logs/auto_update_*.log
```

### 6. crontab 등록

```bash
crontab -e
```

아래 줄을 추가합니다:

```cron
# Claude Code 치트시트 자동 업데이트 - 매일 KST 09:00 (= UTC 00:00)
0 0 * * * /home/ubuntu/claude_code_cheat_sheet/scripts/run_update.sh
```

> **시간대 참고**: 우분투 서버가 UTC 기준이면 `0 0 * * *`이 KST 오전 9시입니다.  
> KST로 설정된 서버라면 `0 9 * * *`으로 변경하세요.

등록 확인:

```bash
crontab -l
```

---

## 쉘 스크립트(run_update.sh) 상세

| 기능 | 설명 |
|------|------|
| `.env` 자동 로드 | 프로젝트 루트의 `.env`에서 `OPENAI_API_KEY` 읽기 |
| venv 자동 활성화 | `venv/` 또는 `.venv/` 디렉터리 자동 감지 |
| git pull | 실행 전 최신 코드 pull (충돌 방지) |
| 로그 저장 | `logs/auto_update_YYYYMMDD_HHMMSS.log` |
| 로그 정리 | 30일 이상 된 로그 자동 삭제 |
| Git 사용자 설정 | cron 환경에서 git config 없을 때 자동 설정 |

---

## 문제 해결

### API 키 오류

```
[ERROR] OPENAI_API_KEY가 설정되지 않았습니다.
```

→ `.env` 파일이 프로젝트 루트에 있는지, 키 형식이 올바른지 확인

### CHANGELOG.md 파싱 실패

```
CHANGELOG.md에서 릴리스 정보를 파싱할 수 없습니다
```

→ CHANGELOG.md 마크다운 형식이 변경되었을 수 있음. `auto_update.py`의 `parse_changelog()` 함수 수정 필요
→ 현재 `## x.y.z` (h2 헤더) + `- ` (불릿 리스트) 형식 기준으로 파싱

### git push 실패

```
git push 실패: ...
```

→ 서버에서 GitHub 인증이 설정되어 있는지 확인 (SSH key 또는 credential helper)

```bash
# SSH 키 확인
ssh -T git@github.com

# HTTPS credential helper 설정
git config --global credential.helper store
```

### 로그 확인

```bash
# 최근 로그 확인
ls -lt logs/ | head -5
cat logs/auto_update_*.log | tail -50

# cron 실행 여부 확인
grep CRON /var/log/syslog | tail -10
```
