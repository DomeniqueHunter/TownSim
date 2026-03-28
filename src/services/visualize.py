import pickle
from typing import Any, Dict, Tuple
from PIL import Image, ImageDraw, ImageFont


class GridVisualizer:
    def __init__(
        self,
        grid: Dict[Tuple[int, int], Any],
        start_value: Any = "S",
        start_color: Tuple[int, int, int] = (255, 0, 0),
        default_color: Tuple[int, int, int] = (0, 0, 255),
        background_color: Tuple[int, int, int] = (200, 200, 200),
        text_color: Tuple[int, int, int] = (255, 255, 255),
        cell_size: int = 40,
        padding: int = 2,
        outer_margin: int = 20,
    ) -> None:
        self.grid = grid
        self.start_value = start_value
        self.start_color = start_color
        self.default_color = default_color
        self.background_color = background_color
        self.text_color = text_color
        self.cell_size = cell_size
        self.padding = padding
        self.outer_margin = outer_margin


    def get_boundaries(self) -> Tuple[int, int, int, int]:
        ys = [pos[0] for pos in self.grid.keys()]
        xs = [pos[1] for pos in self.grid.keys()]

        return min(ys), max(ys), min(xs), max(xs)


    def draw(self, output_file: str = "grid.png") -> None:
        if not self.grid:
            print("Grid is empty")
            return

        min_y, max_y, min_x, max_x = self.get_boundaries()

        grid_width = (max_x - min_x + 1) * self.cell_size
        grid_height = (max_y - min_y + 1) * self.cell_size

        width = grid_width + 2 * self.outer_margin
        height = grid_height + 2 * self.outer_margin

        image = Image.new("RGB", (width, height), self.background_color)
        draw = ImageDraw.Draw(image)

        try:
            font = ImageFont.truetype("arial.ttf", int(self.cell_size * 0.4))
        except IOError:
            font = ImageFont.load_default()

        for (y, x), value in self.grid.items():
            px = (x - min_x) * self.cell_size + self.outer_margin
            py = (max_y - y) * self.cell_size + self.outer_margin  # invert y-axis

            if value == self.start_value:
                color = self.start_color
            else:
                color = self.default_color

            draw.rectangle(
                [
                    (px + self.padding, py + self.padding),
                    (px + self.cell_size - self.padding, py + self.cell_size - self.padding),
                ],
                fill=color,
                outline=(0, 0, 0),
            )

            text = str(value)
            bbox = draw.textbbox((0, 0), text, font=font)
            text_width = bbox[2] - bbox[0]
            text_height = bbox[3] - bbox[1]

            text_x = px + (self.cell_size - text_width) / 2
            text_y = py + (self.cell_size - text_height) / 2

            draw.text((text_x, text_y), text, fill=self.text_color, font=font)

        image.save(output_file)
        print(f"Saved grid to {output_file}")


def load_grid(filename: str) -> Dict[Tuple[int, int], Any]:
    with open(filename, "rb") as file:
        grid = pickle.load(file)
    return grid


def main() -> None:
    filename: str = "grid_ul.pkl"

    grid = load_grid(filename)

    visualizer = GridVisualizer(
        grid=grid,
        start_value="S",
        start_color=(255, 0, 0),
        default_color=(0, 0, 255),
        background_color=(180, 180, 180),
        text_color=(255, 255, 255),
        cell_size=50,
        padding=3,
        outer_margin=40,  # <-- tweak this for more/less margin
    )

    visualizer.draw("grid.png")


if __name__ == "__main__":
    main()
