#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
print_raster.py — ESC/POS raster (GS v 0) robuste avec logs et options de debug.

Modes :
  Maintenance :
    - Annuler/vider buffer (CAN + ESC @) :
        python print_raster.py --cancel <serial> [--baud 9600]

    - Test texte "Hello ESC/POS" :
        python print_raster.py --hello <serial> [--baud 9600]

  Impression (2 syntaxes possibles) :
    a) Positionnelle :
        python print_raster.py <image> <serial> <width> [--baud 9600] [options...]
    b) Flags :
        python print_raster.py --print <image> --dev <serial> --width <px> [--baud 9600] [options...]

Options utiles (debug / rendu) :
  --preview out.png          : enregistre l'image 1‑bit réellement envoyée (aperçu)
  --dry-run out.bin          : écrit le flux ESC/POS dans un fichier, n'imprime PAS
  --no-dither                : pas de dithering (seuil fixe)
  --threshold 128            : seuil si --no-dither (0..255)
  --contrast 1.3             : contraste avant binarisation (1.0 = neutre)
  --gamma 1.0                : correction gamma (1.0 = neutre)
  --invert                   : inverse noir/blanc (utile si polarité inversée)
  --limit-lines N            : n'imprime que les N premières lignes (debug, économie papier)
  --no-autorotate            : désactive la rotation portrait automatique
  --chunk 4096               : taille des sous-écritures série
  --line-sleep 0.02          : pause entre bandes envoyées
  --pre-cancel               : envoie un cancel/reset avant impression

Par défaut : --baud 9600 (stable sur ta tête).
"""

import sys
import os
import time
import argparse
from PIL import Image, ImageOps, ImageEnhance

# Pillow: gestion des API dépréciées
try:
    from PIL.Image import Resampling
    RESAMPLING = Resampling.LANCZOS
except Exception:
    RESAMPLING = Image.LANCZOS

try:
    # Pillow >= 9
    DITHER_FS = Image.Dither.FLOYDSTEINBERG
    DITHER_NONE = Image.Dither.NONE
except Exception:
    # Compat anciens Pillow
    DITHER_FS = 1
    DITHER_NONE = 0

try:
    import serial
except ImportError:
    sys.stderr.write("[ERREUR] 'pyserial' manquant (installe: pip install pyserial)\n")
    sys.exit(1)


def log(msg: str):
    sys.stderr.write("[PRINT] " + msg + "\n")


def open_serial(dev: str, baud: int):
    """Ouvre le port série en 8N1, flow control OFF, timeouts actifs."""
    log(f"Ouvre {dev} @ {baud} 8N1, sans flow control")
    return serial.Serial(
        dev,
        baudrate=int(baud),
        bytesize=8,
        parity='N',
        stopbits=1,
        timeout=2,          # lecture
        write_timeout=10,   # écriture (évite blocage infini)
        xonxoff=False,
        rtscts=False,
        dsrdtr=False
    )


def cancel_and_reset(ser: serial.Serial):
    """Tentative d'annulation d'un job en cours + reset imprimante."""
    log("Envoi Cancel (CAN) + Reset (ESC @)")
    ser.write(b'\x18\x18\x18')     # CAN (Cancel) x3
    ser.write(b'\x1b@')            # ESC @ (reset)
    ser.write(b'\n\n')             # avance papier
    ser.write(b'\x1dV\x01')        # cut partiel (inoffensif si non supporté)
    ser.flush()
    time.sleep(0.1)


def send_hello(ser: serial.Serial):
    ser.reset_input_buffer()
    ser.reset_output_buffer()
    ser.write(b'\x1b@')               # init
    ser.write(b'Hello ESC/POS!\n\n')
    ser.write(b'\x1dV\x01')           # cut partiel si dispo
    ser.flush()
    log("Hello envoyé")


def apply_gamma(imgL: Image.Image, gamma: float) -> Image.Image:
    """Application simple d'un gamma sur une image niveaux de gris."""
    if abs(gamma - 1.0) < 1e-3:
        return imgL
    lut = [min(255, int((i / 255.0) ** (1.0 / gamma) * 255 + 0.5)) for i in range(256)]
    return imgL.point(lut)


def prepare_image(path: str,
                  target_w: int,
                  contrast: float,
                  gamma: float,
                  use_dither: bool,
                  threshold: int,
                  autorotate: bool,
                  preview: str | None):
    """Charge, redimensionne, convertit en 1‑bit et renvoie (image1bit, bytes bruts)."""
    log(f"Charge image: {path}")
    img = Image.open(path).convert('RGB')

    if autorotate and img.width > img.height:
        img = img.rotate(90, expand=True)
        log("Rotation 90° (portrait) [auto]")
    else:
        log("Rotation auto désactivée" if not autorotate else "Pas de rotation nécessaire")

    w = int(target_w)
    h = int(img.height * w / img.width)
    img = img.resize((w, h), RESAMPLING)

    imgL = ImageOps.autocontrast(img.convert('L'))
    if abs(contrast - 1.0) > 1e-3:
        imgL = ImageEnhance.Contrast(imgL).enhance(contrast)
    imgL = apply_gamma(imgL, gamma)

    if use_dither:
        img1 = imgL.convert('1', dither=DITHER_FS)
        method = "dither=FS"
    else:
        th = int(threshold)
        # Seuil fixe → 0 (noir) si < th, 255 (blanc) sinon
        img1 = imgL.point(lambda p: 0 if p < th else 255).convert('1', dither=DITHER_NONE)
        method = f"no-dither threshold={th}"

    # Stat noir/blanc via histogramme (pour '1', valeurs 0 et 255)
    hist = img1.histogram()
    black = hist[0] if len(hist) > 0 else 0
    white = hist[255] if len(hist) > 255 else 0
    total = black + white if (black + white) > 0 else 1
    black_ratio = 100.0 * black / total
    log(f"Image prête: {img1.width}x{img1.height} (1-bit, {method}, noir={black_ratio:.1f}%)")

    if preview:
        try:
            img1.save(preview)
            log(f"Preview écrit: {preview}")
        except Exception as e:
            log(f"Preview échec: {e}")

    raw_bytes = img1.tobytes()  # bits packés (MSB→pixel gauche), row-major
    return img1, raw_bytes


def invert_bits(buf: bytes) -> bytes:
    return bytes((~b) & 0xFF for b in buf)


def build_raster_bands(img1: Image.Image,
                       raw_bytes: bytes,
                       invert: bool,
                       limit_lines: int | None):
    """Prépare l'itération par bandes ≤255 lignes pour GS v 0 (m=0)."""
    width_bytes = (img1.width + 7) // 8
    height = img1.height if not limit_lines else min(limit_lines, img1.height)

    if invert:
        raw_bytes = invert_bits(raw_bytes)

    def iter_bands():
        y = 0
        while y < height:
            slice_h = min(255, height - y)
            header = b'\x1d\x76\x30\x00' + bytes([
                width_bytes & 0xFF, (width_bytes >> 8) & 0xFF,
                slice_h & 0xFF, (slice_h >> 8) & 0xFF
            ])
            start = y * width_bytes
            end = start + slice_h * width_bytes
            yield (y, slice_h, header, memoryview(raw_bytes)[start:end])
            y += slice_h

    log(f"Raster: {img1.width} px ({width_bytes} bytes/ligne) x {height} lignes")
    return width_bytes, height, iter_bands


def send_raster(ser: serial.Serial,
                img1: Image.Image,
                raw_bytes: bytes,
                invert: bool,
                limit_lines: int | None,
                chunk: int,
                line_sleep: float):
    """Envoi du raster en bandes, avec sous-écritures et pauses tampon."""
    ser.reset_input_buffer()
    ser.reset_output_buffer()
    ser.write(b'\x1b@')   # ESC @ init
    ser.write(b'\x1b2')   # interligne par défaut

    width_bytes, height, bands = build_raster_bands(img1, raw_bytes, invert, limit_lines)
    sent_lines = 0
    band_idx = 0

    for y, slice_h, header, block in bands():
        band_idx += 1
        ser.write(header)
        L = len(block)
        sent = 0
        while sent < L:
            n = ser.write(block[sent:sent + chunk])
            if n is None:
                raise serial.SerialTimeoutException("write() timeout")
            sent += n
        sent_lines += slice_h
        log(f"  - Bande {band_idx}: lignes {y}..{y + slice_h - 1} (envoyées: {sent_lines}/{height})")
        time.sleep(line_sleep)

    ser.write(b'\n\n\n')
    ser.write(b'\x1dV\x01')  # cut partiel si supporté
    ser.flush()
    log("Raster envoyé")


def write_raster_to_file(img1: Image.Image,
                         raw_bytes: bytes,
                         out_path: str,
                         invert: bool,
                         limit_lines: int | None):
    """Génère le flux ESC/POS vers un fichier (debug / dry-run)."""
    _, _, bands = build_raster_bands(img1, raw_bytes, invert, limit_lines)
    with open(out_path, 'wb') as f:
        f.write(b'\x1b@')
        f.write(b'\x1b2')
        for _, _, header, block in bands():
            f.write(header)
            f.write(block)
        f.write(b'\n\n\n\x1dV\x01')
    log(f"Flux ESC/POS écrit dans {out_path}")


def parse_args():
    p = argparse.ArgumentParser(description="ESC/POS raster (GS v 0) avec logs/preview/dry-run")
    # Maintenance
    p.add_argument("--cancel", nargs='?', const=True, help="Annuler/vider le buffer: --cancel <serial>")
    p.add_argument("--hello",  nargs='?', const=True, help="Test texte: --hello <serial>")

    # Impression — syntaxe positionnelle
    p.add_argument("image", nargs='?')
    p.add_argument("serial", nargs='?')
    p.add_argument("width", nargs='?', type=int)

    # Impression — syntaxe via flags (compat avec tes commandes)
    p.add_argument("--print", dest="image_flag")
    p.add_argument("--dev", dest="serial_flag")
    p.add_argument("--width", dest="width_flag", type=int)

    # Options communes / rendu / debug
    p.add_argument("--baud", type=int, default=9600)
    p.add_argument("--pre-cancel", action="store_true")
    p.add_argument("--dry-run")
    p.add_argument("--preview")
    p.add_argument("--no-dither", action="store_true")
    p.add_argument("--threshold", type=int, default=128)
    p.add_argument("--contrast", type=float, default=1.3)
    p.add_argument("--gamma", type=float, default=1.0)
    p.add_argument("--invert", action="store_true")
    p.add_argument("--limit-lines", type=int)
    p.add_argument("--no-autorotate", action="store_true")
    p.add_argument("--chunk", type=int, default=4096)
    p.add_argument("--line-sleep", type=float, default=0.02)
    return p.parse_args()


def main():
    args = parse_args()

    # Modes maintenance: --cancel / --hello
    if args.cancel is True or (isinstance(args.cancel, str) and not args.image and not args.image_flag):
        dev = args.cancel if isinstance(args.cancel, str) else args.serial
        if not dev:
            sys.stderr.write("Usage: --cancel <serial>\n")
            sys.exit(2)
        with open_serial(dev, args.baud) as ser:
            cancel_and_reset(ser)
        log("Cancel/reset envoyé")
        return

    if args.hello is True or (isinstance(args.hello, str) and not args.image and not args.image_flag):
        dev = args.hello if isinstance(args.hello, str) else args.serial
        if not dev:
            sys.stderr.write("Usage: --hello <serial>\n")
            sys.exit(2)
        with open_serial(dev, args.baud) as ser:
            send_hello(ser)
        log("Hello OK")
        return

    # Résolution des paramètres impression (positionnels OU flags)
    image_path = args.image_flag or args.image
    serial_dev = args.serial_flag or args.serial
    width = args.width_flag if args.width_flag else args.width

    if not image_path or not serial_dev or not width:
        sys.stderr.write(
            "Usage impression (2 formes) :\n"
            "  a) print_raster.py <image> <serial> <width> [--baud 9600] [options...]\n"
            "  b) print_raster.py --print <image> --dev <serial> --width <px> [--baud 9600] [options...]\n"
        )
        sys.exit(2)

    if not os.path.exists(image_path):
        sys.stderr.write(f"[ERREUR] Image introuvable: {image_path}\n")
        sys.exit(3)

    try:
        use_dither = not args.no_dither
        img1, raw = prepare_image(
            image_path,
            width,
            contrast=args.contrast,
            gamma=args.gamma,
            use_dither=use_dither,
            threshold=args.threshold,
            autorotate=(not args.no_autorotate),
            preview=args.preview
        )

        # Mode preview-only (ne PAS imprimer)
        if args.dry_run:
            write_raster_to_file(img1, raw, args.dry_run, invert=args.invert, limit_lines=args.limit_lines)
            return

        # Impression réelle
        with open_serial(serial_dev, args.baud) as ser:
            if args.pre_cancel:
                cancel_and_reset(ser)
            send_raster(
                ser,
                img1,
                raw,
                invert=args.invert,
                limit_lines=args.limit_lines,
                chunk=args.chunk,
                line_sleep=args.line_sleep
            )
        log("Terminé")

    except serial.SerialTimeoutException as e:
        sys.stderr.write(f"[ERREUR] Timeout écriture: {e}\n")
        sys.exit(11)
    except serial.SerialException as e:
        sys.stderr.write(f"[ERREUR] Série: {e}\n")
        sys.exit(10)
    except Exception as e:
        sys.stderr.write(f"[ERREUR] {type(e).__name__}: {e}\n")
        sys.exit(12)


if __name__ == "__main__":
    main()
