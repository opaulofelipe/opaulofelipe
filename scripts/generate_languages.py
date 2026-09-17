from __future__ import annotations

import json
import math
import os
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from pathlib import Path, PurePosixPath
from xml.sax.saxutils import escape

USERNAME = os.environ.get("GITHUB_USERNAME", "opaulofelipe")
TOKEN = os.environ.get("GITHUB_TOKEN", "")
OUTPUT_DIR = Path("profile")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
API = "https://api.github.com"

PALETTE = ["#E88FA5", "#79ADD8", "#78BE9B", "#A995D6", "#D7B65E", "#D9926B"]

IGNORED_DIRS = {
    "myenv", "venv", ".venv", "env", ".env", "node_modules", "vendor",
    "site-packages", "__pycache__", ".pytest_cache", ".mypy_cache",
    ".ruff_cache", ".tox", ".nox", ".cache", ".parcel-cache", ".next",
    ".nuxt", ".svelte-kit", "dist", "build", "coverage", "target",
    "out", "bin", "obj",
}

IGNORED_FILE_ENDINGS = (
    ".min.js", ".min.css", ".bundle.js", ".bundle.css",
    ".chunk.js", ".chunk.css", ".map",
)

IGNORED_FILENAMES = {
    "package-lock.json", "yarn.lock", "pnpm-lock.yaml",
    "poetry.lock", "pipfile.lock", "composer.lock",
}

EXTENSION_TO_LANGUAGE = {
    ".html": "HTML", ".htm": "HTML",
    ".css": "CSS", ".scss": "SCSS", ".sass": "Sass", ".less": "Less",
    ".js": "JavaScript", ".mjs": "JavaScript", ".cjs": "JavaScript", ".jsx": "JavaScript",
    ".ts": "TypeScript", ".tsx": "TypeScript",
    ".vue": "Vue", ".svelte": "Svelte",
    ".py": "Python", ".sql": "SQL",
    ".java": "Java", ".kt": "Kotlin", ".kts": "Kotlin",
    ".c": "C",
    ".cc": "C++", ".cpp": "C++", ".cxx": "C++", ".hpp": "C++", ".hh": "C++", ".hxx": "C++",
    ".cs": "C#", ".php": "PHP", ".go": "Go", ".rs": "Rust", ".rb": "Ruby",
    ".swift": "Swift", ".dart": "Dart", ".r": "R",
    ".sh": "Shell", ".bash": "Shell", ".zsh": "Shell", ".fish": "Shell",
    ".ps1": "PowerShell", ".lua": "Lua", ".pl": "Perl", ".scala": "Scala",
    ".sol": "Solidity", ".hs": "Haskell", ".m": "MATLAB",
    ".asm": "Assembly", ".s": "Assembly",
}

REFERENCE_BYTES = 10_000
MIN_REPO_WEIGHT = 0.5
MAX_REPO_WEIGHT = 3.0


def request_json(url: str):
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "opaulofelipe-profile-language-card",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if TOKEN:
        headers["Authorization"] = f"Bearer {TOKEN}"

    request = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.load(response)
    except urllib.error.HTTPError as error:
        body = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(
            f"GitHub API retornou HTTP {error.code} para {url}: {body}"
        ) from error


def get_repositories():
    repositories = []
    page = 1
    while True:
        url = (
            f"{API}/users/{USERNAME}/repos"
            f"?type=owner&sort=full_name&direction=asc&per_page=100&page={page}"
        )
        batch = request_json(url)
        if not batch:
            break

        for repo in batch:
            if repo.get("fork", False):
                continue
            if repo.get("name", "").lower() == USERNAME.lower():
                continue
            repositories.append(repo)

        if len(batch) < 100:
            break
        page += 1

    return repositories


def should_ignore_path(path: str) -> bool:
    pure_path = PurePosixPath(path)
    parts_lower = [part.lower() for part in pure_path.parts]
    filename = pure_path.name.lower()

    if any(part in IGNORED_DIRS for part in parts_lower[:-1]):
        return True
    if filename in IGNORED_FILENAMES:
        return True
    if filename.endswith(IGNORED_FILE_ENDINGS):
        return True

    return False


def language_from_path(path: str) -> str | None:
    if should_ignore_path(path):
        return None
    return EXTENSION_TO_LANGUAGE.get(PurePosixPath(path).suffix.lower())


def get_repo_source_usage(repo: dict) -> Counter:
    full_name = repo["full_name"]
    default_branch = repo.get("default_branch") or "main"
    encoded_branch = urllib.parse.quote(default_branch, safe="")
    url = f"{API}/repos/{full_name}/git/trees/{encoded_branch}?recursive=1"
    data = request_json(url)

    if data.get("truncated"):
        print(f"Aviso: a árvore de {full_name} foi truncada pela API do GitHub.")

    usage = Counter()
    for item in data.get("tree", []):
        if item.get("type") != "blob":
            continue

        path = item.get("path", "")
        language = language_from_path(path)
        if not language:
            continue

        size = item.get("size")
        if not isinstance(size, int) or size <= 0:
            continue

        usage[language] += size

    return usage


def repository_weight(total_bytes: int) -> float:
    raw_weight = math.sqrt(total_bytes / REFERENCE_BYTES)
    return min(MAX_REPO_WEIGHT, max(MIN_REPO_WEIGHT, raw_weight))


def calculate_language_scores():
    scores = Counter()
    repositories_used = 0

    for repo in get_repositories():
        try:
            usage = get_repo_source_usage(repo)
        except Exception as error:
            print(f"Falha ao analisar {repo['full_name']}: {error}")
            continue

        total = sum(usage.values())
        if total <= 0:
            continue

        weight = repository_weight(total)
        repositories_used += 1

        for language, size in usage.items():
            scores[language] += (size / total) * weight

        print()
        print(
            f"Analisado: {repo['full_name']} | "
            f"{total} bytes | peso {weight:.2f}"
        )
        for language, size in usage.most_common():
            print(f"  {language}: {size} bytes ({size / total * 100:.1f}%)")

    if repositories_used == 0:
        raise RuntimeError(
            "Nenhum repositório com arquivos de código reconhecidos foi encontrado."
        )

    print()
    print(f"Repositórios considerados: {repositories_used}")
    return scores


def svg_card(items, theme: str) -> str:
    width, height = 640, 330
    cx, cy = 165, 177
    radius, stroke_width = 91, 27
    circumference = 2 * math.pi * radius

    if theme == "dark":
        text, muted, track, title = "#F3F4F6", "#AAB4BF", "#25303A", "#B8E6D1"
    else:
        text, muted, track, title = "#28343A", "#62727A", "#E5E9EA", "#52796F"

    total_score = sum(score for _, score in items) or 1
    circles = [
        f'<circle cx="{cx}" cy="{cy}" r="{radius}" fill="none" '
        f'stroke="{track}" stroke-width="{stroke_width}" opacity="0.45"/>'
    ]

    cumulative = 0.0
    percentages = []

    for index, (language, score) in enumerate(items):
        percentage = score / total_score * 100
        color = PALETTE[index % len(PALETTE)]
        percentages.append((language, percentage, color))

        segment = circumference * percentage / 100
        gap = min(3.0, segment * 0.08)
        visible_segment = max(segment - gap, 0.1)
        offset = -(circumference * cumulative / 100)

        circles.append(
            f'<circle cx="{cx}" cy="{cy}" r="{radius}" fill="none" '
            f'stroke="{color}" stroke-width="{stroke_width}" stroke-linecap="butt" '
            f'stroke-dasharray="{visible_segment:.2f} '
            f'{circumference - visible_segment:.2f}" '
            f'stroke-dashoffset="{offset:.2f}" '
            f'transform="rotate(-90 {cx} {cy})"/>'
        )

        cumulative += percentage

    legend = []
    start_y = 93

    for index, (language, percentage, color) in enumerate(percentages):
        y = start_y + index * 37
        legend.extend([
            f'<circle cx="344" cy="{y - 5}" r="6" fill="{color}"/>',
            f'<text x="363" y="{y}" class="language">{escape(language)}</text>',
            f'<text x="585" y="{y}" text-anchor="end" '
            f'class="percentage">{percentage:.1f}%</text>',
        ])

    center_top = items[0][0] if items else "—"

    return f'''<svg xmlns="http://www.w3.org/2000/svg"
    width="{width}" height="{height}" viewBox="0 0 {width} {height}"
    role="img" aria-label="As seis linguagens mais usadas por {escape(USERNAME)}">
  <style>
    .title {{
      font: 600 18px -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      letter-spacing: .04em;
      fill: {title};
    }}
    .language {{
      font: 500 15px -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      fill: {text};
    }}
    .percentage {{
      font: 500 14px -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      fill: {muted};
    }}
    .center-main {{
      font: 600 16px -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      fill: {text};
    }}
    .center-small {{
      font: 500 11px -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      letter-spacing: .12em;
      fill: {muted};
    }}
  </style>

  <text x="28" y="36" class="title">6 LINGUAGENS MAIS USADAS</text>

  {''.join(circles)}

  <text x="{cx}" y="{cy - 2}" text-anchor="middle" class="center-main">
    {escape(center_top)}
  </text>
  <text x="{cx}" y="{cy + 20}" text-anchor="middle" class="center-small">
    TOP 1
  </text>

  {''.join(legend)}
</svg>
'''


def main():
    scores = calculate_language_scores()
    top_six = scores.most_common(6)

    if not top_six:
        raise RuntimeError("Nenhuma linguagem foi encontrada após aplicar os filtros.")

    light_path = OUTPUT_DIR / "languages-light.svg"
    dark_path = OUTPUT_DIR / "languages-dark.svg"

    light_path.write_text(svg_card(top_six, "light"), encoding="utf-8")
    dark_path.write_text(svg_card(top_six, "dark"), encoding="utf-8")

    total_score = sum(score for _, score in top_six) or 1

    print()
    print("Linguagens exibidas:")
    for language, score in top_six:
        percentage = score / total_score * 100
        print(f"- {language}: {percentage:.1f}%")

    print()
    print("Arquivos gerados:")
    print(f"- {light_path}")
    print(f"- {dark_path}")


if __name__ == "__main__":
    main()
