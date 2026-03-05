#!/usr/bin/env python3
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageFilter

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"


def load_font(size: int):
    for name in [
        "/System/Library/Fonts/Supplemental/Avenir Next.ttc",
        "/System/Library/Fonts/PingFang.ttc",
        "/System/Library/Fonts/Helvetica.ttc",
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


def lobster_avatar(size=192):
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    # body
    d.ellipse((8, 18, size - 8, size - 8), fill=(255, 106, 59))
    # claws
    d.ellipse((8, 0, 70, 62), fill=(255, 86, 46))
    d.ellipse((size - 70, 0, size - 8, 62), fill=(255, 86, 46))
    # eyes
    d.ellipse((60, 68, 84, 92), fill=(255, 255, 255))
    d.ellipse((108, 68, 132, 92), fill=(255, 255, 255))
    d.ellipse((68, 76, 76, 84), fill=(42, 42, 42))
    d.ellipse((116, 76, 124, 84), fill=(42, 42, 42))
    # smile
    d.arc((52, 86, 140, 142), 20, 160, fill=(255, 255, 255), width=6)
    return img


def main():
    qr_path = DATA / "my-lobster-qr-latest.png"
    out = DATA / "my-lobster-qr-card.png"
    if not qr_path.exists():
        raise SystemExit(f"QR not found: {qr_path}")

    card_w, card_h = 1080, 1680
    card = Image.new("RGB", (card_w, card_h), (242, 246, 252))
    draw = ImageDraw.Draw(card)

    title_f = load_font(64)
    sub_f = load_font(34)
    body_f = load_font(40)
    small_f = load_font(28)

    # avatar centered
    avatar = lobster_avatar(192)
    card.paste(avatar, ((card_w - 192) // 2, 96), avatar)

    draw_center_text(draw, "Lobster Link", 318, title_f, (30, 38, 50), card_w)
    draw_center_text(draw, "让龙虾和龙虾协作起来", 398, sub_f, (93, 105, 122), card_w)

    # centered panel with soft shadow
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
    draw_center_text(draw, "Lobster:// Secure Connect", panel_y + 790, small_f, (120, 130, 146), card_w)

    draw_center_text(draw, "Powered by Lobster Link", 1560, small_f, (143, 152, 168), card_w)

    out.parent.mkdir(parents=True, exist_ok=True)
    card.save(out, quality=95)
    print(out)


if __name__ == "__main__":
    main()
