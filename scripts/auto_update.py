#!/usr/bin/env python3
"""
Claude Code 치트시트 자동 업데이트 스크립트

1. GitHub anthropics/claude-code CHANGELOG.md에서 최신 릴리스 정보 파싱
2. VERSION.md 의 applied_version과 비교
3. 새 버전이 있으면 index.html 업데이트 지시 + VERSION.md 갱신
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

    형식:
        ## 2.1.96
        - Fixed ...
        - Added ...

        ## 2.1.94
        - ...

    반환: [{"version": "v2.1.96", "content": "- Fixed ...\n- Added ..."}, ...]
    최신순으로 정렬됨.
    """
    releases = []

    # "## 2.1.96" 패턴으로 분할
    # 각 블록은 "## 버전번호\n내용" 형태
    blocks = re.split(r"^## (\d+\.\d+\.\d+)\s*$", markdown, flags=re.MULTILINE)

    # blocks[0]은 "# Changelog\n" 같은 헤더 부분 (버림)
    # blocks[1] = "2.1.96", blocks[2] = 내용, blocks[3] = "2.1.94", blocks[4] = 내용 ...
    for i in range(1, len(blocks) - 1, 2):
        version = f"v{blocks[i]}"
        content = blocks[i + 1].strip()
        releases.append({
            "version": version,
            "content": content,
        })

    return releases


def get_new_releases(releases: list[dict], applied_version: str) -> list[dict]:
    """applied_version보다 새로운 릴리스만 필터링"""

    def version_tuple(v: str) -> tuple:
        nums = re.findall(r"\d+", v)
        return tuple(int(n) for n in nums)

    applied = version_tuple(applied_version)
    new = []
    for r in releases:
        if version_tuple(r["version"]) > applied:
            new.append(r)
    # 오래된 순으로 정렬 (적용 순서)
    new.sort(key=lambda r: version_tuple(r["version"]))
    return new


# ─── 3. OpenAI API로 index.html 업데이트 생성 ──────────────────────
def generate_update_with_openai(
    new_releases: list[dict], current_html: str
) -> str | None:
    """
    OpenAI API를 사용해 새 릴리스 정보를 반영한 index.html을 생성.
    API 키가 없으면 None 반환.
    """
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        log.warning("OPENAI_API_KEY가 설정되지 않았습니다. 업데이트 건너뜀.")
        return None

    try:
        from openai import OpenAI
    except ImportError:
        log.warning("openai 패키지가 없습니다. pip install openai")
        return None

    client = OpenAI(api_key=api_key)

    releases_text = "\n\n".join(
        f"### {r['version']}\n{r.get('date', '')}\n{r['content']}"
        for r in new_releases
    )

    latest_version = new_releases[-1]["version"]

    prompt = f"""당신은 Claude Code 치트시트(HTML) 업데이트 전문가입니다.

아래는 새로 추가된 Claude Code 릴리스 노트입니다:

{releases_text}

현재 index.html의 내용이 주어집니다. 다음 규칙에 따라 업데이트하세요:

1. 헤더의 버전을 {latest_version}으로 변경
2. 새 기능/변경사항을 해당하는 섹션에 추가 (키보드 단축키, 슬래시 커맨드, CLI 플래그, 환경변수, Hooks 등)
3. 새로 추가된 항목에는 `<span class="inline-block bg-amber-400 text-amber-900 text-2xs font-bold px-1 rounded ml-1 align-middle">NEW</span>` 뱃지를 붙이세요
4. 기존에 NEW 뱃지가 붙어있던 항목 중 이전 릴리스에 해당하는 것들의 NEW 뱃지는 유지하세요 (제거하지 마세요)
5. 한국어로 간결하게 설명
6. 기존 HTML 구조와 스타일을 정확히 따르세요

전체 index.html을 출력하세요. HTML만 출력하고 다른 설명은 하지 마세요.

현재 index.html:
```html
{current_html}
```"""

    log.info("OpenAI gpt-5.3-codex Responses API로 업데이트 생성 중...")
    response = client.responses.create(
        model="gpt-5.3-codex",
        instructions="당신은 HTML 코드 생성 전문가입니다. 요청받은 HTML만 출력하세요.",
        input=prompt,
    )

    response_text = response.output_text

    # HTML만 추출
    html_match = re.search(r"(<!DOCTYPE html>.*</html>)", response_text, re.DOTALL)
    if html_match:
        result = html_match.group(1)
    elif response_text.strip().startswith("<!DOCTYPE") or response_text.strip().startswith("<html"):
        result = response_text.strip()
    else:
        log.error("API 응답에서 유효한 HTML을 추출할 수 없습니다")
        return None

    # ─── 안전장치: 원본 대비 너무 짧으면 거부 ───
    current_len = len(current_html)
    result_len = len(result)
    ratio = result_len / current_len if current_len > 0 else 0
    log.info(f"HTML 크기 비교: 원본 {current_len:,}자 → 생성 {result_len:,}자 (비율: {ratio:.1%})")

    if ratio < 0.8:
        log.error(
            f"생성된 HTML이 원본의 {ratio:.0%} 크기입니다. "
            f"잘린 응답으로 판단하여 업데이트를 거부합니다."
        )
        return None

    return result


# ─── 4. VERSION.md 업데이트 ─────────────────────────────────────────
def update_version_md(new_version: str, summary: str):
    """VERSION.md에 새 버전 정보 반영"""
    text = VERSION_MD.read_text(encoding="utf-8")
    today = datetime.now().strftime("%Y-%m-%d")

    # applied_version 업데이트
    text = re.sub(
        r"(\*\*applied_version\*\*:\s*)v[\d.]+",
        f"\\g<1>{new_version}",
        text,
    )

    # last_updated 업데이트
    text = re.sub(
        r"(\*\*last_updated\*\*:\s*)\d{4}-\d{2}-\d{2}",
        f"\\g<1>{today}",
        text,
    )

    # 히스토리 테이블에 새 행 추가
    new_row = f"| {new_version} | {today} | {summary} |"
    # 테이블 마지막 행 뒤에 추가
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


# ─── 5. Git commit & push ──────────────────────────────────────────
def git_commit_and_push(version: str):
    """변경사항을 git commit하고 push"""
    os.chdir(REPO_DIR)

    def run(cmd: list[str]) -> subprocess.CompletedProcess:
        return subprocess.run(cmd, capture_output=True, text=True, cwd=REPO_DIR)

    # 변경사항 확인
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

    # 5. Claude API로 index.html 업데이트
    current_html = INDEX_HTML.read_text(encoding="utf-8")
    updated_html = generate_update_with_openai(new_releases, current_html)

    if updated_html is None:
        log.error("index.html 업데이트 생성 실패. 종료.")
        sys.exit(1)

    # 6. 파일 저장
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
