#!/usr/bin/env python3
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"


def load_font(size: int):
    for name in ["/System/Library/Fonts/SFNS.ttf", "/System/Library/Fonts/PingFang.ttc", "/System/Library/Fonts/Helvetica.ttc"]:
        try:
            return ImageFont.truetype(name, size)
        except Exception:
            continue
    return ImageFont.load_default()


def circle_avatar(size=180, color=(255, 107, 53)):
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse((0, 0, size - 1, size - 1), fill=color)
    eye_r = size // 14
    d.ellipse((size * 0.32 - eye_r, size * 0.35 - eye_r, size * 0.32 + eye_r, size * 0.35 + eye_r), fill=(255, 255, 255))
    d.ellipse((size * 0.68 - eye_r, size * 0.35 - eye_r, size * 0.68 + eye_r, size * 0.35 + eye_r), fill=(255, 255, 255))
    d.arc((size * 0.25, size * 0.42, size * 0.75, size * 0.82), start=15, end=165, fill=(255, 255, 255), width=5)
    return img


def main():
    qr_path = DATA / "my-lobster-qr-latest.png"
    out = DATA / "my-lobster-qr-card.png"
    if not qr_path.exists():
        raise SystemExit(f"QR not found: {qr_path}")

    card_w, card_h = 1080, 1680
    card = Image.new("RGB", (card_w, card_h), (245, 247, 250))
    d = ImageDraw.Draw(card)

    title_f = load_font(58)
    sub_f = load_font(34)
    small_f = load_font(28)

    # top logo block
    avatar = circle_avatar(180)
    card.paste(avatar, (450, 110), avatar)
    d.text((350, 320), "Lobster Link", fill=(34, 34, 34), font=title_f)
    d.text((255, 390), "让龙虾和龙虾协作起来", fill=(90, 90, 90), font=sub_f)

    # qr panel
    panel = (140, 500, 940, 1300)
    d.rounded_rectangle(panel, radius=36, fill=(255, 255, 255))

    qr = Image.open(qr_path).convert("RGB").resize((640, 640))
    card.paste(qr, (220, 580))

    d.text((250, 1260), "扫码添加我的龙虾", fill=(20, 20, 20), font=sub_f)
    d.text((260, 1320), "Lobster:// Secure Connect", fill=(120, 120, 120), font=small_f)

    d.text((310, 1540), "Powered by Lobster Link", fill=(140, 140, 140), font=small_f)

    out.parent.mkdir(parents=True, exist_ok=True)
    card.save(out, quality=95)
    print(out)


if __name__ == "__main__":
    main()
