from collections import Counter, defaultdict
from pathlib import Path

from PIL import Image

root = Path(r"D:\mittyco-in-backend\uploads")
exts = {".jpg", ".jpeg", ".png", ".webp", ".avif", ".gif", ".bmp", ".tif", ".tiff"}
by_folder = defaultdict(Counter)
valid_by_folder = Counter()
for path in root.rglob("*"):
    if not path.is_file() or path.suffix.lower() not in exts:
        continue
    try:
        with Image.open(path) as image:
            by_folder[path.parent.relative_to(root).as_posix()][image.size] += 1
            valid_by_folder[path.parent.relative_to(root).as_posix()] += 1
    except Exception:
        pass
for folder in sorted(by_folder):
    common = ", ".join(f"{size[0]}x{size[1]} ({count})" for size, count in by_folder[folder].most_common(8))
    print(f"{folder}: valid={valid_by_folder[folder]}; {common}")
