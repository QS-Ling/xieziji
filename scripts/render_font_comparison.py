"""Render the measured recommendation groups to a standalone contact sheet (Pillow)."""
import argparse
import json
import math
import pathlib
import sys
import xml.etree.ElementTree as ET
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from backend.font_library import vector_sample


def render(font_dir, catalog, output, label_font):
    groups=json.loads(pathlib.Path(catalog).read_text(encoding='utf8'))['recommendations']
    font=ImageFont.truetype(label_font, 18)
    heading=ImageFont.truetype(label_font, 23)
    canvas=Image.new('RGB', (1300, max(1,len(groups))*650), '#fbfcf7');draw=ImageDraw.Draw(canvas)
    y=20
    for group in groups:
        draw.text((22,y), group['name']+'  '+str(group['score'])+'/100', font=heading, fill='#264c40');y+=38
        for item in group['mix']:
            draw.text((25,y), item['name']+'  '+str(item['weight'])+'%', font=font, fill='#526758');y+=30
            result=vector_sample(pathlib.Path(font_dir)/(item['name']+'.gfont'), '春风十里山水清音学习实验笔记')
            svg=ET.fromstring(result['svg']);vx,vy,vw,vh=map(float, svg.attrib['viewBox'].split());scale=min(4,1240/vw)
            for line in svg.iter('{http://www.w3.org/2000/svg}polyline'):
                pts=[(25+float(p.split(',')[0])*scale,y+(float(p.split(',')[1])-vy)*scale) for p in line.attrib['points'].split()]
                if len(pts)>1:draw.line(pts, fill='#284b4a', width=2)
            y+=math.ceil(vh*scale)+15
        y+=20
    canvas.crop((0,0,1300,y)).save(output)


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--font-dir', required=True)
    parser.add_argument('--catalog', default='backend/font_similarity.json')
    parser.add_argument('--output', default='docs/font-comparison.png')
    parser.add_argument('--label-font', default='C:/Windows/Fonts/msyh.ttc')
    args=parser.parse_args()
    render(args.font_dir,args.catalog,args.output,args.label_font)
