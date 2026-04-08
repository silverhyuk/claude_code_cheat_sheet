#!/usr/bin/env python3
"""
Claude Code 치트시트 자동 업데이트 스크립트

1. https://code.claude.com/docs/en/changelog 에서 최신 릴리스 정보 스크래핑
2. VERSION.md 의 applied_version과 비교
3. 새 버전이 있으면 index.html 업데이트 지시 + VERSION.md 갱신
4. git commit & push

필요 패키지: pip install requests beautifulsoup4 openai
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
from bs4 import BeautifulSoup

# ─── 설정 ───────────────────────────────────────────────────────────
REPO_DIR = Path(__file__).resolve().parent.parent  # 프로젝트 루트
INDEX_HTML = REPO_DIR / "index.html"
VERSION_MD = REPO_DIR / "VERSION.md"
CHANGELOG_URL = "https://code.claude.com/docs/en/changelog"

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


# ─── 2. 체인지로그 페이지 스크래핑 ──────────────────────────────────
def fetch_changelog() -> str:
    """체인지로그 페이지 HTML 가져오기"""
    log.info(f"체인지로그 페이지 가져오는 중: {CHANGELOG_URL}")
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; ClaudeCodeCheatSheet/1.0)"
    }
    resp = requests.get(CHANGELOG_URL, headers=headers, timeout=30)
    resp.raise_for_status()
    return resp.text


def parse_changelog(html: str) -> list[dict]:
    """
    체인지로그 HTML에서 버전별 릴리스 정보를 파싱.
    반환: [{"version": "v2.1.91", "date": "...", "content": "..."}, ...]
    최신순으로 정렬됨.
    """
    soup = BeautifulSoup(html, "html.parser")
    releases = []

    # 체인지로그 페이지 구조에 따라 파싱 (h2/h3 태그에 버전이 포함)
    # 여러 가능한 구조에 대응
    version_headers = soup.find_all(
        lambda tag: tag.name in ("h1", "h2", "h3")
        and re.search(r"v?\d+\.\d+\.\d+", tag.get_text())
    )

    if not version_headers:
        # 대안: 전체 텍스트에서 버전 패턴 추출
        log.warning("헤더에서 버전을 찾지 못함. 전체 텍스트 파싱 시도...")
        text = soup.get_text()
        version_blocks = re.split(r"(?=(?:^|\n)#{1,3}\s*v?\d+\.\d+\.\d+)", text)
        for block in version_blocks:
            ver_match = re.search(r"(v?\d+\.\d+\.\d+)", block)
            if ver_match:
                version = ver_match.group(1)
                if not version.startswith("v"):
                    version = "v" + version
                releases.append({
                    "version": version,
                    "content": block.strip(),
                })
        return releases

    for i, header in enumerate(version_headers):
        ver_match = re.search(r"(v?\d+\.\d+\.\d+)", header.get_text())
        if not ver_match:
            continue

        version = ver_match.group(1)
        if not version.startswith("v"):
            version = "v" + version

        # 날짜 추출 시도
        date_match = re.search(
            r"(\d{4}[-/]\d{2}[-/]\d{2}|[A-Z][a-z]+ \d{1,2},? \d{4})",
            header.get_text(),
        )
        date_str = date_match.group(1) if date_match else ""

        # 다음 헤더까지의 콘텐츠 수집
        content_parts = []
        sibling = header.find_next_sibling()
        next_header = version_headers[i + 1] if i + 1 < len(version_headers) else None

        while sibling and sibling != next_header:
            content_parts.append(sibling.get_text(strip=True))
            sibling = sibling.find_next_sibling()

        releases.append({
            "version": version,
            "date": date_str,
            "content": "\n".join(content_parts),
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

    log.info("OpenAI Codex Mini API로 업데이트 생성 중...")
    response = client.responses.create(
        model="codex-mini-latest",
        instructions="당신은 HTML 코드 생성 전문가입니다. 요청받은 HTML만 출력하세요.",
        input=prompt,
    )

    response_text = response.output_text

    # HTML만 추출
    html_match = re.search(r"(<!DOCTYPE html>.*</html>)", response_text, re.DOTALL)
    if html_match:
        return html_match.group(1)

    # 이미 HTML인 경우
    if response_text.strip().startswith("<!DOCTYPE") or response_text.strip().startswith("<html"):
        return response_text.strip()

    log.error("Claude 응답에서 유효한 HTML을 추출할 수 없습니다")
    return None


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

    # 2. 체인지로그 스크래핑
    try:
        changelog_html = fetch_changelog()
    except requests.RequestException as e:
        log.error(f"체인지로그 가져오기 실패: {e}")
        sys.exit(1)

    # 3. 릴리스 파싱
    releases = parse_changelog(changelog_html)
    if not releases:
        log.warning("체인지로그에서 릴리스 정보를 파싱할 수 없습니다")
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
