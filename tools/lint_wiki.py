"""台灣小吃 LLM Wiki 的 lint 檢查（依 AGENTS.md 第 9 節）。

用法：python -I tools/lint_wiki.py [wiki 目錄]
只讀不寫；結果印在畫面上，由 LLM 整理後寫進 log.md。
"""
import re
import sys
from pathlib import Path

WIKI = Path(sys.argv[1] if len(sys.argv) > 1 else "wiki")
REQUIRED = ["type", "aliases", "tags", "sources", "updated"]
LINK = re.compile(r"\[\[([^\]|#]+)(?:[|#][^\]]*)?\]\]")
CITE = re.compile(r"來源：|（推論|（見 \[\[")


def parse(path):
    text = path.read_text(encoding="utf-8")
    fm, body = {}, text
    if text.startswith("---\n"):
        end = text.index("\n---\n", 4)
        for line in text[4:end].splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                fm[k.strip()] = v.split("#")[0].strip()
        body = text[end + 5:]
    return fm, body


pages = {p.stem: p for p in WIKI.rglob("*.md")}
data = {name: parse(p) for name, p in pages.items()}
alias = {}
for name, (fm, _) in data.items():
    for a in re.findall(r"[^\[\],\s][^\[\],]*", fm.get("aliases", "").strip("[]")):
        alias[a.strip()] = name

problems = {k: [] for k in ["frontmatter", "斷掉的連結", "孤兒頁", "缺出處", "callout 缺出處",
                            "index 不一致", "sources 欄位不一致", "來源頁影響清單不一致"]}
callouts = []
inbound = {n: 0 for n in pages}

for name, (fm, body) in data.items():
    special = name in ("index", "log")
    if not special:
        for k in REQUIRED:
            if k not in fm:
                problems["frontmatter"].append(f"{name}: 缺 {k}")
    for target in LINK.findall(body):
        t = alias.get(target.strip(), target.strip())
        if t in pages:
            if t != name:
                inbound[t] += 1
        else:
            problems["斷掉的連結"].append(f"{name} → [[{target}]]")

    if fm.get("type") in ("food", "concept"):
        section, parent_cited = "", False
        lines = body.splitlines() + [""]
        for i, line in enumerate(lines):
            if line.startswith("## "):
                section = line[3:].strip()
            m = re.match(r"> \[!(conflict|uncertain|todo)\]", line)
            if m:
                callouts.append((m.group(1), name))
                blk = [line]
                for nxt in lines[i + 1:]:
                    if not nxt.startswith(">"):
                        break
                    blk.append(nxt)
                if m.group(1) != "todo" and not any(CITE.search(b) for b in blk):
                    problems["callout 缺出處"].append(f"{name}: {line[:40]}")
            if section in ("相關頁面", "相關小吃", "待查與矛盾"):
                continue
            s = line.strip()
            if line.startswith("- "):
                parent_cited = bool(CITE.search(s))
            # 縮排子項目沿用上一層的出處（例如「四種型態（來源：…）：」底下的清單）
            if line.startswith("  - ") and parent_cited:
                continue
            candidate = s.startswith("- ") or (s.startswith("> ") and not s.startswith("> [!"))
            if candidate and len(s) > 8 and not CITE.search(s):
                problems["缺出處"].append(f"{name} [{section}]: {s[:50]}")

    if fm.get("type") in ("food", "concept"):
        declared = set(re.findall(r"\[\[([^\]]+)\]\]", fm.get("sources", "")))
        cited = {t for t in LINK.findall(body) if t.startswith("src-")}
        for s in cited - declared:
            problems["sources 欄位不一致"].append(f"{name}: 內文引用 {s} 但 frontmatter 未列")
        for s in declared - cited:
            problems["sources 欄位不一致"].append(f"{name}: frontmatter 列 {s} 但內文沒引用")

# 來源頁「本來源影響的頁面」是否都真的把該來源列進 sources
for name, (fm, body) in data.items():
    if fm.get("type") != "source":
        continue
    m = re.search(r"## 本來源影響的頁面\n(.*?)(\n## |\Z)", body, re.S)
    if not m:
        continue
    for t in LINK.findall(m.group(1)):
        t = alias.get(t, t)
        if t in data and data[t][0].get("type") in ("food", "concept"):
            if name not in data[t][0].get("sources", ""):
                problems["來源頁影響清單不一致"].append(f"{name} 說影響 [[{t}]]，但 {t} 的 sources 沒有它")

# index 是否列出所有頁面、來源數是否正確
idx = data.get("index", ({}, ""))[1]
for name, (fm, _) in data.items():
    if name in ("index", "log"):
        continue
    m = re.search(r"- \[\[" + re.escape(name) + r"\]\][^\n]*?（來源數 (\d+)）", idx)
    if not m:
        problems["index 不一致"].append(f"{name} 未列在 index")
        continue
    if fm.get("type") != "source":
        n = len(re.findall(r"\[\[", fm.get("sources", "")))
        if int(m.group(1)) != n:
            problems["index 不一致"].append(f"{name}: index 寫來源數 {m.group(1)}，實際 {n}")

for name, n in inbound.items():
    if n == 0 and name not in ("index", "log"):
        problems["孤兒頁"].append(name)

print(f"頁面數：{len(pages)}")
for kind in ("conflict", "uncertain", "todo"):
    where = [n for k, n in callouts if k == kind]
    print(f"[!{kind}] {len(where)} 個：{'、'.join(sorted(set(where)))}")
total = 0
for k, v in problems.items():
    total += len(v)
    print(f"\n## {k}（{len(v)}）")
    for x in v:
        print("  -", x)
print(f"\n問題總數：{total}")
sys.exit(1 if total else 0)
