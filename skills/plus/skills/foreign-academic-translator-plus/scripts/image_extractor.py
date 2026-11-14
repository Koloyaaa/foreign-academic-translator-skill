#!/usr/bin/env python3
"""
从 PDF 提取内嵌位图，按 (页序, 纵向 top, 横向 x0) 排序导出到 images/，
并生成 placement.json 落位清单，供译文嵌入位置判定。
用法：python scripts/image_extractor.py <input_pdf> <output_dir> [--prefix <学案名>]
"""
import argparse
import json
import sys
from pathlib import Path


def _encode_image(im: dict, stream) -> tuple:
    """把 pdfplumber 位图条目安全地编码成合法图片字节。
    优先用 PIL 按像素流 + 元数据重建（宽高/色彩空间/位深）；无法解析时再兜底按文件头直存。"""
    raw = stream.get_data() if stream is not None else None
    if not raw:
        return (None, None)
    w = int(im.get("width") or (im.get("srcsize") or (0, 0))[0] or 0)
    h = int(im.get("height") or (im.get("srcsize") or (0, 0))[1] or 0)
    filt = None
    try:
        filt = stream.get("/Filter")
        if hasattr(filt, "name"):
            filt = filt.name
    except Exception:
        filt = None
    filt_str = (str(filt) if filt else "").lower()
    # 标准图像文件头：直接可用
    for magic, ext in ((b"\xff\xd8\xff", "jpg"), (b"\x89PNG\r\n\x1a\n", "png"),
                       (b"GIF87a", "gif"), (b"GIF89a", "gif")):
        if raw[:len(magic)] == magic:
            return (raw, ext)
    # DCTDecode：原样为 JPEG
    if "dctdecode" in filt_str or "jpeg" in filt_str:
        return (raw, "jpg")
    # 其余（Flate 等）：用 PIL 按像素重建
    try:
        from PIL import Image
        colorspace = im.get("colorspace") or []
        cs_name = ""
        if isinstance(colorspace, list):
            cs_name = str(colorspace[0]).lower()
            if not isinstance(cs_name, str):
                cs_name = str(getattr(colorspace[0], "name", colorspace[0])).lower()
        if im.get("imagemask"):
            mode = "1"
        elif "cmyk" in cs_name:
            mode = "CMYK"
        elif "gray" in cs_name or "gray" in str(colorspace).lower():
            mode = "L"
        elif "rgb" in cs_name or "icc" in cs_name or "calrgb" in cs_name:
            mode = "RGB"
        else:
            mode = "RGB"
        if w <= 0 or h <= 0 or len(raw) != w * h * (4 if mode == "CMYK" else 3 if mode == "RGB" else 1):
            # 尺寸/字节数对不上时回到原样直存（避免阻塞流程）
            return (raw, "png")
        img = Image.frombytes(mode, (w, h), raw)
        if img.mode != "RGB":
            img = img.convert("RGB")
        buf = __import__("io").BytesIO()
        img.save(buf, format="PNG")
        return (buf.getvalue(), "png")
    except Exception:
        return (raw, "png")


def _pil_ok(data: bytes) -> bool:
    """校验字节流是否为 PIL 可正常打开的真实图片。"""
    try:
        from PIL import Image
        import io as _io
        Image.open(_io.BytesIO(data)).verify()
        return True
    except Exception:
        return False


def _ext_from_bytes(data: bytes) -> str:
    for magic, ext in ((b"\xff\xd8\xff", "jpg"), (b"\x89PNG\r\n\x1a\n", "png"),
                       (b"GIF87a", "gif"), (b"GIF89a", "gif")):
        if data[:len(magic)] == magic:
            return ext
    return "png"


def _from_pypdf(reader, pno: int, idx: int):
    """回退：用 pypdf 按页抽取第 idx 张图（pypdf 会重新编码为合法图片）。"""
    try:
        imgs = list(reader.pages[pno - 1].images)
    except Exception:
        return None
    if not imgs:
        return None
    cand = imgs[idx] if idx < len(imgs) else imgs[0]
    try:
        data = cand.data
    except Exception:
        return None
    if not data:
        return None
    return (data, _ext_from_bytes(data))


def extract(input_pdf: str, output_dir: str, prefix: str) -> dict:
    import pdfplumber

    reader = None
    try:
        import pypdf
        reader = pypdf.PdfReader(input_pdf)
    except Exception:
        reader = None

    output_dir = Path(output_dir)
    images_dir = output_dir / "images"
    images_dir.mkdir(parents=True, exist_ok=True)

    manifest = []
    seq = 0
    with pdfplumber.open(input_pdf) as pdf:
        for pno, page in enumerate(pdf.pages, start=1):
            for idx, im in enumerate(page.images):
                try:
                    x0 = float(im["x0"]); top = float(im["top"])
                    x1 = float(im["x1"]); bottom = float(im["bottom"])
                except (KeyError, TypeError, ValueError):
                    continue
                w, h = x1 - x0, bottom - top
                if w < 8 or h < 8:  # 过滤过小装饰图
                    continue
                stream = im.get("stream")
                if stream is None:
                    continue
                try:
                    out_bytes, ext = _encode_image(im, stream)
                except Exception as e:
                    print(f"[WARN] 无法编码第{pno}页第{idx}图: {e}", file=sys.stderr)
                    out_bytes, ext = None, None
                # 编码结果非真实图片时回退到 pypdf 重编码
                if reader is not None and (not out_bytes or not _pil_ok(out_bytes)):
                    fb = _from_pypdf(reader, pno, idx)
                    if fb and _pil_ok(fb[0]):
                        out_bytes, ext = fb
                if not out_bytes or not _pil_ok(out_bytes):
                    print(f"[WARN] 第{pno}页第{idx}图无法解码，已跳过", file=sys.stderr)
                    continue
                seq += 1
                fname = f"{prefix}_p{pno}_n{idx}.{ext}"
                (images_dir / fname).write_bytes(out_bytes)
                manifest.append({
                    "seq": seq, "page": pno, "img_idx": idx,
                    "x0": round(x0, 1), "top": round(top, 1),
                    "x1": round(x1, 1), "bottom": round(bottom, 1),
                    "w": round(w, 1), "h": round(h, 1),
                    "aspect_w_h": round(w / h, 2) if h else None,
                    "file": f"images/{fname}",
                })

    # 按页序 + 纵坐标 + 横坐标重排并重编 seq
    manifest.sort(key=lambda r: (r["page"], r["top"], r["x0"]))
    for i, r in enumerate(manifest, 1):
        r["seq"] = i

    (output_dir / "placement.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return {
        "count": len(manifest),
        "images_dir": str(images_dir),
        "manifest": str(output_dir / "placement.json"),
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("input_pdf", help="原始 PDF 路径")
    parser.add_argument("output_dir", help="输出目录（images/ 与 placement.json 将生成于此）")
    parser.add_argument("--prefix", default=None, help="图片文件名前缀，默认取 PDF 文件名主干")
    args = parser.parse_args()

    try:
        prefix = args.prefix or Path(args.input_pdf).stem
        res = extract(args.input_pdf, args.output_dir, prefix)
        print(json.dumps(res, ensure_ascii=False))
    except Exception as e:
        print(f"[ERROR] {e}", file=sys.stderr)
        sys.exit(1)