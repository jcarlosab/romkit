"""Author ROMKit's 16-pixel vector icons and Windows/browser icon assets.

Run with uv run python scripts/desktop/generate_icons.py. All artwork is original,
made from integer rectangles, with nearest-neighbour scaling for crisp pixels.
"""
import os
from pathlib import Path
import struct

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon, QImage, QPainter, QColor, QFont, QFontDatabase
from PySide6.QtWidgets import QApplication

ROOT = Path(__file__).resolve().parents[2]
ASSETS = ROOT / "src/romkit_core/assets"
INK, BLUE, SKY, TEAL, MINT, GOLD, PAPER, RED = (
    "#182b49", "#3868d9", "#91bdff", "#168878", "#88dfbd", "#f5c65b", "#f4f6ed", "#c94f65")


def rect(x, y, w, h, color=INK):
    return f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="{color}"/>'


def arrow(direction, color=TEAL):
    pixels = [(7, 3, 2, 8), (5, 7, 6, 2), (6, 9, 4, 2), (7, 11, 2, 1)]
    if direction == "up":
        pixels = [(x, 15-y-h, w, h) for x,y,w,h in pixels]
    return ''.join(rect(x,y,w,h,color) for x,y,w,h in pixels)


def cartridge():
    return ''.join([rect(3,1,9,1),rect(2,2,12,12),rect(3,14,10,1),
                    rect(3,3,10,10,BLUE),rect(5,2,6,4,INK),rect(6,2,4,3,SKY),
                    rect(4,8,8,5,PAPER),rect(5,9,6,1,SKY),rect(5,11,4,1,BLUE),
                    rect(10,10,1,2,GOLD)])


def bubble():
    return ''.join([rect(2,2,12,1),rect(1,3,14,9),rect(3,12,4,2),rect(3,14,2,1),
                    rect(2,3,12,8,TEAL),rect(4,11,2,2,TEAL),
                    rect(5,5,4,1,PAPER),rect(4,6,1,4,PAPER),rect(9,6,1,4,PAPER),
                    rect(5,8,4,1,PAPER),rect(11,5,1,5,GOLD)])


def folder():
    return ''.join([rect(1,4,6,2),rect(1,6,14,8),rect(2,5,4,2,GOLD),
                    rect(2,7,12,6,GOLD),rect(3,8,10,1,PAPER)])


def document():
    return ''.join([rect(3,1,8,1),rect(2,2,11,13),rect(3,2,7,12,PAPER),
                    rect(10,5,2,9,PAPER),rect(10,2,1,3,SKY),
                    rect(4,5,4,1,BLUE),rect(4,8,6,1,BLUE),rect(4,11,4,1,BLUE)])


def lens():
    return ''.join([rect(8,6,5,1),rect(7,7,1,5),rect(13,7,1,5),rect(8,12,5,1),
                    rect(8,7,5,5,PAPER),rect(12,12,2,2,INK),rect(14,14,2,2,INK),
                    rect(9,8,2,1,SKY)])


def check():
    return ''.join(rect(x,y,w,h,TEAL) for x,y,w,h in [(2,8,3,2),(4,10,3,2),(6,8,3,2),(8,6,3,2),(10,4,3,2)])


def cross():
    return ''.join(rect(x,y,2,2,RED) for x,y in [(4,4),(6,6),(8,8),(10,10),(10,4),(8,6),(6,8),(4,10)])


def frame():
    return rect(2,2,12,12)+rect(3,3,10,10,PAPER)


def icons():
    picture = (rect(1,2,13,11)+rect(2,3,11,9,PAPER)+rect(3,4,2,2,GOLD)
               +rect(3,9,3,2,TEAL)+rect(5,7,3,4,TEAL)+rect(8,9,3,2,TEAL))
    disk = (rect(2,1,11,1)+rect(1,2,14,13)+rect(2,2,12,12,BLUE)
            +rect(4,2,7,4,INK)+rect(5,2,4,3,SKY)+rect(4,9,8,5,PAPER)+rect(6,10,4,1,BLUE))
    info = frame()+rect(7,4,2,2,BLUE)+rect(7,7,2,5,BLUE)
    return {
        # Original game-themed silhouettes: digital pet device and feline mascot.
        "digimon": (rect(5,0,6,1)+rect(3,1,10,2)+rect(2,3,12,10)+rect(3,13,10,2)+rect(5,15,6,1)
            +rect(3,3,10,10,GOLD)+rect(4,2,8,2,GOLD)+rect(4,12,8,2,GOLD)
            +rect(4,4,8,7,INK)+rect(5,5,6,5,MINT)
            +rect(6,6,1,1,INK)+rect(9,6,1,1,INK)+rect(7,8,2,1,TEAL)
            +rect(4,11,2,2,BLUE)+rect(7,12,2,1,RED)+rect(10,11,2,2,BLUE)
            +rect(6,1,4,1,PAPER)),
        "pokapoka": (rect(1,1,3,5)+rect(12,1,3,5)+rect(4,3,8,1)+rect(1,6,14,6)+rect(3,12,10,2)
            +rect(2,2,1,3,GOLD)+rect(13,2,1,3,GOLD)+rect(3,5,10,7,GOLD)
            +rect(2,6,12,5,GOLD)+rect(4,11,8,2,GOLD)+rect(5,4,6,2,PAPER)
            +rect(4,7,2,2,INK)+rect(10,7,2,2,INK)+rect(5,7,1,1,PAPER)+rect(10,7,1,1,PAPER)
            +rect(7,9,2,1,RED)+rect(7,10,1,1,INK)+rect(6,11,1,1,INK)+rect(8,11,1,1,INK)
            +rect(2,10,2,1,PAPER)+rect(12,10,2,1,PAPER)+rect(5,14,6,1,TEAL)),
        "studio": cartridge(), "translator": bubble(), "open-rom": cartridge()+rect(0,10,7,5,INK)+rect(1,11,5,3,GOLD),
        "open-project": folder(), "extract": rect(2,11,12,4)+rect(3,11,10,2,SKY)+arrow("down",BLUE),
        "search-text": document()+lens(), "search-images": picture+lens(),
        "import-translation": cartridge()+rect(0,7,6,2,TEAL)+rect(3,5,2,6,TEAL)+rect(5,7,2,2,MINT),
        "export-text": document()+arrow("up"), "save": disk, "validate": frame()+check(),
        "mark": frame()+check(), "unmark": frame()+rect(5,7,6,2,BLUE),
        "remove": rect(4,5,8,9)+rect(5,6,6,7,PAPER)+rect(3,3,10,2,RED)+rect(6,1,4,2,RED)+rect(6,7,1,5,RED)+rect(9,7,1,5,RED),
        "restore": rect(3,4,9,2,BLUE)+rect(11,6,2,6,BLUE)+rect(6,11,5,2,BLUE)+rect(1,5,4,2,BLUE)+rect(3,2,2,7,BLUE),
        "copy": rect(1,1,9,11)+rect(2,2,7,9,SKY)+rect(5,4,10,11)+rect(6,5,8,9,PAPER)+rect(8,7,4,1,BLUE)+rect(8,10,4,1,BLUE),
        "suggest": rect(7,1,2,12,TEAL)+rect(2,6,12,2,TEAL)+rect(5,4,6,6,GOLD)+rect(7,6,2,2,PAPER)+rect(12,1,2,2,BLUE)+rect(2,12,2,2,BLUE),
        "apply": bubble()+rect(9,10,6,5,PAPER)+rect(10,12,2,2,TEAL)+rect(12,10,2,2,TEAL),
        "info": info, "close": frame()+cross(), "exit": rect(3,1,9,14)+rect(4,2,7,12,BLUE)+rect(9,8,2,2,GOLD),
    }


def ico(path, source):
    from PySide6.QtCore import QBuffer, QIODevice
    chunks = []
    for size in (16, 24, 32, 48, 64, 128, 256):
        image = source.pixmap(16,16).toImage().scaled(size,size,Qt.AspectRatioMode.IgnoreAspectRatio,Qt.TransformationMode.FastTransformation)
        buffer = QBuffer()
        buffer.open(QIODevice.OpenModeFlag.WriteOnly)
        image.save(buffer,"PNG")
        chunks.append((size,bytes(buffer.data())))
    offset = 6 + 16 * len(chunks)
    result = bytearray(struct.pack('<HHH',0,1,len(chunks)))
    for size, png in chunks:
        result.extend(struct.pack('<BBBBHHII',size % 256,size % 256,0,0,1,32,len(png),offset))
        offset += len(png)
    for _,png in chunks:
        result.extend(png)
    path.write_bytes(result)


def main():
    app = QApplication.instance() or QApplication([])
    fonts = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"
    for name in ("segoeui.ttf", "segoeuib.ttf"):
        if (fonts / name).exists():
            QFontDatabase.addApplicationFont(str(fonts / name))
    for name,body in icons().items():
        path = ASSETS / f'{name}.svg'
        path.write_text('<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 16 16" shape-rendering="crispEdges">'+body+'</svg>\n',encoding='utf-8')
        if name in ('studio','translator','digimon','pokapoka'):
            source = QIcon(str(path))
            ico(ASSETS / f'{name}.ico',source)
            source.pixmap(16,16).toImage().scaled(256,256,Qt.AspectRatioMode.IgnoreAspectRatio,Qt.TransformationMode.FastTransformation).save(str(ASSETS / f'{name}.png'))
            ico(ASSETS / f'{name}-favicon.ico',source)
    names = list(icons())
    sheet = QImage(640, ((len(names) + 4) // 5) * 112, QImage.Format.Format_ARGB32)
    sheet.fill(QColor('#f5f7fa'))
    painter = QPainter(sheet)
    painter.setFont(QFont('Segoe UI', 9))
    painter.setPen(QColor(INK))
    for index,name in enumerate(names):
        x,y = index % 5 * 128,index // 5 * 112
        image = QIcon(str(ASSETS / f'{name}.svg')).pixmap(16,16).toImage().scaled(48,48,
            Qt.AspectRatioMode.IgnoreAspectRatio,Qt.TransformationMode.FastTransformation)
        painter.drawImage(x+40,y+16,image)
        painter.drawText(x,y+72,128,24,Qt.AlignmentFlag.AlignCenter,name)
    painter.end()
    sheet.save(str(ROOT / 'docs/icons.png'))


if __name__ == '__main__':
    main()
