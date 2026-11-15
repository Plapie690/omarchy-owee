"""Bounded PNG validation shared by downloaded radar and forecast imagery."""
import struct
import zlib

PNG = b"\x89PNG\r\n\x1a\n"
IMAGE_LIMIT = 1_000_000


def png_size(data):
    """Reject corrupt, oversized or undecodable PNG streams before caching them."""
    if not isinstance(data, bytes) or not 45 <= len(data) <= IMAGE_LIMIT or not data.startswith(PNG):
        raise ValueError("Invalid map image")
    offset, chunks, width, height = 8, 0, 0, 0
    compressed, palette, ended_idat = bytearray(), False, False
    rows = []
    while offset + 12 <= len(data):
        length = struct.unpack(">I", data[offset:offset + 4])[0]
        kind = data[offset + 4:offset + 8]
        if length > IMAGE_LIMIT or offset + length + 12 > len(data):
            raise ValueError("Truncated map image")
        body = data[offset + 8:offset + 8 + length]
        crc = struct.unpack(">I", data[offset + 8 + length:offset + 12 + length])[0]
        if zlib.crc32(kind + body) & 0xffffffff != crc:
            raise ValueError("Corrupted map image")
        if chunks == 0:
            if kind != b"IHDR" or length != 13:
                raise ValueError("Invalid map image")
            width, height, depth, colour, compression, filtering, interlace = struct.unpack(">IIBBBBB", body)
            depths = {0: (1, 2, 4, 8, 16), 2: (8, 16), 3: (1, 2, 4, 8), 4: (8, 16), 6: (8, 16)}
            if (not 1 <= width <= 1024 or not 1 <= height <= 1024 or depth not in depths.get(colour, ())
                    or compression or filtering or interlace not in (0, 1)):
                raise ValueError("Invalid map dimensions or encoding")
            channels = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}[colour]
            passes = ((0, 0, 1, 1),) if not interlace else (
                (0, 0, 8, 8), (4, 0, 8, 8), (0, 4, 4, 8), (2, 0, 4, 4),
                (0, 2, 2, 4), (1, 0, 2, 2), (0, 1, 1, 2))
            for x, y, dx, dy in passes:
                columns = max(0, (width - x + dx - 1) // dx)
                count = max(0, (height - y + dy - 1) // dy)
                if columns and count:
                    rows.extend([(columns * channels * depth + 7) // 8 + 1] * count)
        elif kind == b"IHDR":
            raise ValueError("Duplicate image header")
        if kind == b"PLTE":
            if palette or compressed or not length or length % 3 or length > 768:
                raise ValueError("Invalid image palette")
            palette = True
        elif kind == b"IDAT":
            if ended_idat or (colour == 3 and not palette):
                raise ValueError("Invalid image data order")
            compressed.extend(body)
        elif compressed:
            ended_idat = True
        if kind not in (b"IHDR", b"PLTE", b"IDAT", b"IEND") and not kind[0] & 32:
            raise ValueError("Unsupported critical image chunk")
        offset += length + 12
        chunks += 1
        if chunks > 256:
            raise ValueError("Map image too large")
        if kind == b"IEND":
            if length or offset != len(data) or not compressed:
                raise ValueError("Invalid image end")
            expected = sum(rows)
            try:
                decoder = zlib.decompressobj()
                raster = decoder.decompress(compressed, expected + 1)
            except zlib.error as error:
                raise ValueError("Corrupted image raster") from error
            if len(raster) != expected or not decoder.eof or decoder.unused_data or decoder.unconsumed_tail:
                raise ValueError("Invalid image raster size")
            start = 0
            for size in rows:
                if raster[start] > 4:
                    raise ValueError("Invalid image row filter")
                start += size
            return width, height
    raise ValueError("Truncated map image")
