"""Render ``docs/report_map_paint.md`` as a single self-contained HTML page.

The article is the source of record; this script only lays it out (the design
tokens below) and inlines every figure as a data URI so the page can be
published as one file (the claude.ai artifact the user reads on other devices).
It understands exactly the Markdown the report uses - ATX headings, paragraphs,
`> ` blockquotes, pipe tables, `![alt](path)` images followed by an italic
caption paragraph, `---` breaks, and inline **bold** / *em* / `code` - and
fails loudly on anything else, so a new construct in the report is noticed
rather than silently dropped.

Run: uv run python scripts/report_map_paint_html.py [--md docs/report_map_paint.md]
                                                    [--out /tmp/painting_faerun.html]
"""
from __future__ import annotations

import argparse
import base64
import html
import re
from pathlib import Path

CSS = """
:root{--ground:#F2F3F0;--paper:#FAFAF8;--ink:#1E2226;--ink-2:#4A5158;--ink-3:#7A828A;--rule:#D5D9D6;--rule-soft:#E4E7E4;
--ours:#B8433A;--ours-soft:#F3DDDA;--rescale:#4C72B0;--ck2:#7A6AB3;--vanilla:#1E2226;--water:#4E7CA8;--water-soft:#DCE7F0;
--mono:"IBM Plex Mono",ui-monospace,SFMono-Regular,Menlo,monospace;--serif:"Newsreader",Georgia,"Times New Roman",serif;
--sans:"Archivo","Helvetica Neue",Arial,sans-serif;--narrow:"Archivo Narrow","Archivo","Helvetica Neue",Arial,sans-serif;color-scheme:light}
@media (prefers-color-scheme: dark){:root:not([data-theme="light"]){--ground:#1A1D20;--paper:#22262A;--ink:#E6E8E6;--ink-2:#B4BAC0;--ink-3:#7F878E;
--rule:#3A4045;--rule-soft:#2D3236;--ours:#E0665C;--ours-soft:#3C2422;--rescale:#7FA3DA;--ck2:#A79BD6;--vanilla:#E6E8E6;--water:#7FA9CF;--water-soft:#20303C;color-scheme:dark}}
:root[data-theme="dark"]{--ground:#1A1D20;--paper:#22262A;--ink:#E6E8E6;--ink-2:#B4BAC0;--ink-3:#7F878E;--rule:#3A4045;--rule-soft:#2D3236;
--ours:#E0665C;--ours-soft:#3C2422;--rescale:#7FA3DA;--ck2:#A79BD6;--vanilla:#E6E8E6;--water:#7FA9CF;--water-soft:#20303C;color-scheme:dark}
*{box-sizing:border-box}
body{background:var(--ground);color:var(--ink);font-family:var(--serif);font-size:18px;line-height:1.55;margin:0;font-variant-numeric:oldstyle-nums}
.wrap{max-width:1040px;margin:0 auto;padding:0 24px 96px}
.prose{max-width:66ch;margin:0 auto}
h1,h2,h3{font-family:var(--sans);text-wrap:balance;letter-spacing:-0.01em;line-height:1.12;margin:0}
h1{font-size:clamp(34px,5vw,52px);font-weight:700}
h2{font-size:26px;font-weight:600;margin-top:64px;padding-top:20px;border-top:1px solid var(--rule)}
h2 .n{font-family:var(--mono);font-size:14px;color:var(--ours);letter-spacing:.06em;display:block;margin-bottom:8px;font-weight:500}
h3{font-size:20px;font-weight:600;margin:28px 0 10px}
p{margin:0 0 18px}
strong{font-weight:500;color:var(--ink)}
code{font-family:var(--mono);font-size:.84em;background:var(--paper);border:1px solid var(--rule-soft);border-radius:3px;padding:0 .3em;font-variant-numeric:tabular-nums}
.eyebrow{font-family:var(--narrow);text-transform:uppercase;letter-spacing:.12em;font-size:13px;color:var(--ink-3);font-weight:600;display:flex;gap:14px;flex-wrap:wrap}
.eyebrow span+span::before{content:"\\00b7";margin-right:14px;color:var(--rule)}
.mast{padding:56px 0 28px;display:grid;gap:20px}
.dek{font-size:22px;line-height:1.4;color:var(--ink-2);max-width:62ch}
.dek b{color:var(--ink);font-weight:500}
.legend{display:flex;gap:18px 26px;flex-wrap:wrap;font-family:var(--narrow);font-size:14px;letter-spacing:.02em;color:var(--ink-2);padding:14px 0;border-top:1px solid var(--rule);border-bottom:1px solid var(--rule);margin:8px 0 40px}
.legend i{display:inline-block;width:22px;height:0;border-top:3px solid;vertical-align:middle;margin-right:8px;border-radius:2px}
.legend .v i{border-color:var(--vanilla)}.legend .o i{border-color:var(--ours)}.legend .r i{border-color:var(--rescale);border-top-style:dashed}.legend .c i{border-color:var(--ck2);border-top-style:dotted}
.tablewrap{overflow-x:auto;margin:8px 0 28px}
table{width:100%;border-collapse:collapse;font-family:var(--sans);font-size:15px;line-height:1.4}
th,td{text-align:left;vertical-align:top;padding:10px 12px;border-bottom:1px solid var(--rule-soft)}
th{font-family:var(--narrow);text-transform:uppercase;letter-spacing:.1em;font-size:12px;color:var(--ink-3);font-weight:600;border-bottom:1px solid var(--rule)}
tr:last-child td{border-bottom:0}
td:first-child{color:var(--ink-2)}
figure{margin:32px auto;max-width:1000px}
figure img{display:block;width:100%;height:auto;background:#fff;border:1px solid var(--rule);border-radius:4px}
figcaption{font-family:var(--sans);font-size:14.5px;line-height:1.5;color:var(--ink-2);max-width:78ch;margin:12px auto 0;padding:0 4px}
figcaption .fn{font-family:var(--mono);color:var(--ours);font-size:12.5px;letter-spacing:.04em;margin-right:8px;font-weight:500}
.note{border-left:3px solid var(--water);background:var(--water-soft);padding:14px 18px;margin:22px 0 26px;font-size:17px}
.note p:last-child{margin-bottom:0}
.tag{font-family:var(--mono);font-size:12px;padding:1px 6px;border-radius:3px;border:1px solid var(--ours);color:var(--ours);background:var(--paper);vertical-align:middle}
.tag.a{border-color:var(--rule);color:var(--ink-2)}
.repro{margin-top:64px;padding-top:20px;border-top:1px solid var(--rule);font-family:var(--sans);font-size:14.5px;color:var(--ink-2)}
@media (max-width:640px){body{font-size:17px}.dek{font-size:19px}h2{font-size:23px}}
"""

FONTS = (
    '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Archivo:wght@500;600;700'
    "&family=Archivo+Narrow:wght@500;600&family=Newsreader:ital,opsz,wght@0,6..72,400;0,6..72,500;1,6..72,400"
    '&family=IBM+Plex+Mono:wght@400;500&display=swap">'
)

LEGEND = """<div class="legend">
  <span class="v"><i></i>vanilla CK3 1.19 (0.742 km/px)</span>
  <span class="o"><i></i>ours, shipped</span>
  <span class="r"><i></i>ours, plain rescale</span>
  <span class="c"><i></i>CK2 Faerûn source (2.90 km/px)</span>
</div>"""

DEK = (
    "How the converter turns five 8-bit CK2 bitmaps into a map CK3 renders like its own "
    "— by taking <b>where</b> from CK2 and <b>what a kilometre looks like</b> from vanilla, "
    "and never letting the second overwrite the first."
)


def inline(text: str) -> str:
    """Escape, then bold / em / code / verified-assumed tags."""
    out = html.escape(text, quote=False)
    out = re.sub(r"`verified`", '<span class="tag">verified</span>', out)
    out = re.sub(r"`assumed`", '<span class="tag a">assumed</span>', out)
    out = re.sub(r"`([^`]+)`", r"<code>\1</code>", out)
    out = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", out)
    out = re.sub(r"(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])", r"<em>\1</em>", out)
    out = re.sub(r"\^([−\-]?[\d.]+)", r"<sup>\1</sup>", out)
    return out


def data_uri(path: Path) -> str:
    return "data:image/png;base64," + base64.b64encode(path.read_bytes()).decode()


def render(md: str, md_dir: Path) -> tuple[str, str]:
    lines = md.splitlines()
    out: list[str] = []
    title = "Painting Faerûn"
    i = 0
    open_prose = False

    def prose(on: bool) -> None:
        nonlocal open_prose
        if on and not open_prose:
            out.append('<div class="prose">')
            open_prose = True
        if not on and open_prose:
            out.append("</div>")
            open_prose = False

    para: list[str] = []

    def flush_para() -> None:
        if para:
            prose(True)
            out.append("<p>" + inline(" ".join(para)) + "</p>")
            para.clear()

    while i < len(lines):
        line = lines[i]
        s = line.strip()
        if not s:
            flush_para()
            i += 1
            continue
        if s.startswith("# ") and not s.startswith("## "):
            flush_para()
            title = s[2:].split(":")[0].strip()
            i += 1
            continue
        if s == "---":
            flush_para()
            i += 1
            continue
        if s.startswith("## "):
            flush_para()
            prose(True)
            m = re.match(r"## (?:(\d+)\.\s*)?(.*)", s)
            num, rest = m.group(1), m.group(2)
            if num:
                head, _, tail = rest.partition(":")
                label = f"{int(num):02d} · {head.strip().upper()}" if tail else f"{int(num):02d}"
                body = tail.strip() or head.strip()
                body = body[:1].upper() + body[1:]
                out.append(f'<h2><span class="n">{html.escape(label)}</span>{inline(body)}</h2>')
            else:
                out.append(f"<h2>{inline(rest)}</h2>")
            i += 1
            continue
        if s.startswith("### "):
            flush_para()
            prose(True)
            out.append(f"<h3>{inline(s[4:])}</h3>")
            i += 1
            continue
        if s.startswith(">"):
            flush_para()
            prose(True)
            quote: list[str] = []
            while i < len(lines) and lines[i].strip().startswith(">"):
                quote.append(lines[i].strip()[1:].strip())
                i += 1
            out.append('<div class="note"><p>' + inline(" ".join(q for q in quote if q)) + "</p></div>")
            continue
        if s.startswith("|"):
            flush_para()
            prose(True)
            rows: list[str] = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                rows.append(lines[i].strip())
                i += 1
            cells = [[c.strip() for c in r.strip("|").split("|")] for r in rows]
            cells = [r for r in cells if not all(re.fullmatch(r":?-{2,}:?", c) for c in r)]
            head, body = cells[0], cells[1:]
            t = ['<div class="tablewrap"><table><tr>' + "".join(f"<th>{inline(c)}</th>" for c in head) + "</tr>"]
            for r in body:
                t.append("<tr>" + "".join(f"<td>{inline(c)}</td>" for c in r) + "</tr>")
            t.append("</table></div>")
            out.append("".join(t))
            continue
        m = re.match(r"!\[(.*?)\]\((.*?)\)", s)
        if m:
            flush_para()
            prose(False)
            alt, rel = m.group(1), m.group(2)
            img = data_uri(md_dir / rel)
            i += 1
            while i < len(lines) and not lines[i].strip():
                i += 1
            cap: list[str] = []
            while i < len(lines) and lines[i].strip() and not lines[i].startswith(("#", "|", "!", ">")):
                cap.append(lines[i].strip())
                i += 1
            caption = " ".join(cap)
            if caption.startswith("*") and caption.endswith("*"):
                caption = caption[1:-1]
            fn = ""
            fm = re.match(r"Figure (\d+)\s*[—-]\s*", caption)
            if fm:
                fn = f'<span class="fn">FIG {fm.group(1)}</span>'
                caption = caption[fm.end():]
            out.append(
                f'<figure><img src="{img}" alt="{html.escape(alt)}">'
                f"<figcaption>{fn}{inline(caption)}</figcaption></figure>"
            )
            continue
        para.append(s)
        i += 1
    flush_para()
    prose(False)
    return title, "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--md", default="docs/report_map_paint.md")
    ap.add_argument("--out", default="/tmp/painting_faerun.html")
    ap.add_argument("--build", default="build 12")
    a = ap.parse_args(argv)
    md_path = Path(a.md)
    title, body = render(md_path.read_text(encoding="utf-8"), md_path.parent)
    page = (
        f"<title>{html.escape(title)}</title>\n{FONTS}\n<style>{CSS}</style>\n"
        '<div class="wrap">\n<header class="mast prose">\n'
        f'<div class="eyebrow"><span>Forgotten Kings · converter report</span><span>2026-09-10</span><span>{html.escape(a.build)}</span></div>\n'
        f"<h1>{html.escape(title)}</h1>\n<p class=\"dek\">{DEK}</p>\n</header>\n"
        f'<div class="prose">{LEGEND}</div>\n{body}\n</div>\n'
    )
    Path(a.out).write_text(page, encoding="utf-8")
    print(f"{a.out}: {len(page) // 1024} KB, title {title!r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
