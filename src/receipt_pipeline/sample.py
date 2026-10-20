"""Pinned-source, deterministic sampling; images remain outside Git."""
import hashlib
import json
import random
from pathlib import Path

DATASET = "naver-clova-ix/cord-v2"
SEED = 20261020


def selected_indices(size=800, count=200):
    return sorted(random.Random(SEED).sample(range(size), count))


def download(root=Path("data")):
    from datasets import load_dataset
    from huggingface_hub import HfApi

    root.mkdir(parents=True, exist_ok=True)
    manifest = root / "manifest.json"
    # Once resolved, reuse the immutable revision, even after upstream changes.
    revision = (json.loads(manifest.read_text())["revision"] if manifest.exists()
                else HfApi().dataset_info(DATASET).sha)
    dataset = load_dataset(DATASET, revision=revision, split="train", streaming=True)
    wanted = set(selected_indices())
    rows = []
    for index, row in enumerate(dataset):
        if index not in wanted:
            continue
        image = root / "images" / f"train-{index:04}.png"
        image.parent.mkdir(exist_ok=True)
        row["image"].save(image, format="PNG")
        labels = json.loads(row["ground_truth"])
        rows.append({"id": f"train-{index:04}", "index": index,
                     "image": str(image), "sha256": hashlib.sha256(image.read_bytes()).hexdigest(),
                     "labels": labels})
        if len(rows) == len(wanted):
            break
    if len(rows) != 200:
        raise RuntimeError("Incomplete sample; manifest not published")
    payload = {"dataset": DATASET, "revision": revision, "seed": SEED,
               "split": "train", "receipts": rows}
    manifest.write_text(json.dumps(payload, indent=2))
    return payload


def load_manifest(root=Path("data")):
    return json.loads((root / "manifest.json").read_text())
