#!/usr/bin/env python3
"""PixelSeal watermarking CLI for Bavaria assets.

Usage:
    # Single embed
    python3 watermark.py embed --input master.jpg --message "AAH-provoque" --output watermarked.avif

    # Batch embed with mapping CSV
    python3 watermark.py embed --mapping mapping.csv --output-dir watermarked/

    # Verify
    python3 watermark.py verify --input suspect.jpg

    # Verify against known message
    python3 watermark.py verify --input suspect.jpg --message "AAH-provoque"
"""

import argparse
import csv
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import torch
import torchvision.transforms as T
from PIL import Image


NBITS = 256  # PixelSeal payload size
AVIF_QUALITY = 90
BIT_ACCURACY_THRESHOLD = 0.75


def text_to_bits(text: str) -> torch.Tensor:
    """Encode a UTF-8 string into a 256-bit binary tensor."""
    raw = text.encode("utf-8")
    if len(raw) > NBITS // 8:
        print(f"Warning: message '{text}' is {len(raw)} bytes, truncating to {NBITS // 8} bytes", file=sys.stderr)
        raw = raw[: NBITS // 8]
    bits = []
    for byte in raw:
        for i in range(7, -1, -1):
            bits.append((byte >> i) & 1)
    # Zero-pad to 256 bits
    bits.extend([0] * (NBITS - len(bits)))
    return torch.tensor(bits, dtype=torch.float32).unsqueeze(0)


def bits_to_text(bits: torch.Tensor) -> str:
    """Decode a 256-bit binary tensor back to a UTF-8 string."""
    bit_list = (bits > 0).int().tolist()
    chars = []
    for i in range(0, len(bit_list), 8):
        byte_bits = bit_list[i : i + 8]
        if len(byte_bits) < 8:
            break
        val = 0
        for b in byte_bits:
            val = (val << 1) | b
        if val == 0:
            break  # Stop at null terminator
        chars.append(val)
    return bytes(chars).decode("utf-8", errors="replace")


REPO_DIR = Path(__file__).resolve().parent / "repo"


def load_model(device: str):
    """Load PixelSeal model."""
    # videoseal expects configs/ relative to CWD
    original_cwd = os.getcwd()
    os.chdir(REPO_DIR)
    try:
        import videoseal

        model = videoseal.load("pixelseal")
        model.eval()
        model.to(device)
        return model
    finally:
        os.chdir(original_cwd)


def get_device() -> str:
    """Detect best available device."""
    if torch.backends.mps.is_available():
        return "mps"
    if torch.cuda.is_available():
        return "cuda"
    return "cpu"


def embed_image(model, input_path: str, message: str, output_path: str, device: str) -> dict:
    """Embed a watermark into a single image. Returns manifest row dict."""
    raw_img = Image.open(input_path)
    has_alpha = raw_img.mode == "RGBA"
    alpha_channel = None
    if has_alpha:
        alpha_channel = raw_img.split()[-1]
        img = raw_img.convert("RGB")
    else:
        img = raw_img.convert("RGB")
    img_tensor = T.ToTensor()(img).unsqueeze(0).to(device)
    msg_tensor = text_to_bits(message).to(device)

    with torch.no_grad():
        outputs = model.embed(img_tensor, msgs=msg_tensor, is_video=False)

    watermarked = outputs["imgs_w"][0].cpu()
    watermarked_pil = T.ToPILImage()(watermarked)

    # Re-apply alpha channel if input was RGBA
    if has_alpha and alpha_channel is not None:
        r, g, b = watermarked_pil.split()
        watermarked_pil = Image.merge("RGBA", (r, g, b, alpha_channel))

    # Save — RGBA goes straight to PNG, RGB tries AVIF first
    actual_output = output_path
    if has_alpha:
        if not output_path.lower().endswith(".png"):
            actual_output = output_path.rsplit(".", 1)[0] + ".png"
        watermarked_pil.save(actual_output, compress_level=1)
    else:
        try:
            watermarked_pil.save(output_path, quality=AVIF_QUALITY)
        except Exception as e:
            if output_path.lower().endswith(".avif"):
                actual_output = output_path.rsplit(".", 1)[0] + ".png"
                print(f"Warning: AVIF save failed ({e}), saving as PNG: {actual_output}", file=sys.stderr)
                watermarked_pil.save(actual_output)
            else:
                raise

    # Verify roundtrip
    verify_img = Image.open(actual_output).convert("RGB")
    verify_tensor = T.ToTensor()(verify_img).unsqueeze(0).to(device)
    with torch.no_grad():
        detected = model.detect(verify_tensor, is_video=False)
    preds = detected["preds"][:, 1:]
    accuracy = (preds > 0).float().eq(msg_tensor).float().mean().item()

    if accuracy < BIT_ACCURACY_THRESHOLD:
        print(f"Warning: bit accuracy {accuracy:.1%} below threshold {BIT_ACCURACY_THRESHOLD:.0%} for {actual_output}", file=sys.stderr)

    return {
        "input_path": input_path,
        "output_path": actual_output,
        "parent_code": Path(input_path).stem,
        "message": message,
        "bit_accuracy": f"{accuracy:.4f}",
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "status": "ok" if accuracy >= BIT_ACCURACY_THRESHOLD else "low_accuracy",
    }


def cmd_embed(args):
    device = get_device()
    print(f"Device: {device}")
    model = load_model(device)
    print("Model loaded.")

    rows = []

    if args.mapping:
        # Batch mode with mapping CSV
        os.makedirs(args.output_dir or ".", exist_ok=True)
        with open(args.mapping) as f:
            reader = csv.DictReader(f)
            for entry in reader:
                input_code = entry["input_code"].strip()
                output_code = entry["output_code"].strip()
                input_path = os.path.join(args.input_dir or ".", f"{input_code}.*")

                # Find the actual input file
                import glob

                matches = glob.glob(os.path.join(args.input_dir or ".", f"{input_code}.*"))
                matches = [m for m in matches if m.lower().endswith((".png", ".jpg", ".jpeg", ".webp"))]
                if not matches:
                    print(f"Skipping {input_code}: no image file found", file=sys.stderr)
                    rows.append({
                        "input_path": f"{input_code}.*",
                        "output_path": "",
                        "parent_code": input_code,
                        "message": "",
                        "bit_accuracy": "",
                        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                        "status": "not_found",
                    })
                    continue

                input_path = matches[0]
                message = entry.get("message", f"{input_code}-provoque").strip()
                if not message:
                    message = f"{input_code}-provoque"
                input_is_rgba = Image.open(input_path).mode == "RGBA"
                out_ext = ".png" if input_is_rgba else ".avif"
                output_path = os.path.join(args.output_dir or ".", f"{output_code}{out_ext}")

                print(f"Embedding: {input_path} → {output_path} (message: {message})")
                row = embed_image(model, input_path, message, output_path, device)
                rows.append(row)
                print(f"  Bit accuracy: {row['bit_accuracy']} [{row['status']}]")

    elif args.input:
        # Single file mode
        message = args.message or f"{Path(args.input).stem}-provoque"
        input_is_rgba = Image.open(args.input).mode == "RGBA"
        default_ext = ".png" if input_is_rgba else ".avif"
        output = args.output or Path(args.input).stem + "-wm" + default_ext
        print(f"Embedding: {args.input} → {output} (message: {message})")
        row = embed_image(model, args.input, message, output, device)
        rows.append(row)
        print(f"  Bit accuracy: {row['bit_accuracy']} [{row['status']}]")
    else:
        print("Error: provide --input for single file or --mapping for batch", file=sys.stderr)
        sys.exit(1)

    # Write manifest
    if rows:
        manifest_path = args.manifest or (
            os.path.join(args.output_dir, "watermark-manifest.csv") if args.output_dir else "watermark-manifest.csv"
        )
        fieldnames = ["input_path", "output_path", "parent_code", "message", "bit_accuracy", "timestamp", "status"]
        with open(manifest_path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
        print(f"\nManifest: {manifest_path} ({len(rows)} entries)")


def cmd_verify(args):
    device = get_device()
    print(f"Device: {device}")
    model = load_model(device)
    print("Model loaded.")

    img = Image.open(args.input).convert("RGB")
    img_tensor = T.ToTensor()(img).unsqueeze(0).to(device)

    with torch.no_grad():
        detected = model.detect(img_tensor, is_video=False)

    preds = detected["preds"][:, 1:]
    extracted = bits_to_text(preds[0].cpu())
    print(f"Extracted message: {extracted}")

    if args.message:
        expected = text_to_bits(args.message)
        accuracy = (preds.cpu() > 0).float().eq(expected).float().mean().item()
        print(f"Bit accuracy vs expected: {accuracy:.1%}")
        if accuracy >= BIT_ACCURACY_THRESHOLD:
            print("MATCH — watermark verified.")
        else:
            print("NO MATCH — watermark not confirmed.")


def main():
    parser = argparse.ArgumentParser(description="PixelSeal watermarking CLI")
    sub = parser.add_subparsers(dest="command")

    embed_p = sub.add_parser("embed", help="Embed watermark into image(s)")
    embed_p.add_argument("--input", help="Single input image path")
    embed_p.add_argument("--message", help="Message to embed (default: {filename}-provoque)")
    embed_p.add_argument("--output", help="Single output path")
    embed_p.add_argument("--mapping", help="Batch mapping CSV (columns: input_code, output_code, message)")
    embed_p.add_argument("--input-dir", help="Input directory for batch mode")
    embed_p.add_argument("--output-dir", help="Output directory for batch mode")
    embed_p.add_argument("--manifest", help="Manifest CSV output path")

    verify_p = sub.add_parser("verify", help="Verify watermark in an image")
    verify_p.add_argument("--input", required=True, help="Image to verify")
    verify_p.add_argument("--message", help="Expected message (for accuracy comparison)")

    args = parser.parse_args()
    if args.command == "embed":
        cmd_embed(args)
    elif args.command == "verify":
        cmd_verify(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
