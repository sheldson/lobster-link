#!/usr/bin/env python3
import argparse
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageFilter

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"


def load_en_font(size: int):
    for name in [
        "/System/Library/Fonts/Supplemental/Avenir Next.ttc",
        "/System/Library/Fonts/Helvetica.ttc",
    ]:
        try:
            return ImageFont.truetype(name, size)
        except Exception:
            continue
    return ImageFont.load_default()


def load_cn_font(size: int):
    for name in [
        "/System/Library/Fonts/PingFang.ttc",
        "/System/Library/Fonts/Hiragino Sans GB.ttc",
    ]:
        try:
            return ImageFont.truetype(name, size)
        except Exception:
            continue
    return ImageFont.load_default()


def draw_center_text(draw, text, y, font, color, card_w):
    box = draw.textbbox((0, 0), text, font=font)
    w = box[2] - box[0]
    x = (card_w - w) // 2
    draw.text((x, y), text, font=font, fill=color)


def lobster_avatar(size=220):
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    # antennas
    d.line((size * 0.43, size * 0.20, size * 0.28, size * 0.03), fill=(255, 95, 56), width=7)
    d.line((size * 0.57, size * 0.20, size * 0.72, size * 0.03), fill=(255, 95, 56), width=7)

    # claws (more lobster-like)
    d.ellipse((8, 30, 88, 110), fill=(255, 92, 52))
    d.polygon([(38, 20), (68, 5), (78, 30), (48, 40)], fill=(255, 76, 40))
    d.ellipse((size - 88, 30, size - 8, 110), fill=(255, 92, 52))
    d.polygon([(size - 38, 20), (size - 68, 5), (size - 78, 30), (size - 48, 40)], fill=(255, 76, 40))

    # body + tail segments
    d.ellipse((26, 48, size - 26, size - 18), fill=(255, 112, 68))
    d.rounded_rectangle((62, 138, size - 62, 168), radius=16, fill=(255, 140, 88))
    d.rounded_rectangle((72, 166, size - 72, 194), radius=14, fill=(255, 156, 106))

    # eyes
    d.ellipse((78, 88, 102, 112), fill=(255, 255, 255))
    d.ellipse((118, 88, 142, 112), fill=(255, 255, 255))
    d.ellipse((86, 96, 94, 104), fill=(24, 28, 34))
    d.ellipse((126, 96, 134, 104), fill=(24, 28, 34))

    # mouth
    d.arc((72, 112, 148, 152), 20, 160, fill=(255, 255, 255), width=6)
    return img


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--owner", default="林晓胜")
    args = ap.parse_args()

    qr_path = DATA / "my-lobster-qr-latest.png"
    out = DATA / "my-lobster-qr-card.png"
    if not qr_path.exists():
        raise SystemExit(f"QR not found: {qr_path}")

    card_w, card_h = 1080, 1680
    card = Image.new("RGB", (card_w, card_h), (242, 246, 252))
    draw = ImageDraw.Draw(card)

    title_f = load_en_font(62)
    cn_f = load_cn_font(38)
    body_f = load_cn_font(42)
    small_f = load_en_font(28)
    name_f = load_cn_font(40)

    # avatar centered
    avatar = lobster_avatar(220)
    card.paste(avatar, ((card_w - 220) // 2, 82), avatar)

    draw_center_text(draw, "Lobster Connect", 330, title_f, (30, 38, 50), card_w)
    draw_center_text(draw, "让龙虾和龙虾协作起来", 412, cn_f, (93, 105, 122), card_w)

    # centered panel with shadow
    panel_w, panel_h = 820, 860
    panel_x = (card_w - panel_w) // 2
    panel_y = 500

    shadow = Image.new("RGBA", (panel_w, panel_h), (0, 0, 0, 0))
    sd = ImageDraw.Draw(shadow)
    sd.rounded_rectangle((0, 0, panel_w, panel_h), radius=40, fill=(0, 0, 0, 68))
    shadow = shadow.filter(ImageFilter.GaussianBlur(12))
    card.paste(shadow, (panel_x, panel_y + 12), shadow)

    draw.rounded_rectangle((panel_x, panel_y, panel_x + panel_w, panel_y + panel_h), radius=40, fill=(255, 255, 255))

    qr = Image.open(qr_path).convert("RGB").resize((640, 640))
    qr_x = (card_w - 640) // 2
    qr_y = panel_y + 70
    card.paste(qr, (qr_x, qr_y))

    draw_center_text(draw, "扫码添加我的龙虾", panel_y + 735, body_f, (24, 28, 34), card_w)
    draw_center_text(draw, "Lobster:// Secure Connect", panel_y + 794, small_f, (120, 130, 146), card_w)

    draw_center_text(draw, f"{args.owner} Lobster", 1550, name_f, (70, 78, 92), card_w)

    out.parent.mkdir(parents=True, exist_ok=True)
    card.save(out, quality=95)
    print(out)


if __name__ == "__main__":
    main()
