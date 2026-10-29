"""HTML 构建器：将 Markdown 译文转换为带目录伸缩 / 阅读进度 / 术语高亮 / MathJax / 水印的 HTML 页面。"""

from pathlib import Path
import re
from html import escape, unescape

from .base import WATERMARK, load_css, annotate_first_occurrences, protect_math, restore_math

# 页面内嵌 JS（普通字符串，非 f-string，避免花括号与 Python 格式化冲突）
# 通过占位符 __WATERMARK__ / __SHOW_CONCEPT_TABLE__ 在运行时替换。
_BUILD_JS = r"""
(function () {
    "use strict";
    var WATERMARK = "__WATERMARK__";
    var SHOW_TABLE = __SHOW_CONCEPT_TABLE__;
    var HEADING_SELECTOR = "h1, h2, h3, h4";
    var main = document.querySelector(".content-area");
    var prefKey = "foreign-academic-translator:reader-settings:v1";
    var notesKey = "foreign-academic-translator:notes:v1:" + location.pathname;
    var readerConfig = { palette: "blue", theme: "light", width: 1830 };
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
        if (typeof saved.width === "number" && isFinite(saved.width)) readerConfig.width = Math.max(720, Math.min(2400, saved.width));
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
    function initTocButton() {
        var toc = document.getElementById("toc-outline"); if (!toc) return;
        var button = createButton("☰", "目录", "toc-button"); button.id = "toc-btn";
        document.body.appendChild(button); toc.setAttribute("role", "navigation");
        function setOpen(open) { toc.classList.toggle("open", open); button.textContent = open ? "×" : "☰"; }
        button.addEventListener("click", function () { setOpen(!toc.classList.contains("open")); });
        toc.addEventListener("click", function (event) { if (event.target.tagName === "A") setOpen(false); });
        document.addEventListener("keydown", function (event) { if (event.key === "Escape") setOpen(false); });
    }
    function buildToc() {
        var headings = document.querySelectorAll(HEADING_SELECTOR), sidebar = document.getElementById("toc-outline");
        if (!headings.length || !sidebar) return;
        var list = document.createElement("ul");
        list.style.listStyle = "none"; list.style.padding = "0"; list.style.margin = "0";
        headings.forEach(function (heading, index) {
            if (!heading.id) heading.id = "toc-heading-" + index;
            var item = document.createElement("li"); item.className = "toc-item";
            item.style.margin = "4px 0"; item.style.borderRadius = "4px";
            if (heading.tagName === "H2") item.style.marginTop = "10px";
            else if (heading.tagName === "H3") item.style.paddingLeft = "18px";
            var link = document.createElement("a"); link.href = "#" + heading.id;
            link.textContent = heading.textContent; link.style.textDecoration = "none";
            link.addEventListener("click", function (event) {
                event.preventDefault(); heading.scrollIntoView({ behavior: "smooth", block: "start" });
            });
            item.appendChild(link); list.appendChild(item);
        });
        sidebar.appendChild(list);
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
        var handle = document.createElement("div"); handle.id = "reader-resize-handle";
        handle.className = "reader-resize-handle"; handle.setAttribute("role", "separator");
        handle.setAttribute("aria-label", "拖动调整译文阅读栏宽度"); handle.setAttribute("aria-orientation", "vertical");
        handle.setAttribute("aria-valuemin", "720"); handle.setAttribute("tabindex", "0"); document.body.appendChild(handle);
        function updatePosition() {
            if (window.innerWidth <= 740) { handle.hidden = true; return; }
            handle.hidden = false;
            var rect = main.getBoundingClientRect();
            handle.style.left = Math.max(8, Math.min(window.innerWidth - 8, rect.right - 6)) + "px";
            handle.style.top = Math.max(56, Math.min(window.innerHeight - 148, window.innerHeight / 2 - 64)) + "px";
            handle.setAttribute("aria-valuenow", String(Math.round(rect.width)));
            handle.setAttribute("aria-valuemax", String(Math.max(720, window.innerWidth - 24)));
        }
        function updateWidth(clientX) {
            var width = Math.max(720, Math.min(window.innerWidth - 24, (clientX - window.innerWidth / 2) * 2));
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
            updateWidth(window.innerWidth / 2 + (rect.width + (event.key === "ArrowRight" ? 40 : -40)) / 2);
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
        var helpButton = createButton("✎ 标注", "选中文字或点击公式，再点这里添加高亮或注释", "mark-help-button"); helpButton.id = "mark-help-button";
        toolbar.appendChild(markButton); toolbar.appendChild(noteButton); toolbar.hidden = true; document.body.appendChild(toolbar);
        document.body.appendChild(helpButton);
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
        function revealToolbarForSelection() {
            var selection = window.getSelection(), range = selection && selection.rangeCount ? selection.getRangeAt(0) : null;
            var hasText = !!(selection && selection.toString().trim());
            var formulas = range && main.contains(range.commonAncestorContainer) ? mathNodesForRange(range) : [];
            if (!hasText && !formulas.length) formulas = activeFormulaSelection.filter(function (item) { return item.isConnected; });
            if (!hasText && !formulas.length) { showNotice("先选中正文或点击一个公式，再添加高亮或注释。"); return; }
            if (range && hasText && !main.contains(range.commonAncestorContainer)) { showNotice("请在正文区域选择文字或公式。"); return; }
            activeFormulaSelection = formulas;
            var rect = range && range.getBoundingClientRect ? range.getBoundingClientRect() : null;
            if ((!rect || (!rect.width && !rect.height)) && formulas.length) rect = formulas[0].getBoundingClientRect();
            placeToolbar(rect);
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
        helpButton.addEventListener("mousedown", function (event) { event.preventDefault(); });
        markButton.addEventListener("click", function () { saveSelection(false); });
        noteButton.addEventListener("click", function () { saveSelection(true); });
        helpButton.addEventListener("click", revealToolbarForSelection);
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
            if (toolbar.contains(event.target) || helpButton.contains(event.target)) return;
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
    function parseChoices(text) {
        var starts = [], re = /([A-D])\.\s*/g, match;
        while ((match = re.exec(text)) !== null) {
            if (match.index > 0 && !/[\s\u3000]/.test(text.charAt(match.index - 1))) continue;
            starts.push({ letter: match[1], start: match.index, end: re.lastIndex });
        }
        var choices = [];
        for (var i = 0; i < starts.length; i++) {
            var end = i + 1 < starts.length ? starts[i + 1].start : text.length;
            choices.push({ letter: starts[i].letter, text: text.slice(starts[i].end, end).trim() });
        }
        return choices;
    }
    function initInteractiveQuiz() {
        if (!main) return;
        var quizTitle = null;
        main.querySelectorAll("h2").forEach(function (heading) {
            if (/(测验|quiz|test)/i.test(heading.textContent || "")) quizTitle = heading;
        });
        if (!quizTitle) return;
        var sectionHeadings = [], cursor = quizTitle.nextElementSibling;
        while (cursor && cursor.tagName !== "H2") {
            if (cursor.tagName === "H3") sectionHeadings.push(cursor);
            cursor = cursor.nextElementSibling;
        }
        var answerHeading = null;
        sectionHeadings.forEach(function (heading) {
            if (/(答案|réponses|answers?|answer key)/i.test(heading.textContent || "")) answerHeading = heading;
        });
        var answerData = [], answerNode = answerHeading ? answerHeading.nextElementSibling : null;
        while (answerNode && answerNode.tagName !== "H2") {
            if (answerNode.tagName === "OL" || answerNode.tagName === "UL") {
                Array.prototype.forEach.call(answerNode.children, function (item) {
                    var raw = (item.textContent || "").trim();
                    var match = raw.match(/^\s*([A-D])(?:\s*[,.\uFF0C\u3001\uFF1A:])?\s*([\s\S]*)$/);
                    if (match) answerData.push({ letter: match[1], explanation: match[2].trim() });
                });
            }
            answerNode = answerNode.nextElementSibling;
        }
        if (!answerData.length) return;
        var quizIndex = 0;
        sectionHeadings.forEach(function (heading) {
            var title = heading.textContent || "";
            if (heading === answerHeading) {
                var hiddenNode = heading;
                while (hiddenNode && hiddenNode.tagName !== "H2") { hiddenNode.hidden = true; hiddenNode = hiddenNode.nextElementSibling; }
                return;
            }
            var level = (title.indexOf("中档") !== -1 || /intermédiaire|intermediate|medium/i.test(title)) ? "medium" :
                ((title.indexOf("高难") !== -1 || /advanced|difficult|hard/i.test(title)) ? "advanced" : "basic");
            var questions = [], node = heading.nextElementSibling;
            while (node && node.tagName !== "H2" && node.tagName !== "H3") {
                if (node.tagName === "P" && /^\s*\d+\s*[.、]\s*/.test(node.textContent || "")) {
                    var optionNode = node.nextElementSibling;
                    if (optionNode && optionNode.tagName === "P" && parseChoices(optionNode.textContent || "").length >= 2) {
                        questions.push({ prompt: node, options: optionNode });
                    }
                }
                node = node.nextElementSibling;
            }
            questions.forEach(function (question) {
                var answer = answerData[quizIndex++];
                var choices = parseChoices(question.options.textContent || "");
                if (!answer || choices.length < 2) return;
                var card = document.createElement("section"); card.className = "quiz-question"; card.dataset.level = level;
                var fieldset = document.createElement("fieldset"); fieldset.className = "quiz-options";
                fieldset.setAttribute("aria-label", "选择答案");
                choices.forEach(function (choice) {
                    var label = document.createElement("label"); label.className = "quiz-option";
                    var input = document.createElement("input"); input.type = "radio";
                    input.name = "quiz-" + quizIndex; input.value = choice.letter;
                    label.appendChild(input); label.appendChild(document.createTextNode(choice.letter + ". " + choice.text));
                    fieldset.appendChild(label);
                });
                var submit = createButton("提交答案", "提交本题并查看答案", "quiz-submit");
                var feedback = document.createElement("p"); feedback.className = "quiz-feedback";
                feedback.setAttribute("role", "status"); feedback.setAttribute("aria-live", "polite"); feedback.hidden = true;
                submit.addEventListener("click", function () {
                    var selected = fieldset.querySelector("input:checked");
                    if (!selected) { feedback.textContent = "请先选择一个选项。"; feedback.hidden = false; return; }
                    fieldset.querySelectorAll("input").forEach(function (input) { input.disabled = true; });
                    submit.disabled = true; submit.textContent = "已提交";
                    var correct = selected.value === answer.letter;
                    feedback.classList.toggle("correct", correct); feedback.classList.toggle("incorrect", !correct);
                    feedback.textContent = (correct ? "正确。" : "已提交。") + "答案 / Réponse：" + answer.letter +
                        (answer.explanation ? "。解析：" + answer.explanation : "。");
                    feedback.hidden = false;
                    if (window.MathJax && window.MathJax.typesetPromise) window.MathJax.typesetPromise([feedback]);
                });
                var parent = question.prompt.parentNode;
                parent.insertBefore(card, question.prompt);
                card.appendChild(question.prompt); card.appendChild(fieldset); card.appendChild(submit); card.appendChild(feedback);
                question.options.parentNode.removeChild(question.options);
            });
        });
        var instruction = document.createElement("p"); instruction.className = "quiz-instructions";
        instruction.textContent = "每题选择后单独提交；提交后才会显示正确答案与解析。";
        quizTitle.parentNode.insertBefore(instruction, quizTitle.nextElementSibling);
        if (window.MathJax && window.MathJax.typesetPromise) window.MathJax.typesetPromise([main]).catch(function () {});
    }
    function addWatermarkOnCopy() {
        document.addEventListener("copy", function (event) {
            try {
                var selected = window.getSelection ? window.getSelection().toString() : "";
                if (selected) { event.clipboardData.setData("text/plain", selected + "\n\n欢迎使用 " + WATERMARK); event.preventDefault(); }
            } catch (err) {}
        });
    }
    assignConceptTable(); linkGlossaryTerms(); buildToc(); initTocButton();
    initReaderSettings(); initProgress(); initResizableReader(); initPersonalMarks();
    initInteractiveQuiz(); addWatermarkOnCopy();
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
    title_match = re.search(r"<h1\b[^>]*>(.*?)</h1>", body_html, re.I | re.S)
    page_title = unescape(re.sub(r"<[^>]+>", "", title_match.group(1))).strip() if title_match else "学案译文"

    js = (
        _BUILD_JS.replace("__WATERMARK__", WATERMARK)
        .replace("__SHOW_CONCEPT_TABLE__", "true" if show_concept_table else "false")
    )

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    layout_css = (
        "html, body { height: 100%; margin: 0; padding: 0; }\n"
        "html { scroll-behavior: smooth; }\n"
        "body { max-width: none; min-height: 100vh; margin: 0; padding: 0; background: var(--page-bg); color: var(--text); box-shadow: none; border-radius: 0; }\n"
        ".content-area { width: min(var(--reader-width, 1830px), calc(100% - 84px)); max-width: 1830px; box-sizing: border-box; margin: 42px auto; padding: 62px 46px 96px; background: var(--surface-bg); border-radius: 14px; box-shadow: 0 2px 28px rgba(15,35,60,.06); font-size: 18px; line-height: 1.85; }\n"
        "table { border-collapse: collapse; width: 100%; margin: 20px 0; }\n"
        "th, td { border: 1px solid #d8e0e8; padding: 8px 12px; }\n"
        "img { max-width: 100%; height: auto; display: block; margin: 15px 0; }\n"
        "span[data-en] { background: transparent; padding: 0; border-radius: 0; font-weight: 750; "
        "color: var(--accent-strong); text-decoration: underline dotted; text-underline-offset: 3px; cursor: help; }\n"
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

    layout_css += """
.content-area { width: min(var(--reader-width, 1830px), calc(100% - 84px)); }
.content-area span[data-en], .content-area a.term-link, .content-area .heading-term-link {
  color: var(--accent-strong) !important;
}
.content-area h2 .heading-source, .content-area h3 .heading-source,
.content-area h4 .heading-source { color: var(--accent-strong) !important; }
.content-area .document-title { text-align: center !important; }
.content-area .document-title .source-title {
  display: block !important; width: 100%; text-align: center !important;
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
.mark-help-button {
  position: fixed; left: 16px; bottom: 16px; z-index: 1101; min-width: 92px; height: 44px; padding: 0 14px;
  display: inline-flex; align-items: center; justify-content: center; border: 1px solid var(--border); border-radius: 999px;
  color: var(--accent-strong); background: var(--surface-bg); box-shadow: var(--control-shadow);
  cursor: pointer; font: 650 15px/1.1 'Segoe UI','Roboto',Arial,sans-serif;
  transition: transform .16s ease, background .16s ease;
}
.mark-help-button:hover { transform: translateY(-2px); background: var(--accent-soft); }
.mark-help-button:focus-visible { outline: 3px solid var(--accent); outline-offset: 3px; }
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
.content-area .quiz-option input { flex: 0 0 auto; margin-top: .45em; accent-color: var(--accent-strong); }
.content-area .quiz-option input[type="radio"] {
  appearance: none; -webkit-appearance: none; box-sizing: border-box; width: 19px; height: 19px;
  min-width: 19px; flex: 0 0 19px; margin: .18em 1px 0 0; display: grid; place-content: center;
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
  #reader-resize-handle, #reader-toast, #mark-help-button, .annotation-popover { display: none !important; }
  .content-area .quiz-submit { display: none !important; }
  .content-area .quiz-feedback[hidden] { display: none !important; }
}

"""

    full_html = (
        "<!DOCTYPE html>\n"
        '<html lang="zh-CN">\n'
        "<head>\n"
        '    <meta charset="UTF-8">\n'
        '    <meta name="viewport" content="width=device-width, initial-scale=1.0">\n'
        '    <title>' + escape(page_title) + '</title>\n'
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
