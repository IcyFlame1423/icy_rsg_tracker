import unittest

from icy_rsg_tracker import terrain


def section(y, fill):
    """A 16x16x16 section: fill(x, y, z) -> block name, packed the way 1.16 saves it."""
    names, states = [], []
    for i in range(4096):
        name = fill(i % 16, y * 16 + i // 256, (i // 16) % 16)
        if name not in names:
            names.append(name)
        states.append(names.index(name))
    bits = max(4, (len(names) - 1).bit_length())
    per_long = 64 // bits
    longs = []
    for k in range(0, 4096, per_long):
        word = 0
        for j, value in enumerate(states[k:k + per_long]):
            word |= value << (j * bits)
        longs.append(word - (1 << 64) if word >= 1 << 63 else word)
    return {"Y": y, "Palette": [{"Name": n} for n in names], "BlockStates": longs}


class TerrainTest(unittest.TestCase):
    def test_counts_open_blocks_in_the_band(self):
        # Solid below y 60, air above; lava fills y 30-39.
        def fill(x, y, z):
            if 30 <= y < 40:
                return "minecraft:lava"
            return "minecraft:netherrack" if y < 60 else "minecraft:air"
        level = {"Sections": [section(y, fill) for y in range(0, 8) if y != 5]}  # y 80-95: not saved, all air
        open_blocks, total = terrain.chunk_counts(level)
        self.assertEqual(total, 61 * 256)
        self.assertEqual(open_blocks, (90 - 60 + 1) * 256 + 10 * 256)  # lava counts as open

    def test_a_lava_ocean_is_closed_for_bucket_3(self):
        # Lava up to y 31 (the ocean); above it, half the chunk (x < 8) open to the roof, the
        # other half with a netherrack ledge at y 50.
        def fill(x, y, z):
            if y <= 31:
                return "minecraft:lava"
            return "minecraft:netherrack" if x >= 8 and y == 50 else "minecraft:air"
        level = {"Sections": [section(y, fill) for y in range(0, 8)]}
        open_blocks, _ = terrain.chunk_counts(level)
        self.assertEqual(open_blocks, 61 * 256 - 128)             # only the ledge is solid
        ocean, _ = terrain.chunk_counts(level, ocean_closed=True)
        self.assertEqual(ocean, 128 * 60)                          # open-sky ocean half: closed

    def test_route_chunks_follow_the_line_between_chunk_centres(self):
        self.assertEqual(terrain.route_chunks({"x": 1, "z": 1}, {"x": 40, "z": 2}), [(0, 0), (1, 0), (2, 0)])
        diagonal = terrain.route_chunks({"x": 0, "z": 0}, {"x": 47, "z": 47})
        self.assertEqual((diagonal[0], diagonal[-1]), ((0, 0), (2, 2)))

    def test_no_saved_chunks(self):
        self.assertIsNone(terrain.openness("no-such-folder", {"x": 0, "z": 0}, {"x": 100, "z": 0}))


if __name__ == "__main__":
    unittest.main()
