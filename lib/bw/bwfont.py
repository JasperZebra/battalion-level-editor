"""
Reader for Battalion Wars bitmap font files (.btf / .fnc / .wdf).

Format summary (reverse engineered from the retail font files under
Data/font in both games):

.btf - font glyph atlas texture. A thin wrapper around the same texture
       struct used in .res archives (see bwtex.py), with the texture's name
       stored inline instead of coming from an archive TOC.
       BW1 wrapper:  magic "FTBX", u32 LE (filesize-8), u32 LE (unknown,
                     varies per file), chunk id "TEXT" (4 bytes, reversed
                     on disk like the PAL /MIP chunk ids), u32 LE chunk
                     size, 0x10-byte inline name, then a normal BW1Texture
                     body (little-endian, as read by BW1Texture.from_file).
       BW2 wrapper:  magic "FTBG", u32 LE (filesize-8), u32 LE (unknown),
                     chunk id "DXTG" (literal, not reversed), u32 LE chunk
                     size, 0x20-byte inline name, then a texture body with
                     the same field layout as BW2Texture (big-endian, GC
                     native, PAL / MIP chunk ids reversed) except unkint2
                     uses BW1-style raw values (4/12/20) instead of BW2's
                     (4100/4108/4116) - so it can't be read with
                     BW2Texture.from_file directly, see read_font_texture_bw2.

.fnc - glyph metrics table, one per "master" font (Chisel_CN, Chisel_CN_L,
       Chisel_CN_O, Debugging, Techno_HB, ModelView/fonta, ModelView/tcktape).
       Header (12 bytes): magic "fnc0", u16 version(=1), u16 unknown,
       u32 unknown(=32 in every sample seen). Followed by 8-byte entries:
       u16 flag (0 = unused slot), u16 char_code, u16 width (fixed point,
       scale not fully confirmed - divide by 32 gets values in the right
       ballpark but doesn't cleanly reconstruct the atlas layout), u16
       reserved(=0 on valid entries). char_code appears to be
       ascii_code + 181 across the whole verified range (covers extended
       Latin-1, not just 7-bit ASCII) - confirmed against the decoded
       Techno_HB atlas image. Only the first block of entries (until flag
       and reserved both go to consistent all-zero padding) is understood;
       a later block of entries with large, non-zero "reserved" values
       exists in every .fnc file checked and is NOT understood - do not
       trust it.

.wdf - per-level/per-menu glyph width override table. No header at all:
       a flat byte array, one byte per character = pixel width, index 0
       = char code 0x20 (space). Almost always exactly 96 bytes (covering
       0x20-0x7F, i.e. all of basic printable ASCII); a few files have 1-2
       extra trailing bytes for extra symbols specific to that screen.
       Only present in BW2 - BW1 has no .wdf files, it relies solely on
       the .fnc tables.
"""
from io import BytesIO

from lib.bw.bwtex import BW1Texture, FORMATTOSTR, PALLETE, MIP
from lib.bw.texlib.read_binary import read_id, read_uint32, read_uint32_le
from lib.bw.texlib.texture_utils import decode_image, PaletteFormat, ImageFormat

FORMAT = {
    "DXT1": ImageFormat.CMPR,
    "IA8": ImageFormat.IA8,
    "IA4": ImageFormat.IA4,
    "P4": ImageFormat.C4,
    "P8": ImageFormat.C8,
    "I8": ImageFormat.I8,
    "I4": ImageFormat.I4,
    "RGBA": ImageFormat.RGBA32,
}

BTF_MAGIC_BW1 = b"FTBX"
BTF_MAGIC_BW2 = b"FTBG"


class FontTexture:
    def __init__(self, name, image, fmt):
        self.name = name
        self.image = image
        self.fmt = fmt


def _read_font_texture_bw2(f):
    """Body layout matches BW2Texture's struct (see bwtex.py), but unkint2
    holds BW1-style raw values instead of BW2's *1024 encoding, so
    BW2Texture.from_file's assertion on unkint2 rejects these files -
    duplicated here without that assertion."""
    size_x = read_uint32(f)
    size_y = read_uint32(f)
    unkint1 = read_uint32(f)
    assert unkint1 == 1
    unkint2 = read_uint32(f)

    fmt = f.read(8)
    fmtstr = FORMATTOSTR[fmt]
    colorfmt = f.read(8)
    assert colorfmt == b"8B8G8R8A"

    for _ in range(5):
        read_uint32(f)  # unkint3-7
    pad = f.read(12)
    assert pad == b"\x00" * 12

    mipcount = read_uint32(f)
    w2 = read_uint32(f)
    h2 = read_uint32(f)
    mipcount2 = read_uint32(f)
    assert (size_x, size_y, mipcount) == (w2, h2, mipcount2)

    section = read_id(f)
    size = read_uint32_le(f)
    if fmtstr in ("P4", "P8"):
        assert section == PALLETE
        palette = BytesIO(f.read(size))
        num_colors = len(palette.getbuffer()) // 2
        section = read_id(f)
        size = read_uint32_le(f)
        assert section == MIP
    else:
        palette = None
        num_colors = 0
        assert section == MIP

    imagedata = BytesIO(f.read(size) + b"\x00" * 256 * 256)
    image = decode_image(imagedata, palette, FORMAT[fmtstr], PaletteFormat.RGB5A3,
                          num_colors, size_x, size_y)
    return image, fmtstr


def read_btf(path_or_stream):
    """Decode a .btf font atlas (either game) into a FontTexture."""
    if hasattr(path_or_stream, "read"):
        data = path_or_stream.read()
    else:
        with open(path_or_stream, "rb") as f:
            data = f.read()

    f = BytesIO(data)
    magic = f.read(4)

    if magic == BTF_MAGIC_BW1:
        read_uint32_le(f)  # content size (filesize - 8)
        read_uint32_le(f)  # unknown
        chunk_id = read_id(f)
        assert chunk_id == b"TEXT", chunk_id
        read_uint32_le(f)  # chunk size
        name = f.read(0x10).rstrip(b"\x00").decode("ascii")
        tex = BW1Texture.from_file(name, f)
        return FontTexture(name, tex.texture, tex.fmt)

    elif magic == BTF_MAGIC_BW2:
        read_uint32_le(f)  # content size
        read_uint32_le(f)  # unknown
        chunk_id = f.read(4)
        assert chunk_id == b"DXTG", chunk_id
        read_uint32_le(f)  # chunk size
        name = f.read(0x20).rstrip(b"\x00").decode("ascii", errors="replace")
        image, fmt = _read_font_texture_bw2(f)
        return FontTexture(name, image, fmt)

    else:
        raise ValueError("Not a recognised .btf file (bad magic {0})".format(magic))


def read_wdf(path):
    """Per-level glyph width table: byte i = width of char (0x20 + i)."""
    with open(path, "rb") as f:
        data = f.read()
    return {0x20 + i: w for i, w in enumerate(data)}


class FncEntry:
    def __init__(self, flag, char_code, width_raw, reserved):
        self.flag = flag
        self.char_code = char_code
        self.width_raw = width_raw
        self.reserved = reserved

    @property
    def active(self):
        return self.flag != 0

    @property
    def char(self):
        code = self.char_code - 181
        return chr(code) if 0 <= code < 0x110000 else None


def read_fnc(path):
    """Best-effort parse of a .fnc glyph metrics table. See module docstring
    for the caveats - only the leading block of entries (up to the point
    where 'reserved' stops being 0) should be trusted."""
    import struct
    with open(path, "rb") as f:
        data = f.read()
    assert data[0:4] == b"fnc0", data[0:4]
    version, unk = struct.unpack_from("<HH", data, 4)
    header_val = struct.unpack_from("<I", data, 8)[0]

    entries = []
    body = data[12:]
    for i in range(len(body) // 8):
        flag, code, width_raw, reserved = struct.unpack_from("<HHHH", body, i * 8)
        entries.append(FncEntry(flag, code, width_raw, reserved))

    return version, unk, header_val, entries
