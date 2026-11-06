"""Generate all own contribution cards from real data.

Original implementation by Emi / Canoo, inspired by (with
credit) Platane/snk (snake), yoshi389111/github-profile-3d-contrib
(3D), and DenverCoder1/github-readme-streak-stats (streak).
No code is copied from those projects.

Cards generated, all as static files, no hosted service at
view time:
- tetris.svg: vertical contribution graph, blocks fall slowly,
  bottom row first, fill up, hold, then reset and loop again.
- contrib-3d.svg: static isometric 3D contribution strip.
- own-snake.svg: snake follows a serpentine path through
  the contribution grid, eating dots as it passes, loop.
- own-streak.svg: total contributions, current streak,
  longest streak, last 12 months.
- own-summary.svg: pie chart and pentagon radar for commits,
  issues, PRs, reviews, and repos, plus total contributions,
  stars, and forks. Transparent background. Includes the
  user's GitHub avatar, embedded as base64, top right.
  The streak card also includes the avatar, top right.
  Snake and Tetris do not include an avatar, as Emi asked.

Data, all from the GitHub API with the workflow token:
- GraphQL contribution calendar, last 53 weeks, for levels
  and streaks, and contributionsCollection totals for
  commits, issues, PRs, reviews, and repos.
- REST repos list, non-fork only, for stars and forks.
- Avatar from https://github.com/{login}.png, resized to
  96px when PIL is available, otherwise embedded as is.
  It is embedded as base64 in the SVG, so at view time
  there is no external image to load.

Usage:
- In a GitHub Action, run with GITHUB_TOKEN set, no args.
  It writes to the contrib/ folder in the repo root.
- Local test: pass a GraphQL calendar JSON file as the
  first argument, and a totals JSON file as the second,
  for example the files saved from gh api graphql.
  Avatar is then read from avatar-96.jpg in this folder
  if it exists, otherwise downloaded.
"""

import base64
import io
import json
import math
import os
import sys
import urllib.request

GREEN = ["#161b22", "#0e4429", "#006d32", "#26a641", "#39d353"]
BG = "#0d1117"
TEXT = "#e6edf3"
SUB = "#8b949e"
GRID = "#30363d"
BORDER = "#30363d"
LANG_COLORS = {"JavaScript": "#f1e05a", "Go": "#00ADD8", "Shell": "#89e051", "TypeScript": "#3178c6", "Python": "#3572a5", "Astro": "#ff5a03", "HTML": "#e34c26", "CSS": "#563d7c"}

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

CALENDAR_QUERY = """
query($login: String!) {
  user(login: $login) {
    contributionsCollection {
      totalCommitContributions
      totalIssueContributions
      totalPullRequestContributions
      totalPullRequestReviewContributions
      totalRepositoryContributions
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


def api_get(url, token):
    req = urllib.request.Request(
        url, headers={"Authorization": f"Bearer {token}", "User-Agent": "canoo-cards"}
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp)


def fetch_all(login, token):
    body = json.dumps({"query": CALENDAR_QUERY, "variables": {"login": login}}).encode()
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=body,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": "canoo-cards",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.load(resp)
    if "errors" in data:
        raise RuntimeError(f"GraphQL errors: {data['errors']}")
    coll = data["data"]["user"]["contributionsCollection"]
    repos = api_get(f"https://api.github.com/users/{login}/repos?per_page=100", token)
    non_fork = [r for r in repos if not r.get("fork")]
    stars = sum(r.get("stargazers_count", 0) for r in non_fork)
    forks = sum(r.get("forks_count", 0) for r in non_fork)
    langs = fetch_langs(login, token, repos)
    return coll, stars, forks, len(non_fork), langs


def fetch_langs(login, token, repos=None):
    # Top languages by code size, non-fork repos only.
    if repos is None:
        repos = api_get(f"https://api.github.com/users/{login}/repos?per_page=100", token)
    totals = {}
    for repo in repos:
        if repo.get("fork"):
            continue
        try:
            data = api_get(repo["languages_url"], token)
        except Exception:
            continue
        for name, n in data.items():
            totals[name] = totals.get(name, 0) + n
    top = sorted(totals.items(), key=lambda kv: -kv[1])[:5]
    total = sum(v for _, v in top) or 1
    return [(name, n, LANG_COLORS.get(name, "#10AE7B"), round(100 * n / total, 1)) for name, n in top]


def grid_from_calendar(calendar, weeks_count=26):
    weeks = calendar["weeks"][-weeks_count:]
    grid = []
    for week in weeks:
        row = [0] * 7
        for day in week["contributionDays"]:
            level = COLOR_TO_LEVEL.get(day["color"].lower())
            if level is None:
                count = day["contributionCount"]
                level = 0 if count == 0 else 1 if count <= 2 else 2 if count <= 5 else 3 if count <= 9 else 4
            row[day["weekday"]] = level
        grid.append(row)
    return grid


def full_grid(calendar):
    return grid_from_calendar(calendar, weeks_count=len(calendar["weeks"]))


def avatar_data_uri(login, token=None):
    # Local test file first, then download the GitHub avatar.
    local = os.path.join(os.path.dirname(os.path.abspath(__file__)), "avatar-96.jpg")
    raw = None
    if os.path.exists(local):
        with open(local, "rb") as f:
            raw = f.read()
    else:
        try:
            req = urllib.request.Request(
                f"https://github.com/{login}.png",
                headers={"User-Agent": "canoo-cards"},
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                raw = resp.read()
        except Exception:
            return ""
    if not raw:
        return ""
    try:
        from PIL import Image

        im = Image.open(io.BytesIO(raw)).convert("RGB")
        im.thumbnail((96, 96))
        buf = io.BytesIO()
        im.save(buf, format="JPEG", quality=82)
        raw = buf.getvalue()
    except Exception:
        pass
    return "data:image/jpeg;base64," + base64.b64encode(raw).decode()


def avatar_svg(x, y, size, uri):
    if not uri:
        return ""
    r = size // 2
    cx, cy = x + r, y + r
    return (
        f'<defs><clipPath id="avatar-clip-{x}-{y}">'
        f'<circle cx="{cx}" cy="{cy}" r="{r}"/></clipPath></defs>'
        f'<circle cx="{cx}" cy="{cy}" r="{r + 2}" fill="{BORDER}"/>'
        f'<image x="{x}" y="{y}" width="{size}" height="{size}" '
        f'href="{uri}" clip-path="url(#avatar-clip-{x}-{y})"/>'
    )


def tetris_svg(grid):
    """Loop version, Nov 5: blocks fall slowly, bottom first,
    fill up, hold full, then reset and play again. One global
    16 second cycle, so all blocks reset together, not one
    by one. Fall is encoded in keyTimes per block, with a
    shared hold at 0.88 and reset at 1.0."""
    weeks = len(grid)
    cell = 17
    size = 14
    pad_x, pad_y = 20, 36
    width = 7 * cell + pad_x * 2
    height = weeks * cell + pad_y + 24
    dur = 16
    parts = []
    parts.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" '
        f'height="{height}" viewBox="0 0 {width} {height}">'
    )
    parts.append(f'<rect width="{width}" height="{height}" fill="{BG}" rx="8"/>')
    parts.append(
        f'<text x="{pad_x}" y="20" fill="{TEXT}" font-family="sans-serif" '
        f'font-size="13">Tetris contributions</text>'
    )
    for w in range(weeks):
        for d in range(7):
            level = grid[w][d]
            x = pad_x + d * cell
            y = pad_y + w * cell
            start = round(0.05 + (weeks - 1 - w) * 0.02, 3)
            end = round(min(start + 0.12, 0.87), 3)
            parts.append(
                f'<rect x="{x}" y="{y}" width="{size}" height="{size}" '
                f'rx="3" fill="{GREEN[level]}" opacity="0">'
                f'<animateTransform attributeName="transform" type="translate" '
                f'values="0 -{height}; 0 -{height}; 0 0; 0 0; 0 -{height}" '
                f'keyTimes="0;{start};{end};0.88;1" dur="{dur}s" '
                f'repeatCount="indefinite"/>'
                f'<animate attributeName="opacity" values="0;0;1;1;0" '
                f'keyTimes="0;{start};{end};0.88;1" dur="{dur}s" '
                f'repeatCount="indefinite"/></rect>'
            )
    parts.append(
        f'<rect x="{pad_x}" y="{pad_y + weeks * cell + 4}" '
        f'width="{7 * cell - 3}" height="2" fill="#30363d" rx="1"/>'
    )
    parts.append("</svg>")
    return "\n".join(parts)


def static_3d_svg(grid):
    # Fix, Nov 6: the old version drew a flat cube for every
    # cell, even level 0, so it looked like a solid dark slab
    # with a few bumps, just up and down bars. Now empty cells
    # are skipped entirely, bars are taller and brighter, and
    # cubes are drawn back to front so front cubes are not
    # hidden behind back ones.
    weeks = len(grid)
    dx, dy = 16, 8
    ox = 140
    oy = 120
    width = (weeks + 7) * dx + 80
    height = (weeks + 7) * dy + 180
    top_colors = ["", "#1f8a4a", "#26a641", "#39d353", "#7ee787"]
    left_colors = ["", "#14532d", "#166534", "#15803d", "#22c55e"]
    right_colors = ["", "#0e4429", "#14532d", "#166534", "#15803d"]
    cells = []
    for w in range(weeks):
        for d in range(7):
            level = grid[w][d]
            if level == 0:
                continue
            cells.append((w + d, w, d, level))
    cells.sort()
    cubes = []
    for _, w, d, level in cells:
        # Non-linear heights, so a busy day stands out clearly
        # from a quiet day, instead of a flat plateau.
        h = [0, 8, 20, 36, 56][level]
        x = ox + (w - d) * dx
        y = oy + (w + d) * dy - h
        top = top_colors[level]
        left = left_colors[level]
        right = right_colors[level]
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
        f'<text x="20" y="24" fill="{TEXT}" font-family="sans-serif" '
        f'font-size="13">3D contributions</text>'
    )
    parts.extend(cubes)
    parts.append("</svg>")
    return "\n".join(parts)


def snake_svg(grid):
    # Grid snake, Nov 6: the head hunts the highest
    # contributions first, then the next highest, down to
    # the lowest, oldest first within a level, moving only
    # up, down, left, or right along the grid, never
    # diagonally, at a constant speed. Every time it eats
    # a day, a new segment joins its body behind the head,
    # up to 10 segments. The head waits at each food until
    # the whole body has caught up and gathered there, then
    # moves on to the next food. The wait at each food is
    # the time the current body needs to catch up, plus a
    # short pause to eat, brightest foods longest. Eaten
    # squares dim to 0.3, not 0, so the grid stays visible,
    # and the reset brings them back. Gray blocks are never
    # eaten. Body circles have no cx, cy, animateMotion
    # translates the element by the path point, so cx, cy
    # would push them off the path. Body begin is positive,
    # so the head moves first and the body always trails.
    import math as _math

    weeks = len(grid)
    cell = 13
    size = 10
    pad_x, pad_y = 20, 20
    width = weeks * cell + pad_x * 2
    height = 7 * cell + pad_y * 2

    def centre(w, d):
        return (pad_x + w * cell + size / 2, pad_y + d * cell + size / 2)

    eaten = []
    order = 0
    for w in range(weeks):
        for d in range(7):
            level = grid[w][d]
            if level == 0:
                continue
            eaten.append((level, order, w, d))
            order += 1
    eaten.sort(key=lambda e: (-e[0], e[1]))
    max_body = 10
    dur = 180
    eat_pause = {4: 0.5, 3: 0.3, 2: 0.2, 1: 0.1}
    # Grid walk, turn points only, horizontal then vertical.
    # Each leg entry is (x, y, steps, level, target_index).
    # target_index is 1-based, the number of foods eaten
    # when the head arrives there, so the body length then
    # is min(target_index, max_body).
    legs = []
    cur_w, cur_d = eaten[0][2], eaten[0][3]
    legs.append((*centre(cur_w, cur_d), 0, eaten[0][0], 1))
    total_steps = 0
    for idx, (level, _, tw, td) in enumerate(eaten[1:], start=2):
        if tw != cur_w:
            steps = abs(tw - cur_w)
            legs.append((*centre(tw, cur_d), steps, None, None))
            total_steps += steps
            cur_w = tw
        if td != cur_d:
            steps = abs(td - cur_d)
            legs.append((*centre(tw, td), steps, level, idx))
            total_steps += steps
            cur_d = td
        else:
            legs[-1] = (legs[-1][0], legs[-1][1], legs[-1][2], level, idx)
    # Wait time at each food: the current body needs
    # body_len * step_time to catch up, plus a short eat
    # pause. step_time depends on total dwell, so solve it:
    # total_dwell = S * step_time + P, with step_time =
    # (dur - total_dwell) / total_steps.
    body_lens = [min(k, max_body) for k in range(1, len(eaten) + 1)]
    s_sum = sum(body_lens)
    p_sum = sum(eat_pause[level] for level, _, _, _ in eaten)
    k_ratio = s_sum / total_steps if total_steps else 0
    total_dwell = (k_ratio * dur + p_sum) / (1 + k_ratio) if total_steps else 0
    travel_time = dur - total_dwell
    step_time = travel_time / total_steps if total_steps else 0
    # keyPoints / keyTimes: distance fraction and time
    # fraction. Time per leg is proportional to its steps,
    # so speed is constant while travelling, plus the wait
    # at each food, same point, later time.
    path_pts = []
    key_points = []
    key_times = []
    cum_dist = 0.0
    cum_time = 0.0
    total_dist = total_steps * cell
    eat_time = {}
    for x, y, steps, level, idx in legs:
        if steps:
            cum_dist += steps * cell
            cum_time += steps * step_time
        path_pts.append((x, y))
        key_points.append(cum_dist / total_dist if total_dist else 0)
        key_times.append(cum_time / dur)
        if level is not None:
            eat_time[(x, y)] = cum_time / dur
            wait = min(idx, max_body) * step_time + eat_pause[level]
            cum_time += wait
            key_points.append(cum_dist / total_dist if total_dist else 0)
            key_times.append(cum_time / dur)
    key_points.append(key_points[-1])
    key_times.append(1.0)
    eat_by_cell = {}
    for level, _, w, d in eaten:
        x, y = centre(w, d)
        eat_by_cell[(w, d)] = eat_time.get((x, y), 0.0)
    if eaten:
        eat_by_cell[(eaten[0][2], eaten[0][3])] = 0.0
    path = "M " + " L ".join(f"{x:.1f} {y:.1f}" for x, y in path_pts)
    kp = ";".join(f"{v:.4f}" for v in key_points)
    kt = ";".join(f"{v:.5f}" for v in key_times)
    parts = []
    parts.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'xmlns:xlink="http://www.w3.org/1999/xlink" width="{width}" '
        f'height="{height}" viewBox="0 0 {width} {height}">'
    )
    parts.append(f'<defs><path id="snake-path" d="{path}" fill="none"/></defs>')
    for w in range(weeks):
        for d in range(7):
            rx = pad_x + w * cell
            ry = pad_y + d * cell
            level = grid[w][d]
            if level == 0:
                parts.append(
                    f'<rect x="{rx}" y="{ry}" width="{size}" height="{size}" '
                    f'rx="2" fill="{GREEN[0]}"/>'
                )
                continue
            tt = eat_by_cell[(w, d)]
            eat = min(tt + 0.01, 0.99)
            parts.append(
                f'<rect x="{rx}" y="{ry}" width="{size}" height="{size}" '
                f'rx="2" fill="{GREEN[level]}">'
                f'<animate attributeName="opacity" values="1;1;0.3;0.3;1" '
                f'keyTimes="0;{tt:.3f};{eat:.3f};0.98;1" dur="{dur}s" '
                f'repeatCount="indefinite"/></rect>'
            )
    for i in range(1, max_body + 1):
        if i - 1 >= len(eaten):
            break
        t_appear = eat_by_cell[(eaten[i - 1][2], eaten[i - 1][3])]
        op = round(0.9 - i * 0.04, 2)
        appear = min(max(t_appear, i * step_time / dur, 0.001), 0.99)
        parts.append(
            f'<circle r="5" fill="#39d353" opacity="0">'
            f'<animate attributeName="opacity" values="0;0;{op};{op};0" '
            f'keyTimes="0;{appear:.3f};{min(appear + 0.01, 0.99):.3f};0.97;1" '
            f'dur="{dur}s" repeatCount="indefinite"/>'
            f'<animateMotion dur="{dur}s" calcMode="linear" begin="{i * step_time:.3f}s" '
            f'keyPoints="{kp}" keyTimes="{kt}" repeatCount="indefinite">'
            f'<mpath href="#snake-path" xlink:href="#snake-path"/>'
            f'</animateMotion></circle>'
        )
    parts.append(
        f'<g><circle r="7" fill="#39d353"/>'
        f'<circle cx="2.5" cy="-2.5" r="1.5" fill="#0d1117"/>'
        f'<circle cx="2.5" cy="2.5" r="1.5" fill="#0d1117"/>'
        f'<animateMotion dur="{dur}s" calcMode="linear" '
        f'keyPoints="{kp}" keyTimes="{kt}" repeatCount="indefinite">'
        f'<mpath href="#snake-path" xlink:href="#snake-path"/>'
        f'</animateMotion></g>'
    )
    parts.append("</svg>")
    return "\n".join(parts)


def streak_data(calendar):
    days = []
    for week in calendar["weeks"]:
        for day in week["contributionDays"]:
            days.append((day["date"], day["contributionCount"]))
    days.sort()
    total = sum(c for _, c in days)
    # Fix, Nov 6: the calendar ends today, and today may have
    # 0 contributions so far. Counting back from the last day
    # would give a streak of 0 even though the streak is still
    # alive. Trim trailing zero days, then count back from the
    # last day with contributions, but only if that day is
    # today or yesterday, otherwise the streak has ended.
    from datetime import date as _date

    last_idx = len(days) - 1
    while last_idx >= 0 and days[last_idx][1] == 0:
        last_idx -= 1
    cur = 0
    cur_start = None
    if last_idx >= 0:
        last_date = _date.fromisoformat(days[last_idx][0])
        end_date = _date.fromisoformat(days[-1][0])
        if (end_date - last_date).days <= 1:
            for _, c in reversed(days[: last_idx + 1]):
                if c > 0:
                    cur += 1
                else:
                    break
            cur_start = days[last_idx - cur + 1][0] if cur else None
    best = 0
    run = 0
    best_start = best_end = None
    run_start = None
    for d, c in days:
        if c > 0:
            if run == 0:
                run_start = d
            run += 1
            if run > best:
                best = run
                best_start = run_start
                best_end = d
        else:
            run = 0
    return {
        "total": total,
        "current": cur,
        "current_start": cur_start,
        "current_end": days[last_idx][0] if cur else None,
        "longest": best,
        "longest_start": best_start,
        "longest_end": best_end,
    }


def streak_svg(s, avatar_uri):
    width, height = 495, 195
    parts = []
    parts.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" '
        f'height="{height}" viewBox="0 0 {width} {height}">'
    )
    parts.append(
        f'<rect x="1" y="1" width="{width - 2}" height="{height - 2}" '
        f'rx="10" fill="{BG}" stroke="{BORDER}"/>'
    )
    parts.append(
        f'<text x="24" y="36" fill="{TEXT}" font-family="sans-serif" '
        f'font-size="18" font-weight="bold">GitHub Streak</text>'
    )
    parts.append(
        f'<text x="24" y="56" fill="{SUB}" font-family="sans-serif" '
        f'font-size="12">Own card, last 12 months</text>'
    )
    parts.append(avatar_svg(424, 14, 48, avatar_uri))
    cols = [
        (f"{s['total']:,}", "Total Contributions", ""),
        (str(s["current"]), "Current Streak", f"{s['current_start']} to {s['current_end']}"),
        (str(s["longest"]), "Longest Streak", f"{s['longest_start']} to {s['longest_end']}"),
    ]
    x = 24
    for value, label, dates in cols:
        parts.append(
            f'<text x="{x}" y="110" fill="#39d353" font-family="sans-serif" '
            f'font-size="30" font-weight="bold">{value}</text>'
        )
        parts.append(
            f'<text x="{x}" y="132" fill="{TEXT}" font-family="sans-serif" '
            f'font-size="13">{label}</text>'
        )
        if dates:
            parts.append(
                f'<text x="{x}" y="150" fill="{SUB}" font-family="sans-serif" '
                f'font-size="11">{dates}</text>'
            )
        x += 160
    frac = s["current"] / s["longest"] if s["longest"] else 0
    bar_w = width - 48
    parts.append(
        f'<rect x="24" y="168" width="{bar_w}" height="6" rx="3" fill="{BORDER}"/>'
    )
    parts.append(
        f'<rect x="24" y="168" width="{bar_w * frac:.0f}" height="6" rx="3" fill="#39d353"/>'
    )
    parts.append("</svg>")
    return "\n".join(parts)


def polar(cx, cy, r, angle_deg):
    a = math.radians(angle_deg - 90)
    return (cx + r * math.cos(a), cy + r * math.sin(a))


def pie_slice(cx, cy, r_outer, r_inner, start, end):
    x1, y1 = polar(cx, cy, r_outer, start)
    x2, y2 = polar(cx, cy, r_outer, end)
    x3, y3 = polar(cx, cy, r_inner, end)
    x4, y4 = polar(cx, cy, r_inner, start)
    large = 1 if end - start > 180 else 0
    return (
        f"M {x1:.1f} {y1:.1f} "
        f"A {r_outer} {r_outer} 0 {large} 1 {x2:.1f} {y2:.1f} "
        f"L {x3:.1f} {y3:.1f} "
        f"A {r_inner} {r_inner} 0 {large} 0 {x4:.1f} {y4:.1f} Z"
    )


def summary_svg(coll, total_contributions, stars, forks, repo_count, avatar_uri, langs=None):
    types = [
        ("Commits", coll["totalCommitContributions"], "#39d353"),
        ("Issues", coll["totalIssueContributions"], "#26a641"),
        ("Pull requests", coll["totalPullRequestContributions"], "#006d32"),
        ("Reviews", coll["totalPullRequestReviewContributions"], "#10ae7b"),
        ("Repos", coll["totalRepositoryContributions"], "#8b949e"),
    ]
    width, height = 900, 360
    parts = []
    parts.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" '
        f'height="{height}" viewBox="0 0 {width} {height}">'
    )
    parts.append(
        f'<text x="20" y="28" fill="{TEXT}" font-family="sans-serif" '
        f'font-size="16" font-weight="bold">Contributions</text>'
    )
    parts.append(
        f'<text x="20" y="48" fill="{SUB}" font-family="sans-serif" '
        f'font-size="12">Last 12 months, own card, transparent background</text>'
    )
    parts.append(avatar_svg(824, 12, 56, avatar_uri))
    # The left pie alternates every 10 seconds, 20 second loop:
    # contributions by type first, then top languages.
    # The radar and big totals on the right stay constant.
    dur = 20
    contrib_parts = []
    total_types = sum(v for _, v, _ in types)
    cx, cy, r_outer, r_inner = 130, 200, 95, 58
    angle = 0
    for _, value, color in types:
        sweep = 360 * value / total_types if total_types else 0
        if value:
            contrib_parts.append(
                f'<path d="{pie_slice(cx, cy, r_outer, r_inner, angle, angle + sweep)}" '
                f'fill="{color}"/>'
            )
        angle += sweep
    contrib_parts.append(
        f'<text x="{cx}" y="{cy - 6}" fill="{TEXT}" font-family="sans-serif" '
        f'font-size="22" font-weight="bold" text-anchor="middle">{total_types}</text>'
    )
    contrib_parts.append(
        f'<text x="{cx}" y="{cy + 14}" fill="{SUB}" font-family="sans-serif" '
        f'font-size="11" text-anchor="middle">total</text>'
    )
    y = 110
    for label, value, color in types:
        contrib_parts.append(
            f'<rect x="250" y="{y - 10}" width="12" height="12" rx="3" fill="{color}"/>'
        )
        contrib_parts.append(
            f'<text x="270" y="{y + 2}" fill="{TEXT}" font-family="sans-serif" '
            f'font-size="13">{label} {value}</text>'
        )
        y += 28
    parts.append(
        f'<g><animate attributeName="opacity" values="1;1;0;0;1" '
        f'keyTimes="0;0.45;0.5;0.95;1" dur="{dur}s" repeatCount="indefinite"/>'
        + "\n".join(contrib_parts)
        + "</g>"
    )
    if langs:
        lang_parts = []
        total_lang = sum(n for _, n, _, _ in langs) or 1
        angle = 0
        for name, value, color, _pct in langs:
            sweep = 360 * value / total_lang if total_lang else 0
            if value:
                lang_parts.append(
                    f'<path d="{pie_slice(cx, cy, r_outer, r_inner, angle, angle + sweep)}" '
                    f'fill="{color}"/>'
                )
            angle += sweep
        lang_parts.append(
            f'<text x="{cx}" y="{cy - 6}" fill="{TEXT}" font-family="sans-serif" '
            f'font-size="22" font-weight="bold" text-anchor="middle">{len(langs)}</text>'
        )
        lang_parts.append(
            f'<text x="{cx}" y="{cy + 14}" fill="{SUB}" font-family="sans-serif" '
            f'font-size="11" text-anchor="middle">langs</text>'
        )
        y = 110
        for name, value, color, _pct in langs:
            pct = round(100 * value / total_lang, 1) if total_lang else 0
            lang_parts.append(
                f'<rect x="250" y="{y - 10}" width="12" height="12" rx="3" fill="{color}"/>'
            )
            lang_parts.append(
                f'<text x="270" y="{y + 2}" fill="{TEXT}" font-family="sans-serif" '
                f'font-size="13">{name} {pct}%</text>'
            )
            y += 28
        parts.append(
            f'<g opacity="0"><animate attributeName="opacity" values="0;0;1;1;0" '
            f'keyTimes="0;0.45;0.5;0.95;1" dur="{dur}s" repeatCount="indefinite"/>'
            + "\n".join(lang_parts)
            + "</g>"
        )
    rcx, rcy, r_max = 540, 200, 90
    max_value = max(v for _, v, _ in types)
    for frac in (0.33, 0.66, 1.0):
        points = []
        for i in range(5):
            x, y = polar(rcx, rcy, r_max * frac, i * 72)
            points.append(f"{x:.1f},{y:.1f}")
        parts.append(
            f'<polygon points="{" ".join(points)}" fill="none" stroke="{GRID}"/>'
        )
    data_points = []
    for i, (_, value, _) in enumerate(types):
        x, y = polar(rcx, rcy, r_max * value / max_value, i * 72)
        data_points.append(f"{x:.1f},{y:.1f}")
    parts.append(
        f'<polygon points="{" ".join(data_points)}" fill="#10ae7b" '
        f'fill-opacity="0.35" stroke="#39d353" stroke-width="2"/>'
    )
    short = ["Commits", "Issues", "PRs", "Reviews", "Repos"]
    for i, label in enumerate(short):
        x, y = polar(rcx, rcy, r_max + 18, i * 72)
        anchor = "middle"
        if x < rcx - 20:
            anchor = "end"
        elif x > rcx + 20:
            anchor = "start"
        parts.append(
            f'<text x="{x:.1f}" y="{y:.1f}" fill="{TEXT}" font-family="sans-serif" '
            f'font-size="12" text-anchor="{anchor}">{label}</text>'
        )
    stats = [
        (f"{total_contributions:,}", "contributions"),
        (str(stars), "stars"),
        (str(forks), "forks"),
        (str(repo_count), "repos"),
    ]
    y = 125
    for value, label in stats:
        parts.append(
            f'<text x="730" y="{y}" fill="{TEXT}" font-family="sans-serif" '
            f'font-size="26" font-weight="bold">{value}</text>'
        )
        parts.append(
            f'<text x="730" y="{y + 20}" fill="{SUB}" font-family="sans-serif" '
            f'font-size="12">{label}</text>'
        )
        y += 55
    parts.append(
        f'<text x="20" y="{height - 14}" fill="{SUB}" font-family="sans-serif" '
        f'font-size="11">Pie alternates every 10s: contributions, then top languages. GraphQL totals, last 12 months.</text>'
    )
    parts.append("</svg>")
    return "\n".join(parts)


def main():
    if len(sys.argv) > 1:
        with open(sys.argv[1], encoding="utf-8") as f:
            data = json.load(f)
        coll = data["data"]["user"]["contributionsCollection"]
        calendar = coll["contributionCalendar"]
        # Totals live in a second file for local tests.
        totals_path = sys.argv[2] if len(sys.argv) > 2 else "totals.json"
        if os.path.exists(totals_path):
            with open(totals_path, encoding="utf-8") as f:
                coll = json.load(f)["data"]["user"]["contributionsCollection"]
                coll["contributionCalendar"] = calendar
        stars, forks, repo_count = 12, 3, 9
        login = os.environ.get("GITHUB_USER", "canoo")
        langs = [("JavaScript", 210876, "#f1e05a", 36.4), ("Go", 156965, "#00ADD8", 27.1), ("Shell", 73487, "#89e051", 12.7), ("TypeScript", 36769, "#3178c6", 6.4), ("Python", 32901, "#3572a5", 5.7)]
    else:
        token = os.environ.get("GITHUB_TOKEN", "")
        if not token:
            raise SystemExit("GITHUB_TOKEN is required")
        login = os.environ.get("GITHUB_USER") or os.environ.get(
            "GITHUB_REPOSITORY_OWNER", "canoo"
        )
        coll, stars, forks, repo_count, langs = fetch_all(login, token)
        calendar = coll["contributionCalendar"]
    avatar_uri = avatar_data_uri(login)
    grid26 = grid_from_calendar(calendar, 26)
    grid_full = full_grid(calendar)
    s = streak_data(calendar)
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    # When this file lives in contrib-variations/, root is the workspace,
    # so output to contrib-variations/ for local tests. When it lives
    # in .github/scripts/, root is the repo root, output to contrib/.
    if os.path.basename(root) == "workspace":
        out_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "")
    else:
        out_dir = os.path.join(root, "contrib")
    # Simpler: always write next to this script's folder for tests,
    # and to contrib/ under the repo root when run from .github/scripts.
    script_dir = os.path.dirname(os.path.abspath(__file__))
    if os.path.basename(script_dir) == "scripts":
        out_dir = os.path.join(root, "contrib")
    else:
        out_dir = script_dir
    os.makedirs(out_dir, exist_ok=True)
    files = {
        "tetris.svg": tetris_svg(grid26),
        "contrib-3d.svg": static_3d_svg(grid26),
        "own-snake.svg": snake_svg(grid_full),
        "own-streak.svg": streak_svg(s, avatar_uri),
        "own-summary.svg": summary_svg(
            coll, calendar["totalContributions"], stars, forks, repo_count, avatar_uri, langs
        ),
    }
    for name, content in files.items():
        with open(os.path.join(out_dir, name), "w", encoding="utf-8") as f:
            f.write(content)
    print(f"user: {login}, total: {calendar['totalContributions']}, streak: {s['current']}")
    print(f"wrote {len(files)} cards to {out_dir}")


if __name__ == "__main__":
    main()
