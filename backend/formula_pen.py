"""Deterministic, bounded pen wobble for generated formula geometry.

Only geometric strokes (fraction rules, accents, roots, frames and fences) are
sampled here. Font glyphs keep their original paths, so handwriting variation
remains a separate concern.
"""
import math
import random


DEFAULTS = dict(symbol_scale=80., smooth=True, jitter=.12, draw_missing=True)
LIMITS = dict(symbol_scale=(50., 150.), jitter=(0., 1.))


def settings(data):
    raw = data.get('formula', {})
    if raw is None:
        raw = {}
    if not isinstance(raw, dict):
        raise ValueError('公式设置必须为对象')
    symbol_scale = raw.get('symbol_scale', DEFAULTS['symbol_scale'])
    jitter = raw.get('jitter', DEFAULTS['jitter'])
    smooth = raw.get('smooth', DEFAULTS['smooth'])
    draw_missing = raw.get('draw_missing', DEFAULTS['draw_missing'])
    if type(smooth) is not bool:
        raise ValueError('符号平滑开关必须为布尔值')
    if type(draw_missing) is not bool:
        raise ValueError('缺字绘制开关必须为布尔值')
    for key, value in (('symbol_scale', symbol_scale), ('jitter', jitter)):
        low, high = LIMITS[key]
        if isinstance(value, bool) or type(value) not in (int, float) or not math.isfinite(value) or not low <= value <= high:
            raise ValueError(f'公式参数 {key} 必须在 {low:g}–{high:g} 之间')
    return dict(symbol_scale=float(symbol_scale) / 100., smooth=smooth,
                jitter=float(jitter), draw_missing=draw_missing)


class Pen:
    """Small smooth perturbation used by straight mathematical rules."""

    def __init__(self, seed, jitter):
        self.jitter = float(jitter or 0.)
        self.rng = random.Random('formula-pen:' + str(seed)) if self.jitter > 0 else None

    def rule(self, start, end, size):
        x0, y0 = start
        x1, y1 = end
        if not self.rng:
            return [start, end]
        length = math.dist(start, end)
        amplitude = min(self.jitter, max(0., size) * .05)
        if amplitude <= 0 or length <= 1e-9:
            return [start, end]
        count = max(4, min(48, math.ceil(length / max(size * .35, 1e-6))))
        dx, dy = (x1 - x0) / length, (y1 - y0) / length
        nx, ny = -dy, dx
        phase = self.rng.uniform(0., 2 * math.pi)
        second = self.rng.uniform(0., 2 * math.pi)
        first_frequency = self.rng.uniform(.7, 1.3)
        second_frequency = self.rng.uniform(1.8, 2.6)
        points = []
        for index in range(count + 1):
            t = index / count
            # Taper both ends to zero so rules stay attached to their anchors.
            taper = math.sin(math.pi * t) ** .7
            wobble = amplitude * taper * (
                .65 * math.sin(2 * math.pi * first_frequency * t + phase) +
                .35 * math.sin(2 * math.pi * second_frequency * t + second))
            points.append((x0 + dx * length * t + nx * wobble,
                           y0 + dy * length * t + ny * wobble))
        return points
