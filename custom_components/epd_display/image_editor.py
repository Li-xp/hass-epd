"""Image editor for EPD Display integration.

Supported element types
-----------------------
rectangle, line, point, text, entity_text, computed_text, calendar, image

``computed_text`` uses Jinja2 templates evaluated against full HA state.

``calendar`` renders a full month grid and can overlay events fetched from
one or more HA calendar entities.  Events are passed in via computed_results
under the key ``_cal_<idx>`` (a list of dicts with ``start`` and ``summary``).

SVG support
-----------
SVG files are rasterised with a built-in pure-Python renderer (no external
dependencies).  Handles path/circle/ellipse/rect/line/polyline/polygon and
all standard curve commands (C S Q T A).  Sufficient for Material Design Icons
and most single-colour icon sets.
"""

import calendar as _cal_mod
import json
import logging
import math
import os
import re
import xml.etree.ElementTree as _ET
from datetime import date, datetime
from typing import Any

from PIL import Image, ImageDraw, ImageFont

_LOGGER = logging.getLogger(__name__)

IMAGES_SUBDIR = "epd_images"
TEMPLATES_SUBDIR = "epd_templates"


# ═══════════════════════════════════════════════════════════════
#  内嵌 SVG 光栅化器（纯 Python，无外部依赖）
#  支持：path (M L H V C S Q T A Z) / circle / ellipse / rect /
#        line / polyline / polygon / g 分组
# ═══════════════════════════════════════════════════════════════

def _svg_parse_color(c, default=(0, 0, 0, 255)):
    if not c or c in ("none", "transparent", ""):
        return None
    if c == "currentColor": return default   # treat as foreground color
    if c == "black":  return (0, 0, 0, 255)
    if c == "white":  return (255, 255, 255, 255)
    m = re.match(r"#([0-9a-fA-F]{3,8})", c)
    if m:
        h = m.group(1)
        if len(h) == 3: h = h[0]*2 + h[1]*2 + h[2]*2
        r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
        a = int(h[6:8], 16) if len(h) == 8 else 255
        return (r, g, b, a)
    return default


def _svg_tokenize_path(d: str):
    """
    Return list of (cmd, [float, ...]) from an SVG path d attribute.

    Fully spec-compliant tokeniser: handles all legal number formats including
      • negative sign as implicit separator  ( M12-3  →  M 12 -3 )
      • decimal point as implicit separator  ( M.5.5  →  M 0.5 0.5 )
      • scientific notation                  ( 1.2e-3 )
      • commands immediately adjacent to numbers ( M12,34L56,78 )
    """
    # Regex that matches either a command letter or a number token
    # Numbers: optional sign, integer/decimal parts, optional exponent
    _TOKEN = re.compile(
        r"([MmZzLlHhVvCcSsQqTtAa])"          # command letter
        r"|([+-]?(?:\d+\.?\d*|\.\d+)"         # number: 12  12.3  .3
        r"(?:[eE][+-]?\d+)?)",                 # optional exponent
        re.ASCII,
    )
    cmds, cur_cmd, cur_nums = [], None, []
    for m in _TOKEN.finditer(d):
        cmd_tok, num_tok = m.group(1), m.group(2)
        if cmd_tok:
            if cur_cmd is not None:
                cmds.append((cur_cmd, cur_nums))
            cur_cmd, cur_nums = cmd_tok, []
        elif num_tok:
            try:
                cur_nums.append(float(num_tok))
            except ValueError:
                pass
    if cur_cmd is not None:
        cmds.append((cur_cmd, cur_nums))
    return cmds


def _cubic(p0, p1, p2, p3, steps=10):
    for k in range(1, steps + 1):
        t = k / steps
        yield (
            (1-t)**3*p0[0] + 3*(1-t)**2*t*p1[0] + 3*(1-t)*t**2*p2[0] + t**3*p3[0],
            (1-t)**3*p0[1] + 3*(1-t)**2*t*p1[1] + 3*(1-t)*t**2*p2[1] + t**3*p3[1],
        )

def _quad(p0, p1, p2, steps=8):
    for k in range(1, steps + 1):
        t = k / steps
        yield (
            (1-t)**2*p0[0] + 2*(1-t)*t*p1[0] + t**2*p2[0],
            (1-t)**2*p0[1] + 2*(1-t)*t*p1[1] + t**2*p2[1],
        )


def _svg_path_polygons(d: str, sx: float, sy: float):
    """Convert SVG path d → list of point-lists (each subpath)."""
    cmds = _svg_tokenize_path(d)
    polygons, cur = [], []
    cx = cy = 0.0
    start_x = start_y = 0.0
    last_ctrl_x = last_ctrl_y = 0.0   # for S/T smooth continuations

    for cmd, n in cmds:
        rel = cmd.islower() and cmd not in ("z", "Z")

        if cmd in ("M", "m"):
            if cur: polygons.append(cur); cur = []
            i = 0
            while i + 1 < len(n):
                nx_ = n[i] * sx + (cx if rel else 0)
                ny_ = n[i + 1] * sy + (cy if rel else 0)
                cx, cy = nx_, ny_
                if i == 0:
                    start_x, start_y = cx, cy
                cur.append((cx, cy))
                i += 2

        elif cmd in ("Z", "z"):
            cur.append((start_x, start_y))
            polygons.append(cur); cur = []
            cx, cy = start_x, start_y

        elif cmd in ("L", "l"):
            i = 0
            while i + 1 < len(n):
                cx = n[i]*sx + (cx if rel else 0)
                cy = n[i+1]*sy + (cy if rel else 0)
                cur.append((cx, cy)); i += 2

        elif cmd in ("H", "h"):
            for v in n:
                cx = cx + v*sx if rel else v*sx; cur.append((cx, cy))

        elif cmd in ("V", "v"):
            for v in n:
                cy = cy + v*sy if rel else v*sy; cur.append((cx, cy))

        elif cmd in ("C", "c"):
            i = 0
            while i + 5 < len(n):
                if rel:
                    x1,y1 = cx+n[i]*sx, cy+n[i+1]*sy
                    x2,y2 = cx+n[i+2]*sx, cy+n[i+3]*sy
                    ex,ey = cx+n[i+4]*sx, cy+n[i+5]*sy
                else:
                    x1,y1 = n[i]*sx, n[i+1]*sy
                    x2,y2 = n[i+2]*sx, n[i+3]*sy
                    ex,ey = n[i+4]*sx, n[i+5]*sy
                last_ctrl_x, last_ctrl_y = x2, y2
                cur.extend(_cubic((cx,cy),(x1,y1),(x2,y2),(ex,ey)))
                cx, cy = ex, ey; i += 6

        elif cmd in ("S", "s"):
            i = 0
            while i + 3 < len(n):
                x1 = 2*cx - last_ctrl_x; y1 = 2*cy - last_ctrl_y
                if rel:
                    x2,y2 = cx+n[i]*sx, cy+n[i+1]*sy
                    ex,ey = cx+n[i+2]*sx, cy+n[i+3]*sy
                else:
                    x2,y2 = n[i]*sx, n[i+1]*sy
                    ex,ey = n[i+2]*sx, n[i+3]*sy
                last_ctrl_x, last_ctrl_y = x2, y2
                cur.extend(_cubic((cx,cy),(x1,y1),(x2,y2),(ex,ey)))
                cx, cy = ex, ey; i += 4

        elif cmd in ("Q", "q"):
            i = 0
            while i + 3 < len(n):
                if rel:
                    x1,y1 = cx+n[i]*sx, cy+n[i+1]*sy
                    ex,ey = cx+n[i+2]*sx, cy+n[i+3]*sy
                else:
                    x1,y1 = n[i]*sx, n[i+1]*sy
                    ex,ey = n[i+2]*sx, n[i+3]*sy
                last_ctrl_x, last_ctrl_y = x1, y1
                cur.extend(_quad((cx,cy),(x1,y1),(ex,ey)))
                cx, cy = ex, ey; i += 4

        elif cmd in ("T", "t"):
            i = 0
            while i + 1 < len(n):
                x1 = 2*cx - last_ctrl_x; y1 = 2*cy - last_ctrl_y
                ex = cx + n[i]*sx if rel else n[i]*sx
                ey = cy + n[i+1]*sy if rel else n[i+1]*sy
                last_ctrl_x, last_ctrl_y = x1, y1
                cur.extend(_quad((cx,cy),(x1,y1),(ex,ey)))
                cx, cy = ex, ey; i += 2

        elif cmd in ("A", "a"):
            i = 0
            while i + 6 < len(n):
                ex = cx + n[i+5]*sx if rel else n[i+5]*sx
                ey = cy + n[i+6]*sy if rel else n[i+6]*sy
                # arc approximated with 8 line segments (sufficient for icons)
                for k in range(1, 9):
                    cur.append((cx + (ex-cx)*k/8, cy + (ey-cy)*k/8))
                cx, cy = ex, ey; i += 7

    if cur:
        polygons.append(cur)
    return polygons


def _render_svg_element(el, draw: ImageDraw.ImageDraw, sx: float, sy: float,
                        fg_color=None, inherited: dict | None = None):
    """Render one SVG element, supporting CSS inheritance from parent/root."""
    tag = el.tag.split("}")[-1] if "}" in el.tag else el.tag
    inherited = inherited or {}

    # Parse style attribute – highest priority
    style_props: dict = {}
    style_str = el.get("style", "")
    if style_str:
        for decl in style_str.split(";"):
            decl = decl.strip()
            if ":" in decl:
                k, v = decl.split(":", 1)
                style_props[k.strip().lower()] = v.strip()

    def _attr(name: str, default: str) -> str:
        """Resolve attribute with CSS cascade: style > attr > inherited > default."""
        if name in style_props:
            return style_props[name]
        v = el.get(name)
        if v is not None:
            return v
        if name in inherited:
            return inherited[name]
        return default

    # Build inherited context to pass to children
    # Inheritable SVG presentation attrs: fill, stroke, stroke-width, color, opacity
    child_inherited = dict(inherited)
    for iattr in ("fill", "stroke", "stroke-width", "color", "opacity"):
        v = style_props.get(iattr) or el.get(iattr)
        if v is not None:
            child_inherited[iattr] = v

    # SVG spec: fill defaults to "black" ONLY if not inherited
    raw_fill   = _attr("fill",         inherited.get("fill", "black"))
    raw_stroke = _attr("stroke",       inherited.get("stroke", ""))
    raw_sw     = _attr("stroke-width", inherited.get("stroke-width", "1"))
    try:
        sw = max(1, int(float(raw_sw) * min(sx, sy)))
    except (ValueError, TypeError):
        sw = 1

    def col(raw):
        if not raw or raw in ("none", "transparent"):
            return None
        # currentColor → fg_color (or inherited color, or black)
        if raw == "currentColor":
            inherited_color = inherited.get("color") or inherited.get("fill")
            if fg_color:
                return fg_color
            if inherited_color and inherited_color not in ("none", "currentColor"):
                return _svg_parse_color(inherited_color)
            return (0, 0, 0, 255)
        if fg_color and raw not in ("none", "transparent"):
            return fg_color
        return _svg_parse_color(raw)

    fill   = col(raw_fill)
    stroke = col(raw_stroke) if raw_stroke and raw_stroke not in ("none", "") else None

    if tag == "path":
        d = el.get("d", "")
        if not d: return
        for pts in _svg_path_polygons(d, sx, sy):
            if len(pts) >= 3:
                if fill:   draw.polygon(pts, fill=fill)
                if stroke: draw.line(pts + [pts[0]], fill=stroke, width=sw)
            elif len(pts) == 2 and stroke:
                draw.line(pts, fill=stroke, width=sw)

    elif tag in ("circle", "ellipse"):
        cx = float(el.get("cx", 0)) * sx
        cy = float(el.get("cy", 0)) * sy
        rx = float(el.get("r", el.get("rx", "0"))) * sx
        ry = float(el.get("ry", el.get("r", "0"))) * sy
        bb = [cx-rx, cy-ry, cx+rx, cy+ry]
        if fill:   draw.ellipse(bb, fill=fill)
        if stroke: draw.ellipse(bb, outline=stroke, width=sw)

    elif tag == "rect":
        x = float(el.get("x", 0)) * sx;  y = float(el.get("y", 0)) * sy
        w = float(el.get("width", 0)) * sx; h = float(el.get("height", 0)) * sy
        if fill:   draw.rectangle([x, y, x+w, y+h], fill=fill)
        if stroke: draw.rectangle([x, y, x+w, y+h], outline=stroke, width=sw)

    elif tag == "line":
        x1=float(el.get("x1",0))*sx; y1=float(el.get("y1",0))*sy
        x2=float(el.get("x2",0))*sx; y2=float(el.get("y2",0))*sy
        if stroke: draw.line([(x1,y1),(x2,y2)], fill=stroke, width=sw)

    elif tag in ("polyline", "polygon"):
        nums = [float(v) for v in re.split(r"[\s,]+", el.get("points","").strip()) if v]
        pts  = [(nums[i]*sx, nums[i+1]*sy) for i in range(0, len(nums)-1, 2)]
        if pts:
            if fill and len(pts) >= 3: draw.polygon(pts, fill=fill)
            if stroke:
                line_pts = pts + [pts[0]] if tag == "polygon" else pts
                draw.line(line_pts, fill=stroke, width=sw)

    elif tag in ("g", "svg", "symbol", "defs"):
        if tag == "defs":
            return  # skip defs content
        for child in el:
            _render_svg_element(child, draw, sx, sy, fg_color, child_inherited)


def render_svg(source, size, fg_color=None) -> Image.Image:
    """
    Rasterise an SVG file or string to a PIL RGBA Image.

    Parameters
    ----------
    source    : str  – file path OR raw SVG string
    size      : int or (w, h)
    fg_color  : tuple (r,g,b,a) – override all fill/stroke colours (for
                tinting monochrome icons)
    """
    if isinstance(size, int):
        size = (size, size)
    tw, th = size

    try:
        if source.strip().startswith("<"):
            root = _ET.fromstring(source)
        else:
            root = _ET.parse(source).getroot()
    except _ET.ParseError as e:
        raise ValueError(f"SVG parse error: {e}")

    # strip namespaces
    for el in root.iter():
        if "}" in el.tag:
            el.tag = el.tag.split("}", 1)[1]

    vb = root.get("viewBox") or root.get("viewbox") or ""
    if vb:
        vb_nums = [float(v) for v in re.split(r"[\s,]+", vb.strip()) if v]
        _, _, vw, vh = vb_nums if len(vb_nums) == 4 else (0, 0, float(root.get("width", 24)), float(root.get("height", 24)))
    else:
        vw = float(root.get("width",  24))
        vh = float(root.get("height", 24))

    sx, sy = tw / vw, th / vh

    img  = Image.new("RGBA", (tw, th), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Collect root-level presentation attributes to inherit
    root_inherited: dict = {}
    for iattr in ("fill", "stroke", "stroke-width", "color", "opacity"):
        v = root.get(iattr)
        if v is not None:
            root_inherited[iattr] = v

    for child in root:
        _render_svg_element(child, draw, sx, sy, fg_color, root_inherited)

    return img


def _open_image(path: str, target_w=None, target_h=None,
                keep_aspect=True, opacity=1.0) -> Image.Image:
    """
    Open any image file (including .svg) and return a sized RGBA Image.
    Automatically calls render_svg() for .svg files.
    """
    ext = os.path.splitext(path)[1].lower()
    if ext == ".svg":
        # choose render size
        rw = target_w or target_h or 64
        rh = target_h or target_w or 64
        icon = render_svg(path, (rw, rh))
        # render_svg already produces the right size
        return icon if opacity >= 1.0 else _apply_opacity(icon, opacity)

    icon = Image.open(path).convert("RGBA")

    if target_w or target_h:
        orig_w, orig_h = icon.size
        if keep_aspect:
            tw_ = target_w or target_h
            th_ = target_h or target_w
            ratio = min(tw_ / orig_w, th_ / orig_h)
            icon = icon.resize(
                (max(1, int(orig_w * ratio)), max(1, int(orig_h * ratio))),
                Image.Resampling.LANCZOS,
            )
        else:
            icon = icon.resize(
                (target_w or orig_w, target_h or orig_h),
                Image.Resampling.LANCZOS,
            )

    if opacity < 1.0:
        icon = _apply_opacity(icon, opacity)
    return icon


def _apply_opacity(icon: Image.Image, opacity: float) -> Image.Image:
    r, g, b, a = icon.split()
    a = a.point(lambda p: int(p * opacity))
    return Image.merge("RGBA", (r, g, b, a))


def _paste_icon(img: Image.Image, icon: Image.Image, x: int, y: int):
    """Alpha-composite icon onto img at (x, y), returns refreshed ImageDraw."""
    bg = img.crop((x, y, x + icon.width, y + icon.height)).convert("RGBA")
    merged = Image.alpha_composite(bg, icon).convert("RGB")
    img.paste(merged, (x, y))
    return ImageDraw.Draw(img)


# CJK font – resolved once at import time by scanning the system
def _find_cjk_font() -> str | None:
    """Scan common font directories for a CJK-capable font, return path or None."""
    import glob
    # Explicit high-priority candidates (both truetype/ and opentype/ variants)
    candidates = [
        # User-provided font (highest priority) – place any .ttf/.ttc here
        "/config/www/epd_font.ttf",
        "/config/www/epd_font.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/opentype/noto/NotoSerifCJK-Regular.ttc",
        "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
        "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
        "/usr/share/fonts/opentype/ipafont-gothic/ipag.ttf",   # Japanese fallback (has CJK)
        "/System/Library/Fonts/PingFang.ttc",
        "/System/Library/Fonts/STHeiti Light.ttc",
        "/Windows/Fonts/msyh.ttc",
        "/Windows/Fonts/simsun.ttc",
    ]
    for p in candidates:
        if os.path.isfile(p):
            return p
    # Dynamic scan – cover any distro layout
    patterns = [
        "/usr/share/fonts/**/*CJK*Regular*.ttc",
        "/usr/share/fonts/**/*CJK*Regular*.otf",
        "/usr/share/fonts/**/*CJK*.ttc",
        "/usr/share/fonts/**/*CJK*.otf",
        "/usr/share/fonts/**/*wqy*.ttc",
        "/usr/share/fonts/**/*wqy*.ttf",
    ]
    for pat in patterns:
        for p in sorted(glob.glob(pat, recursive=True)):
            if os.path.isfile(p):
                return p
    return None

_CJK_FONT_PATH: str | None = _find_cjk_font()

_FONT_SEARCH_PATHS = [
    # CJK first – populated at import time
    *([_CJK_FONT_PATH] if _CJK_FONT_PATH else []),
    # Latin fallbacks
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    "/System/Library/Fonts/Helvetica.ttc",
]


def _load_font_file(path: str, size: int):
    """Try loading a font file, handling .ttc index and common errors."""
    # Try without index first
    try:
        return ImageFont.truetype(path, size)
    except Exception as e1:
        # .ttc collections sometimes need explicit index=0
        if path.lower().endswith(".ttc"):
            try:
                return ImageFont.truetype(path, size, index=0)
            except Exception as e2:
                _LOGGER.debug("Font load failed %s (index=0): %s", path, e2)
        _LOGGER.debug("Font load failed %s: %s", path, e1)
    return None


def _resolve_font(font_path: str | None, font_size: int):
    # 1. Explicitly requested font_path
    if font_path and os.path.isfile(font_path):
        f = _load_font_file(font_path, font_size)
        if f:
            return f
        _LOGGER.warning("Cannot load requested font %s, trying fallbacks", font_path)

    # 2. User-placed font in /config/www/ – checked every call (not cached at import)
    for user_path in ("/config/www/epd_font.ttf", "/config/www/epd_font.ttc",
                      "/config/www/epd_font.otf"):
        if os.path.isfile(user_path):
            f = _load_font_file(user_path, font_size)
            if f:
                _LOGGER.debug("Using user font: %s", user_path)
                return f
            else:
                _LOGGER.warning(
                    "User font %s exists but failed to load – "
                    "make sure it is a valid TTF/TTC/OTF file.", user_path)

    # 3. System font search list (resolved at import time)
    for p in _FONT_SEARCH_PATHS:
        if p and os.path.isfile(p):
            f = _load_font_file(p, font_size)
            if f:
                return f

    _LOGGER.warning("No usable CJK font found. Chinese text will render as boxes. "
                    "Place a CJK .ttf font at /config/www/epd_font.ttf to fix.")
    return ImageFont.load_default()


def _parse_color(color_value: Any) -> str | tuple:
    if isinstance(color_value, list):
        return tuple(color_value)
    return color_value


# ─── Template persistence ─────────────────────────────────

def save_template(config_dir: str, name: str, data: dict) -> str:
    tpl_dir = os.path.join(config_dir, TEMPLATES_SUBDIR)
    os.makedirs(tpl_dir, exist_ok=True)
    path = os.path.join(tpl_dir, f"{name}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    _LOGGER.info("EPD template saved: %s", path)
    return path


def load_template(config_dir: str, name: str) -> dict | None:
    path = os.path.join(config_dir, TEMPLATES_SUBDIR, f"{name}.json")
    if not os.path.isfile(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def list_templates(config_dir: str) -> list[str]:
    tpl_dir = os.path.join(config_dir, TEMPLATES_SUBDIR)
    if not os.path.isdir(tpl_dir):
        return []
    return sorted(n[:-5] for n in os.listdir(tpl_dir) if n.endswith(".json"))


def delete_template(config_dir: str, name: str) -> bool:
    path = os.path.join(config_dir, TEMPLATES_SUBDIR, f"{name}.json")
    if os.path.isfile(path):
        os.remove(path)
        return True
    return False


# ─── Image generation ─────────────────────────────────────

def _wrap_text(text: str, font, max_width: int) -> list[str]:
    """
    Word-wrap `text` to fit within `max_width` pixels.
    Handles CJK (no spaces) and Latin (space-separated) text.
    Explicit newlines (\n) are always honoured.
    """
    lines = []
    for paragraph in text.split("\n"):
        if not paragraph:
            lines.append("")
            continue
        # Try to fit the whole paragraph first
        bbox = font.getbbox(paragraph)
        if (bbox[2] - bbox[0]) <= max_width:
            lines.append(paragraph)
            continue
        # Need to wrap
        cur_line = ""
        for ch in paragraph:
            test = cur_line + ch
            bbox = font.getbbox(test)
            if (bbox[2] - bbox[0]) <= max_width:
                cur_line = test
            else:
                if cur_line:
                    lines.append(cur_line)
                cur_line = ch
        if cur_line:
            lines.append(cur_line)
    return lines


def _draw_textbox(draw: "ImageDraw.ImageDraw", img: "Image.Image", elem: dict,
                  text: str):
    """
    Render `text` inside a box defined by elem x/y/width/height.

    Supported elem fields:
      x, y, width, height   – box geometry
      color                 – text colour (default black)
      font_path, font_size  – font
      bg_color              – box background fill (default none/transparent)
      border_color          – box border colour (default none)
      border_width          – border line width (default 1)
      padding               – inner padding px (default 4)
      line_spacing          – extra px between lines (default 2)
      valign                – "top" | "middle" | "bottom" (default "top")
      align                 – "left" | "center" | "right" (default "left")
      clip                  – if true, text is clipped to box (default true)
    """
    x      = int(elem.get("x", 0))
    y      = int(elem.get("y", 0))
    width  = int(elem.get("width", 200))
    height = int(elem.get("height", 100))
    color  = _parse_color(elem.get("color", "black"))
    font   = _resolve_font(elem.get("font_path"), elem.get("font_size", 20))
    pad    = int(elem.get("padding", 4))
    lsp    = int(elem.get("line_spacing", 2))
    valign = elem.get("valign", "top")
    align  = elem.get("align", "left")
    clip   = elem.get("clip", True)

    bg_color     = elem.get("bg_color", "")
    border_color = elem.get("border_color", "")
    border_width = int(elem.get("border_width", 1))

    # Draw background
    if bg_color:
        draw.rectangle([x, y, x + width, y + height],
                       fill=_parse_color(bg_color))

    # Draw border
    if border_color:
        draw.rectangle([x, y, x + width, y + height],
                       outline=_parse_color(border_color),
                       width=border_width)

    if not text:
        return

    inner_w = width  - pad * 2
    inner_h = height - pad * 2
    if inner_w <= 0 or inner_h <= 0:
        return

    # Wrap text
    lines = _wrap_text(str(text), font, inner_w)

    # Measure line height
    sample_bbox = font.getbbox("Ag测")
    line_h = sample_bbox[3] - sample_bbox[1]
    step   = line_h + lsp

    # Clip lines that exceed box height
    max_lines = max(1, inner_h // step)
    if clip and len(lines) > max_lines:
        lines = lines[:max_lines]
        # Mark last line with ellipsis if clipped
        if lines:
            while lines[-1]:
                trimmed = lines[-1][:-1]
                test = trimmed + "…"
                bbox = font.getbbox(test)
                if (bbox[2] - bbox[0]) <= inner_w:
                    lines[-1] = test
                    break
                lines[-1] = trimmed

    total_h = len(lines) * step - lsp

    # Vertical alignment
    if valign == "middle":
        text_y = y + pad + max(0, (inner_h - total_h) // 2)
    elif valign == "bottom":
        text_y = y + pad + max(0, inner_h - total_h)
    else:
        text_y = y + pad

    # Draw each line
    for line in lines:
        if text_y > y + height - pad:
            break
        line_bbox = font.getbbox(line) if line else (0, 0, 0, line_h)
        lw = line_bbox[2] - line_bbox[0]
        if align == "center":
            text_x = x + pad + max(0, (inner_w - lw) // 2)
        elif align == "right":
            text_x = x + pad + max(0, inner_w - lw)
        else:
            text_x = x + pad
        draw.text((text_x, text_y), line, fill=color, font=font)
        text_y += step


def generate_image(
    config_dir: str,
    width: int,
    height: int,
    background_color: str = "white",
    background_image: str | None = None,
    elements: list[dict] | None = None,
    output_filename: str = "epd_editor_output.png",
    entity_states: dict[str, str] | None = None,
    computed_results: dict[str, str] | None = None,
) -> str:
    """Compose an image and save it.

    computed_results keys
    ---------------------
    "<idx>"       rendered string for ``computed_text`` element at index idx
    "_cal_<idx>"  list[dict] of calendar events for ``calendar`` element at idx
    """
    entity_states    = entity_states    or {}
    computed_results = computed_results or {}

    if background_image and os.path.isfile(background_image):
        img = Image.open(background_image).convert("RGB").resize((width, height))
    else:
        img = Image.new("RGB", (width, height), color=background_color)

    draw = ImageDraw.Draw(img)

    for idx, elem in enumerate(elements or []):
        etype = elem.get("type")

        if etype == "rectangle":
            x, y = elem.get("x", 0), elem.get("y", 0)
            w, h = elem.get("width", 50), elem.get("height", 50)
            fill    = _parse_color(elem.get("fill", ""))
            outline = _parse_color(elem.get("outline", "black"))
            lw      = elem.get("line_width", 1)
            draw.rectangle([x, y, x + w, y + h],
                           fill=fill if fill else None,
                           outline=outline, width=lw)

        elif etype == "line":
            points = elem.get("points", [])
            color  = _parse_color(elem.get("color", "black"))
            lw     = elem.get("line_width", 1)
            if len(points) >= 4:
                draw.line(points, fill=color, width=lw)

        elif etype == "point":
            x, y  = elem.get("x", 0), elem.get("y", 0)
            r     = elem.get("radius", 3)
            color = _parse_color(elem.get("color", "black"))
            draw.ellipse([x - r, y - r, x + r, y + r], fill=color)

        elif etype == "text":
            x, y  = elem.get("x", 0), elem.get("y", 0)
            text  = elem.get("text", "")
            color = _parse_color(elem.get("color", "black"))
            font  = _resolve_font(elem.get("font_path"), elem.get("font_size", 20))
            draw.text((x, y), text, fill=color, font=font)

        elif etype == "textbox":
            # Static text with word-wrap inside a bounding box
            text = elem.get("text", "")
            _draw_textbox(draw, img, elem, text)

        elif etype == "textbox_entity":
            # entity_text with word-wrap
            eid      = elem.get("entity_id", "")
            prefix   = elem.get("prefix", "")
            suffix   = elem.get("suffix", "")
            state_v  = entity_states.get(eid, "N/A")
            text     = f"{prefix}{state_v}{suffix}"
            _draw_textbox(draw, img, elem, text)

        elif etype == "textbox_computed":
            # computed_text with word-wrap
            rendered = computed_results.get(str(idx), elem.get("template", ""))
            rendered = str(rendered).strip()
            _draw_textbox(draw, img, elem, rendered)

        elif etype == "entity_text":
            x, y      = elem.get("x", 0), elem.get("y", 0)
            eid       = elem.get("entity_id", "")
            prefix    = elem.get("prefix", "")
            suffix    = elem.get("suffix", "")
            color     = _parse_color(elem.get("color", "black"))
            font      = _resolve_font(elem.get("font_path"), elem.get("font_size", 20))
            state_val = entity_states.get(eid, "N/A")
            draw.text((x, y), f"{prefix}{state_val}{suffix}", fill=color, font=font)

        elif etype == "computed_text":
            x, y     = elem.get("x", 0), elem.get("y", 0)
            color    = _parse_color(elem.get("color", "black"))
            font     = _resolve_font(elem.get("font_path"), elem.get("font_size", 20))
            rendered = computed_results.get(str(idx), elem.get("template", ""))
            rendered = str(rendered).strip()

            _IMG_EXTS = (".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp", ".svg")

            # 判断是否应该以图片方式渲染，优先级：
            # 1. 内容本身是 SVG XML（<svg...>）→ 直接光栅化
            # 2. 内容是 file:// 路径
            # 3. 内容是任意以图片扩展名结尾的路径（含相对路径）
            _is_svg_content = rendered.startswith("<svg") or rendered.startswith("<?xml")
            _is_file_url    = rendered.startswith("file://")
            _is_img_path    = rendered.lower().endswith(_IMG_EXTS) and not rendered.startswith("<")

            if _is_svg_content:
                try:
                    target_w = elem.get("width") or 64
                    target_h = elem.get("height") or target_w
                    icon = render_svg(rendered, (target_w, target_h))
                    opacity = elem.get("opacity", 1.0)
                    if opacity < 1.0:
                        icon = _apply_opacity(icon, opacity)
                    draw = _paste_icon(img, icon, x, y)
                except Exception as _err:
                    _LOGGER.warning("computed_text SVG content render error: %s", _err)
                    draw.text((x, y), "[SVG ERR]", fill=color, font=font)

            elif _is_img_path or _is_file_url:
                path = rendered.replace("file://", "")
                if os.path.isfile(path):
                    try:
                        icon = _open_image(path, elem.get("width"), elem.get("height"),
                                           elem.get("keep_aspect", True), elem.get("opacity", 1.0))
                        draw = _paste_icon(img, icon, x, y)
                    except Exception as _err:
                        _LOGGER.warning("computed_text image render error (%s): %s", path, _err)
                        draw.text((x, y), f"[ERR:{os.path.basename(path)}]", fill=color, font=font)
                else:
                    _LOGGER.warning("computed_text: image path not found: %s", path)
                    draw.text((x, y), f"[?:{os.path.basename(rendered)}]", fill=color, font=font)

            else:
                draw.text((x, y), rendered, fill=color, font=font)

        elif etype == "calendar":
            cal_events = computed_results.get(f"_cal_{idx}", [])
            _draw_calendar(draw, elem, cal_events)

        elif etype == "image":
            x, y = elem.get("x", 0), elem.get("y", 0)
            target_w = elem.get("width") or 64
            target_h = elem.get("height") or target_w
            opacity  = elem.get("opacity", 1.0)

            # 支持三种来源：
            # 1. svg_content 字段（直接嵌入 SVG XML 字符串）
            # 2. path 字段（本地文件路径，支持 .svg / 位图）
            svg_content = elem.get("svg_content", "")
            path        = elem.get("path", "")

            if svg_content and (svg_content.strip().startswith("<svg") or svg_content.strip().startswith("<?xml")):
                try:
                    icon = render_svg(svg_content.strip(), (target_w, target_h))
                    if opacity < 1.0:
                        icon = _apply_opacity(icon, opacity)
                    draw = _paste_icon(img, icon, x, y)
                except Exception as _e:
                    _LOGGER.warning("image element SVG content error: %s", _e)
            elif path:
                if os.path.isfile(path):
                    try:
                        icon = _open_image(path, elem.get("width"), elem.get("height"),
                                           elem.get("keep_aspect", True), opacity)
                        draw = _paste_icon(img, icon, x, y)
                    except Exception as _img_err:
                        _LOGGER.warning("image element render error (%s): %s", path, _img_err)
                else:
                    _LOGGER.warning("image element: file not found: %s", path)
            else:
                _LOGGER.warning("image element: no path or svg_content provided")

        else:
            _LOGGER.warning("Unknown element type: %s", etype)

    out_dir  = os.path.join(config_dir, IMAGES_SUBDIR)
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, output_filename)
    img.save(out_path, "PNG")
    _LOGGER.info("EPD image saved: %s (%dx%d)", out_path, width, height)
    return out_path


# ─── Calendar renderer ────────────────────────────────────

def _draw_calendar(draw: ImageDraw.Draw, elem: dict, events: list[dict]) -> None:
    """Render a month calendar grid with optional HA calendar events.

    Element fields (all optional except x/y/width/height)
    ──────────────────────────────────────────────────────
    x, y                  top-left corner
    width, height         bounding box (default 320×240)
    year, month           int – defaults to current month
    show_year_month       bool (default True)
    first_weekday         0=Mon … 6=Sun (default 0)
    lang                  "zh" | "en" (default "zh")
    show_event_text       bool (default True) – show summary text in cells
    max_events_per_cell   int (default 2)

    Color / style fields (all have sensible defaults)
    ─────────────────────────────────────────────────
    bg_color, header_bg_color, header_color,
    weekday_bg_color, weekday_color,
    day_color, today_color, today_bg_color,
    sunday_color, saturday_color,
    event_dot_color, event_text_color,
    grid_color, border_color, border_radius,
    header_height (default 30), weekday_height (default 20),
    header_font_size (18), weekday_font_size (12),
    day_font_size (15), event_font_size (9),
    font_path
    """

    ox = elem.get("x", 0)
    oy = elem.get("y", 0)
    W  = elem.get("width",  320)
    H  = elem.get("height", 240)

    today  = date.today()
    year   = int(elem.get("year",  today.year))
    month  = int(elem.get("month", today.month))
    fwd    = int(elem.get("first_weekday", 0))
    lang   = elem.get("lang", "zh")
    show_hdr  = bool(elem.get("show_year_month", True))
    show_etxt = bool(elem.get("show_event_text", True))
    max_evt   = int(elem.get("max_events_per_cell", 2))

    def C(k, d): return _parse_color(elem.get(k, d))
    bg_col   = C("bg_color",         "white")
    hdr_bg   = C("header_bg_color",  "#222222")
    hdr_fg   = C("header_color",     "white")
    wd_bg    = C("weekday_bg_color",  "#eeeeee")
    wd_fg    = C("weekday_color",     "#555555")
    day_fg   = C("day_color",         "black")
    tod_fg   = C("today_color",       "white")
    tod_bg   = C("today_bg_color",    "#444444")
    sun_fg   = C("sunday_color",      "#cc0000")
    sat_fg   = C("saturday_color",    "#0055cc")
    dot_col  = C("event_dot_color",   "#e06030")
    evt_fg   = C("event_text_color",  "#333333")
    grid_col = C("grid_color",        "#dddddd")
    bdr_col  = C("border_color",      "#999999")
    bdr_r    = int(elem.get("border_radius", 6))

    fp       = elem.get("font_path")
    hfont    = _resolve_font(fp, int(elem.get("header_font_size",  18)))
    wfont    = _resolve_font(fp, int(elem.get("weekday_font_size", 12)))
    dfont    = _resolve_font(fp, int(elem.get("day_font_size",     15)))
    efont    = _resolve_font(fp, int(elem.get("event_font_size",    9)))

    # background
    _rrect(draw, ox, oy, W, H, bdr_r, fill=bg_col)

    # header
    hdr_h = int(elem.get("header_height", 30)) if show_hdr else 0
    if show_hdr:
        _rrect(draw, ox, oy, W, hdr_h, bdr_r, fill=hdr_bg, clip_btm=True)
        title = (f"{year}年 {month}月" if lang == "zh"
                 else datetime(year, month, 1).strftime("%B %Y"))
        _tcenter(draw, ox, oy, W, hdr_h, title, hdr_fg, hfont)

    # weekday label row
    wd_h = int(elem.get("weekday_height", 20))
    wy   = oy + hdr_h
    draw.rectangle([ox, wy, ox + W, wy + wd_h], fill=wd_bg)

    WLBLS = (["一","二","三","四","五","六","日"] if lang == "zh"
             else ["Mo","Tu","We","Th","Fr","Sa","Su"])
    wlbls  = WLBLS[fwd:] + WLBLS[:fwd]
    cell_w = W / 7

    for col, lbl in enumerate(wlbls):
        awd = (fwd + col) % 7          # 0=Mon … 6=Sun
        lc  = sun_fg if awd == 6 else (sat_fg if awd == 5 else wd_fg)
        _tcenter(draw, ox + col*cell_w, wy, cell_w, wd_h, lbl, lc, wfont)

    # day cells
    grid_y0 = wy + wd_h
    grid_h  = H - hdr_h - wd_h
    cal     = _cal_mod.Calendar(firstweekday=fwd)
    weeks   = cal.monthdatescalendar(year, month)
    cell_h  = grid_h / max(len(weeks), 1)

    # index events by local date
    ebd: dict[date, list[str]] = {}
    for ev in (events or []):
        raw  = str(ev.get("start") or ev.get("start_time", ""))
        summ = str(ev.get("summary", ev.get("message", "事件")))
        try:
            d = (datetime.fromisoformat(raw.replace("Z","")).date()
                 if ("T" in raw or " " in raw)
                 else date.fromisoformat(raw[:10]))
            ebd.setdefault(d, []).append(summ)
        except Exception:
            pass

    for ri, week in enumerate(weeks):
        cy = grid_y0 + ri * cell_h
        for ci, ddate in enumerate(week):
            cx       = ox + ci * cell_w
            cur_mo   = (ddate.month == month)
            is_today = (ddate == today)
            awd      = (fwd + ci) % 7

            draw.rectangle([cx, cy, cx + cell_w - 1, cy + cell_h - 1],
                           fill=bg_col, outline=grid_col, width=1)

            if is_today:
                cr = min(cell_w, cell_h) * 0.36
                tx, ty = cx + cell_w*0.5, cy + cell_h*0.28
                draw.ellipse([tx-cr, ty-cr, tx+cr, ty+cr], fill=tod_bg)
                nc = tod_fg
            elif not cur_mo:
                nc = grid_col
            elif awd == 6:
                nc = sun_fg
            elif awd == 5:
                nc = sat_fg
            else:
                nc = day_fg

            _tcenter(draw, cx, cy, cell_w, cell_h * 0.52,
                     str(ddate.day), nc, dfont)

            day_evts = ebd.get(ddate, [])
            if day_evts:
                dr = max(2, cell_w * 0.07)
                dx, dy = cx + cell_w*0.5, cy + cell_h*0.58
                draw.ellipse([dx-dr, dy-dr, dx+dr, dy+dr], fill=dot_col)
                if show_etxt and cell_h > 38:
                    lh = int(elem.get("event_font_size", 9)) + 2
                    for ei, summ in enumerate(day_evts[:max_evt]):
                        trunc = _trunc(draw, summ, efont, cell_w - 4)
                        draw.text((cx+2, dy + dr + 2 + ei*lh),
                                  trunc, fill=evt_fg, font=efont)

    # outer border
    _rrect(draw, ox, oy, W, H, bdr_r, outline=bdr_col, width=1)


# ─── Drawing helpers ──────────────────────────────────────

def _rrect(draw, x, y, w, h, r, fill=None, outline=None, width=1,
           clip_btm=False):
    """Rounded rectangle."""
    x, y, w, h = int(x), int(y), int(w), int(h)
    r = max(0, min(r, w//2, h//2))
    x1, y1 = x + w, y + h
    if r == 0:
        draw.rectangle([x, y, x1, y1], fill=fill, outline=outline, width=width)
        return
    if fill:
        draw.rectangle([x+r, y,   x1-r, y1  ], fill=fill)
        draw.rectangle([x,   y+r, x1,   y1-r], fill=fill)
        for cx, cy in [(x, y), (x1-2*r, y), (x, y1-2*r), (x1-2*r, y1-2*r)]:
            draw.ellipse([cx, cy, cx+2*r, cy+2*r], fill=fill)
    if outline:
        kw = dict(fill=outline, width=width)
        draw.arc([x,       y,      x+2*r,  y+2*r ],  180, 270, **kw)
        draw.arc([x1-2*r,  y,      x1,     y+2*r ],  270, 360, **kw)
        if not clip_btm:
            draw.arc([x,      y1-2*r, x+2*r,  y1 ],   90, 180, **kw)
            draw.arc([x1-2*r, y1-2*r, x1,     y1 ],    0,  90, **kw)
        draw.line([x+r,  y,  x1-r, y ], **kw)
        if not clip_btm:
            draw.line([x+r, y1, x1-r, y1], **kw)
        draw.line([x,  y+r, x,  y1-r], **kw)
        draw.line([x1, y+r, x1, y1-r], **kw)


def _tcenter(draw, rx, ry, rw, rh, text, color, font):
    try:
        bb = draw.textbbox((0, 0), text, font=font)
        tw, th = bb[2]-bb[0], bb[3]-bb[1]
    except Exception:
        tw, th = len(text)*8, 14
    draw.text((rx + (rw-tw)/2, ry + (rh-th)/2), text, fill=color, font=font)


def _trunc(draw, text: str, font, max_w: float) -> str:
    try:
        if draw.textlength(text, font=font) <= max_w:
            return text
        while len(text) > 1:
            text = text[:-1]
            if draw.textlength(text + "…", font=font) <= max_w:
                return text + "…"
        return ""
    except Exception:
        return text[:max(1, int(max_w//8))]
