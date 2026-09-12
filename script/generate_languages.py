from __future__ import annotations

import json
import math
import os
import urllib.error
import urllib.request
from collections import Counter
from pathlib import Path
from xml.sax.saxutils import escape

USERNAME = os.environ.get("GITHUB_USERNAME", "opaulofelipe")
TOKEN = os.environ.get("GITHUB_TOKEN", "")
OUTPUT_DIR = Path("profile")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

PALETTE = [
    "#E88FA5",
    "#79ADD8",
    "#78BE9B",
    "#A995D6",
    "#D7B65E",
    "#D9926B",
]

API = "https://api.github.com"


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

        repositories.extend(
            repo for repo in batch if not repo.get("fork", False)
        )

        if len(batch) < 100:
            break

        page += 1

    return repositories


def get_language_totals():
    totals = Counter()

    for repo in get_repositories():
        language_url = repo.get("languages_url")
        if not language_url:
            continue

        languages = request_json(language_url)

        for language, bytes_count in languages.items():
            totals[language] += int(bytes_count)

    return totals


def svg_card(items, theme: str) -> str:
    width = 640
    height = 330
    cx = 165
    cy = 177
    radius = 91
    stroke_width = 27
    circumference = 2 * math.pi * radius

    if theme == "dark":
        text = "#F3F4F6"
        muted = "#AAB4BF"
        track = "#25303A"
        title = "#B8E6D1"
    else:
        text = "#28343A"
        muted = "#62727A"
        track = "#E5E9EA"
        title = "#52796F"

    total = sum(value for _, value in items) or 1

    circles = [
        (
            f'<circle cx="{cx}" cy="{cy}" r="{radius}" '
            f'fill="none" stroke="{track}" stroke-width="{stroke_width}" '
            f'opacity="0.45"/>'
        )
    ]

    cumulative = 0.0
    percentages = []

    for index, (language, value) in enumerate(items):
        percentage = value / total * 100
        percentages.append((language, percentage, PALETTE[index]))

        segment = circumference * percentage / 100
        gap = min(3.0, segment * 0.08)
        visible_segment = max(segment - gap, 0.1)
        offset = -(circumference * cumulative / 100)

        circles.append(
            f'<circle cx="{cx}" cy="{cy}" r="{radius}" '
            f'fill="none" stroke="{PALETTE[index]}" '
            f'stroke-width="{stroke_width}" stroke-linecap="butt" '
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
        legend.extend(
            [
                f'<circle cx="344" cy="{y - 5}" r="6" fill="{color}"/>',
                f'<text x="363" y="{y}" class="language">{escape(language)}</text>',
                (
                    f'<text x="585" y="{y}" text-anchor="end" '
                    f'class="percentage">{percentage:.1f}%</text>'
                ),
            ]
        )

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
    totals = get_language_totals()
    top_six = totals.most_common(6)

    if not top_six:
        raise RuntimeError("Nenhuma linguagem foi encontrada nos repositórios públicos.")

    (OUTPUT_DIR / "languages-light.svg").write_text(
        svg_card(top_six, "light"),
        encoding="utf-8",
    )

    (OUTPUT_DIR / "languages-dark.svg").write_text(
        svg_card(top_six, "dark"),
        encoding="utf-8",
    )

    print("Linguagens incluídas:")
    for language, value in top_six:
        print(f"- {language}: {value} bytes")


if __name__ == "__main__":
    main()
