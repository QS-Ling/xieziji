"""Geometric interpretations of the sourced rules in cursive_rules.json.

These templates approximate pen movement; they are not learned handwriting.
"""
import math
import functools
import json
import pathlib
from backend.glyph_fallback import Stroke, moved


@functools.lru_cache(maxsize=1)
def rulebook():
    return json.loads(pathlib.Path(__file__).with_name('cursive_rules.json').read_text(encoding='utf-8'))


def excursion(size):
    return size*rulebook()['geometry']['max_excursion_em']


def tangent(stroke, start, reach):
    points=stroke if start else list(reversed(stroke))
    if len(points)<2:return None
    origin=points[0]
    target=points[1]
    travelled=0.
    heading=None
    for a,b in zip(points,points[1:]):
        length=math.dist(a,b)
        if length<1e-9:continue
        direction=((b[0]-a[0])/length,(b[1]-a[1])/length)
        if heading and direction[0]*heading[0]+direction[1]*heading[1]<.5:break
        if heading is None:heading=direction
        remaining=reach-travelled
        step=min(length,remaining)
        target=(a[0]+direction[0]*step,a[1]+direction[1]*step)
        travelled+=step
        if travelled>=reach:break
    dx,dy=(target[0]-origin[0],target[1]-origin[1]) if start else (origin[0]-target[0],origin[1]-target[1])
    length=math.hypot(dx,dy)
    return (dx/length,dy/length) if length>1e-9 else None


def bezier(a,c,d,b):
    result=[]
    for i in range(17):
        t=i/16;s=1-t
        result.append((s**3*a[0]+3*s*s*t*c[0]+3*s*t*t*d[0]+t**3*b[0],
                       s**3*a[1]+3*s*s*t*c[1]+3*s*t*t*d[1]+t**3*b[1]))
    result[0],result[-1]=a,b
    return result


def candidates(previous, current, size, rng, style='thread'):
    """QS1: tangent continuation; QS2: upper/lower turn; QS3: return lead."""
    a,b=previous[-1][-1],current[0][0]
    dx,dy=b[0]-a[0],b[1]-a[1]
    distance=math.hypot(dx,dy)
    geometry=rulebook()['geometry']
    if not (size*.025<dx<size*geometry['max_horizontal_em'] and distance<size*geometry['max_distance_em'] and abs(dy)<size*geometry['max_vertical_em']):return []
    outgoing=tangent(previous[-1],False,size*.08)
    incoming=tangent(current[0],True,size*.08)
    if outgoing is None or incoming is None:return []
    if style=='copybook':
        return copybook_candidates(a,b,outgoing,incoming,size,geometry)
    handle=min(size*geometry['handle_max_em'],max(size*geometry['handle_min_em'],distance*geometry['handle_distance_ratio']))*rng.uniform(.9,1.1)
    def offset(p,v,h):return (p[0]+v[0]*h,p[1]+v[1]*h)
    c,d=offset(a,outgoing,handle),offset(b,incoming,-handle)
    flow=bezier(a,c,d,b)
    # A transverse bow lets a long horizontal release into the next glyph,
    # instead of clipping both control points into a nearly straight bridge.
    chord=(dx/distance,dy/distance);normal=(-chord[1],chord[0])
    sign=rng.choice((-1,1))
    arches=[]
    for side in (sign,-sign):
        middle=((a[0]+b[0])/2+normal[0]*size*geometry['arch_em']*side,
                (a[1]+b[1])/2+normal[1]*size*geometry['arch_em']*side)
        left=bezier(a,c,offset(middle,chord,-handle*.65),middle)
        right=bezier(middle,offset(middle,chord,handle*.65),d,b)
        arches.append(left+right[1:])
    # Prefer the small bow when both terminal directions are nearly horizontal.
    return arches+[flow] if abs(outgoing[1])<.4 and abs(incoming[1])<.4 else [flow]+arches


def copybook_candidates(a,b,outgoing,incoming,size,geometry):
    """Study-based restrained leads, not traced paths or a trained model.

    Prefer the economical continuation seen in the inspected copybook pages.
    Do not add a fixed bow or route a connector around an obstructing stroke.
    """
    dx,dy=b[0]-a[0],b[1]-a[1]
    distance=math.hypot(dx,dy)
    profile=geometry['copybook']
    if dx>size*profile['max_horizontal_em'] or distance>size*profile['max_distance_em']:return []
    chord=(dx/distance,dy/distance)
    align=[max(-1.,min(1.,v[0]*chord[0]+v[1]*chord[1])) for v in (outgoing,incoming)]
    # Turned-back tips get shorter handles; do not exaggerate their return.
    handles=[min(size*profile['handle_max_em'],distance*(.14+.1*(v+1)/2)) for v in align]
    result=[]
    for factor in (.7,1.,1.25):
        h1,h2=[h*factor for h in handles]
        c=(a[0]+outgoing[0]*h1,a[1]+outgoing[1]*h1)
        d=(b[0]-incoming[0]*h2,b[1]-incoming[1]*h2)
        curve=bezier(a,c,d,b)
        length=sum(math.dist(p,q) for p,q in zip(curve,curve[1:]))
        excursion=max(abs((p[0]-a[0])*chord[1]-(p[1]-a[1])*chord[0]) for p in curve)
        vectors=[(q[0]-p[0],q[1]-p[1]) for p,q in zip(curve,curve[1:]) if math.dist(p,q)>1e-9]
        turns=[abs(math.atan2(u[0]*v[1]-u[1]*v[0],u[0]*v[0]+u[1]*v[1])) for u,v in zip(vectors,vectors[1:])]
        if (length/distance>profile['max_length_ratio'] or excursion>min(size*.1,distance*profile['max_bow_ratio'])
                or max(turns,default=0)>math.radians(40)):continue
        # A ranking, not extra random decoration: shortest smooth candidate wins.
        score=(length-distance)/distance+sum(t*t for t in turns)+excursion/distance*.3
        result.append((score,curve))
    return [curve for _,curve in sorted(result,key=lambda entry:entry[0])]


def compact_copybook_groups(groups,variation,size):
    """Vary empty inter-glyph space before fitting leads; never overlap ink.

    The page has already wrapped, so contraction only adds spare line-end room.
    Separators and formula boundaries retain their original spacing.
    """
    result=[];offset=0.;previous_right=None
    profile=rulebook()['geometry']['copybook']
    for source,paths,formula in groups:
        paths=[moved(s,((x-offset,y) for x,y in s)) for s in paths]
        eligible=bool(paths) and not formula and len(source)==1 and source.isalnum()
        if eligible and previous_right is not None:
            gap=min(x for s in paths for x,y in s)-previous_right
            if size*.045<gap<size*.45:
                reduction=min(max(0.,gap-size*.045),size*.12,gap*variation.join_rng.uniform(*profile['spacing_reduction_range']))
                paths=[moved(s,((x-reduction,y) for x,y in s)) for s in paths]
                offset+=reduction
        result.append((source,paths,formula))
        previous_right=max(x for s in paths for x,y in s) if eligible else None
    return result


def connect_thread_line(groups, variation, size):
    from backend.humanization import segment_distance
    if variation.config.get('cursive_style')=='copybook':
        groups=compact_copybook_groups(groups,variation,size)
    result=[];previous=None;run=0
    all_paths=[s for _,paths,_ in groups for s in paths]
    segments=[(s,k,p,q) for s in all_paths for k,(p,q) in enumerate(zip(s,s[1:]))]
    for source,paths,formula in groups:
        eligible=bool(paths) and not formula and len(source)==1 and source.isalnum()
        if previous is not None and eligible and run<2 and variation.join_rng.random()<variation.amplitude('cursive')/100:
            ink=[p for s in previous+paths for p in s]
            xmin,xmax=min(p[0] for p in ink),max(p[0] for p in ink)
            ymin,ymax=min(p[1] for p in ink)-excursion(size),max(p[1] for p in ink)+excursion(size)
            accepted=None
            style=variation.config.get('cursive_style','thread')
            for curve in candidates(previous,paths,size,variation.join_rng,style):
                if not all(xmin<=x<=xmax and ymin<=y<=ymax for x,y in curve):continue
                lo_x,hi_x=min(p[0] for p in curve),max(p[0] for p in curve)
                lo_y,hi_y=min(p[1] for p in curve),max(p[1] for p in curve)
                clearance=size*rulebook()['geometry']['clearance_em']
                obstacles=[(p,q) for s,k,p,q in segments
                           if not (s is previous[-1] and k==len(s)-2 or s is paths[0] and k==0)
                           and max(p[0],q[0])>=lo_x-clearance and min(p[0],q[0])<=hi_x+clearance
                           and max(p[1],q[1])>=lo_y-clearance and min(p[1],q[1])<=hi_y+clearance]
                if any(segment_distance(a,b,p,q)<clearance for a,b in zip(curve,curve[1:]) for p,q in obstacles):continue
                # Allow contact at the two attachments, but no return across
                # their terminal segments farther along the connector.
                terminals=[(previous[-1][-2],previous[-1][-1]),(paths[0][0],paths[0][1])]
                if any(segment_distance(a,b,p,q)<1e-8 for a,b in zip(curve[2:-3],curve[3:-2]) for p,q in terminals):continue
                if any(segment_distance(curve[i],curve[i+1],curve[j],curve[j+1])<1e-8
                       for i in range(len(curve)-1) for j in range(i+3,len(curve)-1)):continue
                accepted=curve;break
            if accepted:
                result.append(Stroke(accepted,getattr(previous[-1],'fallback',None) or getattr(paths[0],'fallback',None),connector=True))
                run+=1
            else:run=0
        else:run=0
        result.extend(paths);previous=paths if eligible else None
    return result
