#!/usr/bin/env python3
"""
Claude Code 치트시트 자동 업데이트 스크립트

1. GitHub anthropics/claude-code CHANGELOG.md에서 최신 릴리스 정보 파싱
2. VERSION.md 의 applied_version과 비교
3. 새 버전이 있으면 OpenAI API로 추가 항목을 JSON으로 받아 index.html에 삽입
4. git commit & push

필요 패키지: pip install requests openai
환경변수: OPENAI_API_KEY (OpenAI API 호출용)
"""

import os
import re
import sys
import json
import subprocess
import logging
from datetime import datetime
from pathlib import Path

import requests

# ─── 설정 ───────────────────────────────────────────────────────────
REPO_DIR = Path(__file__).resolve().parent.parent  # 프로젝트 루트
INDEX_HTML = REPO_DIR / "index.html"
VERSION_MD = REPO_DIR / "VERSION.md"
CHANGELOG_URL = "https://raw.githubusercontent.com/anthropics/claude-code/main/CHANGELOG.md"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

# ─── index.html 섹션 → 서브섹션 매핑 ────────────────────────────────
# API에게 이 목록을 알려주고, 각 항목이 어디에 들어갈지 지정하게 함
SECTIONS = {
    "키보드 단축키": ["일반 조작", "모드 전환", "입력", "접두사", "세션 선택기"],
    "MCP 서버": ["서버 추가", "범위", "관리"],
    "슬래시 명령어": ["세션", "설정", "도구", "특수"],
    "메모리 & 파일": ["CLAUDE.md 위치", "규칙 & 가져오기", "자동 메모리"],
    "워크플로우 & 팁": ["플랜 모드", "사고(Thinking) & 노력 수준", "Git Worktree", "음성 모드", "컨텍스트 관리", "세션 활용", "SDK / 헤드리스", "스케줄링 & 원격"],
    "설정 & 환경변수": ["설정 파일", "주요 설정", "주요 환경변수", "Hooks 이벤트"],
    "스킬 & 에이전트": ["내장 스킬", "커스텀 스킬 위치", "스킬 프론트매터", "내장 에이전트", "에이전트 프론트매터"],
    "CLI & 플래그": ["핵심 명령어", "주요 플래그", "권한 모드"],
}


# ─── 1. VERSION.md에서 현재 적용 버전 읽기 ─────────────────────────
def get_applied_version() -> str:
    """VERSION.md에서 applied_version 값을 파싱"""
    text = VERSION_MD.read_text(encoding="utf-8")
    match = re.search(r"\*\*applied_version\*\*:\s*(v[\d.]+)", text)
    if not match:
        log.error("VERSION.md에서 applied_version을 찾을 수 없습니다")
        sys.exit(1)
    return match.group(1)


# ─── 2. GitHub CHANGELOG.md 가져오기 & 파싱 ─────────────────────────
def fetch_changelog() -> str:
    """GitHub raw CHANGELOG.md 마크다운 텍스트 가져오기"""
    log.info(f"CHANGELOG.md 가져오는 중: {CHANGELOG_URL}")
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; ClaudeCodeCheatSheet/1.0)"
    }
    resp = requests.get(CHANGELOG_URL, headers=headers, timeout=30)
    resp.raise_for_status()
    return resp.text


def parse_changelog(markdown: str) -> list[dict]:
    """
    CHANGELOG.md 마크다운에서 버전별 릴리스 정보를 파싱.
    반환: [{"version": "v2.1.96", "content": "- Fixed ...\n- Added ..."}, ...]
    """
    releases = []
    blocks = re.split(r"^## (\d+\.\d+\.\d+)\s*$", markdown, flags=re.MULTILINE)
    for i in range(1, len(blocks) - 1, 2):
        version = f"v{blocks[i]}"
        content = blocks[i + 1].strip()
        releases.append({"version": version, "content": content})
    return releases


def get_new_releases(releases: list[dict], applied_version: str) -> list[dict]:
    """applied_version보다 새로운 릴리스만 필터링"""

    def version_tuple(v: str) -> tuple:
        nums = re.findall(r"\d+", v)
        return tuple(int(n) for n in nums)

    applied = version_tuple(applied_version)
    new = [r for r in releases if version_tuple(r["version"]) > applied]
    new.sort(key=lambda r: version_tuple(r["version"]))
    return new


# ─── 3. OpenAI API로 추가 항목 JSON 생성 ────────────────────────────
def get_new_items_from_api(new_releases: list[dict]) -> list[dict] | None:
    """
    OpenAI API에 릴리스 노트를 보내고, 치트시트에 추가할 항목을 JSON으로 받음.
    반환 형식: [{"section": "...", "subsection": "...", "key": "...", "desc": "..."}, ...]
    """
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        log.warning("OPENAI_API_KEY가 설정되지 않았습니다.")
        return None

    try:
        from openai import OpenAI
    except ImportError:
        log.warning("openai 패키지가 없습니다. pip install openai")
        return None

    client = OpenAI(api_key=api_key)

    releases_text = "\n\n".join(
        f"### {r['version']}\n{r['content']}" for r in new_releases
    )

    sections_desc = json.dumps(SECTIONS, ensure_ascii=False, indent=2)

    prompt = f"""아래는 Claude Code의 새로운 릴리스 노트입니다:

{releases_text}

위 릴리스 노트에서 **치트시트에 추가할 만한 새 기능, 명령어, 설정, 환경변수, 플래그, 단축키** 항목만 추출하세요.
버그 수정, 성능 개선, 내부 변경 등 치트시트에 넣을 필요 없는 항목은 제외하세요.

치트시트의 섹션/서브섹션 구조:
{sections_desc}

각 항목을 아래 JSON 배열 형식으로 출력하세요. JSON만 출력하고 다른 텍스트는 절대 포함하지 마세요:

```json
[
  {{
    "section": "섹션명 (위 구조에서 선택)",
    "subsection": "서브섹션명 (위 구조에서 선택)",
    "key": "항목의 키 (예: Ctrl+X, /command, --flag, ENV_VAR 등)",
    "desc": "한국어 간결한 설명 (10자~30자)"
  }}
]
```

추가할 항목이 없으면 빈 배열 `[]`을 출력하세요."""

    log.info("OpenAI API로 추가 항목 추출 중...")
    response = client.responses.create(
        model="gpt-5.3-codex",
        instructions="당신은 Claude Code 전문가입니다. 요청된 JSON만 출력하세요. 마크다운 코드블록 없이 순수 JSON만 출력하세요.",
        input=prompt,
    )

    response_text = response.output_text.strip()
    log.info(f"API 응답 길이: {len(response_text)}자")

    # JSON 추출 (코드블록 안에 있을 수 있음)
    json_match = re.search(r"\[.*\]", response_text, re.DOTALL)
    if not json_match:
        log.error(f"API 응답에서 JSON을 추출할 수 없습니다: {response_text[:200]}")
        return None

    try:
        items = json.loads(json_match.group(0))
    except json.JSONDecodeError as e:
        log.error(f"JSON 파싱 실패: {e}\n응답: {response_text[:500]}")
        return None

    if not isinstance(items, list):
        log.error("API 응답이 배열이 아닙니다")
        return None

    log.info(f"추출된 항목: {len(items)}개")
    for item in items:
        log.info(f"  [{item.get('section')}/{item.get('subsection')}] {item.get('key')} → {item.get('desc')}")

    return items


# ─── 4. index.html에 항목 삽입 ──────────────────────────────────────
NEW_BADGE = '<span class="inline-block bg-amber-400 text-amber-900 text-2xs font-bold px-1 rounded ml-1 align-middle">NEW</span>'


def build_row_html(key: str, desc: str) -> str:
    """치트시트 한 줄 HTML 생성"""
    # key가 코드/명령어 형태인지 단축키 형태인지 판별
    if key.startswith("Ctrl") or key.startswith("⌃") or key.startswith("Alt") or key.startswith("⌥") or key.startswith("Shift") or key.startswith("Esc"):
        # 단축키 → kbd 태그
        key_html = f'<kbd class="k inline-block bg-gray-100 border border-gray-200 rounded px-1 font-mono text-2xs leading-relaxed whitespace-nowrap">{key}</kbd>'
    else:
        # 코드/명령어 → code 태그
        key_html = f'<code class="bg-gray-100 rounded px-1 font-mono text-2xs">{key}</code>'

    return (
        f'        <div class="flex gap-1.5 py-0.5 items-baseline">'
        f'<div class="shrink-0 min-w-28">{key_html}</div>'
        f'<div class="text-gray-500">{desc} {NEW_BADGE}</div></div>'
    )


def find_subsection_insert_pos(lines: list[str], subsection_name: str) -> int | None:
    """
    서브섹션의 마지막 항목 뒤 위치(= </div> 직전)를 찾음.
    서브섹션 헤더를 찾고, 그 아래 divide-y div의 마지막 항목 위치를 반환.
    """
    # 서브섹션 헤더 찾기
    header_idx = None
    for i, line in enumerate(lines):
        if f">{subsection_name}</div>" in line:
            header_idx = i
            break

    if header_idx is None:
        return None

    # 헤더 다음의 <div class="divide-y ..."> 블록에서 마지막 항목 찾기
    # 항목은 <div class="flex gap-1.5 py-0.5 ..."> 패턴
    last_item_idx = None
    for i in range(header_idx + 1, min(header_idx + 80, len(lines))):
        line = lines[i].strip()
        if 'class="flex gap-1.5 py-0.5' in lines[i]:
            last_item_idx = i
        # 서브섹션 블록의 끝 (다음 서브섹션 헤더 또는 섹션 끝)
        if last_item_idx and (
            'font-bold text-2xs uppercase tracking-wider' in line
            or line == '</div>'  # divide-y 닫힘
        ):
            break

    return last_item_idx


def insert_items_into_html(html: str, items: list[dict], latest_version: str) -> str:
    """항목들을 index.html의 적절한 위치에 삽입"""
    lines = html.split("\n")

    # 버전 업데이트
    for i, line in enumerate(lines):
        if "&middot; 한국어" in line:
            lines[i] = re.sub(r"v[\d.]+", latest_version, line)
            break

    # 삽입할 항목을 서브섹션별로 그룹핑 (역순으로 삽입해야 인덱스가 밀리지 않음)
    insertions: list[tuple[int, str]] = []  # (line_idx, html)

    for item in items:
        subsection = item.get("subsection", "")
        key = item.get("key", "")
        desc = item.get("desc", "")

        if not subsection or not key or not desc:
            log.warning(f"불완전한 항목 건너뜀: {item}")
            continue

        # 중복 체크: 이미 같은 key가 있는지
        key_escaped = re.escape(key)
        if any(re.search(key_escaped, line) for line in lines):
            log.info(f"  중복 건너뜀: {key}")
            continue

        pos = find_subsection_insert_pos(lines, subsection)
        if pos is None:
            log.warning(f"  서브섹션 '{subsection}'을 찾을 수 없음: {key}")
            continue

        row_html = build_row_html(key, desc)
        insertions.append((pos, row_html))

    if not insertions:
        log.info("삽입할 새 항목이 없습니다.")
        return html

    # 역순 정렬 (뒤에서부터 삽입해야 앞의 인덱스가 밀리지 않음)
    insertions.sort(key=lambda x: x[0], reverse=True)

    for pos, row_html in insertions:
        lines.insert(pos + 1, row_html)

    log.info(f"총 {len(insertions)}개 항목 삽입 완료")
    return "\n".join(lines)


# ─── 5. VERSION.md 업데이트 ─────────────────────────────────────────
def update_version_md(new_version: str, summary: str):
    """VERSION.md에 새 버전 정보 반영"""
    text = VERSION_MD.read_text(encoding="utf-8")
    today = datetime.now().strftime("%Y-%m-%d")

    text = re.sub(
        r"(\*\*applied_version\*\*:\s*)v[\d.]+",
        f"\\g<1>{new_version}",
        text,
    )
    text = re.sub(
        r"(\*\*last_updated\*\*:\s*)\d{4}-\d{2}-\d{2}",
        f"\\g<1>{today}",
        text,
    )

    new_row = f"| {new_version} | {today} | {summary} |"
    lines = text.split("\n")
    table_end = -1
    for i, line in enumerate(lines):
        if line.startswith("|") and "---" not in line and "버전" not in line:
            table_end = i
    if table_end >= 0:
        lines.insert(table_end + 1, new_row)
    text = "\n".join(lines)

    VERSION_MD.write_text(text, encoding="utf-8")
    log.info(f"VERSION.md 업데이트 완료: {new_version}")


# ─── 6. Git commit & push ──────────────────────────────────────────
def git_commit_and_push(version: str):
    """변경사항을 git commit하고 push"""
    os.chdir(REPO_DIR)

    def run(cmd: list[str]) -> subprocess.CompletedProcess:
        return subprocess.run(cmd, capture_output=True, text=True, cwd=REPO_DIR)

    status = run(["git", "status", "--porcelain"])
    if not status.stdout.strip():
        log.info("변경사항 없음. 커밋 건너뜀.")
        return

    run(["git", "add", "index.html", "VERSION.md"])

    commit_msg = f"feat: {version} 릴리스 노트 반영 (자동 업데이트)"
    result = run(["git", "commit", "-m", commit_msg])
    if result.returncode != 0:
        log.error(f"git commit 실패: {result.stderr}")
        return

    log.info(f"커밋 완료: {commit_msg}")

    result = run(["git", "push"])
    if result.returncode != 0:
        log.error(f"git push 실패: {result.stderr}")
        return

    log.info("push 완료!")


# ─── 메인 ───────────────────────────────────────────────────────────
def main():
    log.info("=" * 60)
    log.info("Claude Code 치트시트 자동 업데이트 시작")
    log.info("=" * 60)

    # 1. 현재 적용 버전 확인
    applied_version = get_applied_version()
    log.info(f"현재 적용 버전: {applied_version}")

    # 2. CHANGELOG.md 가져오기
    try:
        changelog_md = fetch_changelog()
    except requests.RequestException as e:
        log.error(f"CHANGELOG.md 가져오기 실패: {e}")
        sys.exit(1)

    # 3. 릴리스 파싱
    releases = parse_changelog(changelog_md)
    if not releases:
        log.warning("CHANGELOG.md에서 릴리스 정보를 파싱할 수 없습니다")
        sys.exit(1)

    log.info(f"파싱된 릴리스: {len(releases)}개")
    for r in releases[:5]:
        log.info(f"  - {r['version']}")

    # 4. 새 릴리스 확인
    new_releases = get_new_releases(releases, applied_version)
    if not new_releases:
        log.info("새로운 릴리스가 없습니다. 종료.")
        return

    latest_version = new_releases[-1]["version"]
    log.info(f"새 릴리스 발견: {len(new_releases)}개 (최신: {latest_version})")
    for r in new_releases:
        log.info(f"  - {r['version']}")

    # 5. API로 추가 항목 추출
    new_items = get_new_items_from_api(new_releases)
    if new_items is None:
        log.error("API에서 추가 항목을 가져오지 못했습니다. 종료.")
        sys.exit(1)

    # 6. index.html에 항목 삽입
    current_html = INDEX_HTML.read_text(encoding="utf-8")
    updated_html = insert_items_into_html(current_html, new_items, latest_version)

    INDEX_HTML.write_text(updated_html, encoding="utf-8")
    log.info("index.html 업데이트 완료")

    # 7. VERSION.md 업데이트
    version_range = (
        f"{new_releases[0]['version']}~{latest_version}"
        if len(new_releases) > 1
        else latest_version
    )
    summary = f"{version_range} 신규 기능 자동 반영"
    update_version_md(latest_version, summary)

    # 8. Git commit & push
    git_commit_and_push(latest_version)

    log.info("=" * 60)
    log.info("자동 업데이트 완료!")
    log.info("=" * 60)


if __name__ == "__main__":
    main()
