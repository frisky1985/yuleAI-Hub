#!/usr/bin/env python3
"""yuleAI-Hub 自动维护：搜素索引 + 站点地图"""

import json, re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SITE_URL = "https://frisky1985.github.io/yuleAI-Hub"

def fix_missing_titles():
    """为缺失 <title> 的页面补充基本 HTML 结构。"""
    count = 0
    for f in sorted(ROOT.rglob("index.html")):
        rel = f.relative_to(ROOT)
        if rel.parent.name.startswith(".") or str(rel.parent) == ".":
            continue
        text = f.read_text(encoding="utf-8", errors="replace")
        if "<title>" in text:
            continue
        m = re.search(r'<h1[^>]*>(.*?)</h1>', text)
        h1 = m.group(1) if m else rel.parent.name
        title = re.sub(r'[📚📖⚡📋🔧📁💡🌟🔍🛠🎯✨✅❌🔗🌱💬⭐🧠🚀]', '', h1).strip() or rel.parent.name
        wrapped = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>{title} — yuleAI-Hub</title>
<link href="https://fonts.googleapis.com/css2?family=LXGW+WenKai&family=Noto+Sans+SC:wght@300;400;500;700&display=swap" rel="stylesheet">
<style>:root{{--primary:#6C5CE7;--primary-bg:#f0edff;--bg:#FBF9F5;--bg-card:#fff;--fg:#2d3436;--fg2:#636e72;--border:#e8e4dd;--radius:14px;--font:"LXGW WenKai","Noto Sans SC",serif;--sans:"Noto Sans SC",sans-serif}}
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:var(--font);background:var(--bg);color:var(--fg);line-height:1.8;padding:32px;max-width:860px;margin:0 auto}}
a{{color:var(--primary)}} h1{{color:var(--primary);margin-bottom:16px}} h2{{margin:24px 0 8px}}
pre{{background:#1a1a2e;color:#e2e8f0;border-radius:8px;padding:16px;overflow-x:auto;margin:16px 0}}
code{{font-family:"JetBrains Mono",monospace;font-size:13px;background:var(--primary-bg);padding:2px 6px;border-radius:4px}}
pre code{{background:0 0;padding:0;color:inherit}}
</style></head><body>{text}</body></html>'''
        f.write_text(wrapped, encoding="utf-8")
        count += 1
    if count:
        print(f"🔧 修复 {count} 个页面标题")

def build_search_json():
    entries = []
    seen = set()
    for f in sorted(ROOT.rglob("index.html")):
        rel = f.relative_to(ROOT)
        if rel.parent.name.startswith(".") or str(rel.parent) == ".":
            continue
        text = f.read_text(encoding="utf-8", errors="replace")
        m = re.search(r'<title>(.*?)</title>', text)
        title = m.group(1).strip() if m else ""
        if not title:
            continue
        url = f"/{rel.parent}/"
        if url in seen:
            continue
        seen.add(url)
        title_clean = title.replace(" — yuleAI-Hub", "")
        # 从正文取描述
        desc_m = re.search(r'<meta\s+name="description"\s+content="([^"]*)"', text)
        desc = desc_m.group(1) if desc_m else ""
        if not desc:
            body = re.sub(r'<[^>]+>', '', text)[:120].strip()
            desc = body if body else ""
        parent = str(rel.parent)
        type_map = {"knowledge":"knowledge","know-how":"knowhow","skills":"skills",
                     "rules":"rules","tools":"tool","projects":"project"}
        ptype = "knowhow"
        for k, v in type_map.items():
            if parent.startswith(k):
                ptype = v; break
        # 标签
        content_lower = text.lower()
        keywords = {"MCP":"MCP","Agent":"Agent","Hermes":"Hermes","OpenClaw":"OpenClaw",
                    "QoderCLI":"QoderCLI","DeepSeek":"DeepSeek","Warp":"Warp","API":"API"}
        tags = [kw for kw, tag in keywords.items() if kw.lower() in content_lower]
        entries.append({"title": title_clean, "url": url, "desc": desc[:150],
                        "type": ptype, "tags": tags[:6], "date": "2026-05-26"})
    entries.insert(0, {"title":"yuleAI-Hub — AI Agent 知识花园","url":"/","desc":"AI Agent 协同的知识花园",
                       "type":"home","tags":["AI","Agent","MCP"],"date":"2026-05-26"})
    (ROOT / "search.json").write_text(json.dumps(entries, ensure_ascii=False, indent=2))
    print(f"✅ search.json: {len(entries)} entries")

def build_sitemap():
    urls = []
    for f in sorted(ROOT.rglob("index.html")):
        if f.parent.name.startswith(".") or f.parent == ROOT:
            continue
        priority = "0.8" if len(f.read_text()) > 3000 else "0.5"
        url_path = f"/{f.relative_to(ROOT).parent}/"
        urls.append(f"  <url><loc>{SITE_URL}{url_path}</loc><lastmod>2026-05-26</lastmod><changefreq>weekly</changefreq><priority>{priority}</priority></url>")
    xml = '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
    xml += "\n".join(urls) + "\n</urlset>\n"
    (ROOT / "sitemap.xml").write_text(xml)
    print(f"✅ sitemap.xml: {len(urls)} URLs")

if __name__ == "__main__":
    fix_missing_titles()
    build_search_json()
    build_sitemap()
    print("🎉 自动维护完成")
