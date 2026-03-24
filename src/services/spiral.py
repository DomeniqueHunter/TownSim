

class SpiralGrid:

    def __init__(self, size:tuple | None=None, grid:dict=None) -> None:
        self.grid = grid or {}
        self.size = size

        if size is not None:
            n, m = size

            half_n = n // 2
            half_m = m // 2

            if n % 2 == 1:
                self.min_y = -half_n
                self.max_y = half_n
            else:
                self.min_y = -half_n
                self.max_y = half_n - 1

            if m % 2 == 1:
                self.min_x = -half_m
                self.max_x = half_m
            else:
                self.min_x = -half_m
                self.max_x = half_m - 1
        else:
            self.min_y = None
            self.max_y = None
            self.min_x = None
            self.max_x = None

    def spiral_positions(self):
        y = 0
        x = 0

        yield (y, x)

        step_size = 1

        while True:
            for _ in range(step_size):
                x += 1
                yield (y, x)

            for _ in range(step_size):
                y -= 1
                yield (y, x)

            step_size += 1

            for _ in range(step_size):
                x -= 1
                yield (y, x)

            for _ in range(step_size):
                y += 1
                yield (y, x)

            step_size += 1

    def in_bounds(self, pos:tuple) -> bool:
        if self.size is None:
            return True

        y, x = pos

        return (
            self.min_y <= y <= self.max_y
            and self.min_x <= x <= self.max_x
        )

    def get_next_free(self) -> tuple[int, int]:
        for pos in self.spiral_positions():
            if not self.in_bounds(pos):
                continue

            if pos not in self.grid:
                return pos

        raise RuntimeError("Grid is full")
    
    def add_next_free(self, object:object) -> tuple:
        next_free = self.get_next_free()
        self.grid[next_free] = object
        return next_free
        
    def set_grid_field(self, object:object, pos:tuple) -> tuple:
        if not self.grid.get(pos):
            self.grid[pos] = object
        return pos

    def set_next(self, value) -> tuple[int, int]:
        pos = self.get_next_free()
        self.grid[pos] = value
        return pos

    def get_boundaries(self) -> tuple:
        if not self.grid:
            raise ValueError("Grid is empty")

        positions = self.grid.keys()

        ys = [p[0] for p in positions]
        xs = [p[1] for p in positions]

        return (min(ys), min(xs)), (max(ys), max(xs))

    def show(self) -> None:
        if not self.grid:
            print("(empty grid)")
            return

        if self.size is None:
            (min_y, min_x), (max_y, max_x) = self.get_boundaries()
        else:
            min_y = self.min_y
            max_y = self.max_y
            min_x = self.min_x
            max_x = self.max_x

        for y in range(max_y, min_y - 1, -1):
            row = []
            for x in range(min_x, max_x + 1):
                value = self.grid.get((y, x), "  ")
                row.append(str(value))
            print(" ".join(row))


def test_unlimited() -> None:
    grid = SpiralGrid()

    grid.grid[(0, 0)] = "S"

    offset = 0
    for i in range(108 + offset):
        grid.set_next(str(i)[-1])

    pos = grid.set_next("E")
    print(pos)
    grid.print()

    bounds = grid.get_boundaries()
    print(bounds)


def test_limited() -> None:
    grid = SpiralGrid((10, 20))

    grid.grid[(0, 0)] = "S"

    for i in range(108):
        grid.set_next(str(i)[-1])

    pos = grid.set_next("E")

    print(pos)
    grid.print()


def test() -> None:
    test_unlimited()
    print("--" * 20)
    test_limited()


if __name__ == "__main__":
    test()
