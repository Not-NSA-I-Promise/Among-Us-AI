r"""Read float constants out of a PE file by virtual address.

The IL2CPP decompile names its constants by address - `Move xmm0, [0x18296DC98]`
- and the value itself lives in GameAssembly.dll's read-only data. This maps
that virtual address back to a file offset and reads the float.

    .venv\\Scripts\\python.exe pefloat.py 0x18296DC98 0x18296D514 ...
"""
import struct
import sys


def load_sections(path):
    with open(path, "rb") as f:
        data = f.read()
    pe = struct.unpack_from("<I", data, 0x3C)[0]
    assert data[pe:pe + 4] == b"PE\0\0", "not a PE file"
    coff = pe + 4
    n_sections = struct.unpack_from("<H", data, coff + 2)[0]
    opt_size = struct.unpack_from("<H", data, coff + 16)[0]
    opt = coff + 20
    magic = struct.unpack_from("<H", data, opt)[0]
    image_base = struct.unpack_from("<Q" if magic == 0x20B else "<I",
                                    data, opt + 24)[0]
    sec = opt + opt_size
    sections = []
    for i in range(n_sections):
        off = sec + i * 40
        name = data[off:off + 8].rstrip(b"\0").decode("ascii", "replace")
        vsize, vaddr, rawsize, rawptr = struct.unpack_from("<IIII", data, off + 8)
        sections.append((name, vaddr, vsize, rawptr, rawsize))
    return data, image_base, sections


def va_to_offset(sections, image_base, va):
    rva = va - image_base
    for name, vaddr, vsize, rawptr, rawsize in sections:
        if vaddr <= rva < vaddr + max(vsize, rawsize):
            return rawptr + (rva - vaddr)
    return None


def main():
    path = r"C:\Games\Among Us\GameAssembly.dll"
    data, image_base, sections = load_sections(path)
    print(f"image base 0x{image_base:X}")
    for arg in sys.argv[1:]:
        va = int(arg, 16)
        off = va_to_offset(sections, image_base, va)
        if off is None:
            print(f"{arg}: not mapped")
            continue
        f32 = struct.unpack_from("<f", data, off)[0]
        i32 = struct.unpack_from("<i", data, off)[0]
        f64 = struct.unpack_from("<d", data, off)[0]
        print(f"{arg}: float={f32!r}  int={i32}  double={f64!r}")


if __name__ == "__main__":
    main()
