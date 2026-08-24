# -*- coding: utf-8 -*-
"""
column_src.txt を読み込んで column.html（独り言コーナー）を組み立てるスクリプト。
index.html のバナーにある「最新：…」の行も一緒に書き換えます。

使い方:
    python build_column.py

書き方のルールは column_src.txt の先頭に書いてあります。
"""

import html
import re
import sys
from pathlib import Path

# Windows のコンソールでも日本語を出せるようにしておく
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "column_src.txt"
COLUMN = ROOT / "column.html"
INDEX = ROOT / "index.html"

SIGNATURE = "なかモンPlayground 管理人"


# ---------------------------------------------------------------- 入出力

def read_text(path):
    """メモ帳などで Shift_JIS 保存されていても読めるようにしておく。"""
    data = path.read_bytes()
    for enc in ("utf-8-sig", "cp932"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    sys.exit(f"[エラー] {path.name} の文字コードが判別できませんでした（UTF-8 で保存してください）")


def write_text(path, text):
    path.write_text(text, encoding="utf-8", newline="\n")


def replace_block(text, name, body, path):
    """<!-- name:START --> ... <!-- name:END --> の中身を差し替える。"""
    pattern = re.compile(
        r"(<!-- %s:START -->)\n?(.*?)\n?([ \t]*<!-- %s:END -->)" % (name, name),
        re.DOTALL,
    )
    if not pattern.search(text):
        sys.exit(f"[エラー] {path.name} に <!-- {name}:START --> 〜 <!-- {name}:END --> が見つかりません")
    return pattern.sub(lambda m: f"{m.group(1)}\n{body}\n{m.group(3)}", text, count=1)


# ---------------------------------------------------------------- 文字装飾

# 原稿に直接書いてもそのまま生かすタグ（それ以外の < > はただの文字として表示する）
ALLOWED_TAGS = ("s", "b", "strong", "em", "u", "small", "br")


def keep_allowed_tags(text):
    for tag in ALLOWED_TAGS:
        text = text.replace(f"&lt;{tag}&gt;", f"<{tag}>").replace(f"&lt;/{tag}&gt;", f"</{tag}>")
        text = text.replace(f"&lt;{tag.upper()}&gt;", f"<{tag}>").replace(f"&lt;/{tag.upper()}&gt;", f"</{tag}>")
    return text


def join_lines(lines):
    """原稿の改行はつなげて1行にする（折り返しはブラウザ任せ）。

    日本語なので区切り文字は入れない。改行したいときは原稿の行末に <br> と書く。
    """
    return "".join(inline(line.strip()) for line in lines if line.strip())


TAG_SPLIT_RE = re.compile(r"(<[^>]+>)")
BARE_URL_RE = re.compile(r"https?://[^\s<>\"'（）()「」【】、。]+")


def autolink(text):
    """本文にそのまま書かれた URL をリンクにする（すでにリンクの中は触らない）。"""
    parts = TAG_SPLIT_RE.split(text)
    inside_link = False
    out = []
    for part in parts:
        if part.startswith("<") and part.endswith(">"):
            lowered = part.lower()
            if lowered.startswith("<a "):
                inside_link = True
            elif lowered.startswith("</a"):
                inside_link = False
            out.append(part)
            continue
        if inside_link:
            out.append(part)
            continue
        out.append(
            BARE_URL_RE.sub(
                lambda m: f'<a href="{m.group(0)}" target="_blank" rel="noopener noreferrer">{m.group(0)}</a>',
                part,
            )
        )
    return "".join(out)


def inline(text):
    """文中の **強調** / ~~取り消し線~~ / [表示](URL) / 裸の URL を HTML にする。"""
    out = html.escape(text, quote=False)
    out = keep_allowed_tags(out)

    def link(m):
        label, url = m.group(1), m.group(2)
        blank = ' target="_blank" rel="noopener noreferrer"' if url.startswith("http") else ""
        return f'<a href="{url}"{blank}>{label}</a>'

    out = re.sub(r"\[([^\]]+)\]\(([^)\s]+)\)", link, out)
    out = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", out)
    out = re.sub(r"~~(.+?)~~", r"<s>\1</s>", out)
    out = autolink(out)
    return out


# ---------------------------------------------------------------- 原稿の解析

HEAD_RE = re.compile(r"^===\s*(.+)$")
IMG_RE = re.compile(r"^!\[([^\]]*)\]\(([^)\s]+)\)$")


def normalize_date(raw):
    m = re.match(r"^\s*(\d{4})\s*[/\-.年]\s*(\d{1,2})\s*[/\-.月]\s*(\d{1,2})", raw)
    if not m:
        sys.exit(f"[エラー] 日付の書き方が読めませんでした: 「{raw}」（例: 2026/08/18）")
    y, mo, d = m.groups()
    return f"{int(y):04d}/{int(mo):02d}/{int(d):02d}"


def split_entries(lines):
    """=== 行ごとに記事へ切り分ける。"""
    entries = []
    current = None
    for raw in lines:
        line = raw.rstrip("\n").rstrip()
        head = HEAD_RE.match(line)
        if head:
            # タイトルの中に | が入っていてもいいように、区切りは先頭2つだけ見る
            fields = [f.strip() for f in head.group(1).split("|", 2)]
            if len(fields) == 2:
                date, tag, title = fields[0], "", fields[1]
            elif len(fields) == 3:
                date, tag, title = fields
            else:
                sys.exit(f"[エラー] 記事見出しの書き方が読めませんでした: 「{line}」")
            current = {"date": normalize_date(date), "tag": tag, "title": title, "body": []}
            entries.append(current)
            continue
        if current is None:
            continue  # ファイル冒頭の説明コメントなど
        current["body"].append(line)
    if not entries:
        sys.exit("[エラー] 記事が1本も見つかりませんでした（=== で始まる行が必要です）")
    return entries


def is_block_start(line):
    s = line.strip()
    return (
        not s
        or s.startswith("##")
        or s.startswith("- ")
        or s.startswith(">")
        or s.startswith("!")
        or s.startswith("→")
        or s.startswith("->")
        or s.startswith("#")
    )


def render_body(lines, indent):
    """記事本文の各行を HTML の塊に変換する。"""
    pad = " " * indent
    out = []
    i = 0
    while i < len(lines):
        line = lines[i]
        s = line.strip()

        if not s:
            i += 1
            continue

        # 画像（!メモ より先に判定する）
        img = IMG_RE.match(s)
        if img:
            alt, src = img.group(1), img.group(2)
            out.append(f'{pad}<p><img src="{src}" alt="{html.escape(alt, quote=True)}"></p>')
            i += 1
            continue

        # コメント行（## より後に判定するため先に小見出しを見る）
        if s.startswith("##"):
            out.append(f"{pad}<h3>{inline(s.lstrip('#').strip())}</h3>")
            i += 1
            continue

        if s.startswith("#"):
            i += 1
            continue

        # 箇条書き
        if s.startswith("- "):
            items = []
            while i < len(lines) and lines[i].strip().startswith("- "):
                items.append(lines[i].strip()[2:].strip())
                i += 1
            rows = "\n".join(f"{pad}    <li>{inline(it)}</li>" for it in items)
            out.append(f"{pad}<ul>\n{rows}\n{pad}</ul>")
            continue

        # 引用
        if s.startswith(">"):
            quoted = []
            while i < len(lines) and lines[i].strip().startswith(">"):
                quoted.append(lines[i].strip()[1:].strip())
                i += 1
            out.append(f'{pad}<div class="quote">\n{pad}    {join_lines(quoted)}\n{pad}</div>')
            continue

        # ボタン付きリンク
        if s.startswith("→") or s.startswith("->"):
            rest = s[2:] if s.startswith("->") else s[1:]
            if "|" not in rest:
                sys.exit(f"[エラー] リンクの書き方が読めませんでした: 「{s}」（→ ボタンの文字 | リンク先）")
            label, url = [p.strip() for p in rest.rsplit("|", 1)]
            blank = ' target="_blank" rel="noopener noreferrer"' if url.startswith("http") else ""
            out.append(
                f'{pad}<div class="entry-more">\n'
                f'{pad}    <a href="{url}"{blank}>{inline(label)}</a>\n'
                f"{pad}</div>"
            )
            i += 1
            continue

        # メモ
        if s.startswith("!"):
            memo = []
            while i < len(lines) and lines[i].strip().startswith("!") and not IMG_RE.match(lines[i].strip()):
                memo.append(lines[i].strip()[1:].strip())
                i += 1
            title = memo[0] if memo else ""
            rest = [m for m in memo[1:] if m]
            body = f"{pad}    {join_lines(rest)}" if rest else ""
            block = [f'{pad}<div class="memo">', f'{pad}    <span class="memo-title">{inline(title)}</span>']
            if body:
                block.append(body)
            block.append(f"{pad}</div>")
            out.append("\n".join(block))
            continue

        # 段落（次の空行 or 別の記号が出るまで）
        para = [s]
        i += 1
        while i < len(lines) and not is_block_start(lines[i]):
            para.append(lines[i].strip())
            i += 1
        out.append(f"{pad}<p>\n{pad}    {join_lines(para)}\n{pad}</p>")

    return "\n\n".join(out)


# ---------------------------------------------------------------- HTML 組み立て

def render_entry(entry, indent=8):
    pad = " " * indent
    meta = [
        f'{pad}    <div class="entry-meta">',
        f'{pad}        <span class="entry-date">{html.escape(entry["date"])}</span>',
        f'{pad}        <span class="entry-no">#{entry["no"]:03d}</span>',
    ]
    if entry["tag"]:
        meta.append(f'{pad}        <span class="entry-tag">{inline(entry["tag"])}</span>')
    meta.append(f"{pad}    </div>")

    anchor = entry["anchor"]
    head = "\n".join([
        f'{pad}<article class="entry" id="{anchor}">',
        "\n".join(meta),
        f'{pad}    <h2>{inline(entry["title"])}<a href="#{anchor}" class="anchor">#</a></h2>',
    ])
    foot = "\n".join([
        f'{pad}    <div class="entry-foot">{SIGNATURE}</div>',
        f"{pad}</article>",
    ])
    return "\n\n".join(b for b in (head, entry["html_body"], foot) if b.strip())


def render_toc(entries, indent=12):
    pad = " " * indent
    rows = [
        f'{pad}<li><a href="#{e["anchor"]}">{inline(e["title"])}</a>'
        f'<span class="toc-date">{html.escape(e["date"])}</span></li>'
        for e in entries
    ]
    return f'{" " * (indent - 4)}<ol>\n' + "\n".join(rows) + f'\n{" " * (indent - 4)}</ol>'


# ---------------------------------------------------------------- main

def main():
    if not SRC.exists():
        sys.exit(f"[エラー] {SRC.name} が見つかりません")

    entries = split_entries(read_text(SRC).splitlines())

    # 日付が古い順に通し番号を振り、表示は新しい順
    entries.sort(key=lambda e: e["date"])
    for n, e in enumerate(entries, start=1):
        e["no"] = n
        e["anchor"] = f"no{n:03d}"
        e["html_body"] = render_body(e["body"], indent=12)
    newest_first = sorted(entries, key=lambda e: e["date"], reverse=True)

    # column.html
    column = read_text(COLUMN)
    column = replace_block(column, "TOC", render_toc(newest_first), COLUMN)
    column = replace_block(column, "ENTRIES", "\n\n".join(render_entry(e) for e in newest_first), COLUMN)
    write_text(COLUMN, column)

    # index.html のバナー（最新の1本）
    latest = newest_first[0]
    banner = (
        f'            <span class="latest">最新：#{latest["no"]:03d}'
        f'「{inline(latest["title"])}」<span class="latest-date">（{latest["date"]}）</span></span>'
    )
    index = read_text(INDEX)
    index = replace_block(index, "LATEST", banner, INDEX)
    write_text(INDEX, index)

    print(f"OK: {len(entries)} 本の独り言を書き出しました → column.html / index.html")
    for e in newest_first:
        print(f'  #{e["no"]:03d}  {e["date"]}  {e["title"]}')


if __name__ == "__main__":
    main()
