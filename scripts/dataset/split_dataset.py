#!/usr/bin/env python
"""
将分类图像数据集按比例划分为 train/val/test 目录。

期望的原始目录结构：
  input_root/
    class_a/*.png
    class_b/*.png
    ...

输出目录结构：
  output_root/
    train/class_a/*.png
    val/class_a/*.png
    test/class_a/*.png
    ...
"""

from __future__ import annotations

import argparse
import math
import random
import shutil
from dataclasses import dataclass
from pathlib import Path


@dataclass
class ClassStat:
    class_name: str
    total: int
    train: int
    val: int
    test: int


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="按固定比例划分分类数据集。")
    parser.add_argument(
        "--input-root",
        type=Path,
        default=Path("data"),
        help="原始数据集根目录，默认 data。",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=Path("data_split_811"),
        help="划分后数据集的输出根目录，默认 data_split_811。",
    )
    parser.add_argument(
        "--train-ratio",
        type=float,
        default=0.8,
        help="训练集比例，默认 0.8。",
    )
    parser.add_argument(
        "--val-ratio",
        type=float,
        default=0.1,
        help="验证集比例，默认 0.1。",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="随机种子，默认 42。",
    )
    return parser.parse_args()


def copy_files(files: list[Path], target_dir: Path) -> None:
    target_dir.mkdir(parents=True, exist_ok=True)
    for src in files:
        shutil.copy2(src, target_dir / src.name)


def print_summary(stats: list[ClassStat]) -> None:
    header = ("class", "total", "train", "val", "test")
    rows = [[s.class_name, str(s.total), str(s.train), str(s.val), str(s.test)] for s in stats]
    widths = [
        max(len(header[i]), max((len(row[i]) for row in rows), default=0))
        for i in range(len(header))
    ]

    def fmt(values: tuple[str, ...] | list[str]) -> str:
        return "  ".join(values[i].ljust(widths[i]) for i in range(len(values)))

    print(fmt(list(header)))
    print(fmt(["-" * w for w in widths]))
    for row in rows:
        print(fmt(row))

    total_all = sum(s.total for s in stats)
    train_all = sum(s.train for s in stats)
    val_all = sum(s.val for s in stats)
    test_all = sum(s.test for s in stats)
    print()
    print(f"TOTAL: {total_all} (train={train_all}, val={val_all}, test={test_all})")


def main() -> None:
    args = parse_args()
    input_root: Path = args.input_root
    output_root: Path = args.output_root
    train_ratio: float = args.train_ratio
    val_ratio: float = args.val_ratio

    if not input_root.exists() or not input_root.is_dir():
        raise FileNotFoundError(f"未找到输入根目录: {input_root}")

    test_ratio = 1.0 - train_ratio - val_ratio
    if train_ratio <= 0 or val_ratio < 0 or test_ratio <= 0:
        raise ValueError("划分比例不合法：要求 train > 0、val >= 0 且 test > 0。")

    if output_root.exists():
        raise FileExistsError(
            f"输出根目录已存在: {output_root}。"
            "请先删除该目录，或传入新的 --output-root。"
        )

    rng = random.Random(args.seed)
    class_dirs = sorted([p for p in input_root.iterdir() if p.is_dir()], key=lambda p: p.name)
    if not class_dirs:
        raise RuntimeError(f"在 {input_root} 中没有找到任何类别目录。")

    for split in ("train", "val", "test"):
        (output_root / split).mkdir(parents=True, exist_ok=True)

    stats: list[ClassStat] = []
    for class_dir in class_dirs:
        class_name = class_dir.name
        files = sorted([p for p in class_dir.iterdir() if p.is_file()], key=lambda p: p.name)
        total = len(files)

        shuffled = files[:]
        rng.shuffle(shuffled)

        train_count = int(math.floor(total * train_ratio))
        val_count = int(math.floor(total * val_ratio))
        test_count = total - train_count - val_count

        train_files = shuffled[:train_count]
        val_files = shuffled[train_count : train_count + val_count]
        test_files = shuffled[train_count + val_count :]

        copy_files(train_files, output_root / "train" / class_name)
        copy_files(val_files, output_root / "val" / class_name)
        copy_files(test_files, output_root / "test" / class_name)

        stats.append(
            ClassStat(
                class_name=class_name,
                total=total,
                train=len(train_files),
                val=len(val_files),
                test=len(test_files),
            )
        )

    print_summary(stats)


if __name__ == "__main__":
    main()
