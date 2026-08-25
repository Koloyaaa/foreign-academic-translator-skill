"""HTML 构建器：将 Markdown 译文转换为带 TOC / 术语高亮 / MathJax / 水印的 HTML 页面。"""

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

    // ===== 2. 右侧大纲：章节横线分隔 + 当前阅读位置高亮 =====
    function buildToc() {
        var headings = document.querySelectorAll(HEADING_SELECTOR);
        var sidebar = document.getElementById("toc-sidebar");
        if (!headings.length || !sidebar) return;
        var list = document.createElement("ul");
        list.style.listStyle = "none";
        list.style.padding = "0";
        list.style.margin = "0";
        var firstH2 = true;
        headings.forEach(function (hd, i) {
            if (!hd.id) hd.id = "toc-heading-" + i;
            var li = document.createElement("li");
            li.className = "toc-item";
            li.style.margin = "4px 0";
            li.style.borderRadius = "4px";
            li.style.transition = "background 0.2s";
            if (hd.tagName === "H2") {
                li.style.paddingLeft = "12px";
                if (!firstH2) {
                    li.style.borderTop = "1px solid #e3e8ee";
                    li.style.paddingTop = "8px";
                    li.style.marginTop = "8px";
                }
                firstH2 = false;
            } else if (hd.tagName === "H3") {
                li.style.paddingLeft = "26px";
            }
            var link = document.createElement("a");
            link.href = "#" + hd.id;
            link.textContent = hd.textContent;
            link.style.textDecoration = "none";
            link.style.color = "#1a4a8a";
            link.style.fontSize = "13px";
            link.style.display = "block";
            link.style.padding = "3px 8px";
            link.style.borderRadius = "4px";
            link.addEventListener("click", function (event) {
                event.preventDefault();
                hd.scrollIntoView({ behavior: "smooth", block: "start" });
            });
            li.appendChild(link);
            list.appendChild(li);
        });
        sidebar.appendChild(list);

        // 滚动时用浅灰半透明色块标记当前阅读章节
        function updateActive() {
            var pos = window.scrollY + 140;
            var idx = -1;
            headings.forEach(function (hd, i) {
                if (hd.getBoundingClientRect().top + window.scrollY <= pos) idx = i;
            });
            var items = sidebar.querySelectorAll(".toc-item");
            items.forEach(function (item, i) {
                item.style.background = (i === idx) ? "rgba(160, 170, 180, 0.30)" : "transparent";
            });
        }
        window.addEventListener("scroll", updateActive, { passive: true });
        updateActive();
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

    // ===== 4. 复制劫持水印 =====
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

    # 依次尝试扩展名解析：部分环境未注册扩展入口点，需回退到完整模块路径
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
    """将 Markdown 转换为带大纲 TOC / 术语高亮 / MathJax / 水印的完整 HTML 页面。"""
    # 先保护公式再转 markdown，避免 _ / * 被转成 <em> 切碎公式；转换后还原，供 MathJax 渲染
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
        "body { max-width: none; background: #fafbfc; }\n"
        ".layout-wrapper { display: flex; max-width: 1200px; margin: 0 auto; min-height: 100vh; }\n"
        ".content-area { flex: 1; max-width: calc(100% - 280px); padding: 20px 40px 40px 20px; overflow-x: auto; }\n"
        ".toc-sidebar { width: 260px; flex-shrink: 0; position: sticky; top: 0; height: 100vh; overflow-y: auto; "
        "padding: 24px 16px; border-left: 1px solid #e8ecf0; background: #f8f9fa; box-sizing: border-box; }\n"
        ".toc-header { font-weight: 700; color: #1a3c5e; font-size: 16px; margin-bottom: 12px; "
        "padding-bottom: 8px; border-bottom: 2px solid #2a7a9c; }\n"
        "table { border-collapse: collapse; width: 100%; margin: 20px 0; }\n"
        "th, td { border: 1px solid #d8e0e8; padding: 8px 12px; }\n"
        "img { max-width: 100%; height: auto; display: block; margin: 15px 0; }\n"
        "span[data-en] { background: #fff1d6; padding: 2px 6px; border-radius: 4px; font-weight: 600; "
        "color: #8a5a1a; border-bottom: 2px solid #f5b86e; cursor: help; }\n"
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
        '<div class="layout-wrapper">\n'
        '    <main class="content-area">\n'
        + body_html
        + "\n"
        '        <footer style="margin-top: 40px; padding-top: 16px; border-top: 2px dashed #d0d7de;'
        ' text-align: center; color: #8a97a5; font-size: 12px;">\n'
        "            欢迎使用 " + WATERMARK + "\n"
        "        </footer>\n"
        "    </main>\n"
        '    <aside class="toc-sidebar" id="toc-sidebar">\n'
        '        <div class="toc-header">\u76EE\u5F55</div>\n'
        "    </aside>\n"
        "</div>\n"
        "    <script>\n"
        + js
        + "\n    </script>\n"
        "</body>\n"
        "</html>\n"
    )

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(full_html)
    return output_path
