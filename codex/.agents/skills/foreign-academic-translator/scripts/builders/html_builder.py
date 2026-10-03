"""HTML 构建器：将 Markdown 译文转换为带目录伸缩 / 阅读进度 / 术语高亮 / MathJax / 水印的 HTML 页面。"""

from pathlib import Path

from .base import WATERMARK, load_css, annotate_first_occurrences, protect_math, restore_math

# 页面内嵌 JS（普通字符串，非 f-string，避免花括号与 Python 格式化冲突）
# 通过占位符 __WATERMARK__ / __SHOW_CONCEPT_TABLE__ 在运行时替换。
_BUILD_JS = r"""
(function () {
    "use strict";
    var WATERMARK = "__WATERMARK__";
    var SHOW_TABLE = __SHOW_CONCEPT_TABLE__;
    var HEADING_SELECTOR = "h1, h2, h3";
    var HIGHLIGHT = {
        background: "#fff1d6", padding: "2px 6px", borderRadius: "4px",
        fontWeight: "600", color: "#8a5a1a", borderBottom: "2px solid #f5b86e"
    };

    // ===== 1. 术语：暖色高亮；仅正文（非标题内）添加超链接 =====
    // 括号标注（原文）已在生成 HTML 时自动补全到首次出现的术语上。
    document.querySelectorAll("span[data-en]").forEach(function (el) {
        Object.assign(el.style, HIGHLIGHT);
        var inHeading = el.closest(HEADING_SELECTOR);
        if (SHOW_TABLE && !inHeading) {
            var link = document.createElement("a");
            link.href = "#concept-table";
            link.style.color = "inherit";
            link.style.textDecoration = "none";
            link.style.cursor = "pointer";
            Object.assign(link.style, HIGHLIGHT);
            while (el.firstChild) link.appendChild(el.firstChild);
            el.parentNode.replaceChild(link, el);
        }
    });

    // ===== 2. 目录伸缩：右侧大纲 #toc-outline（默认收起，按钮切换） =====
    function buildToc() {
        var headings = document.querySelectorAll(HEADING_SELECTOR);
        var sidebar = document.getElementById("toc-outline");
        if (!headings.length || !sidebar) return;
        var list = document.createElement("ul");
        list.style.listStyle = "none";
        list.style.padding = "0";
        list.style.margin = "0";
        headings.forEach(function (hd, i) {
            if (!hd.id) hd.id = "toc-heading-" + i;
            var li = document.createElement("li");
            li.className = "toc-item";
            li.style.margin = "4px 0";
            li.style.borderRadius = "4px";
            li.style.transition = "background 0.2s";
            if (hd.tagName === "H2") li.style.marginTop = "10px";
            else if (hd.tagName === "H3") li.style.paddingLeft = "18px";
            var link = document.createElement("a");
            link.href = "#" + hd.id;
            link.textContent = hd.textContent;
            link.style.textDecoration = "none";
            link.style.color = "#1a4a8a";
            link.style.fontSize = "13px";
            link.style.display = "block";
            link.style.padding = "4px 8px";
            link.style.borderRadius = "4px";
            link.addEventListener("click", function (event) {
                event.preventDefault();
                hd.scrollIntoView({ behavior: "smooth", block: "start" });
            });
            li.appendChild(link);
            list.appendChild(li);
        });
        sidebar.appendChild(list);
    }

    // ===== 3. 概念表锚点赋值 =====
    function assignConceptTable() {
        if (!SHOW_TABLE) return;
        var target = null;
        var heads = document.querySelectorAll("h2, h3");
        for (var i = 0; i < heads.length; i++) {
            var text = heads[i].textContent || "";
            if (text.indexOf("\u6982\u5FF5\u6C47\u603B\u8868") !== -1 || text.indexOf("\u91CD\u8981\u672F\u8BED\u6982\u5FF5") !== -1) {
                var sib = heads[i].nextElementSibling;
                while (sib && sib.tagName !== "TABLE") sib = sib.nextElementSibling;
                if (sib) target = sib;
                break;
            }
        }
        if (!target) {
            var tables = document.querySelectorAll("table");
            if (tables.length) target = tables[tables.length - 1];
        }
        if (target) target.id = "concept-table";
    }

    // ===== 4. 目录伸缩按钮（#toc-btn ☰ 切换、点选收起、Esc 关闭） =====
    var toc = document.getElementById("toc-outline");
    if (toc) {
        var btn = document.createElement("button");
        btn.id = "toc-btn";
        btn.setAttribute("aria-label", "\u76EE\u5F55");
        btn.title = "\u76EE\u5F55";
        btn.innerHTML = "\u2630";
        document.body.appendChild(btn);
        toc.setAttribute("role", "navigation");
        function setOpen(open) {
            toc.classList.toggle("open", open);
            btn.innerHTML = open ? "\u2715" : "\u2630";
        }
        btn.addEventListener("click", function () {
            setOpen(!toc.classList.contains("open"));
        });
        toc.addEventListener("click", function (e) {
            if (e.target && e.target.tagName === "A") setOpen(false);
        });
        document.addEventListener("keydown", function (e) {
            if (e.key === "Escape") setOpen(false);
        });
    }

    // ===== 5. 阅读进度（#reading-progress，右下角百分比） =====
    var pdiv = document.createElement("div");
    pdiv.id = "reading-progress";
    pdiv.textContent = "0%";
    document.body.appendChild(pdiv);
    function updateProgress() {
        var d = document.documentElement;
        var max = d.scrollHeight - d.clientHeight;
        var top = d.scrollTop || document.body.scrollTop;
        var p = max > 0 ? Math.round(top / max * 100) : 0;
        pdiv.textContent = p + "%";
    }
    window.addEventListener("scroll", updateProgress, { passive: true });
    window.addEventListener("resize", updateProgress);
    updateProgress();

    // ===== 6. 复制劫持水印 =====
    document.addEventListener("copy", function (event) {
        try {
            var selected = window.getSelection ? window.getSelection().toString() : "";
            if (selected) {
                event.clipboardData.setData("text/plain", selected + "\n\n\u6B22\u8FCE\u4F7F\u7528 " + WATERMARK);
                event.preventDefault();
            }
        } catch (err) {}
    });

    // ===== 启动 =====
    buildToc();
    assignConceptTable();
})();
"""


def _render_body(md_content: str) -> str:
    """Markdown -> HTML 主体，优先使用 markdown 库，缺失时降级为 <pre>。"""
    try:
        import markdown as _markdown
    except ImportError:
        from html import escape

        return "<pre>" + escape(md_content) + "</pre>"

    attempts = (
        ["tables", "fenced_code"],
        ["markdown.extensions.tables", "markdown.extensions.fenced_code"],
    )
    for exts in attempts:
        try:
            return _markdown.markdown(md_content, extensions=exts)
        except (ImportError, KeyError):
            continue

    from html import escape

    return "<pre>" + escape(md_content) + "</pre>"


def build_html(md_content: str, output_path: Path, show_concept_table: bool = True) -> Path:
    """将 Markdown 转换为带目录伸缩 / 阅读进度 / 术语高亮 / MathJax / 水印的完整 HTML 页面。"""
    protected_md, maths = protect_math(md_content)
    body_html = annotate_first_occurrences(_render_body(protected_md))
    body_html = restore_math(body_html, maths)
    css = load_css()

    js = (
        _BUILD_JS.replace("__WATERMARK__", WATERMARK)
        .replace("__SHOW_CONCEPT_TABLE__", "true" if show_concept_table else "false")
    )

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    layout_css = (
        "html, body { height: 100%; margin: 0; padding: 0; }\n"
        "html { scroll-behavior: smooth; }\n"
        "body { max-width: none; background: #fafbfc; }\n"
        ".content-area { max-width: 1080px; margin: 0 auto; padding: 24px 40px 96px; }\n"
        "table { border-collapse: collapse; width: 100%; margin: 20px 0; }\n"
        "th, td { border: 1px solid #d8e0e8; padding: 8px 12px; }\n"
        "img { max-width: 100%; height: auto; display: block; margin: 15px 0; }\n"
        "span[data-en] { background: #fff1d6; padding: 2px 6px; border-radius: 4px; font-weight: 600; "
        "color: #8a5a1a; border-bottom: 2px solid #f5b86e; cursor: help; }\n"
        "/* 目录伸缩 */\n"
        "#toc-btn { position: fixed; right: 14px; top: 50%; transform: translateY(-50%); width: 46px; "
        "height: 46px; border-radius: 50%; background: #1a3c5e; color: #fff; border: none; cursor: pointer; "
        "font-size: 21px; line-height: 1; display: flex; align-items: center; justify-content: center; "
        "box-shadow: 0 4px 14px rgba(15,35,60,.28); z-index: 1002; user-select: none; "
        "transition: background .2s ease, box-shadow .2s ease, transform .18s ease; }\n"
        "#toc-btn:hover { background: #2a5a8a; box-shadow: 0 6px 18px rgba(15,35,60,.36); }\n"
        "#toc-btn:active { transform: translateY(-50%) scale(.94); }\n"
        "#toc-outline { position: fixed !important; top: 50% !important; right: 78px !important; "
        "transform: translateY(-50%) !important; display: none !important; margin: 0 !important; "
        "width: min(260px, 44vw); max-height: 74vh; overflow-y: auto; background: #ffffff; "
        "border: 1px solid #e3e8ee; border-radius: 10px; box-shadow: 0 8px 28px rgba(15,35,60,.14); "
        "padding: 14px 12px; box-sizing: border-box; opacity: 0; transition: opacity .18s ease, transform .18s ease; }\n"
        "#toc-outline.open { display: block !important; opacity: 1; }\n"
        ".toc-outline a { display: block; padding: 4px 8px; border-radius: 6px; "
        "border-left: 2px solid transparent; transition: background .15s ease, color .15s ease, "
        "padding-left .15s ease, border-color .15s ease; }\n"
        ".toc-outline a:hover { background: #eef4fb; padding-left: 14px; border-left-color: #2a7a9c; }\n"
        ".toc-header { font-weight: 700; color: #1a3c5e; font-size: 15px; margin-bottom: 10px; "
        "padding-bottom: 8px; border-bottom: 2px solid #2a7a9c; }\n"
        "/* 注释样式：通俗解读注记 + 提示框 */\n"
        ".note { background: #fff7e8; border-left: 4px solid #f2b34c; border-radius: 0 8px 8px 0; "
        "padding: 10px 16px; margin: 12px 0 22px; font-family: 'KaiTi','STKaiti','楷体',serif; "
        "font-size: 15px; color: #5f4a17; line-height: 1.8; }\n"
        ".note::before { content: \"通俗解读\"; font-family: 'Segoe UI','Roboto',Arial,sans-serif; "
        "display: inline-block; font-size: 12px; font-weight: 600; letter-spacing: 1px; color: #b47a12; "
        "background: #fdeecb; border-radius: 4px; padding: 1px 8px; margin-right: 8px; }\n"
        ".tipbox { background: #eff4ff; border: 1px solid #c9ddf9; border-left: 4px solid #2a7a9c; "
        "border-radius: 0 8px 8px 0; padding: 10px 16px; margin: 14px 0 22px; font-size: 14px; color: #1d3a6f; }\n"
        "#reading-progress { position: fixed; right: 16px; bottom: 16px; z-index: 1001; font-size: 20px; "
        "font-weight: 600; line-height: 1; letter-spacing: .5px; color: #1a3c5e; background: rgba(255,255,255,.92); "
        "border: 1px solid #dfe6ef; border-radius: 20px; padding: 6px 14px; "
        "box-shadow: 0 2px 10px rgba(15,35,60,.18); user-select: none; }\n"
        "@media (max-width: 700px) { #toc-outline { right: 70px !important; width: min(240px, 60vw) !important; } }\n"
    )

    full_html = (
        "<!DOCTYPE html>\n"
        '<html lang="zh-CN">\n'
        "<head>\n"
        '    <meta charset="UTF-8">\n'
        '    <meta name="viewport" content="width=device-width, initial-scale=1.0">\n'
        "    <title>学案译文</title>\n"
        "    <style>\n"
        + css
        + "\n    </style>\n"
        "    <style>\n"
        + layout_css
        + "    </style>\n"
        "    <script>\n"
        "        MathJax = {\n"
        "            tex: { inlineMath: [['$', '$'], ['\\(', '\\)']], displayMath: [['$$', '$$'], ['\\[', '\\]']] },\n"
        "            svg: { fontCache: 'global' }\n"
        "        };\n"
        "    </script>\n"
        '    <script type="text/javascript" id="MathJax-script" async\n'
        '        src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-svg.js"></script>\n'
        "</head>\n"
        "<body>\n"
        '    <main class="content-area">\n'
        + body_html
        + "\n"
        '        <footer style="margin-top: 40px; padding-top: 16px; border-top: 2px dashed #d0d7de;'
        ' text-align: center; color: #8a97a5; font-size: 12px;">\n'
        "            欢迎使用 " + WATERMARK + "\n"
        "        </footer>\n"
        "    </main>\n"
        '    <aside class="toc-outline" id="toc-outline">\n'
        '        <div class="toc-header">\u76EE\u5F55</div>\n'
        "    </aside>\n"
        "    <script>\n"
        + js
        + "\n    </script>\n"
        "</body>\n"
        "</html>\n"
    )

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(full_html)
    return output_path