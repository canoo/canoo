#!/usr/bin/env python3
"""Own GitHub stats generator, v1.

Why this exists: the public github-readme-stats deployment was paused in
Nov 2026, so its cards render broken. This script makes static SVG cards
from the GitHub API, so a profile README does not depend on that service.

How to reuse it: copy this file and .github/workflows/stats.yml into your
own profile repo, set GITHUB_USER to your username, and let the workflow
commit stats/stats.svg and stats/top-langs.svg. No server, no Vercel, no
paid tier. It counts public repos only when run with GITHUB_TOKEN, which
is scoped to the profile repo itself.

Notes and limits, stated plainly:
- Search API totals can be capped or laggy, so commits, PRs and issues
  are search totals, not an audited count.
- Private repos are not counted here, because the workflow token cannot
  see them. If you run this locally with a personal token that can, it
  will count the repos that token can read.
"""

import html
import json
import os
import sys
import urllib.request

API = "https://api.github.com"
USER = os.environ.get("GITHUB_USER", "canoo")
TOKEN = os.environ.get("GITHUB_TOKEN", "")
OUT = os.environ.get("STATS_OUT", "stats")

LANG_COLORS = {
    "TypeScript": "#3178c6", "JavaScript": "#f1e05a", "Python": "#3572a5",
    "Go": "#00ADD8", "C#": "#178600", "C++": "#f34b7c", "HTML": "#e34c26",
    "CSS": "#563d7c", "Shell": "#89e051", "Java": "#b07219",
    "Rust": "#dea584", "Ruby": "#701516", "PHP": "#4F5D95",
    "Swift": "#F05138", "Kotlin": "#A97BFF", "Astro": "#ff5a03",
}


def get(path):
    req = urllib.request.Request(API + path, headers={
        "Accept": "application/vnd.github+json",
        "User-Agent": "own-github-stats/1.0",
    })
    if TOKEN:
        req.add_header("Authorization", "Bearer " + TOKEN)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp)


def search_total(query):
    try:
        data = get("/search/issues?q=" + query)
        return data.get("total_count", 0)
    except Exception as exc:  # search can be rate limited, do not fake a number
        print("search failed for %s: %s" % (query, exc), file=sys.stderr)
        return None


def fmt(n):
    if n is None:
        return "n/a"
    return f"{n:,}"


def esc(s):
    return html.escape(str(s), quote=True)


def stats_svg(user, rows):
    y = 58
    items = ""
    for label, value in rows:
        items += (
            f'<text x="24" y="{y}" fill="#8b949e" font-size="14" '
            f'font-family="Segoe UI, Helvetica, Arial, sans-serif">{esc(label)}</text>'
            f'<text x="470" y="{y}" fill="#e6edf3" font-size="14" text-anchor="end" '
            f'font-family="Segoe UI, Helvetica, Arial, sans-serif">{esc(value)}</text>\n'
        )
        y += 28
    height = y + 12
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="495" height="{height}" '
        f'viewBox="0 0 495 {height}">'
        f'<rect width="495" height="{height}" rx="6" fill="#0d1117" stroke="#30363d"/>'
        f'<text x="24" y="32" fill="#10AE7B" font-size="18" font-weight="600" '
        f'font-family="Segoe UI, Helvetica, Arial, sans-serif">{esc(user)} GitHub Stats</text>'
        f"{items}</svg>\n"
    )


def langs_svg(user, langs):
    total = sum(langs.values()) or 1
    top = sorted(langs.items(), key=lambda kv: kv[1], reverse=True)[:5]
    x = 24
    bar = ""
    for name, n in top:
        w = max(4, round(447 * n / total))
        color = LANG_COLORS.get(name, "#10AE7B")
        bar += f'<rect x="{x}" y="48" width="{w}" height="10" fill="{color}"/>'
        x += w
    rows = ""
    y = 88
    for name, n in top:
        pct = round(100 * n / total, 1)
        color = LANG_COLORS.get(name, "#10AE7B")
        rows += (
            f'<circle cx="30" cy="{y - 5}" r="6" fill="{color}"/>'
            f'<text x="44" y="{y}" fill="#e6edf3" font-size="14" '
            f'font-family="Segoe UI, Helvetica, Arial, sans-serif">{esc(name)}</text>'
            f'<text x="470" y="{y}" fill="#8b949e" font-size="14" text-anchor="end" '
            f'font-family="Segoe UI, Helvetica, Arial, sans-serif">{pct}%</text>\n'
        )
        y += 28
    height = y + 12
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="495" height="{height}" '
        f'viewBox="0 0 495 {height}">'
        f'<rect width="495" height="{height}" rx="6" fill="#0d1117" stroke="#30363d"/>'
        f'<text x="24" y="32" fill="#10AE7B" font-size="18" font-weight="600" '
        f'font-family="Segoe UI, Helvetica, Arial, sans-serif">Most Used Languages</text>'
        f"{bar}{rows}</svg>\n"
    )


def main():
    user_data = get(f"/users/{USER}")
    repos = get(f"/users/{USER}/repos?per_page=100&sort=updated")
    # Forks would skew the language card with other projects code, so
    # only count repos the user owns outright.
    repos = [r for r in repos if not r.get("fork")]
    stars = sum(r.get("stargazers_count", 0) for r in repos)
    langs = {}
    for repo in repos:
        lang_url = repo.get("languages_url", "")
        if not lang_url:
            continue
        try:
            req = urllib.request.Request(lang_url, headers={
                "Accept": "application/vnd.github+json",
                "User-Agent": "own-github-stats/1.0",
            })
            if TOKEN:
                req.add_header("Authorization", "Bearer " + TOKEN)
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.load(resp)
            for name, n in data.items():
                langs[name] = langs.get(name, 0) + n
        except Exception as exc:
            print("languages failed for %s: %s" % (repo.get("name"), exc), file=sys.stderr)

    # Search API is used for PRs and issues. Commits search needs a token
    # in some cases, so fall back to n/a rather than inventing a number.
    prs = search_total(f"author:{USER}+type:pr")
    issues = search_total(f"author:{USER}+type:issue")
    commits = None
    try:
        req = urllib.request.Request(
            API + f"/search/commits?q=author:{USER}",
            headers={"Accept": "application/vnd.github+json",
                     "User-Agent": "own-github-stats/1.0"})
        if TOKEN:
            req.add_header("Authorization", "Bearer " + TOKEN)
        with urllib.request.urlopen(req, timeout=30) as resp:
            commits = json.load(resp).get("total_count")
    except Exception as exc:
        print("commits search failed: %s" % exc, file=sys.stderr)

    rows = [
        ("Total Stars Earned", fmt(stars)),
        ("Total Commits (search)", fmt(commits)),
        ("Total PRs", fmt(prs)),
        ("Total Issues", fmt(issues)),
        ("Public Repos", fmt(user_data.get("public_repos"))),
        ("Followers", fmt(user_data.get("followers"))),
    ]
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, "stats.svg"), "w", encoding="utf-8") as f:
        f.write(stats_svg(USER, rows))
    with open(os.path.join(OUT, "top-langs.svg"), "w", encoding="utf-8") as f:
        f.write(langs_svg(USER, langs))
    print(f"wrote stats for {USER}: stars={stars} prs={prs} issues={issues} "
          f"commits={commits} langs={sorted(langs, key=langs.get, reverse=True)[:5]}")


if __name__ == "__main__":
    main()
