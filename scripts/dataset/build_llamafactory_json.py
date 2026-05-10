#!/usr/bin/env python
"""
根据划分后的图像目录构建 LLaMA-Factory 所需的 JSON 数据。

期望的数据划分目录结构：
  split_root/
    train/<class_name>/*.png
    val/<class_name>/*.png
    test/<class_name>/*.png

生成文件：
  split_root/train.json
  split_root/val.json
  split_root/test.json
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


DEFAULT_PROMPT = (
    "<image>\u8bf7\u5224\u65ad\u8fd9\u5f20K\u7ebf\u56fe\u5c5e\u4e8e\u54ea\u4e00\u79cd\u5f62\u6001\u3002"
    "\u53ef\u9009\u7c7b\u522b\uff1a"
    "\u4e0a\u5347\u4e09\u89d2\u5f62\u3001"
    "\u4e0b\u964d\u4e09\u89d2\u5f62\u3001"
    "\u53cc\u5e95\u3001"
    "\u53cc\u9876\u3001"
    "\u5934\u80a9\u5e95\u3001"
    "\u5934\u80a9\u9876\u3001"
    "\u65e0\u660e\u663e\u5f62\u6001\u3002"
    "\u53ea\u8f93\u51fa\u7c7b\u522b\u540d\u79f0\u3002"
)

LABEL_MAP = {
    "ascending_triangle": "\u4e0a\u5347\u4e09\u89d2\u5f62",
    "descending_triangle": "\u4e0b\u964d\u4e09\u89d2\u5f62",
    "double_bottom": "\u53cc\u5e95",
    "double_top": "\u53cc\u9876",
    "head_and_shoulders_bottom": "\u5934\u80a9\u5e95",
    "head_and_shoulders_top": "\u5934\u80a9\u9876",
    "no_pattern": "\u65e0\u660e\u663e\u5f62\u6001",
}

IMAGE_PREFIX = "kline"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="根据划分后的图像目录生成 LLaMA-Factory JSON。")
    parser.add_argument(
        "--split-root",
        type=Path,
        default=Path("data_split_811"),
        help="包含 train/val/test 子目录的数据集根目录，默认 data_split_811。",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="train.json/val.json/test.json 的输出目录，默认直接写入 split_root。",
    )
    parser.add_argument(
        "--prompt",
        type=str,
        default=DEFAULT_PROMPT,
        help="每条样本的用户提示词内容。",
    )
    return parser.parse_args()


def build_records(split_root: Path, split: str, prompt: str) -> list[dict]:
    split_dir = split_root / split
    if not split_dir.exists() or not split_dir.is_dir():
        raise FileNotFoundError(f"缺少数据划分目录: {split_dir}")

    records: list[dict] = []
    class_dirs = sorted([p for p in split_dir.iterdir() if p.is_dir()], key=lambda p: p.name)
    for class_dir in class_dirs:
        class_name = class_dir.name
        if class_name not in LABEL_MAP:
            raise KeyError(
                f"发现未知类别目录: {class_name}。"
                f"请在当前脚本的 LABEL_MAP 中补充映射。"
            )
        label = LABEL_MAP[class_name]

        image_files = sorted([p for p in class_dir.iterdir() if p.is_file()], key=lambda p: p.name)
        for img_path in image_files:
            relative_image = img_path.relative_to(split_root).as_posix()
            if relative_image.startswith(("train/", "val/", "test/")):
                relative_image = f"{IMAGE_PREFIX}/{relative_image}"
            records.append(
                {
                    "messages": [
                        {"role": "user", "content": prompt},
                        {"role": "assistant", "content": label},
                    ],
                    "images": [relative_image],
                }
            )

    return records


def main() -> None:
    args = parse_args()
    split_root: Path = args.split_root
    output_dir: Path = args.output_dir if args.output_dir is not None else split_root
    prompt: str = args.prompt

    if not split_root.exists() or not split_root.is_dir():
        raise FileNotFoundError(f"未找到数据划分根目录: {split_root}")

    output_dir.mkdir(parents=True, exist_ok=True)

    for split in ("train", "val", "test"):
        records = build_records(split_root=split_root, split=split, prompt=prompt)
        out_path = output_dir / f"{split}.json"
        with out_path.open("w", encoding="utf-8") as f:
            json.dump(records, f, ensure_ascii=False, indent=2)
            f.write("\n")
        print(f"{split}\t{len(records)}\t{out_path}")


if __name__ == "__main__":
    main()
