"""Rasterize the workbench's exact paper polylines for vision-capable MCP hosts.

Only our generated SVG primitive subset is accepted; no remote files, scripts,
fonts, CSS, transforms or general-purpose SVG execution are involved.
"""
import io
import math
import xml.etree.ElementTree as ET


def preview_png(svg, longest=1600):
    from PIL import Image, ImageDraw
    root = ET.fromstring(svg)
    width, height = float(root.attrib['data-paper-width']), float(root.attrib['data-paper-height'])
    if not all(math.isfinite(v) and 0 < v <= 600 for v in (width, height)):
        raise ValueError('预览纸张尺寸无效')
    scale = longest * 2 / max(width, height)
    image = Image.new('RGB', (max(1, round(width * scale)), max(1, round(height * scale))), 'white')
    draw = ImageDraw.Draw(image)
    for group in root:
        tag = group.tag.rsplit('}', 1)[-1]
        if tag == 'rect' and group.attrib.get('id') == 'writable-area':
            a = group.attrib
            box = [float(a.get('x', 0)), float(a.get('y', 0)),
                   float(a.get('x', 0)) + float(a['width']), float(a.get('y', 0)) + float(a['height'])]
            draw.rectangle([v * scale for v in box], outline='#c3ced4', width=max(1, round(.2 * scale)))
        elif tag == 'g' and group.attrib.get('id') in ('writing-paths', 'row-guides'):
            for item in group:
                a = item.attrib
                primitive = item.tag.rsplit('}', 1)[-1]
                if primitive == 'polyline':
                    points = [tuple(float(n) * scale for n in p.split(',')) for p in a['points'].split()]
                    if len(points) > 1:
                        draw.line(points, fill=a.get('stroke', '#243e42'), width=max(1, round(float(a.get('stroke-width', .22)) * scale)), joint='curve')
                elif primitive == 'line':
                    draw.line([(float(a['x1']) * scale, float(a['y1']) * scale),
                               (float(a['x2']) * scale, float(a['y2']) * scale)], fill='#dce5dc', width=1)
    image = image.resize((max(1, round(width * scale / 2)), max(1, round(height * scale / 2))), Image.Resampling.LANCZOS)
    output = io.BytesIO()
    image.save(output, format='PNG')
    return output.getvalue()
