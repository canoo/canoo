"""Generate Tetris and 3D contribution cards from real data.

Original implementation by Emi / Canoo, inspired by (with credit):
- Platane/snk, the snake contribution graph
- yoshi389111/github-profile-3d-contrib, the 3D contribution graph

Neither project is copied here. The Tetris falling animation
and the static 3D strip are written from scratch.

How it runs, with no hosted service at view time:
- A GitHub Action runs this script on a schedule, with the
  workflow GITHUB_TOKEN. It reads the public contribution
  calendar for the repo owner through the GitHub GraphQL API.
- It writes contrib/tetris.svg and contrib/contrib-3d.svg
  into this repo, and the workflow commits them.
- The README embeds those files, so at view time there is
  no server, no Vercel, no API call. Motion lives inside the
  Tetris SVG itself, as SMIL animation.

Tetris behaviour: blocks fall once, bottom row first, and
freeze in place, so the graph stacks upward from the floor
and stays finished. Reloading the page replays the build.
The 3D strip is static, no spin, no animation.

Levels come from the GraphQL color for each day, mapped
to 0 to 4. Counts are not shown in the SVGs, only levels,
the same as the standard contribution graph.
"""

import json
import os
import sys
import urllib.request

GREEN = ["#161b22", "#0e4429", "#006d32", "#26a641", "#39d353"]
BG = "#0d1117"

# Light palette returned by the GraphQL API, plus the dark
# palette in case GitHub ever returns that instead.
COLOR_TO_LEVEL = {
    "#ebedf0": 0,
    "#9be9a8": 1,
    "#40c463": 2,
    "#30a14e": 3,
    "#216e39": 4,
    "#161b22": 0,
    "#0e4429": 1,
    "#006d32": 2,
    "#26a641": 3,
    "#39d353": 4,
}

QUERY = """
query($login: String!) {
  user(login: $login) {
    contributionsCollection {
      contributionCalendar {
        totalContributions
        weeks {
          contributionDays {
            date
            contributionCount
            color
            weekday
          }
        }
      }
    }
  }
}
"""

WEEKS = 26


def fetch_calendar(login, token):
    body = json.dumps({"query": QUERY, "variables": {"login": login}}).encode()
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=body,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": "canoo-contrib-variations",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.load(resp)
    if "errors" in data:
        raise RuntimeError(f"GraphQL errors: {data['errors']}")
    return data["data"]["user"]["contributionsCollection"]["contributionCalendar"]


def grid_from_calendar(calendar):
    weeks = calendar["weeks"][-WEEKS:]
    grid = []
    for week in weeks:
        row = [0] * 7
        for day in week["contributionDays"]:
            level = COLOR_TO_LEVEL.get(day["color"].lower())
            if level is None:
                # Fall back to count buckets if a color is unknown.
                count = day["contributionCount"]
                level = 0 if count == 0 else 1 if count <= 2 else 2 if count <= 5 else 3 if count <= 9 else 4
            row[day["weekday"]] = level
        grid.append(row)
    return grid


def tetris_svg(grid):
    weeks = len(grid)
    cell = 17
    size = 14
    pad_x, pad_y = 20, 36
    width = 7 * cell + pad_x * 2
    height = weeks * cell + pad_y + 24
    parts = []
    parts.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" '
        f'height="{height}" viewBox="0 0 {width} {height}">'
    )
    parts.append(f'<rect width="{width}" height="{height}" fill="{BG}" rx="8"/>')
    parts.append(
        f'<text x="{pad_x}" y="20" fill="#e6edf3" font-family="sans-serif" '
        f'font-size="13">Tetris contributions</text>'
    )
    for w in range(weeks):
        for d in range(7):
            level = grid[w][d]
            x = pad_x + d * cell
            y = pad_y + w * cell
            begin = round((weeks - 1 - w) * 0.12 + d * 0.02, 2)
            parts.append(
                f'<rect x="{x}" y="{y}" width="{size}" height="{size}" '
                f'rx="3" fill="{GREEN[level]}" '
                f'transform="translate(0 -{height})">'
                f'<animateTransform attributeName="transform" type="translate" '
                f'from="0 -{height}" to="0 0" dur="1.2s" begin="{begin}s" '
                f'fill="freeze"/></rect>'
            )
    parts.append(
        f'<rect x="{pad_x}" y="{pad_y + weeks * cell + 4}" '
        f'width="{7 * cell - 3}" height="2" fill="#30363d" rx="1"/>'
    )
    parts.append("</svg>")
    return "\n".join(parts)


def static_3d_svg(grid):
    weeks = len(grid)
    dx, dy = 16, 8
    ox = 140
    oy = 60
    width = (weeks + 7) * dx + 80
    height = (weeks + 7) * dy + 110
    cubes = []
    for w in range(weeks):
        for d in range(7):
            level = grid[w][d]
            h = level * 7
            x = ox + (w - d) * dx
            y = oy + (w + d) * dy - h
            top = GREEN[level]
            left = "#0e4429" if level else "#161b22"
            right = "#006d32" if level else "#21262d"
            cubes.append(
                f'<polygon points="{x},{y} {x + dx},{y + dy} {x},{y + 2 * dy} '
                f'{x - dx},{y + dy}" fill="{top}"/>'
            )
            cubes.append(
                f'<polygon points="{x - dx},{y + dy} {x},{y + 2 * dy} '
                f'{x},{y + 2 * dy + h} {x - dx},{y + dy + h}" fill="{left}"/>'
            )
            cubes.append(
                f'<polygon points="{x},{y + 2 * dy} {x + dx},{y + dy} '
                f'{x + dx},{y + dy + h} {x},{y + 2 * dy + h}" fill="{right}"/>'
            )
    parts = []
    parts.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" '
        f'height="{height}" viewBox="0 0 {width} {height}">'
    )
    parts.append(f'<rect width="{width}" height="{height}" fill="{BG}" rx="8"/>')
    parts.append(
        f'<text x="20" y="24" fill="#e6edf3" font-family="sans-serif" '
        f'font-size="13">3D contributions</text>'
    )
    parts.extend(cubes)
    parts.append("</svg>")
    return "\n".join(parts)


def main():
    # Local test: pass a GraphQL response JSON file as the first
    # argument, for example the file saved from gh api graphql.
    # In the workflow, no argument is given, and the script calls
    # the GraphQL API with GITHUB_TOKEN instead.
    if len(sys.argv) > 1:
        with open(sys.argv[1], encoding="utf-8") as f:
            data = json.load(f)
        calendar = data["data"]["user"]["contributionsCollection"]["contributionCalendar"]
        login = os.environ.get("GITHUB_USER", "canoo")
    else:
        token = os.environ.get("GITHUB_TOKEN", "")
        if not token:
            raise SystemExit("GITHUB_TOKEN is required")
        login = os.environ.get("GITHUB_USER") or os.environ.get(
            "GITHUB_REPOSITORY_OWNER", "canoo"
        )
        calendar = fetch_calendar(login, token)
    grid = grid_from_calendar(calendar)
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    out_dir = os.path.join(root, "contrib")
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "tetris.svg"), "w", encoding="utf-8") as f:
        f.write(tetris_svg(grid))
    with open(os.path.join(out_dir, "contrib-3d.svg"), "w", encoding="utf-8") as f:
        f.write(static_3d_svg(grid))
    total = calendar.get("totalContributions")
    print(f"user: {login}, total contributions (all time): {total}")
    print(f"weeks used: {len(grid)}, blocks: {len(grid) * 7}")
    print(f"wrote: {out_dir}/tetris.svg and {out_dir}/contrib-3d.svg")


if __name__ == "__main__":
    main()
