from __future__ import annotations

from dataclasses import dataclass

from PIL import Image


WHITE = 0
UNASSIGNED_INK = 255


@dataclass
class PagePixelArray:
    """One byte per source pixel: white, unassigned ink, or owning row.

    Values are intentionally minimal:
      0     white source pixel
      255   black source pixel whose row is not assigned yet
      1..254 black source pixel assigned to a physical row

    Row ownership codes are one-based so that 0 can remain the white sentinel.
    The review UI still uses its existing zero-based row indexes; use
    ``row_code(row_index)`` when translating between them.
    """

    width: int
    height: int
    data: bytearray

    @classmethod
    def from_image(cls, page: Image.Image, *, threshold: int = 210) -> "PagePixelArray":
        gray = page.convert("L")
        width, height = gray.size
        source = gray.tobytes()
        data = bytearray(UNASSIGNED_INK if value < threshold else WHITE for value in source)
        return cls(width=width, height=height, data=data)

    @staticmethod
    def row_code(row_index: int) -> int:
        code = int(row_index) + 1
        if not 1 <= code <= 254:
            raise ValueError(f"row index {row_index} cannot be represented in one ownership byte")
        return code

    def _offset(self, x: int, y: int) -> int:
        if not 0 <= x < self.width or not 0 <= y < self.height:
            raise IndexError((x, y))
        return y * self.width + x

    def value(self, x: int, y: int) -> int:
        return self.data[self._offset(x, y)]

    def assign_row_map(self, row_map: dict) -> int:
        """Assign currently-unassigned ink by the row map's exact geometry.

        No padding is involved.  Pixels outside all physical row rectangles stay
        at 255, which makes segmentation gaps visible instead of silently giving
        those pixels to a neighbouring crop.
        """
        assigned = 0
        for column_index, column in enumerate(row_map.get("columns") or []):
            left = max(0, int(column.get("left", 0)))
            right = min(self.width, int(column.get("right", self.width)))
            if right <= left:
                continue
            for row_index, row in enumerate(column.get("rows") or []):
                code = self.row_code(row_index)
                top = max(0, int(row["page_top"]))
                bottom = min(self.height, int(row["page_bottom"]))
                if bottom <= top:
                    continue
                for y in range(top, bottom):
                    start = y * self.width + left
                    end = y * self.width + right
                    for offset in range(start, end):
                        if self.data[offset] == UNASSIGNED_INK:
                            self.data[offset] = code
                            assigned += 1
        return assigned

    def owner_ink_points(
        self,
        *,
        row_index: int,
        left: int,
        top: int,
        right: int,
        bottom: int,
    ) -> set[tuple[int, int]]:
        """Return page-coordinate ink owned by one row inside a rectangle."""
        code = self.row_code(row_index)
        left = max(0, int(left))
        right = min(self.width, int(right))
        top = max(0, int(top))
        bottom = min(self.height, int(bottom))
        points: set[tuple[int, int]] = set()
        for y in range(top, bottom):
            start = y * self.width
            for x in range(left, right):
                if self.data[start + x] == code:
                    points.add((x, y))
        return points

    def render_owner_crop(
        self,
        *,
        row_index: int,
        box: tuple[int, int, int, int],
    ) -> Image.Image:
        """Render only one row's owned ink as a normal monochrome PIL crop."""
        left, top, right, bottom = map(int, box)
        left = max(0, left)
        top = max(0, top)
        right = min(self.width, right)
        bottom = min(self.height, bottom)
        if right <= left or bottom <= top:
            raise ValueError(f"empty crop box: {(left, top, right, bottom)}")

        code = self.row_code(row_index)
        crop_width = right - left
        crop_height = bottom - top
        out = bytearray([255]) * (crop_width * crop_height)
        for local_y, page_y in enumerate(range(top, bottom)):
            page_start = page_y * self.width
            out_start = local_y * crop_width
            for local_x, page_x in enumerate(range(left, right)):
                if self.data[page_start + page_x] == code:
                    out[out_start + local_x] = 0
        return Image.frombytes("L", (crop_width, crop_height), bytes(out))

    def counts(self) -> dict[str, int]:
        white = self.data.count(WHITE)
        unassigned = self.data.count(UNASSIGNED_INK)
        return {
            "white": white,
            "unassigned_ink": unassigned,
            "assigned_ink": len(self.data) - white - unassigned,
        }
