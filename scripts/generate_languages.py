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

PALETTE = [
    "#E88FA5",
    "#79ADD8",
    "#78BE9B",
    "#A995D6",
    "#D7B65E",
    "#D9926B",
]

# Pastas que não devem participar da estatística porque normalmente
# contêm ambientes virtuais, dependências, caches ou arquivos gerados.
IGNORED_DIRS = {
    "myenv",
    "venv",
    ".venv",
    "env",
    ".env",
    "node_modules",
    "vendor",
    "site-packages",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".tox",
    ".nox",
    ".cache",
    ".parcel-cache",
    ".next",
    ".nuxt",
    ".svelte-kit",
    "dist",
    "build",
    "coverage",
    "target",
    "out",
    "bin",
    "obj",
}

# Arquivos gerados/minificados também ficam fora.
IGNORED_FILE_ENDINGS = (
    ".min.js",
    ".min.css",
    ".bundle.js",
    ".bundle.css",
    ".chunk.js",
    ".chunk.css",
    ".map",
)

IGNORED_FILENAMES = {
    "package-lock.json",
    "yarn.lock",
    "pnpm-lock.yaml",
    "poetry.lock",
    "pipfile.lock",
    "composer.lock",
}

# Extensões consideradas código-fonte.
EXTENSION_TO_LANGUAGE = {
    ".html": "HTML",
    ".htm": "HTML",

    ".css": "CSS",
    ".scss": "SCSS",
    ".sass": "Sass",
    ".less": "Less",

    ".js": "JavaScript",
    ".mjs": "JavaScript",
    ".cjs": "JavaScript",
    ".jsx": "JavaScript",

    ".ts": "TypeScript",
    ".tsx": "TypeScript",

    ".vue": "Vue",
    ".svelte": "Svelte",

    ".py": "Python",

    ".sql": "SQL",

    ".java": "Java",
    ".kt": "Kotlin",
    ".kts": "Kotlin",

    ".c": "C",

    ".cc": "C++",
    ".cpp": "C++",
    ".cxx": "C++",
    ".hpp": "C++",
    ".hh": "C++",
    ".hxx": "C++",

    ".cs": "C#",

    ".php": "PHP",

    ".go": "Go",

    ".rs": "Rust",

    ".rb": "Ruby",

    ".swift": "Swift",

    ".dart": "Dart",

    ".r": "R",

    ".sh": "Shell",
    ".bash": "Shell",
    ".zsh": "Shell",
    ".fish": "Shell",

    ".ps1": "PowerShell",

    ".lua": "Lua",

    ".pl": "Perl",

    ".scala": "Scala",

    ".sol": "Solidity",

    ".hs": "Haskell",

    ".m": "MATLAB",

    ".asm": "Assembly",
    ".s": "Assembly",
}


def request_json(url: str):
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "opaulofelipe-profile-language-card",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    if TOKEN:
        headers["Authorization"] = f"Bearer {TOKEN}"

    request = urllib.request.Request(
        url,
        headers=headers,
    )

    try:
        with urllib.request.urlopen(
            request,
            timeout=30,
        ) as response:
            return json.load(response)

    except urllib.error.HTTPError as error:
        body = error.read().decode(
            "utf-8",
            errors="replace",
        )

        raise RuntimeError(
            f"GitHub API retornou HTTP {error.code} "
            f"para {url}: {body}"
        ) from error


def get_repositories():
    repositories = []
    page = 1

    while True:
        url = (
            f"{API}/users/{USERNAME}/repos"
            f"?type=owner"
            f"&sort=full_name"
            f"&direction=asc"
            f"&per_page=100"
            f"&page={page}"
        )

        batch = request_json(url)

        if not batch:
            break

        for repo in batch:

            # Ignora forks.
            if repo.get("fork", False):
                continue

            # Ignora o próprio repositório de perfil.
            #
            # Isso é importante porque este script é Python.
            # Se incluíssemos esse repositório, o próprio sistema
            # de estatísticas aumentaria artificialmente Python.
            if (
                repo.get("name", "").lower()
                == USERNAME.lower()
            ):
                continue

            repositories.append(repo)

        if len(batch) < 100:
            break

        page += 1

    return repositories


def should_ignore_path(path: str) -> bool:
    pure_path = PurePosixPath(path)

    parts_lower = [
        part.lower()
        for part in pure_path.parts
    ]

    filename = pure_path.name.lower()

    # Ignora qualquer arquivo dentro das pastas proibidas.
    if any(
        part in IGNORED_DIRS
        for part in parts_lower[:-1]
    ):
        return True

    if filename in IGNORED_FILENAMES:
        return True

    if filename.endswith(
        IGNORED_FILE_ENDINGS
    ):
        return True

    return False


def language_from_path(
    path: str,
) -> str | None:

    if should_ignore_path(path):
        return None

    suffix = (
        PurePosixPath(path)
        .suffix
        .lower()
    )

    return EXTENSION_TO_LANGUAGE.get(
        suffix
    )


def get_repo_source_usage(
    repo: dict,
) -> Counter:

    full_name = repo["full_name"]

    default_branch = (
        repo.get("default_branch")
        or "main"
    )

    encoded_branch = urllib.parse.quote(
        default_branch,
        safe="",
    )

    url = (
        f"{API}/repos/"
        f"{full_name}/git/trees/"
        f"{encoded_branch}"
        f"?recursive=1"
    )

    data = request_json(url)

    if data.get("truncated"):
        print(
            f"Aviso: a árvore do repositório "
            f"{full_name} foi truncada pela "
            f"API do GitHub."
        )

    usage = Counter()

    for item in data.get(
        "tree",
        [],
    ):

        if item.get("type") != "blob":
            continue

        path = item.get(
            "path",
            "",
        )

        language = language_from_path(
            path
        )

        if not language:
            continue

        size = item.get("size")

        if (
            not isinstance(size, int)
            or size <= 0
        ):
            continue

        usage[language] += size

    return usage


def calculate_language_scores():
    """
    Cada repositório tem peso total igual a 1.

    Isso evita que um projeto enorme, ou um projeto contendo
    muitos arquivos, domine sozinho toda a estatística.

    Exemplo:

    Projeto A:
    JavaScript 80%
    CSS 20%

    Projeto B:
    Python 100%

    Resultado agregado:
    JavaScript recebe 0.8 ponto
    CSS recebe 0.2 ponto
    Python recebe 1 ponto
    """

    scores = Counter()

    repositories_used = 0

    for repo in get_repositories():

        try:
            usage = get_repo_source_usage(
                repo
            )

        except Exception as error:
            print(
                f"Falha ao analisar "
                f"{repo['full_name']}: "
                f"{error}"
            )
            continue

        total = sum(
            usage.values()
        )

        if total <= 0:
            continue

        repositories_used += 1

        # Cada repositório tem peso 1.
        for language, size in usage.items():

            repo_percentage = (
                size / total
            )

            scores[
                language
            ] += repo_percentage

        print()
        print(
            f"Analisado: "
            f"{repo['full_name']}"
        )

        for language, size in (
            usage.most_common()
        ):
            print(
                f"  {language}: "
                f"{size} bytes"
            )

    if repositories_used == 0:
        raise RuntimeError(
            "Nenhum repositório com "
            "arquivos de código reconhecidos "
            "foi encontrado."
        )

    print()
    print(
        f"Repositórios considerados: "
        f"{repositories_used}"
    )

    return scores


def svg_card(
    items,
    theme: str,
) -> str:

    width = 640
    height = 330

    cx = 165
    cy = 177

    radius = 91
    stroke_width = 27

    circumference = (
        2 * math.pi * radius
    )

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

    total_score = sum(
        score
        for _, score in items
    ) or 1

    circles = [
        (
            f'<circle '
            f'cx="{cx}" '
            f'cy="{cy}" '
            f'r="{radius}" '
            f'fill="none" '
            f'stroke="{track}" '
            f'stroke-width="{stroke_width}" '
            f'opacity="0.45"/>'
        )
    ]

    cumulative = 0.0

    percentages = []

    for index, (
        language,
        score,
    ) in enumerate(items):

        percentage = (
            score
            / total_score
            * 100
        )

        color = PALETTE[
            index % len(PALETTE)
        ]

        percentages.append(
            (
                language,
                percentage,
                color,
            )
        )

        segment = (
            circumference
            * percentage
            / 100
        )

        gap = min(
            3.0,
            segment * 0.08,
        )

        visible_segment = max(
            segment - gap,
            0.1,
        )

        offset = -(
            circumference
            * cumulative
            / 100
        )

        circles.append(
            f'<circle '
            f'cx="{cx}" '
            f'cy="{cy}" '
            f'r="{radius}" '
            f'fill="none" '
            f'stroke="{color}" '
            f'stroke-width="{stroke_width}" '
            f'stroke-linecap="butt" '
            f'stroke-dasharray="'
            f'{visible_segment:.2f} '
            f'{circumference - visible_segment:.2f}" '
            f'stroke-dashoffset="{offset:.2f}" '
            f'transform="rotate(-90 {cx} {cy})"/>'
        )

        cumulative += percentage

    legend = []

    start_y = 93

    for index, (
        language,
        percentage,
        color,
    ) in enumerate(percentages):

        y = (
            start_y
            + index * 37
        )

        legend.extend(
            [
                (
                    f'<circle '
                    f'cx="344" '
                    f'cy="{y - 5}" '
                    f'r="6" '
                    f'fill="{color}"/>'
                ),

                (
                    f'<text '
                    f'x="363" '
                    f'y="{y}" '
                    f'class="language">'
                    f'{escape(language)}'
                    f'</text>'
                ),

                (
                    f'<text '
                    f'x="585" '
                    f'y="{y}" '
                    f'text-anchor="end" '
                    f'class="percentage">'
                    f'{percentage:.1f}%'
                    f'</text>'
                ),
            ]
        )

    if items:
        center_top = items[0][0]
    else:
        center_top = "—"

    svg = f"""
<svg
    xmlns="http://www.w3.org/2000/svg"
    width="{width}"
    height="{height}"
    viewBox="0 0 {width} {height}"
    role="img"
    aria-label="As seis linguagens mais usadas por {escape(USERNAME)}"
>

<style>

.title {{
    font:
        600 18px
        -apple-system,
        BlinkMacSystemFont,
        "Segoe UI",
        sans-serif;

    letter-spacing: .04em;
    fill: {title};
}}

.language {{
    font:
        500 15px
        -apple-system,
        BlinkMacSystemFont,
        "Segoe UI",
        sans-serif;

    fill: {text};
}}

.percentage {{
    font:
        500 14px
        -apple-system,
        BlinkMacSystemFont,
        "Segoe UI",
        sans-serif;

    fill: {muted};
}}

.center-main {{
    font:
        600 16px
        -apple-system,
        BlinkMacSystemFont,
        "Segoe UI",
        sans-serif;

    fill: {text};
}}

.center-small {{
    font:
        500 11px
        -apple-system,
        BlinkMacSystemFont,
        "Segoe UI",
        sans-serif;

    letter-spacing: .12em;
    fill: {muted};
}}

</style>

<text
    x="28"
    y="36"
    class="title"
>
6 LINGUAGENS MAIS USADAS
</text>

{''.join(circles)}

<text
    x="{cx}"
    y="{cy - 2}"
    text-anchor="middle"
    class="center-main"
>
{escape(center_top)}
</text>

<text
    x="{cx}"
    y="{cy + 20}"
    text-anchor="middle"
    class="center-small"
>
TOP 1
</text>

{''.join(legend)}

</svg>
"""

    return svg.strip()


def main():
    scores = calculate_language_scores()

    top_six = scores.most_common(6)

    if not top_six:
        raise RuntimeError(
            "Nenhuma linguagem foi encontrada "
            "após aplicar os filtros."
        )

    light_svg = svg_card(
        top_six,
        "light",
    )

    dark_svg = svg_card(
        top_six,
        "dark",
    )

    light_path = (
        OUTPUT_DIR
        / "languages-light.svg"
    )

    dark_path = (
        OUTPUT_DIR
        / "languages-dark.svg"
    )

    light_path.write_text(
        light_svg,
        encoding="utf-8",
    )

    dark_path.write_text(
        dark_svg,
        encoding="utf-8",
    )

    total_score = sum(
        score
        for _, score in top_six
    ) or 1

    print()
    print(
        "Linguagens exibidas:"
    )

    for (
        language,
        score,
    ) in top_six:

        percentage = (
            score
            / total_score
            * 100
        )

        print(
            f"- {language}: "
            f"{percentage:.1f}%"
        )

    print()
    print(
        "Arquivos gerados:"
    )

    print(
        f"- {light_path}"
    )

    print(
        f"- {dark_path}"
    )


if __name__ == "__main__":
    main()
