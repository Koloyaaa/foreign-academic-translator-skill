"""HTML 构建器：将 Markdown 译文转换为带双侧目录、阅读进度、术语高亮和 MathJax 的 HTML 页面。"""

from pathlib import Path
import re
from html import escape, unescape
from os.path import relpath
from urllib.parse import quote

from .base import (
    WATERMARK,
    load_css,
    annotate_first_occurrences,
    protect_math,
    restore_math,
    style_source_markers,
    validate_rendered_text,
)

FONT_AWESOME_CSS_URL = "https://cdnjs.cloudflare.com/ajax/libs/font-awesome/7.3.1/css/all.min.css"

# 页面内嵌 JS（普通字符串，非 f-string，避免花括号与 Python 格式化冲突）
# 通过占位符 __SHOW_CONCEPT_TABLE__ 在运行时替换。
_BUILD_JS = r"""
(function () {
    "use strict";
    var SHOW_TABLE = __SHOW_CONCEPT_TABLE__;
    var HEADING_SELECTOR = "h1, h2, h3, h4";
    var main = document.querySelector(".content-area");
    var prefKey = "foreign-academic-translator:reader-settings:v1";
    var notesKey = "foreign-academic-translator:notes:v1:" + location.pathname;
    var readerConfig = { palette: "blue", theme: "light", width: 10000 };
    var toastTimer = 0;
    function readJSON(key, fallback) {
        try { var value = localStorage.getItem(key); return value ? JSON.parse(value) : fallback; }
        catch (err) { return fallback; }
    }
    function writeJSON(key, value) {
        try { localStorage.setItem(key, JSON.stringify(value)); return true; }
        catch (err) { return false; }
    }
    function createButton(label, title, className) {
        var button = document.createElement("button");
        button.type = "button"; button.className = className || "reader-control-button";
        button.textContent = label; button.title = title; button.setAttribute("aria-label", title);
        return button;
    }
    function showNotice(message) {
        var notice = document.getElementById("reader-toast");
        if (!notice) {
            notice = document.createElement("div"); notice.id = "reader-toast"; notice.className = "reader-toast";
            notice.setAttribute("role", "status"); notice.setAttribute("aria-live", "polite"); document.body.appendChild(notice);
        }
        notice.textContent = message; notice.classList.add("visible");
        window.clearTimeout(toastTimer);
        toastTimer = window.setTimeout(function () { notice.classList.remove("visible"); }, 3600);
    }
    function createMenu(parent, label) {
        var menu = document.createElement("div"); menu.className = "reader-menu";
        menu.setAttribute("role", "menu"); menu.setAttribute("aria-label", label); parent.appendChild(menu); return menu;
    }
    function addOptions(menu, choices, onSelect) {
        choices.forEach(function (choice) {
            var item = createButton(choice.label, choice.label, "reader-menu-item");
            item.dataset.value = choice.value; item.setAttribute("role", "menuitemradio");
            item.addEventListener("click", function () { onSelect(choice.value); });
            menu.appendChild(item);
        });
    }
    function updateMenuSelection(menu, value) {
        menu.querySelectorAll(".reader-menu-item").forEach(function (item) {
            item.setAttribute("aria-checked", String(item.dataset.value === value));
        });
    }
    function initReaderSettings() {
        var saved = readJSON(prefKey, {});
        var paletteLabels = { blue: "蓝色", teal: "青绿", violet: "紫色", amber: "琥珀" };
        var themeLabels = { light: "浅色", dark: "深色", system: "跟随系统" };
        if (["blue", "teal", "violet", "amber"].indexOf(saved.palette) !== -1) readerConfig.palette = saved.palette;
        if (["light", "dark", "system"].indexOf(saved.theme) !== -1) readerConfig.theme = saved.theme;
        if (typeof saved.width === "number" && isFinite(saved.width)) {
            readerConfig.width = saved.width === 1830 ? 10000 : Math.max(720, Math.min(10000, saved.width));
        }
        var bar = document.createElement("div"); bar.id = "reader-controls"; bar.setAttribute("aria-label", "阅读显示设置");
        var paletteWrap = document.createElement("div"); paletteWrap.className = "reader-control-wrap";
        var themeWrap = document.createElement("div"); themeWrap.className = "reader-control-wrap";
        var paletteButton = createButton("🎨", "配色：" + paletteLabels[readerConfig.palette], "reader-control-button icon-control");
        var themeButton = createButton("◐", "明暗：" + themeLabels[readerConfig.theme], "reader-control-button icon-control");
        paletteButton.setAttribute("aria-haspopup", "menu"); paletteButton.setAttribute("aria-expanded", "false");
        themeButton.setAttribute("aria-haspopup", "menu"); themeButton.setAttribute("aria-expanded", "false");
        var paletteMenu = createMenu(paletteWrap, "配色选择"), themeMenu = createMenu(themeWrap, "明暗模式选择");
        paletteWrap.appendChild(paletteButton); paletteWrap.appendChild(paletteMenu);
        themeWrap.appendChild(themeButton); themeWrap.appendChild(themeMenu);
        bar.appendChild(paletteWrap); bar.appendChild(themeWrap); document.body.appendChild(bar);
        function closeMenus() {
            paletteMenu.classList.remove("open"); themeMenu.classList.remove("open");
            paletteButton.setAttribute("aria-expanded", "false"); themeButton.setAttribute("aria-expanded", "false");
        }
        paletteButton.addEventListener("click", function () {
            var open = !paletteMenu.classList.contains("open"); closeMenus();
            if (open) { paletteMenu.classList.add("open"); paletteButton.setAttribute("aria-expanded", "true"); }
        });
        themeButton.addEventListener("click", function () {
            var open = !themeMenu.classList.contains("open"); closeMenus();
            if (open) { themeMenu.classList.add("open"); themeButton.setAttribute("aria-expanded", "true"); }
        });
        function apply() {
            document.documentElement.setAttribute("data-palette", readerConfig.palette);
            document.documentElement.setAttribute("data-theme", readerConfig.theme);
            document.documentElement.style.setProperty("--reader-width", readerConfig.width + "px");
            paletteButton.title = "配色：" + paletteLabels[readerConfig.palette]; paletteButton.setAttribute("aria-label", paletteButton.title);
            themeButton.title = "明暗：" + themeLabels[readerConfig.theme]; themeButton.setAttribute("aria-label", themeButton.title);
            updateMenuSelection(paletteMenu, readerConfig.palette); updateMenuSelection(themeMenu, readerConfig.theme);
            writeJSON(prefKey, readerConfig); window.dispatchEvent(new Event("readerwidthchange"));
        }
        addOptions(paletteMenu, [
            { value: "blue", label: "🔵 蓝色" }, { value: "teal", label: "🟢 青绿" },
            { value: "violet", label: "🟣 紫色" }, { value: "amber", label: "🟠 琥珀" }
        ], function (value) { readerConfig.palette = value; apply(); closeMenus(); });
        addOptions(themeMenu, [
            { value: "light", label: "☀️ 浅色" }, { value: "dark", label: "🌙 深色" },
            { value: "system", label: "🖥️ 跟随系统" }
        ], function (value) { readerConfig.theme = value; apply(); closeMenus(); });
        document.addEventListener("click", function (event) { if (!bar.contains(event.target)) closeMenus(); });
        document.addEventListener("keydown", function (event) { if (event.key === "Escape") closeMenus(); });
        apply();
    }
    function assignConceptTable() {
        if (!SHOW_TABLE) return;
        var headings = document.querySelectorAll("h2, h3"), target = null;
        for (var i = 0; i < headings.length; i++) {
            var title = headings[i].textContent || "";
            if (title.indexOf("概念汇总表") !== -1 || title.indexOf("重要术语概念") !== -1) {
                var sibling = headings[i].nextElementSibling;
                while (sibling && sibling.tagName !== "TABLE") sibling = sibling.nextElementSibling;
                if (sibling) target = sibling; break;
            }
        }
        if (!target) { var tables = document.querySelectorAll("table"); if (tables.length) target = tables[tables.length - 1]; }
        if (target) target.id = "concept-table";
    }
    function linkElementToGlossary(element, extraClass) {
        if (!SHOW_TABLE || element.closest("a")) return;
        var link = document.createElement("a"); link.href = "#concept-table";
        link.className = (element.className || "") + " " + (extraClass || "term-link");
        link.title = element.getAttribute("data-en") || "跳转到术语表";
        while (element.firstChild) link.appendChild(element.firstChild);
        element.parentNode.replaceChild(link, element);
    }
    function linkGlossaryTerms() {
        if (!SHOW_TABLE) return;
        var glossaryTerms = [];
        var table = document.getElementById("concept-table");
        if (table) {
            table.querySelectorAll("tr").forEach(function (row, index) {
                if (!index || !row.cells || !row.cells.length) return;
                var value = row.cells[0].textContent || "";
                if (value.trim()) glossaryTerms.push(normalizeConcept(value));
            });
        }
        function normalizeConcept(value) {
            return (value || "").normalize("NFD").replace(/[\u0300-\u036f]/g, "")
                .toLowerCase().replace(/[’']/g, " ").replace(/[^a-z0-9\u3400-\u9fff]+/g, " ")
                .trim().replace(/^(le|la|les|l|un|une|des|du|the)\s+/, "")
                .replace(/\b([a-z]{4,})s\b/g, "$1");
        }
        function isGlossaryConcept(value) {
            var headingTerm = normalizeConcept(value);
            var stopWords = { de: true, des: true, du: true, la: true, le: true, les: true, l: true,
                un: true, une: true, et: true, en: true, pour: true, sur: true, au: true, aux: true,
                the: true, of: true, and: true, in: true, on: true, transformation: true };
            var headingTokens = headingTerm.split(/\s+/).filter(function (token) { return token.length >= 5 && !stopWords[token]; });
            return headingTerm.length >= 5 && glossaryTerms.some(function (term) {
                if (term === headingTerm || headingTerm.indexOf(term) !== -1 || term.indexOf(headingTerm) !== -1) return true;
                var termTokens = term.split(/\s+/);
                return termTokens.some(function (token) {
                    return token.length >= 5 && !stopWords[token] && headingTokens.indexOf(token) !== -1;
                });
            });
        }
        document.querySelectorAll(".content-area .document-title .source-title, .content-area h1 .heading-source, .content-area h2 .heading-source, .content-area h3 .heading-source, .content-area h4 .heading-source").forEach(function (element) {
            if (isGlossaryConcept(element.textContent)) linkElementToGlossary(element, "heading-term-link");
        });
        document.querySelectorAll(".content-area span[data-en]").forEach(function (element) {
            linkElementToGlossary(element, "term-link");
        });
    }
    function initTocTracking() {
        var toc = document.getElementById("toc-outline");
        if (!main || !toc) return;
        var headings = Array.prototype.slice.call(main.querySelectorAll(HEADING_SELECTOR));
        var links = Array.prototype.slice.call(toc.querySelectorAll(".toc-item a[href^='#']"));
        var header = toc.querySelector(".toc-header");
        if (!headings.length || !links.length) return;
        var activeId = "";
        var scheduled = false;
        function keepLinkVisible(link) {
            var rail = toc.getBoundingClientRect();
            var item = link.getBoundingClientRect();
            var top = header ? header.getBoundingClientRect().bottom + 6 : rail.top + 8;
            var bottom = rail.bottom - 8;
            if (item.top < top) toc.scrollTop -= top - item.top;
            else if (item.bottom > bottom) toc.scrollTop += item.bottom - bottom;
        }
        function update() {
            var marker = Math.max(100, Math.min(220, window.innerHeight * .24));
            var current = headings[0];
            for (var i = 0; i < headings.length; i++) {
                if (headings[i].getBoundingClientRect().top <= marker) current = headings[i];
                else break;
            }
            if (window.pageYOffset + window.innerHeight >= document.documentElement.scrollHeight - 3) {
                current = headings[headings.length - 1];
            }
            if (!current || current.id === activeId) return;
            activeId = current.id;
            var activeLink = null;
            links.forEach(function (link) {
                var selected = link.getAttribute("href") === "#" + activeId;
                link.classList.toggle("is-active", selected);
                if (selected) { link.setAttribute("aria-current", "location"); activeLink = link; }
                else link.removeAttribute("aria-current");
            });
            if (activeLink) keepLinkVisible(activeLink);
        }
        function scheduleUpdate() {
            if (scheduled) return;
            scheduled = true;
            window.requestAnimationFrame(function () { scheduled = false; update(); });
        }
        window.addEventListener("scroll", scheduleUpdate, { passive: true });
        window.addEventListener("resize", scheduleUpdate);
        window.addEventListener("load", scheduleUpdate);
        if (window.ResizeObserver) new window.ResizeObserver(scheduleUpdate).observe(main);
        if (document.fonts && document.fonts.ready) document.fonts.ready.then(scheduleUpdate);
        update();
    }
    function initProgress() {
        var chip = document.createElement("div"); chip.id = "reading-progress";
        chip.setAttribute("aria-live", "polite"); document.body.appendChild(chip);
        function update() {
            if (!main) return;
            var start = main.getBoundingClientRect().top + window.pageYOffset;
            var end = main.getBoundingClientRect().bottom + window.pageYOffset;
            if (SHOW_TABLE) {
                var excluded = Array.prototype.find.call(main.querySelectorAll(HEADING_SELECTOR), function (heading) {
                    var title = heading.textContent || "";
                    return /(测验|考试|章末测试|quiz|qcm|evaluation|évaluation|exam(?:en)?s?|épreuve|\btest\b|词汇表|术语表|概念汇总表|重要术语概念|glossaire|glossary|vocabulaire)/i.test(title);
                });
                if (excluded) end = excluded.getBoundingClientRect().top + window.pageYOffset;
            }
            var max = Math.max(0, end - start - window.innerHeight);
            var current = Math.max(0, (window.pageYOffset || document.documentElement.scrollTop) - start);
            chip.textContent = (max ? Math.min(100, Math.round(Math.min(max, current) / max * 100)) : 100) + "%";
        }
        window.addEventListener("scroll", update, { passive: true });
        window.addEventListener("resize", update); window.addEventListener("load", update); update();
    }
    function initResizableReader() {
        if (!main) return;
        var fileOutline = document.getElementById("file-outline");
        var tocOutline = document.getElementById("toc-outline");
        function reservedWidth() {
            return (fileOutline ? fileOutline.getBoundingClientRect().width : 0) +
                (tocOutline ? tocOutline.getBoundingClientRect().width : 0);
        }
        function readerCenter() {
            var left = fileOutline ? fileOutline.getBoundingClientRect().width : 0;
            var right = tocOutline ? tocOutline.getBoundingClientRect().width : 0;
            return (left + window.innerWidth - right) / 2;
        }
        function maxReaderWidth() { return Math.max(720, window.innerWidth - reservedWidth()); }
        var handle = document.createElement("div"); handle.id = "reader-resize-handle";
        handle.className = "reader-resize-handle"; handle.setAttribute("role", "separator");
        handle.setAttribute("aria-label", "拖动调整译文阅读栏宽度"); handle.setAttribute("aria-orientation", "vertical");
        handle.setAttribute("aria-valuemin", "720"); handle.setAttribute("tabindex", "0"); document.body.appendChild(handle);
        function updatePosition() {
            if (window.innerWidth <= 1280) { handle.hidden = true; return; }
            handle.hidden = false;
            var rect = main.getBoundingClientRect();
            handle.style.left = Math.max(8, Math.min(window.innerWidth - 8, rect.right - 6)) + "px";
            handle.style.top = Math.max(56, Math.min(window.innerHeight - 148, window.innerHeight / 2 - 64)) + "px";
            handle.setAttribute("aria-valuenow", String(Math.round(rect.width)));
            handle.setAttribute("aria-valuemax", String(Math.round(maxReaderWidth())));
        }
        function updateWidth(clientX) {
            var width = Math.max(720, Math.min(maxReaderWidth(), (clientX - readerCenter()) * 2));
            readerConfig.width = width; document.documentElement.style.setProperty("--reader-width", width + "px");
            writeJSON(prefKey, readerConfig); updatePosition(); window.dispatchEvent(new Event("readerwidthchange"));
        }
        var dragging = false;
        handle.addEventListener("pointerdown", function (event) {
            if (window.innerWidth <= 740) return;
            dragging = true; handle.classList.add("dragging"); event.preventDefault();
            if (handle.setPointerCapture) handle.setPointerCapture(event.pointerId);
        });
        handle.addEventListener("pointermove", function (event) { if (dragging) updateWidth(event.clientX); });
        function stopDrag() { dragging = false; handle.classList.remove("dragging"); }
        handle.addEventListener("pointerup", stopDrag); handle.addEventListener("pointercancel", stopDrag);
        handle.addEventListener("keydown", function (event) {
            if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") return;
            event.preventDefault(); var rect = main.getBoundingClientRect();
            updateWidth(readerCenter() + (rect.width + (event.key === "ArrowRight" ? 40 : -40)) / 2);
        });
        window.addEventListener("resize", updatePosition); window.addEventListener("scroll", updatePosition, { passive: true });
        window.addEventListener("readerwidthchange", updatePosition); updatePosition();
    }
    function textIndex() {
        var walker = document.createTreeWalker(main, NodeFilter.SHOW_TEXT, {
            acceptNode: function (node) {
                var parent = node.parentElement;
                if (!parent || parent.closest("script, style, button, footer, mjx-container, .reader-controls, .selection-toolbar, .annotation-popover, .reader-toast")) return NodeFilter.FILTER_REJECT;
                return node.nodeValue ? NodeFilter.FILTER_ACCEPT : NodeFilter.FILTER_REJECT;
            }
        });
        var nodes = [], text = "", node;
        while ((node = walker.nextNode())) { nodes.push({ node: node, start: text.length, end: text.length + node.nodeValue.length }); text += node.nodeValue; }
        return { nodes: nodes, text: text };
    }
    function offsetFor(index, node, offset) {
        for (var i = 0; i < index.nodes.length; i++) if (index.nodes[i].node === node) return index.nodes[i].start + offset;
        return -1;
    }
    function rangeFor(index, start, end) {
        var first = null, last = null;
        for (var i = 0; i < index.nodes.length; i++) {
            var part = index.nodes[i];
            if (!first && start >= part.start && start < part.end) first = { node: part.node, offset: start - part.start };
            if (end > part.start && end <= part.end) { last = { node: part.node, offset: end - part.start }; break; }
        }
        if (!first || !last) return null;
        var range = document.createRange(); range.setStart(first.node, first.offset); range.setEnd(last.node, last.offset); return range;
    }
    function anchorPosition(index, record) {
        var anchor = (record.prefix || "") + record.quote + (record.suffix || ""), at = index.text.indexOf(anchor);
        if (at >= 0) return at + (record.prefix || "").length;
        return index.text.indexOf(record.quote);
    }
    function rangeOverlapsExisting(range) {
        var marks = main.querySelectorAll(".user-highlight");
        for (var i = 0; i < marks.length; i++) {
            try { if (range.intersectsNode(marks[i])) return true; } catch (err) {}
        }
        return false;
    }
    function mathContainers() { return Array.prototype.slice.call(main.querySelectorAll("mjx-container")); }
    function syncMathIds() {
        var containers = mathContainers();
        var used = Object.create(null), next = 0;
        containers.forEach(function (container) { if (container.dataset.mathId) used[container.dataset.mathId] = true; });
        containers.forEach(function (container) {
            if (container.dataset.mathId) return;
            while (used["formula-" + next]) next++;
            container.dataset.mathId = "formula-" + next; used[container.dataset.mathId] = true; next++;
        });
        return containers;
    }
    function mathNodesForRange(range) {
        if (!range) return [];
        return mathContainers().filter(function (container) {
            try { return range.intersectsNode(container); } catch (err) { return false; }
        });
    }
    function textPartsForRange(range, index) {
        if (!range) return [];
        var parts = [];
        index.nodes.forEach(function (item) {
            var node = item.node, from = 0, to = node.nodeValue.length;
            try { if (!range.intersectsNode(node)) return; } catch (err) { return; }
            if (range.startContainer === node) from = range.startOffset;
            if (range.endContainer === node) to = range.endOffset;
            if (to <= from) return;
            var quote = node.nodeValue.slice(from, to), start = item.start + from, end = item.start + to;
            if (!quote.trim()) return;
            parts.push({ quote: quote, prefix: index.text.slice(Math.max(0, start - 28), start), suffix: index.text.slice(end, end + 28) });
        });
        return parts;
    }
    function applyFormulaRecord(record) {
        if (!record.mathIds || !record.mathIds.length) return null;
        var containers = syncMathIds(), first = null;
        record.mathIds.forEach(function (id) {
            var formula = containers.find(function (item) { return item.dataset.mathId === id; });
            if (!formula || (formula.dataset.userMarkId && formula.dataset.userMarkId !== record.id)) return;
            formula.classList.add("user-highlight"); formula.dataset.userMarkId = record.id;
            if (record.note) formula.dataset.note = record.note; else delete formula.dataset.note;
            if (!first) first = formula;
        });
        return first;
    }
    function applyRecord(record) {
        if (!main || !record || (!record.quote && !(record.mathIds && record.mathIds.length))) return null;
        var first = null, parts = Array.isArray(record.parts) ? record.parts : (record.quote ? [record] : []);
        parts.forEach(function (part) {
            if (!part.quote) return;
            var index = textIndex(), start = anchorPosition(index, part);
            if (start < 0) return;
            var range = rangeFor(index, start, start + part.quote.length);
            if (!range || rangeOverlapsExisting(range)) return;
            var mark = document.createElement("mark"); mark.className = "user-highlight"; mark.dataset.userMarkId = record.id;
            if (record.note) mark.dataset.note = record.note;
            try { range.surroundContents(mark); }
            catch (err) { try { mark.appendChild(range.extractContents()); range.insertNode(mark); } catch (ignored) {} }
            if (!first && mark.isConnected) first = mark;
        });
        return first || applyFormulaRecord(record);
    }
    function initPersonalMarks() {
        var records = readJSON(notesKey, []); if (!Array.isArray(records)) records = [];
        syncMathIds();
        records.forEach(applyRecord);
        function persist() { return writeJSON(notesKey, records); }
        var toolbar = document.createElement("div"); toolbar.className = "selection-toolbar"; toolbar.setAttribute("role", "toolbar");
        var markButton = createButton("高亮", "保存选中文字或公式的高亮", "selection-action");
        var noteButton = createButton("加注释", "给选中文字或公式添加个人注释", "selection-action");
        toolbar.appendChild(markButton); toolbar.appendChild(noteButton); toolbar.hidden = true; document.body.appendChild(toolbar);
        var guide = main && main.querySelector(".reading-guide");
        if (guide && !guide.dataset.markHelpAdded) {
            guide.dataset.markHelpAdded = "true";
            guide.appendChild(document.createTextNode(" 文本标记：选中正文或点击公式后可高亮或加注释；点击标记可查看、编辑或删除。"));
        }
        var popover = document.createElement("section"); popover.className = "annotation-popover";
        popover.setAttribute("role", "dialog"); popover.setAttribute("aria-label", "个人注释"); popover.hidden = true;
        var popTitle = document.createElement("strong"); popTitle.className = "annotation-title"; popTitle.textContent = "我的注释";
        var popText = document.createElement("p"); popText.className = "annotation-text";
        var actions = document.createElement("div"); actions.className = "annotation-actions";
        var editButton = createButton("编辑", "编辑这条个人注释", "annotation-action");
        var removeButton = createButton("删除标记", "删除这条高亮和注释", "annotation-action");
        var closeButton = createButton("关闭", "关闭个人注释", "annotation-action");
        actions.appendChild(editButton); actions.appendChild(removeButton); actions.appendChild(closeButton);
        popover.appendChild(popTitle); popover.appendChild(popText); popover.appendChild(actions); document.body.appendChild(popover);
        var activeMark = null, activeRecord = null, activeFormulaSelection = [];
        function dismissToolbar() { toolbar.hidden = true; }
        function closePopover() { popover.hidden = true; activeMark = null; activeRecord = null; }
        function placeToolbar(rect) {
            if (!rect) return;
            toolbar.style.left = Math.max(8, rect.left + rect.width / 2 - 70) + "px";
            toolbar.style.top = Math.max(8, rect.top - 46) + "px"; toolbar.hidden = false;
        }
        function showPopover(mark, item) {
            activeMark = mark; activeRecord = item;
            popText.textContent = item.note ? item.note : "此处是你标记的内容，目前还没有添加文字注释。";

            var rect = mark.getBoundingClientRect(), width = Math.min(340, window.innerWidth - 24);
            popover.style.width = width + "px"; popover.hidden = false;
            var height = popover.offsetHeight, left = Math.max(12, Math.min(window.innerWidth - width - 12, rect.left));
            var top = rect.bottom + 8;
            if (top + height > window.innerHeight - 12) top = Math.max(12, rect.top - height - 8);
            popover.style.left = left + "px"; popover.style.top = top + "px";
        }
        function unwrapMark(mark) {
            var parent = mark.parentNode;
            while (mark.firstChild) parent.insertBefore(mark.firstChild, mark);
            parent.removeChild(mark);
        }
        function saveSelection(withNote) {
            var selection = window.getSelection(), range = selection && selection.rangeCount ? selection.getRangeAt(0) : null;
            var hasText = !!(selection && selection.toString().trim());
            if (range && hasText && !main.contains(range.commonAncestorContainer)) return;
            var formulas = range && main.contains(range.commonAncestorContainer) ? mathNodesForRange(range) : [];
            if (!hasText && !formulas.length) formulas = activeFormulaSelection.filter(function (item) { return item.isConnected; });
            if (!hasText && !formulas.length) return;
            if (range && rangeOverlapsExisting(range)) { showNotice("这段文字或公式已经有高亮。请选取未标记的部分，或先删除原有标记。"); return; }
            var index = textIndex(), parts = textPartsForRange(range, index);
            syncMathIds();
            var mathIds = formulas.map(function (formula) { return formula.dataset.mathId; }).filter(Boolean);
            if (!parts.length && !mathIds.length) return;
            var note = "";
            if (withNote) { note = window.prompt("写下你对这段内容的注释：", ""); if (note === null) return; }
            var record = { id: "mark-" + Date.now() + "-" + Math.random().toString(36).slice(2, 8),
                quote: parts.length ? parts.map(function (part) { return part.quote; }).join("") : "公式", parts: parts, mathIds: mathIds, note: note.trim() };
            records.push(record);
            var savedMark = applyRecord(record); dismissToolbar(); activeFormulaSelection = [];
            if (selection) selection.removeAllRanges();
            if (!persist()) {
                showNotice("浏览器未开放本地保存；标记和注释仍会留在当前页面，关闭页面后可能无法保留。");
                if (withNote && savedMark) showPopover(savedMark, record);
                return;
            }
            if (withNote && savedMark) showPopover(savedMark, record);
            else if (savedMark) showNotice("已添加高亮。点击标记可查看或补充注释。");
            else showNotice("标记已保存，但这段文字暂时无法定位显示。请刷新页面后重试。");
        }
        markButton.addEventListener("mousedown", function (event) { event.preventDefault(); });
        noteButton.addEventListener("mousedown", function (event) { event.preventDefault(); });
        markButton.addEventListener("click", function () { saveSelection(false); });
        noteButton.addEventListener("click", function () { saveSelection(true); });
        editButton.addEventListener("click", function () {
            if (!activeRecord || !activeMark) return;
            var updated = window.prompt("编辑这条个人注释：", activeRecord.note || "");
            if (updated === null) return;
            var previous = activeRecord.note; activeRecord.note = updated.trim();
            if (!persist()) { activeRecord.note = previous; showNotice("浏览器没有开放本地存储权限，注释修改未保存。"); return; }
            Array.prototype.forEach.call(main.querySelectorAll("[data-user-mark-id]"), function (item) {
                if (item.dataset.userMarkId !== activeRecord.id) return;
                if (activeRecord.note) item.dataset.note = activeRecord.note; else delete item.dataset.note;
            });
            showPopover(activeMark, activeRecord);
        });
        removeButton.addEventListener("click", function () {
            if (!activeRecord || !activeMark) return;
            var id = activeRecord.id, index = records.findIndex(function (item) { return item.id === id; });
            if (index < 0) return;
            var removed = records.splice(index, 1)[0];
            if (!persist()) { records.splice(index, 0, removed); showNotice("浏览器没有开放本地存储权限，删除未保存。"); return; }
            var markedNodes = Array.prototype.slice.call(main.querySelectorAll("[data-user-mark-id]"));
            closePopover();
            markedNodes.forEach(function (node) {
                if (node.dataset.userMarkId !== id) return;
                if (node.tagName && node.tagName.toLowerCase() === "mark") unwrapMark(node);
                else { node.classList.remove("user-highlight"); delete node.dataset.userMarkId; delete node.dataset.note; }
            });
        });
        closeButton.addEventListener("click", closePopover);
        document.addEventListener("mouseup", function () {
            window.setTimeout(function () {
                var selection = window.getSelection(), range = selection && selection.rangeCount ? selection.getRangeAt(0) : null;
                var hasText = !!(selection && selection.toString().trim());
                var formulas = range && main.contains(range.commonAncestorContainer) ? mathNodesForRange(range) : [];
                if (!range || !main.contains(range.commonAncestorContainer) || (!hasText && !formulas.length)) { dismissToolbar(); return; }
                activeFormulaSelection = formulas;
                var rect = range.getBoundingClientRect();
                if ((!rect || (!rect.width && !rect.height)) && formulas.length) rect = formulas[0].getBoundingClientRect();
                placeToolbar(rect);
            }, 0);
        });
        main.addEventListener("click", function (event) {
            var marked = event.target.closest && event.target.closest(".user-highlight");
            if (marked) {
                var item = records.find(function (record) { return record.id === marked.dataset.userMarkId; });
                if (item && activeMark === marked && !popover.hidden) closePopover();
                else if (item) showPopover(marked, item);
                return;
            }
            var formula = event.target.closest && event.target.closest("mjx-container");
            if (!formula) return;
            var selection = window.getSelection(), range = selection && selection.rangeCount ? selection.getRangeAt(0) : null;
            if (selection && selection.toString().trim()) return;
            activeFormulaSelection = range ? mathNodesForRange(range) : [];
            if (!activeFormulaSelection.length) activeFormulaSelection = [formula];
            var rect = range && range.getBoundingClientRect ? range.getBoundingClientRect() : null;
            if ((!rect || (!rect.width && !rect.height)) && formula) rect = formula.getBoundingClientRect();
            placeToolbar(rect);
        });
        document.addEventListener("click", function (event) {
            if (popover.contains(event.target)) return;
            if (toolbar.contains(event.target)) return;
            if (event.target.closest && event.target.closest(".user-highlight")) return;
            closePopover();
        });
        document.addEventListener("keydown", function (event) { if (event.key === "Escape") closePopover(); });
        document.addEventListener("selectionchange", function () {
            var selection = window.getSelection(), range = selection && selection.rangeCount ? selection.getRangeAt(0) : null;
            if (selection && selection.toString().trim()) return;
            if (range && main.contains(range.commonAncestorContainer) && mathNodesForRange(range).length) return;
            if (!activeFormulaSelection.length) dismissToolbar();
        });
        if (window.MutationObserver && main) {
            var formulaObserver = new MutationObserver(function () {
                syncMathIds(); records.forEach(applyFormulaRecord);
            });
            formulaObserver.observe(main, { childList: true, subtree: true });
        }
        window.setTimeout(function () { syncMathIds(); records.forEach(applyFormulaRecord); }, 0);
    }
    function wireStaticQuiz() {
        document.querySelectorAll(".quiz-question").forEach(function (card, index) {
            var fieldset = card.querySelector(".quiz-options");
            var submit = card.querySelector(".quiz-submit");
            var feedback = card.querySelector(".quiz-feedback");
            var explanation = card.querySelector("template.quiz-explanation");
            if (!fieldset || !submit || !feedback || !card.dataset.answer) return;
            fieldset.querySelectorAll('input[type="radio"]').forEach(function (input) {
                input.name = "quiz-" + (index + 1);
            });
            submit.addEventListener("click", function () {
                var selected = fieldset.querySelector('input[type="radio"]:checked');
                if (!selected) {
                    feedback.textContent = "请先选择一个选项。";
                    feedback.hidden = false;
                    return;
                }
                fieldset.querySelectorAll("input").forEach(function (input) { input.disabled = true; });
                submit.disabled = true;
                submit.textContent = "已提交";
                var correct = selected.value === card.dataset.answer;
                feedback.classList.toggle("correct", correct);
                feedback.classList.toggle("incorrect", !correct);
                feedback.textContent = (correct ? "正确。" : "已提交。") +
                    "答案 / Réponse：" + card.dataset.answer + "。解析：";
                if (explanation) feedback.appendChild(explanation.content.cloneNode(true));
                feedback.hidden = false;
                if (window.MathJax && window.MathJax.typesetPromise) window.MathJax.typesetPromise([feedback]);
            });
        });
    }
    assignConceptTable(); linkGlossaryTerms();
    initReaderSettings(); initTocTracking(); initProgress(); initResizableReader(); initPersonalMarks();
    wireStaticQuiz();
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


_QUIZ_LANGUAGE_LABEL_RE = re.compile(
    r"(?:中文|汉语|Chinese|法语|法文|Français|French|英语|英文|English|"
    r"西班牙语|西班牙文|Español|Spanish|德语|Deutsch|German|"
    r"意大利语|Italiano|Italian|日语|日本語|Japanese)\s*[:：]\s*",
    re.I,
)
_QUIZ_CJK_RE = re.compile(r"[\u3400-\u9fff]")
_QUIZ_LATIN_RE = re.compile(r"[A-Za-zÀ-ÖØ-öø-ÿ]")


def _split_quiz_languages(text: str):
    """识别测验中按语言标注或斜线分隔的双语内容。"""
    text = (text or "").strip()
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if len(lines) > 1:
        has_language_labels = any(_QUIZ_LANGUAGE_LABEL_RE.match(line) for line in lines)
        has_cjk_line = any(_QUIZ_CJK_RE.search(line) for line in lines)
        has_latin_only_line = any(
            _QUIZ_LATIN_RE.search(line) and not _QUIZ_CJK_RE.search(line) for line in lines
        )
        if has_language_labels or (has_cjk_line and has_latin_only_line):
            return lines
        text = " ".join(lines)

    labels = list(_QUIZ_LANGUAGE_LABEL_RE.finditer(text))
    if labels:
        segments = []
        if text[:labels[0].start()].strip():
            segments.append(text[:labels[0].start()].strip())
        for index, label in enumerate(labels):
            end = labels[index + 1].start() if index + 1 < len(labels) else len(text)
            segment = text[label.start():end].strip()
            if segment:
                segments.append(segment)
        if len(segments) > 1:
            return segments

    slash_segments = re.split(r"\s+[/／]\s+", text)
    if len(slash_segments) == 2:
        first, second = slash_segments
        if (
            (_QUIZ_CJK_RE.search(first) and _QUIZ_LATIN_RE.search(second))
            or (_QUIZ_LATIN_RE.search(first) and _QUIZ_CJK_RE.search(second))
        ):
            return [first.strip(), second.strip()]
    return [text]


def _render_quiz_text(text: str) -> str:
    """双语内容按语言拆成独立段落；单语内容沿用普通 Markdown 渲染。"""
    segments = _split_quiz_languages(text)
    if len(segments) == 1:
        return _render_body(segments[0])
    return '<div class="quiz-bilingual">' + _render_body("\n\n".join(segments)) + "</div>"


_QUIZ_TITLE_RE = re.compile(r"(?:章末测验|测验题|测验|quiz|qcm|évaluation|evaluation|test)", re.I)
_ANSWER_TITLE_RE = re.compile(r"(?:答案|解析|answer|correction|réponse|reponse)", re.I)
_DIFFICULTY_TITLES = (
    (re.compile(r"(?:基础|basic|easy|de base)", re.I), "basic"),
    (re.compile(r"(?:中档|intermediate|medium|intermédiaire|intermediaire)", re.I), "medium"),
    (re.compile(r"(?:高难|advanced|difficult|hard|difficile)", re.I), "advanced"),
)
_QUESTION_LINE_RE = re.compile(r"^\s*(\d+)\s*[.、)）]\s*(.+?)\s*$")
_OPTION_LINE_RE = re.compile(r"^\s*(?:[-*+]\s*)?([A-D])\s*[.)、．]\s*(.*?)\s*$", re.I)
_ANSWER_LINE_RE = re.compile(
    r"^\s*(?:[-*+]\s*)?(\d+)\s*[.、)）]\s*(?:\*\*)?([A-D])(?:\*\*)?"
    r"(?:\s*(?:[.、:：—–-]\s*|\s+)(.*?))?\s*$",
    re.I,
)


def _parse_quiz_question_lines(lines, start_number: int, level: str):
    questions = []
    current = None

    def finish():
        nonlocal current
        if current is None:
            return
        if not current["prompt"].strip():
            raise ValueError(f"测验第 {current['number']} 题缺少题干。")
        choices = current["choices"]
        if list(choices) != ["A", "B", "C", "D"]:
            found = "、".join(choices) if choices else "无选项"
            raise ValueError(
                f"测验第 {current['number']} 题选项必须按 A、B、C、D 各出现一次；当前为：{found}。"
            )
        if any(not value.strip() for value in choices.values()):
            raise ValueError(f"测验第 {current['number']} 题有空选项。")
        questions.append({
            "number": current["number"],
            "level": level,
            "prompt": current["prompt"].strip(),
            "choices": choices,
        })
        current = None

    for raw_line in lines:
        line = raw_line.strip()
        if not line:
            continue
        question_match = _QUESTION_LINE_RE.match(line)
        option_match = _OPTION_LINE_RE.match(line)
        if question_match:
            finish()
            number = int(question_match.group(1))
            expected = start_number + len(questions)
            if number != expected:
                raise ValueError(
                    f"测验题号应从 1 开始连续编号；此处应为第 {expected} 题，却写成第 {number} 题。"
                )
            current = {
                "number": number,
                "prompt": question_match.group(2).strip(),
                "choices": {},
            }
            continue
        if option_match:
            if current is None:
                raise ValueError("测验选项前没有对应题目，请检查 A、B、C、D 的位置。")
            letter = option_match.group(1).upper()
            if letter in current["choices"]:
                raise ValueError(f"测验第 {current['number']} 题重复出现 {letter} 选项。")
            current["choices"][letter] = option_match.group(2).strip()
            continue
        if current is None:
            raise ValueError("测验难度标题下出现无法识别的内容；题目请用连续编号，选项请各占一行。")
        if current["choices"]:
            last_letter = next(reversed(current["choices"]))
            current["choices"][last_letter] += "\n" + line
        else:
            current["prompt"] += "\n" + line

    finish()
    return questions


def _parse_quiz_answers(lines):
    answers = []
    for raw_line in lines:
        line = raw_line.strip()
        if not line:
            continue
        match = _ANSWER_LINE_RE.match(line)
        if match:
            answers.append({
                "number": int(match.group(1)),
                "letter": match.group(2).upper(),
                "explanation": (match.group(3) or "").strip(),
            })
        elif answers:
            answers[-1]["explanation"] += "\n" + line
        else:
            raise ValueError("答案区格式无法识别；每题请写成“题号. 正确选项 — 解析”。")
    return answers


def _build_quiz_html(md_content: str, required: bool = False):
    lines = md_content.splitlines()
    markers = [
        index for index, line in enumerate(lines)
        if re.fullmatch(r"\s*<!--\s*INTERACTIVE_QUIZ\s*-->\s*", line)
    ]
    if not markers:
        if required:
            raise ValueError("已要求生成交互测验，但 Markdown 中缺少 <!-- INTERACTIVE_QUIZ --> 标记。")
        return md_content, 0
    if len(markers) > 1:
        raise ValueError("发现多个交互测验标记；请将测验合并为一个章节。")

    start = markers[0]
    heading_index = start + 1
    while heading_index < len(lines) and not lines[heading_index].strip():
        heading_index += 1
    if (
        heading_index >= len(lines)
        or not re.match(r"^##\s+", lines[heading_index])
        or not _QUIZ_TITLE_RE.search(re.sub(r"^##\s+", "", lines[heading_index]))
    ):
        raise ValueError("交互测验标记后必须紧跟“## 章末测验”一级章节标题。")
    end = next(
        (index for index in range(heading_index + 1, len(lines)) if re.match(r"^##\s+", lines[index])),
        len(lines),
    )
    section = lines[heading_index:end]
    heading = re.sub(r"^##\s+", "", section[0]).strip()
    subsections = []
    for index, line in enumerate(section[1:], start=1):
        match = re.match(r"^###\s+(.+?)\s*#*\s*$", line)
        if match:
            subsections.append((index, match.group(1).strip()))

    answer_index = next(
        (index for index, (_, title) in enumerate(subsections) if _ANSWER_TITLE_RE.search(title)),
        None,
    )
    if answer_index is None:
        raise ValueError("测验章节缺少“答案与解析”小标题，无法保证每题都能交互判分。")

    questions = []
    for sub_index, (line_index, title) in enumerate(subsections[:answer_index]):
        level = next((value for pattern, value in _DIFFICULTY_TITLES if pattern.search(title)), None)
        if level is None:
            raise ValueError(f"无法识别测验难度标题“{title}”；请使用基础、中档或高难。")
        next_line_index = (
            subsections[sub_index + 1][0]
            if sub_index + 1 < len(subsections)
            else len(section)
        )
        level_questions = _parse_quiz_question_lines(
            section[line_index + 1:next_line_index],
            start_number=len(questions) + 1,
            level=level,
        )
        if not level_questions:
            raise ValueError(f"测验难度“{title}”下没有题目。")
        questions.extend(level_questions)

    answer_line_index = subsections[answer_index][0]
    answers = _parse_quiz_answers(section[answer_line_index + 1:])
    if not questions:
        raise ValueError("测验章节没有可识别的题目。")
    if len(answers) != len(questions):
        raise ValueError(
            f"测验题目与答案数量不一致：{len(questions)} 道题、{len(answers)} 条答案。"
        )
    for expected, (question, answer) in enumerate(zip(questions, answers), start=1):
        if answer["number"] != expected:
            raise ValueError(f"答案区题号应为 {expected}，当前为 {answer['number']}。")
        if answer["letter"] not in question["choices"]:
            raise ValueError(f"第 {expected} 题答案必须是 A、B、C、D 之一。")
        if not answer["explanation"]:
            raise ValueError(f"测验第 {expected} 题缺少解析。")

    chunks = [_render_body("## " + heading), '<p class="quiz-instructions">每题选择后单独提交；提交后显示正确答案与解析。</p>']
    question_index = 0
    for sub_index, (line_index, title) in enumerate(subsections[:answer_index]):
        next_line_index = (
            subsections[sub_index + 1][0]
            if sub_index + 1 < len(subsections)
            else len(section)
        )
        chunk_questions = _parse_quiz_question_lines(
            section[line_index + 1:next_line_index],
            start_number=question_index + 1,
            level=questions[question_index]["level"] if question_index < len(questions) else "basic",
        )
        chunks.append(_render_body("### " + title))
        for question in chunk_questions:
            answer = answers[question_index]
            chunks.append(
                '<section class="quiz-question" data-level="' + question["level"] +
                '" data-answer="' + answer["letter"] + '">'
                '<div class="quiz-prompt">' + _render_quiz_text(question["prompt"]) + '</div>'
                '<fieldset class="quiz-options" aria-label="选择答案">'
                '<legend class="quiz-options-legend">请选择一个答案</legend>'
            )
            for letter, choice in question["choices"].items():
                chunks.append(
                    '<label class="quiz-option"><input type="radio" value="' + letter + '">'
                    '<span class="quiz-option-letter">' + letter + '.</span>'
                '<div class="quiz-option-text">' + _render_quiz_text(choice) + '</div></label>'
                )
            chunks.append(
                '</fieldset><button type="button" class="quiz-submit">提交答案</button>'
                '<div class="quiz-feedback" role="status" aria-live="polite" hidden></div>'
                '<template class="quiz-explanation">' + _render_quiz_text(answer["explanation"]) + '</template>'
                '</section>'
            )
            question_index += 1

    replacement = "\n\n" + "\n\n".join(chunks) + "\n\n"
    return "\n".join(lines[:start]) + replacement + "\n".join(lines[end:]), len(questions)


def _heading_label_text(content: str) -> str:
    content = re.sub(
        r"<span\b(?=[^>]*\bclass\s*=\s*([\"'])[^\"']*\b(?:source-title|heading-source)\b[^\"']*\1)[^>]*>.*?</span\s*>",
        " ",
        content,
        flags=re.I | re.S,
    )
    label = re.sub(r"<[^>]+>", " ", content)
    return unescape(re.sub(r"\s+", " ", label)).strip()


def _add_heading_ids_and_toc(body_html: str):
    heading_re = re.compile(
        r"<h([1-4])\b([^>]*)>(.*?)</h\1\s*>",
        re.I | re.S,
    )
    used_ids = set()
    toc_items = []
    heading_index = 0

    def add_id(match):
        nonlocal heading_index
        level, attributes, content = match.groups()
        id_match = re.search(r'\bid\s*=\s*(["\'])(.*?)\1', attributes, re.I | re.S)
        base_id = id_match.group(2) if id_match else "lesson-heading-" + str(heading_index + 1)
        candidate = base_id
        suffix = 2
        while candidate in used_ids:
            candidate = base_id + "-" + str(suffix)
            suffix += 1
        used_ids.add(candidate)
        escaped_id = escape(candidate, quote=True)
        if id_match:
            attributes = attributes[:id_match.start()] + ' id="' + escaped_id + '"' + attributes[id_match.end():]
        else:
            attributes += ' id="' + escaped_id + '"'
        label = _heading_label_text(content)
        if label:
            toc_items.append(
                '<li class="toc-item toc-level-' + level + '"><a href="#' + escaped_id + '">' +
                escape(label) + '</a></li>'
            )
        heading_index += 1
        return "<h" + level + attributes + ">" + content + "</h" + level + ">"

    updated = heading_re.sub(add_id, body_html)
    toc_html = (
        '<ul class="toc-list" role="list" aria-label="本学案知识大纲">'
        + "".join(toc_items) + "</ul>"
    )
    return updated, toc_html, len(toc_items)


def _add_document_title_class(body_html: str, layout: str):
    heading_re = re.compile(r"<h1\b([^>]*)>(.*?)</h1\s*>", re.I | re.S)
    match = heading_re.search(body_html)
    if not match:
        raise ValueError("HTML 质量门禁未通过：译文必须有一个一级标题。")
    attributes, content = match.groups()
    if layout == "concept_highlight":
        source_title = re.search(
            r"<span\b[^>]*class\s*=\s*([\"'])[^\"']*\bsource-title\b[^\"']*\1",
            content,
            re.I,
        )
        if not source_title:
            raise ValueError(
                "concept_highlight 标题格式不符合要求：一级标题中需要包含 "
                '<span class=\"source-title\">原文标题</span>。'
            )
    class_match = re.search(r'\bclass\s*=\s*(["\'])(.*?)\1', attributes, re.I | re.S)
    if class_match:
        classes = class_match.group(2).split()
        if "document-title" not in classes:
            classes.append("document-title")
        attributes = attributes[:class_match.start(2)] + " ".join(classes) + attributes[class_match.end(2):]
    else:
        attributes += ' class="document-title"'
    replacement = "<h1" + attributes + ">" + content + "</h1>"
    return body_html[:match.start()] + replacement + body_html[match.end():]


def _looks_like_course_header(content: str) -> bool:
    """识别由学年和课程编号组成的课程页眉，避免它占用学案标题层级。"""
    visible = unescape(re.sub(r"<[^>]+>", " ", content))
    has_course_code = re.search(r"\b[A-Z]{2,}-?\d{3,}[A-Z]?\b", visible, re.I)
    has_academic_year = re.search(
        r"\b(?:19|20)\d{2}\s*[-–—]\s*(?:19|20)\d{2}\b", visible
    )
    has_header_separator = re.search(r"[|｜•·]", visible)
    has_institution_marker = re.search(r"\bSPEIT\b|\bcourse\b|课程|学年", visible, re.I)
    return bool(has_course_code and (has_academic_year or has_header_separator or has_institution_marker))


def _ensure_class(attributes: str, class_name: str) -> str:
    class_match = re.search(r'\bclass\s*=\s*(["\'])(.*?)\1', attributes, re.I | re.S)
    if class_match:
        classes = class_match.group(2).split()
        if class_name not in classes:
            classes.append(class_name)
        return attributes[:class_match.start(2)] + " ".join(classes) + attributes[class_match.end(2):]
    return attributes + ' class="' + class_name + '"'


def _normalize_course_header(body_html: str) -> str:
    """把误作 H1 的课程元信息移入页眉，并将其后的首个 H2 提升为学案标题。"""
    first_h1 = re.search(r"<h1\b([^>]*)>(.*?)</h1\s*>", body_html, re.I | re.S)
    if not first_h1 or not _looks_like_course_header(first_h1.group(2)):
        return body_html

    header_html = '<p class="course-header">' + first_h1.group(2) + "</p>"
    body_html = body_html[:first_h1.start()] + header_html + body_html[first_h1.end():]
    first_h2 = re.search(r"<h2\b([^>]*)>(.*?)</h2\s*>", body_html[first_h1.start() + len(header_html):], re.I | re.S)
    if not first_h2:
        raise ValueError(
            "HTML 质量门禁未通过：检测到课程信息页眉，但其后没有学案主题标题。"
        )

    attributes, content = first_h2.groups()
    span_re = re.compile(r"<span\b([^>]*)>(.*?)</span\s*>", re.I | re.S)

    def mark_source_title(match):
        span_attributes, span_content = match.groups()
        class_match = re.search(r'\bclass\s*=\s*(["\'])(.*?)\1', span_attributes, re.I | re.S)
        if not class_match or "heading-source" not in class_match.group(2).split():
            return match.group(0)
        span_attributes = _ensure_class(span_attributes, "source-title")
        return "<span" + span_attributes + ">" + span_content + "</span>"

    content = span_re.sub(mark_source_title, content)
    attributes = _ensure_class(attributes, "document-title")
    start = first_h1.start() + len(header_html) + first_h2.start()
    end = first_h1.start() + len(header_html) + first_h2.end()
    lesson_title = "<h1" + attributes + ">" + content + "</h1>"
    return body_html[:start] + lesson_title + body_html[end:]


def _has_redundant_summary_prefix(content: str) -> bool:
    """识别标题中可省略的章节类型前缀，保留真正的知识主题。"""
    source_spans = []
    for match in re.finditer(r"<span\b([^>]*)>(.*?)</span\s*>", content, re.I | re.S):
        class_match = re.search(r'\bclass\s*=\s*(["\'])(.*?)\1', match.group(1), re.I | re.S)
        if class_match and re.search(r"\b(?:source-title|heading-source)\b", class_match.group(2), re.I):
            source_spans.append(unescape(re.sub(r"<[^>]+>", " ", match.group(2))).strip())

    translated = re.sub(
        r"<span\b(?=[^>]*\bclass\s*=\s*([\"'])[^\"']*\b(?:source-title|heading-source)\b[^\"']*\1)[^>]*>.*?</span\s*>",
        " ",
        content,
        flags=re.I | re.S,
    )
    translated = unescape(re.sub(r"<[^>]+>", " ", translated))
    candidates = [re.sub(r"\s+", " ", translated).strip()] + source_spans
    prefix_patterns = (
        r"^第[0-9零一二三四五六七八九十百]+章\s*(?:总结|小结|概要|摘要)\s*[:：—–-]\s*\S",
        r"^本章(?:总结|小结|概要|摘要)\s*[:：—–-]\s*\S",
        r"^(?:Résumé|Bilan)\s+du\s+chapitre\s+\d+\s*[—–:-]\s*\S",
        r"^Chapter\s+\d+\s+(?:summary|review|recap)\s*[:—–-]\s*\S",
    )
    return any(
        re.search(pattern, candidate, re.I)
        for pattern in prefix_patterns
        for candidate in candidates
    )


def _build_file_outline(output_path: Path) -> str:
    """生成 VS Code Explorer 风格的 output HTML 文件树，目录默认展开。"""
    output_path = Path(output_path)
    current_path = output_path.resolve()
    output_root = next(
        (parent for parent in output_path.parents if parent.name.casefold() == "output"),
        None,
    )
    root_resolved = output_root.resolve() if output_root else None
    entries = {}
    if output_root and output_root.is_dir():
        for path in output_root.rglob("*.html"):
            try:
                resolved = path.resolve()
                relative = resolved.relative_to(root_resolved)
            except (ValueError, OSError):
                continue
            if path.is_file():
                entries[resolved] = (relative, path)
    if root_resolved:
        try:
            relative_current = current_path.relative_to(root_resolved)
            entries.setdefault(current_path, (relative_current, output_path))
        except ValueError:
            pass
    if not entries:
        entries[current_path] = (Path(output_path.name), output_path)

    tree = {"directories": {}, "files": []}
    for resolved, (relative, display_path) in entries.items():
        parts = relative.parts
        node = tree
        for folder in parts[:-1]:
            node = node["directories"].setdefault(
                folder, {"directories": {}, "files": []}
            )
        node["files"].append((parts[-1], resolved, display_path, relative))

    def render_tree(node):
        pieces = ['<ul class="file-tree-group" role="group">']
        for folder in sorted(node["directories"], key=str.casefold):
            child = node["directories"][folder]
            pieces.append(
                '<li class="file-tree-folder"><details open>'
                '<summary><span class="file-tree-chevron" aria-hidden="true"><i class="fa-solid fa-angle-down"></i></span>'
                '<span class="file-tree-icon folder-icon" aria-hidden="true">'
                '<i class="fa-solid fa-folder-open folder-open-icon"></i>'
                '<i class="fa-solid fa-folder folder-closed-icon"></i></span>'
                '<span class="file-tree-name">' + escape(folder) + '</span></summary>'
                + render_tree(child) + '</details></li>'
            )
        for name, resolved, display_path, relative in sorted(
            node["files"], key=lambda item: item[0].casefold()
        ):
            try:
                href_path = relpath(resolved, current_path.parent).replace("\\", "/")
            except ValueError:
                href_path = display_path.name
            href = quote(href_path, safe="/")
            current = resolved == current_path
            current_class = " current" if current else ""
            current_attr = ' aria-current="page"' if current else ""
            title = "output/" + relative.as_posix() if root_resolved else display_path.name
            pieces.append(
                '<li class="file-tree-file' + current_class + '">'
                '<a role="treeitem" href="' + escape(href, quote=True) + '" title="' +
                escape(title, quote=True) + '"' + current_attr + '>'
                '<span class="file-tree-indent" aria-hidden="true"></span>'
                '<span class="file-tree-icon html-icon" aria-hidden="true"><i class="fa-solid fa-file-code"></i></span>'
                '<span class="file-tree-name">' + escape(name) + '</span></a></li>'
            )
        pieces.append("</ul>")
        return "".join(pieces)

    root_label = output_root.name if output_root else "当前文件"
    return (
        '<div class="file-tree" role="tree" aria-label="学案文件路径">'
        '<details class="file-tree-root-folder" open>'
        '<summary class="file-tree-root"><span class="file-tree-chevron" aria-hidden="true">'
        '<i class="fa-solid fa-angle-down"></i></span>'
        '<span class="file-tree-icon folder-icon" aria-hidden="true">'
        '<i class="fa-solid fa-folder-open folder-open-icon"></i>'
        '<i class="fa-solid fa-folder folder-closed-icon"></i></span>'
        '<span class="file-tree-name">' + escape(root_label) + '</span></summary>'
        + render_tree(tree) + "</details></div>"
    )


def build_html(
    md_content: str,
    output_path: Path,
    show_concept_table: bool = True,
    layout: str = "translation_only",
    require_interactive_quiz: bool = False,
    final_output_path: Path | None = None,
) -> Path:
    """生成带静态双侧导航、可交互测验、阅读进度和水印的 HTML 页面。"""
    allowed_layouts = {"translation_only", "translation_first", "source_first", "concept_highlight"}
    if layout not in allowed_layouts:
        raise ValueError("不支持的 HTML 展示布局：" + str(layout))
    protected_md, maths = protect_math(md_content)
    prepared_md, expected_quiz_count = _build_quiz_html(
        protected_md,
        required=require_interactive_quiz,
    )
    body_html = annotate_first_occurrences(_render_body(style_source_markers(prepared_md, "html")))
    body_html = restore_math(body_html, maths)
    body_html = _normalize_course_header(body_html)
    body_html = _add_document_title_class(body_html, layout)
    body_html, toc_html, toc_count = _add_heading_ids_and_toc(body_html)
    validate_rendered_text(body_html, "HTML")

    heading_count = len(re.findall(r"<h[1-4]\b", body_html, re.I))
    if heading_count == 0 or toc_count != heading_count:
        raise ValueError(
            f"HTML 质量门禁未通过：发现 {heading_count} 个标题，但右侧知识大纲只有 {toc_count} 项。"
        )
    first_h1 = re.search(r"<h1\b([^>]*)>(.*?)</h1\s*>", body_html, re.I | re.S)
    if first_h1 and _has_redundant_summary_prefix(first_h1.group(2)):
        raise ValueError(
            "HTML 质量门禁未通过：学案主标题含有‘第 X 章总结 / Résumé du chapitre’等结构前缀；"
            "请只保留具体知识主题。"
        )
    if layout == "concept_highlight" and first_h1:
        if not re.search(r"class=[\"'][^\"']*\bcourse-header\b", body_html, re.I):
            first_h1_content = unescape(re.sub(r"<[^>]+>", " ", first_h1.group(2))).strip()
            if _looks_like_course_header(first_h1_content):
                raise ValueError(
                    "HTML 质量门禁未通过：课程代码或学年信息误占学案主标题，请移入 course-header 页眉。"
                )
    if show_concept_table and re.search(r"<span\b[^>]*\bdata-en\s*=", body_html, re.I):
        has_table_heading = re.search(r"(?:重要术语概念汇总表|概念汇总表)", body_html)
        if not has_table_heading or not re.search(r"<table\b", body_html, re.I):
            raise ValueError("HTML 质量门禁未通过：已标注术语，但缺少概念表标题或表格。")
    quiz_cards = re.findall(
        r'<section\b(?=[^>]*class=["\'][^"\']*\bquiz-question\b)(.*?)</section\s*>',
        body_html,
        re.I | re.S,
    )
    if len(quiz_cards) != expected_quiz_count:
        raise ValueError(
            f"HTML 质量门禁未通过：测验源文有 {expected_quiz_count} 题，"
            f"交互卡片只有 {len(quiz_cards)} 题。"
        )
    for index, card in enumerate(quiz_cards, start=1):
        option_count = len(re.findall(r'<label\b[^>]*class=["\']quiz-option["\']', card, re.I))
        radio_values = re.findall(
            r'<input\b[^>]*type=["\']radio["\'][^>]*value=["\']([A-D])["\']',
            card,
            re.I,
        )
        submit_count = len(re.findall(r'class=["\'][^"\']*\bquiz-submit\b', card, re.I))
        explanation_count = len(re.findall(r"<template\b[^>]*class=", card, re.I))
        answer_match = re.search(r'data-answer=["\']([A-D])["\']', card, re.I)
        if (
            option_count != 4
            or sorted(letter.upper() for letter in radio_values) != ["A", "B", "C", "D"]
            or submit_count != 1
            or explanation_count != 1
            or not answer_match
            or answer_match.group(1).upper() not in radio_values
        ):
            raise ValueError(
                f"HTML 质量门禁未通过：第 {index} 道测验卡片必须含 A-D 四个单选项、"
                "一个提交按钮、正确答案和解析模板。"
            )

    css = load_css()
    title_match = re.search(r"<h1\b[^>]*>(.*?)</h1>", body_html, re.I | re.S)
    page_title = _heading_label_text(title_match.group(1)) if title_match else "学案译文"

    js = _BUILD_JS.replace(
        "__SHOW_CONCEPT_TABLE__", "true" if show_concept_table else "false"
    )
    if (
        "addWatermarkOnCopy" in js
        or 'addEventListener("copy"' in js
        or "clipboardData.setData" in js
    ):
        raise ValueError("HTML 质量门禁未通过：复制文本不得自动追加署名水印。")

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    file_outline_html = _build_file_outline(final_output_path or output_path)
    if (
        'class="file-tree-root-folder" open' not in file_outline_html
        or "fa-angle-down" not in file_outline_html
        or "fa-folder-open" not in file_outline_html
        or "fa-file-code" not in file_outline_html
    ):
        raise ValueError("HTML 质量门禁未通过：左侧文件树必须可折叠且使用 Font Awesome 图标。")
    if "function initTocTracking()" not in js or 'classList.toggle("is-active"' not in js:
        raise ValueError("HTML 质量门禁未通过：右侧知识大纲缺少阅读位置跟踪。")

    layout_css = (
        "html { --outline-width: clamp(190px, 17vw, 250px); }\n"
        "html, body { height: 100%; margin: 0; padding: 0; }\n"
        "html { scroll-behavior: smooth; }\n"
        "body { max-width: none; min-height: 100vh; margin: 0; padding: 0; background: var(--page-bg); color: var(--text); box-shadow: none; border-radius: 0; }\n"
        ".content-area { width: min(var(--reader-width, 10000px), calc(100vw - var(--outline-width) - var(--outline-width))); max-width: none; box-sizing: border-box; margin: 16px auto; padding: 24px 46px 96px; background: var(--surface-bg); border-radius: 0; box-shadow: none; font-size: 18px; line-height: 1.85; }\n"
        "table { border-collapse: collapse; width: 100%; margin: 20px 0; }\n"
        "th, td { border: 1px solid #d8e0e8; padding: 8px 12px; }\n"
        "img { max-width: 100%; height: auto; display: block; margin: 15px 0; }\n"
        "span[data-en] { background: transparent; padding: 0; border-radius: 0; font-weight: 750; "
        "color: var(--accent-strong); text-decoration: underline dotted; text-underline-offset: 3px; cursor: help; }\n"
        "/* 左侧文件树与右侧学案大纲固定常开 */\n"
        "#file-outline, #toc-outline { position: fixed !important; top: 0 !important; bottom: 0 !important; z-index: 1000; "
        "width: var(--outline-width) !important; height: 100vh; height: 100dvh; max-height: none; overflow: auto; margin: 0 !important; "
        "transform: none !important; display: block !important; box-sizing: border-box; "
        "padding: 10px 0; color: var(--text); background: var(--surface-bg); border: 1px solid var(--border); "
        "border-radius: 0; box-shadow: none; font: 13px/1.55 'Segoe UI','Roboto',Arial,sans-serif; }\n"
        "#file-outline { left: 0 !important; border-left: 0; }\n"
        "#toc-outline { right: 0 !important; padding: 12px 8px; border-right: 0; }\n"
        ".toc-header { position: sticky; top: 0; z-index: 2; padding: 0 12px 9px; margin-bottom: 6px; "
        "border-bottom: 1px solid var(--border); background: var(--surface-bg); "
        "font-weight: 700; color: var(--accent-strong); font-size: 13px; }\n"
        ".toc-list, .file-tree-group { list-style: none; margin: 0; padding: 0; }\n"
        ".toc-item a { display: block; padding: 4px 9px; border-left: 2px solid transparent; border-radius: 3px; "
        "color: var(--text); text-decoration: none; overflow-wrap: anywhere; }\n"
        ".toc-item a:hover { color: var(--accent-strong); background: var(--accent-soft); border-left-color: var(--accent); }\n"
        ".toc-item a.is-active { color: var(--accent-strong); background: var(--accent-soft); "
        "border-left-color: var(--accent); font-weight: 700; }\n"
        ".toc-level-2 a { padding-left: 18px; }\n"
        ".toc-level-3 a { padding-left: 30px; font-size: 12px; }\n"
        ".toc-level-4 a { padding-left: 42px; font-size: 12px; }\n"
        ".file-tree { user-select: none; }\n"
        ".file-tree-root, .file-tree-folder summary, .file-tree-file a { min-height: 24px; display: flex; "
        "align-items: center; gap: 6px; box-sizing: border-box; padding: 2px 9px; color: var(--text); "
        "text-decoration: none; white-space: nowrap; }\n"
        ".file-tree-root, .file-tree-folder summary { cursor: pointer; list-style: none; }\n"
        ".file-tree-root::-webkit-details-marker, .file-tree-folder summary::-webkit-details-marker { display: none; }\n"
        ".file-tree-root { padding-left: 11px; font-weight: 700; }\n"
        ".file-tree-root:hover, .file-tree-folder summary:hover, .file-tree-file a:hover { background: var(--accent-soft); }\n"
        ".file-tree-chevron { width: 12px; flex: 0 0 12px; color: var(--muted); text-align: center; }\n"
        ".file-tree-chevron i { display: block; font-size: 11px; transition: transform .16s ease; }\n"
        ".file-tree-folder details:not([open]) > summary .file-tree-chevron i, "
        ".file-tree-root-folder:not([open]) > .file-tree-root .file-tree-chevron i { transform: rotate(-90deg); }\n"
        ".file-tree-icon { width: 16px; flex: 0 0 16px; font-size: 13px; text-align: center; }\n"
        ".folder-icon { color: #d8ad45; } .html-icon { color: #4c9bd6; }\n"
        ".folder-open-icon { display: none; } .folder-closed-icon { display: inline-block; }\n"
        ".file-tree-folder details[open] > summary .folder-open-icon, "
        ".file-tree-root-folder[open] > .file-tree-root .folder-open-icon { display: inline-block; }\n"
        ".file-tree-folder details[open] > summary .folder-closed-icon, "
        ".file-tree-root-folder[open] > .file-tree-root .folder-closed-icon { display: none; }\n"
        ".file-tree-name { overflow: hidden; text-overflow: ellipsis; }\n"
        ".file-tree-group { padding-left: 15px; }\n"
        ".file-tree-file a { padding-left: 25px; }\n"
        ".file-tree-file.current a { color: var(--accent-strong); background: var(--accent-soft); font-weight: 650; }\n"
        ".file-tree-file.current .html-icon { filter: saturate(1.25); }\n"
        ".file-tree-indent { width: 4px; flex: 0 0 4px; }\n"
        ".content-area p.course-header { margin: 0 0 24px !important; text-align: center !important; "
        "color: var(--muted) !important; font-size: 1.05em; font-weight: 650; line-height: 1.45; }\n"
        ".content-area p.course-header .source-title { display: inline !important; width: auto !important; "
        "margin: 0 0 0 .55em !important; color: var(--muted) !important; font-size: .82em !important; "
        "font-weight: 400 !important; }\n"
        ".content-area h1.document-title { text-align: center !important; font-size: 2.25em; line-height: 1.28; "
        "margin: 18px auto 30px !important; padding: 0 0 16px !important; border-left: 0 !important; "
        "border-bottom: 4px solid var(--accent) !important; background: transparent !important; box-shadow: none !important; }\n"
        ".content-area h1.document-title .source-title { display: block !important; width: 100%; margin-top: .35em; "
        "text-align: center !important; color: var(--muted) !important; font-size: .42em !important; "
        "font-weight: 500 !important; line-height: 1.45; letter-spacing: 0; }\n"
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
        "@media (max-width: 1280px) { body { display: grid; grid-template-columns: minmax(0,1fr) minmax(0,1fr); "
        "grid-template-areas: 'left right' 'content content'; align-items: start; gap: 14px; padding: 14px; box-sizing: border-box; } "
        "#file-outline, #toc-outline { position: static !important; top: auto !important; left: auto !important; right: auto !important; "
        "bottom: auto !important; transform: none !important; width: 100% !important; height: auto !important; max-height: 30vh; "
        "border: 1px solid var(--border); border-radius: 8px; } #file-outline { grid-area: left; } "
        "#toc-outline { grid-area: right; } .content-area { grid-area: content; width: min(var(--reader-width,1830px),100%); margin: 0 auto; } }\n"
        "@media (max-width: 700px) { body { display: flex; flex-direction: column; align-items: stretch; gap: 10px; padding: 10px; } "
        "#file-outline, #toc-outline { width: 100% !important; height: auto !important; max-height: 24vh; } #file-outline { order: 1; } "
        "#toc-outline { order: 2; } .content-area { order: 3; width: 100%; margin: 0; padding: 36px 22px 80px; } }\n"
    )

    layout_css += """
.content-area span[data-en], .content-area a.term-link, .content-area .heading-term-link {
  color: var(--accent-strong) !important;
}
.content-area h2 .heading-source, .content-area h3 .heading-source,
.content-area h4 .heading-source { color: var(--accent-strong) !important; }
.content-area .document-title { text-align: center !important; }
.content-area .document-title .source-title {
  display: block !important; width: 100%; text-align: center !important;
}
.content-area p.course-header { overflow-wrap: anywhere; }
@media (max-width: 700px) {
  .content-area h1.document-title { font-size: 1.7em !important; }
}
.content-area mjx-container[display="true"] {
  display: block !important; width: fit-content; max-width: calc(100% - 24px) !important;
  box-sizing: border-box; margin: 1.25em auto !important; padding: 12px 18px !important;
  overflow-x: auto; overflow-y: hidden; border: 0 !important; border-left: 0 !important;
  background: var(--formula-bg); border-radius: 8px; text-align: center !important;
}
.content-area .note {
  color: #59431b !important; background: #fff5df !important; border-left-color: #c5842a !important;
}
.content-area .note::before { color: #925f16 !important; background: #f8e6bd !important; }
html[data-theme="dark"] .content-area .note {
  color: #f0dfb6 !important; background: #332d20 !important; border-left-color: #d9a64f !important;
}
html[data-theme="dark"] .content-area .note::before { color: #ffdda0 !important; background: #4a3c22 !important; }
@media (prefers-color-scheme: dark) {
  html[data-theme="system"] .content-area .note {
    color: #f0dfb6 !important; background: #332d20 !important; border-left-color: #d9a64f !important;
  }
  html[data-theme="system"] .content-area .note::before { color: #ffdda0 !important; background: #4a3c22 !important; }
}
.reader-control-button.icon-control {
  width: 44px; height: 44px; padding: 0; display: grid; place-items: center; font-size: 19px;
}
.reader-resize-handle {
  position: fixed; z-index: 1050; width: 12px; height: 128px; border-radius: 999px;
  cursor: ew-resize; touch-action: none; background: transparent; transition: background .16s ease, box-shadow .16s ease;
}
.reader-resize-handle::after {
  content: ""; position: absolute; left: 5px; top: 8px; bottom: 8px; width: 2px;
  border-radius: 2px; background: var(--accent); opacity: .3; transition: opacity .16s ease, width .16s ease;
}
.reader-resize-handle:hover::after, .reader-resize-handle:focus-visible::after,
.reader-resize-handle.dragging::after { left: 4px; width: 4px; opacity: 1; }
.reader-resize-handle:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
.reader-resize-handle[hidden] { display: none; }
.reader-toast {
  position: fixed; z-index: 1300; right: 18px; bottom: 64px; max-width: min(380px, calc(100vw - 36px));
  padding: 10px 14px; border: 1px solid #d6a1a0; border-radius: 10px; color: #602c2b;
  background: #fff1ef; box-shadow: 0 6px 22px rgba(42, 25, 25, .18);
  opacity: 0; transform: translateY(6px); pointer-events: none; transition: opacity .18s ease, transform .18s ease;
}
.reader-toast.visible { opacity: 1; transform: translateY(0); }
.annotation-popover {
  position: fixed; z-index: 1250; box-sizing: border-box; max-width: calc(100vw - 24px);
  padding: 14px 16px; border: 1px solid #d9b978; border-left: 4px solid #c5842a;
  border-radius: 10px; color: #59431b; background: #fff8e9; box-shadow: 0 8px 26px rgba(60, 45, 20, .2);
}
.annotation-popover[hidden] { display: none; }
.annotation-title { display: block; margin-bottom: 7px; color: #80530e; }
.annotation-text { margin: 0 0 12px !important; white-space: pre-wrap; overflow-wrap: anywhere; text-align: left !important; }
.annotation-actions { display: flex; flex-wrap: wrap; gap: 6px; justify-content: flex-end; }
.annotation-action {
  border: 1px solid #dfc993; border-radius: 7px; padding: 6px 10px; color: #59431b;
  background: #fffdf7; cursor: pointer; font: 600 13px/1.2 'Segoe UI', Arial, sans-serif;
}
.annotation-action:hover { background: #f8e6bd; }
html[data-theme="dark"] .annotation-popover {
  color: #f0dfb6; background: #332d20; border-color: #8a7040; border-left-color: #d9a64f;
}
html[data-theme="dark"] .annotation-title { color: #ffdda0; }
html[data-theme="dark"] .annotation-action { color: #f0dfb6; background: #403720; border-color: #76633a; }
.selection-toolbar { gap: 6px; padding: 7px; border-color: var(--accent); }
.selection-action { color: var(--accent-strong); background: var(--accent-soft); font-weight: 700; }
.selection-action:hover { color: #fff; background: var(--accent-strong); }
@media (prefers-color-scheme: dark) {
  html[data-theme="system"] .annotation-popover { color: #f0dfb6; background: #332d20; border-color: #8a7040; border-left-color: #d9a64f; }
  html[data-theme="system"] .annotation-title { color: #ffdda0; }
  html[data-theme="system"] .annotation-action { color: #f0dfb6; background: #403720; border-color: #76633a; }
}
.content-area mark.user-highlight {
  background: #ffe28a !important; color: #382900 !important; border-radius: 3px; cursor: pointer;
  box-shadow: 0 0 0 2px #b66a00; font-weight: 700;
}
.content-area mark.user-highlight[data-note] { text-decoration: underline dotted #8d4e00; text-underline-offset: 3px; }
.content-area mjx-container.user-highlight {
  background: #ffe28a !important; color: #382900 !important; outline: 2px solid #b66a00 !important;
  outline-offset: 2px; border-radius: 6px; box-shadow: 0 0 0 4px rgba(182, 106, 0, .18); cursor: pointer;
}
.content-area mjx-container.user-highlight[data-note] { outline-style: dashed !important; }
html[data-theme="dark"] .content-area mark.user-highlight {
  background: #75520a !important; color: #fff4ca !important; box-shadow: 0 0 0 2px #ffc857;
}
html[data-theme="dark"] .content-area mark.user-highlight[data-note] { text-decoration-color: #ffd978; }
html[data-theme="dark"] .content-area mjx-container.user-highlight {
  background: #75520a !important; color: #fff4ca !important; outline-color: #ffc857 !important;
  box-shadow: 0 0 0 4px rgba(255, 200, 87, .2);
}
html[data-theme="dark"] .content-area mjx-container.user-highlight[data-note] { outline-color: #ffd978 !important; }
@media (prefers-color-scheme: dark) {
  html[data-theme="system"] .content-area mark.user-highlight {
    background: #75520a !important; color: #fff4ca !important; box-shadow: 0 0 0 2px #ffc857;
  }
  html[data-theme="system"] .content-area mark.user-highlight[data-note] { text-decoration-color: #ffd978; }
  html[data-theme="system"] .content-area mjx-container.user-highlight {
    background: #75520a !important; color: #fff4ca !important; outline-color: #ffc857 !important;
    box-shadow: 0 0 0 4px rgba(255, 200, 87, .2);
  }
  html[data-theme="system"] .content-area mjx-container.user-highlight[data-note] { outline-color: #ffd978 !important; }
}
.content-area .quiz-instructions { margin: .75em 0 1em; color: var(--muted); font-size: .9em; }
.content-area .quiz-question {
  margin: 16px 0 22px; padding: 18px 20px; border: 1px solid var(--border);
  border-radius: 10px; background: var(--surface-soft);
}
.content-area .quiz-question > p:first-child { margin-top: 0; }
.content-area .quiz-options { display: grid; gap: 8px; margin: 12px 0; padding: 0; border: 0; }
.content-area .quiz-option {
  display: flex; align-items: flex-start; gap: 9px; padding: 9px 11px;
  border: 1px solid var(--border); border-radius: 8px; background: var(--surface-bg); cursor: pointer;
}
.content-area .quiz-option:hover { border-color: var(--accent); background: var(--accent-soft); }
.content-area .quiz-options-legend { margin-bottom: 3px; color: var(--muted); font-size: 13px; }
.content-area .quiz-option-text { min-width: 0; flex: 1; }
.content-area .quiz-option-text p { margin: 0 !important; text-align: left !important; }
.content-area .quiz-bilingual > p { margin: 0 !important; text-align: left !important; }
.content-area .quiz-bilingual > p + p { margin-top: .18em !important; }
.content-area .quiz-option input { flex: 0 0 auto; margin: 0 1px 0 0; accent-color: var(--accent-strong); }
.content-area .quiz-option input[type="radio"] {
  appearance: none; -webkit-appearance: none; box-sizing: border-box; width: 19px; height: 19px;
  min-width: 19px; flex: 0 0 19px; align-self: center; margin: 0 1px 0 0; display: grid; place-content: center;
  border: 2px solid var(--accent); border-radius: 50%; background: var(--surface-bg); cursor: pointer;
  transition: border-color .16s ease, box-shadow .16s ease, background .16s ease;
}
.content-area .quiz-option input[type="radio"]::before {
  content: ""; width: 9px; height: 9px; border-radius: 50%; background: var(--accent-strong);
  transform: scale(0); transition: transform .14s ease;
}
.content-area .quiz-option input[type="radio"]:checked { border-color: var(--accent-strong); }
.content-area .quiz-option input[type="radio"]:checked::before { transform: scale(1); }
.content-area .quiz-option input[type="radio"]:hover { border-color: var(--accent-strong); box-shadow: 0 0 0 3px var(--accent-soft); }
.content-area .quiz-option input[type="radio"]:focus-visible { outline: 3px solid var(--accent-soft); outline-offset: 2px; }
.content-area .quiz-option input[type="radio"]:disabled { cursor: default; opacity: .72; }
.content-area .quiz-option:has(input[type="radio"]:checked) { border-color: var(--accent); background: var(--accent-soft); }
.content-area .quiz-submit {
  border: 0; border-radius: 8px; padding: 9px 15px; color: #fff;
  background: var(--accent-strong); cursor: pointer; font: 650 14px/1.2 'Segoe UI', Arial, sans-serif;
}
.content-area .quiz-submit:hover { background: var(--accent); }
.content-area .quiz-submit:disabled { opacity: .65; cursor: default; }
.content-area .quiz-feedback { margin: 12px 0 0 !important; padding: 10px 12px; border-radius: 7px; text-align: left !important; }
.content-area .quiz-feedback[hidden] { display: none; }
.content-area .quiz-feedback.correct { color: #205b3a; background: #e8f5ec; border-left: 4px solid #438b5f; }
.content-area .quiz-feedback.incorrect { color: #75403a; background: #fff0ed; border-left: 4px solid #c86d5d; }
@media (max-width: 700px) {
  .reader-resize-handle { display: none; }
  .content-area .quiz-question { padding: 14px; }
}
@media print {
  #reader-resize-handle, #reader-toast, .annotation-popover { display: none !important; }
  .content-area .quiz-submit { display: none !important; }
  .content-area .quiz-feedback[hidden] { display: none !important; }
}
#reader-controls { right: calc(var(--outline-width) + 16px) !important; }
#reading-progress, .reader-toast { right: calc(var(--outline-width) + 16px) !important; }
@media (max-width: 1280px) {
  #reader-controls { right: 16px !important; }
  #reading-progress, .reader-toast { right: 16px !important; }
}

"""

    if (
        ".toc-item a.is-active" not in layout_css
        or ".file-tree-root-folder:not([open])" not in layout_css
        or ".file-tree-root-folder[open] > .file-tree-root .folder-open-icon" not in layout_css
        or "initTocTracking();" not in js
    ):
        raise ValueError("HTML 质量门禁未通过：导航栏缺少当前阅读位置高亮或根目录折叠状态样式。")
    if (
        ".content-area .quiz-bilingual > p + p" not in layout_css
        or "align-self: center" not in layout_css
        or "margin: 0 1px 0 0" not in layout_css
    ):
        raise ValueError("HTML 质量门禁未通过：双语测验没有分行显示，或选项选择器没有垂直居中。")
    content_area_css = re.search(r"\.content-area\s*\{([^}]*)\}", layout_css, re.I | re.S)
    if (
        not content_area_css
        or "margin: 16px auto" not in content_area_css.group(1)
        or "padding: 24px 46px 96px" not in content_area_css.group(1)
    ):
        raise ValueError("HTML 质量门禁未通过：桌面正文顶部留白超出紧凑版式要求。")

    if re.search(r'<h[1-6]\b(?=[^>]*class=["\'][^"\']*\bcourse-header\b)[^>]*>', body_html, re.I):
        raise ValueError("HTML 质量门禁未通过：课程信息页眉不能占用正文标题层级。")
    if re.search(r'<p\b(?=[^>]*class=["\'][^"\']*\bcourse-header\b)[^>]*>', body_html, re.I):
        header_css = re.search(r"\.content-area p\.course-header\s*\{([^}]*)\}", layout_css, re.I | re.S)
        header_source_css = re.search(
            r"\.content-area p\.course-header \.source-title\s*\{([^}]*)\}", layout_css, re.I | re.S
        )
        if (
            not header_css
            or "text-align: center !important" not in header_css.group(1)
            or not header_source_css
            or "display: inline !important" not in header_source_css.group(1)
            or "font-size: .82em !important" not in header_source_css.group(1)
        ):
            raise ValueError("HTML 质量门禁未通过：课程信息页眉缺少紧凑排版样式。")
    if layout == "concept_highlight":
        lesson_title_css = re.search(
            r"\.content-area h1\.document-title\s*\{([^}]*)\}", layout_css, re.I | re.S
        )
        lesson_source_css = re.search(
            r"\.content-area h1\.document-title \.source-title\s*\{([^}]*)\}",
            layout_css,
            re.I | re.S,
        )
        if (
            not lesson_title_css
            or "text-align: center !important" not in lesson_title_css.group(1)
            or not lesson_source_css
            or "display: block !important" not in lesson_source_css.group(1)
            or "text-align: center !important" not in lesson_source_css.group(1)
            or "font-size: .42em !important" not in lesson_source_css.group(1)
        ):
            raise ValueError(
                "HTML 质量门禁未通过：concept_highlight 主标题必须居中，原文标题必须换行并显著缩小。"
            )

    full_html = (
        "<!DOCTYPE html>\n"
        '<html lang="zh-CN">\n'
        "<head>\n"
        '    <meta charset="UTF-8">\n'
        '    <meta name="viewport" content="width=device-width, initial-scale=1.0">\n'
        '    <title>' + escape(page_title) + '</title>\n'
        '    <link rel="stylesheet" href="' + FONT_AWESOME_CSS_URL + '" crossorigin="anonymous" referrerpolicy="no-referrer">\n'
        "    <style>\n"
        + css
        + "\n    </style>\n"
        "    <style>\n"
        + layout_css
        + "    </style>\n"
        "    <script>\n"
        "        MathJax = {\n"
        "            tex: { inlineMath: [['$', '$'], ['\\\\(', '\\\\)']], displayMath: [['$$', '$$'], ['\\\\[', '\\\\]']] },\n"
        "            svg: { fontCache: 'global' }\n"
        "        };\n"
        "    </script>\n"
        '    <script type="text/javascript" id="MathJax-script" async\n'
        '        src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-svg.js"></script>\n'
        "</head>\n"
        "<body>\n"
        '    <nav class="file-outline" id="file-outline" aria-label="学案文件路径">\n'
        '        <div class="toc-header">资源管理器</div>\n'
        + file_outline_html + "\n"
        '    </nav>\n'
        '    <main class="content-area">\n'
        + body_html
        + "\n"
        '        <footer style="margin-top: 40px; padding-top: 16px; border-top: 2px dashed #d0d7de;'
        ' text-align: center; color: #8a97a5; font-size: 12px;">\n'
        "            欢迎使用 " + WATERMARK + "\n"
        "        </footer>\n"
        "    </main>\n"
        '    <nav class="toc-outline" id="toc-outline" aria-label="本学案知识大纲">\n'
        '        <div class="toc-header">本学案知识大纲</div>\n'
        + toc_html + "\n"
        '    </nav>\n'
        "    <script>\n"
        + js
        + "\n    </script>\n"
        "</body>\n"
        "</html>\n"
    )
    expected_mathjax_config = r"tex: { inlineMath: [['$', '$'], ['\\(', '\\)']], displayMath: [['$$', '$$'], ['\\[', '\\]']] }"
    if expected_mathjax_config not in full_html:
        raise ValueError("HTML 质量门禁未通过：MathJax 行内/行间公式定界符转义错误。")
    if FONT_AWESOME_CSS_URL not in full_html:
        raise ValueError("HTML 质量门禁未通过：左侧文件树缺少 Font Awesome 在线样式表。")

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(full_html)
    return output_path
