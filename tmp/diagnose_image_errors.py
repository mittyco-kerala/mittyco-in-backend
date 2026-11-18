from collections import Counter
from pathlib import Path

from PIL import Image

root = Path(r"D:\mittyco-in-backend\uploads")
extensions = {".jpg", ".jpeg", ".png", ".webp", ".avif", ".gif", ".bmp", ".tif", ".tiff"}
errors = Counter()
extension_counts = Counter()
samples = {}

for path in root.rglob("*"):
    if not path.is_file() or path.suffix.lower() not in extensions:
        continue
    try:
        with Image.open(path) as image:
            image.size
    except Exception as exc:
        key = (path.suffix.lower(), type(exc).__name__, str(exc)[:140])
        errors[key] += 1
        extension_counts[path.suffix.lower()] += 1
        samples.setdefault(key, str(path))

print("errors by extension", dict(extension_counts))
for key, count in errors.most_common(20):
    print(count, key[0], key[1], key[2])
    print(" sample", samples[key])
