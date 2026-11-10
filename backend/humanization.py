"""Bounded, reproducible variation of whole glyphs, with smooth line drift."""
import math
import random


DEFAULTS = dict(enabled=False, vertical=.3, scale=5., rotation=2., spacing=.2, baseline=.4,
                stroke=0., cursive=0., slant=0.)
LIMITS = dict(vertical=2., scale=20., rotation=10., spacing=2., baseline=2.,
              stroke=10., cursive=100., slant=2.)


def settings(data):
    raw = data.get('humanization', {})
    if not isinstance(raw, dict): raise ValueError('仿真设置必须为对象')
    result = {}
    style=raw.get('cursive_style','short')
    if style not in ('short','thread','copybook'):raise ValueError('连笔方式必须为 short、thread 或 copybook')
    result['cursive_style']=style
    mode=raw.get('stroke_mode','single')
    if mode not in ('single','multi'):raise ValueError('笔画变化方式必须为 single 或 multi')
    result['stroke_mode']=mode
    probability=raw.get('stroke_probability',45.)
    if type(probability) not in (int,float) or not 0<=probability<=100 or not math.isfinite(probability):
        raise ValueError('自由端生效概率必须为 0–100 之间的有限数字')
    result['stroke_probability']=float(probability)
    for key in ('enabled', *(name + '_enabled' for name in LIMITS)):
        value = raw.get(key, False if key == 'enabled' else True)
        if type(value) is not bool: raise ValueError('仿真开关必须为布尔值')
        result[key] = value
    for key, maximum in LIMITS.items():
        value = raw.get(key, DEFAULTS[key])
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 <= value <= maximum or not math.isfinite(value):
            raise ValueError(f'仿真参数 {key} 必须为 0–{maximum:g} 之间的有限数字')
        result[key] = float(value)
    return result


def active(config):
    return config['enabled'] and any(config[key + '_enabled'] and config[key] > 0 for key in LIMITS)


class Variation:
    def __init__(self, config, seed):
        self.config = config
        self.rng = random.Random('glyph-variation:' + seed)
        self.line_rng = random.Random('line-variation:' + seed)
        self.stroke_rng = random.Random('stroke-variation:' + seed)
        self.join_rng = random.Random('join-variation:' + seed)
        self.slant_rng = random.Random('slant-variation:' + seed)

    def amplitude(self, key):
        return self.config[key] if self.config['enabled'] and self.config[key + '_enabled'] else 0.

    def glyph(self, token, size, spacing):
        if not token['paths']: return dict(token)
        adjustment=dict(changed=False,max_shift_mm=0.,changed_points=0,changed_ends=0)
        if self.amplitude('stroke'):
            original=token['paths']
            if self.config.get('stroke_mode')=='multi':
                varied=vary_endpoints(original,size,self.amplitude('stroke'),self.stroke_rng,
                                     self.config.get('stroke_probability',45.),adjustment)
            else:
                varied=vary_endpoint(original,size,self.amplitude('stroke'),self.stroke_rng,adjustment)
            token = dict(token, paths=varied)
        scale = 1 + self.rng.uniform(-1, 1) * self.amplitude('scale') / 100
        degrees = self.rng.uniform(-1, 1) * self.amplitude('rotation')
        vertical = self.rng.uniform(-1, 1) * self.amplitude('vertical')
        gap = max(0., spacing + self.rng.uniform(-1, 1) * self.amplitude('spacing'))
        if not self.amplitude('scale') and not self.amplitude('rotation') and not adjustment['changed']:
            return dict(token, paths=[[(x, y+vertical) for x, y in stroke] for stroke in token['paths']],
                        advance=token['advance']+gap-spacing,
                        variation=dict(scale=scale, rotation=degrees, vertical=vertical, gap=gap,stroke_adjustment=adjustment))
        points = [p for stroke in token['paths'] for p in stroke]
        cx = (min(x for x, y in points) + max(x for x, y in points)) / 2
        cy = (min(y for x, y in points) + max(y for x, y in points)) / 2
        radians = math.radians(degrees)
        cos, sin = math.cos(radians), math.sin(radians)
        paths = [[(cx + scale * ((x-cx)*cos - (y-cy)*sin),
                   cy + scale * ((x-cx)*sin + (y-cy)*cos) + vertical)
                  for x, y in stroke] for stroke in token['paths']]
        xmin = min(x for stroke in paths for x, y in stroke)
        xmax = max(x for stroke in paths for x, y in stroke)
        # Lay out each transformed ink footprint, so rotated/scaled letters are
        # measured before wrapping and adjacent glyph boxes never cross.
        paths = [[(x-xmin, y) for x, y in stroke] for stroke in paths]
        return dict(token, paths=paths, bounds=(0., xmax-xmin),
                    advance=max(xmax-xmin, size*scale*.12)+gap,
                    variation=dict(scale=scale, rotation=degrees, vertical=vertical, gap=gap,stroke_adjustment=adjustment))

    def line_phase(self):
        return self.line_rng.uniform(0., 2*math.pi)

    def baseline(self, phase, x, usable):
        return self.amplitude('baseline') * math.sin(phase + math.pi*x/usable)

    def line_slant(self):
        return self.slant_rng.uniform(-self.amplitude('slant'), self.amplitude('slant'))

    def layout_state(self):
        return tuple(rng.getstate() for rng in (self.line_rng,self.join_rng,self.slant_rng))

    def restore_layout(self, state):
        for rng,value in zip((self.line_rng,self.join_rng,self.slant_rng),state): rng.setstate(value)


def point_segment(p, a, b):
    dx, dy = b[0]-a[0], b[1]-a[1]
    length = dx*dx+dy*dy
    t = max(0., min(1., ((p[0]-a[0])*dx+(p[1]-a[1])*dy)/length)) if length else 0.
    return math.dist(p, (a[0]+t*dx, a[1]+t*dy))


def segment_distance(a, b, c, d):
    def side(p, q, r):
        return (q[0]-p[0])*(r[1]-p[1])-(q[1]-p[1])*(r[0]-p[0])
    if side(a,b,c)*side(a,b,d)<0 and side(c,d,a)*side(c,d,b)<0:
        return 0.
    return min(point_segment(a,c,d),point_segment(b,c,d),point_segment(c,a,b),point_segment(d,a,b))


def vary_endpoint(paths, size, percent, rng, report=None, endpoint=None):
    """Adjust a physical stroke-end span, independent of point density."""
    if report is not None:report.update(changed=False,max_shift_mm=0.,changed_points=0,changed_ends=0)
    candidates=[(i,end) for i,s in enumerate(paths) if len(s)>1 for end in (0,-1)] if endpoint is None else [endpoint]
    if endpoint is None:rng.shuffle(candidates)
    clearance=size*.02
    for i,end in candidates:
        stroke=paths[i]
        if math.dist(stroke[0],stroke[-1])<clearance:continue
        working=[tuple(p) for p in (stroke if end==0 else reversed(stroke))]
        distances=[0.]
        for a,b in zip(working,working[1:]):distances.append(distances[-1]+math.dist(a,b))
        support=min(size*.32,distances[-1]*.45)
        amplitude=min(size*percent/100,support*.35)
        if amplitude<size*.008:continue
        # Insert an exact unchanged anchor inside a long edge. Otherwise a
        # sparse font would deform all the way to the next distant vertex.
        for k in range(1,len(working)):
            if distances[k-1]<support<distances[k]:
                t=(support-distances[k-1])/(distances[k]-distances[k-1])
                a,b=working[k-1],working[k]
                working.insert(k,(a[0]+(b[0]-a[0])*t,a[1]+(b[1]-a[1])*t))
                distances.insert(k,support);break
        p=working[0]
        target=next((q for q,d in zip(working,distances) if d>=min(support*.3,size*.06)),None)
        if target is None:continue
        length=math.dist(p,target)
        if length<1e-8:continue
        direction=((p[0]-target[0])/length,(p[1]-target[1])/length)
        obstacles=[(a,b) for j,s in enumerate(paths) for k,(a,b) in enumerate(zip(working if j==i else s,(working if j==i else s)[1:]))
                   if j!=i or min(distances[k],distances[k+1])>support+clearance*2]
        if any(point_segment(p,a,b)<clearance for a,b in obstacles):continue
        delta=amplitude*rng.uniform(.7,1.)*rng.choice((-1,1))
        varied=[]
        for q,d in zip(working,distances):
            t=max(0.,1-d/support);weight=t*t*(3-2*t)
            varied.append((q[0]+direction[0]*delta*weight,q[1]+direction[1]*delta*weight))
        valid=True
        for a,b,c,d in zip(working,working[1:],varied,varied[1:]):
            if a==c and b==d:continue
            for u,v in obstacles:
                old=segment_distance(a,b,u,v);new=segment_distance(c,d,u,v)
                anchored=(a==c and point_segment(a,u,v)<1e-8 or b==d and point_segment(b,u,v)<1e-8)
                if anchored:
                    middle=((c[0]+d[0])/2,(c[1]+d[1])/2)
                    if point_segment(middle,u,v)<clearance*.1:valid=False;break
                elif new<clearance or old<clearance:
                    valid=False;break
            if not valid:break
        if valid:
            result=[list(s) for s in paths];result[i]=varied if end==0 else list(reversed(varied))
            if report is not None:report.update(changed=True,max_shift_mm=abs(delta),changed_points=sum(math.dist(a,b)>1e-8 for a,b in zip(working,varied)),changed_ends=1)
            return result
    return paths


def free_endpoints(paths,size):
    """Geometric free ends, excluding closed strokes and nearby/connected ink."""
    clearance=size*.02
    result=[]
    for i,stroke in enumerate(paths):
        if len(stroke)<2 or math.dist(stroke[0],stroke[-1])<clearance:continue
        arc=[0.]
        for a,b in zip(stroke,stroke[1:]):arc.append(arc[-1]+math.dist(a,b))
        if arc[-1]<size*.05:continue
        for end in (0,-1):
            p=stroke[end]
            obstacles=[]
            for j,other in enumerate(paths):
                for k,(a,b) in enumerate(zip(other,other[1:])):
                    if i==j:
                        along=min(arc[k],arc[k+1]) if end==0 else arc[-1]-max(arc[k],arc[k+1])
                        if along<=size*.12:continue
                    obstacles.append((a,b))
            if not any(point_segment(p,a,b)<clearance for a,b in obstacles):result.append((i,end))
    return result


def vary_endpoints(paths,size,percent,rng,probability=45.,report=None):
    """Consider every original free end, applying bounded sequential edits.

    Starting ends use 55% and finishing ends 90% of the per-end limit, with
    additional random attenuation. Total endpoint displacement is at most
    twice the selected amplitude for this glyph, regardless of its complexity.
    """
    eligible=free_endpoints(paths,size)
    if report is not None:
        report.update(changed=False,max_shift_mm=0.,changed_points=0,changed_ends=0,
                      eligible_ends=len(eligible),selected_ends=0,total_shift_mm=0.,end_changes=[])
    if percent<=0 or probability<=0:return paths
    rng.shuffle(eligible)
    result=paths;budget=size*percent/100*2;used=0.;changes=[];points=0;selected=0
    for index,end in eligible:
        if rng.random()>=probability/100:continue
        selected+=1
        remaining=max(0.,budget-used)
        if remaining<size*.008:continue
        strength=.55 if end==0 else .9
        requested=min(percent*strength*rng.uniform(.6,1.),remaining*100/size)
        detail={}
        varied=vary_endpoint(result,size,requested,rng,detail,endpoint=(index,end))
        if not detail['changed']:continue
        shift=detail['max_shift_mm']
        if shift>remaining+1e-8:continue
        result=varied;used+=shift;points+=detail['changed_points']
        changes.append(dict(stroke_index=index,end='start' if end==0 else 'end',max_shift_mm=shift))
    if report is not None:
        report.update(changed=bool(changes),max_shift_mm=max((c['max_shift_mm'] for c in changes),default=0.),
                      changed_points=points,changed_ends=len(changes),selected_ends=selected,
                      total_shift_mm=min(budget,used),end_changes=changes)
    return result


def connect_line(groups, variation, size):
    """Join adjacent plain-text glyphs only, using short forward curves with clear ink."""
    if variation and variation.amplitude('cursive') and variation.config.get('cursive_style') in ('thread','copybook'):
        from backend.cursive import connect_thread_line
        return connect_thread_line(groups,variation,size)
    result=[]; previous=None; run=0
    for source, paths, formula in groups:
        eligible = bool(paths) and not formula and len(source)==1 and source.isalnum()
        if previous is not None and eligible and variation and run<2:
            a, b = previous[-1][-1], paths[0][0]
            dx, dy = b[0]-a[0], b[1]-a[1]
            outgoing = (a[0]-previous[-1][-2][0], a[1]-previous[-1][-2][1]) if len(previous[-1])>1 else (0,0)
            incoming = (paths[0][1][0]-b[0],paths[0][1][1]-b[1]) if len(paths[0])>1 else (0,0)
            if (size*.02 < dx < size*.85 and abs(dy)<size*.55 and outgoing[0]>0 and incoming[0]>0
                    and variation.join_rng.random()<variation.amplitude('cursive')/100):
                def control(p, direction, sign):
                    factor=min(dx*.3/math.hypot(*direction),.5)
                    return (p[0]+sign*direction[0]*factor,
                            max(min(a[1],b[1]),min(max(a[1],b[1]),p[1]+sign*direction[1]*factor)))
                c, d = control(a,outgoing,1), control(b,incoming,-1)
                curve=[((1-t)**3*a[0]+3*(1-t)**2*t*c[0]+3*(1-t)*t*t*d[0]+t**3*b[0],
                        (1-t)**3*a[1]+3*(1-t)**2*t*c[1]+3*(1-t)*t*t*d[1]+t**3*b[1]) for t in [i/12 for i in range(13)]]
                curve[0],curve[-1]=a,b
                # The adjoining terminal segments lie outside the connector's
                # forward x interval and may touch its endpoints. Check all
                # other ink against whole segments, including between samples.
                obstacles=[(p,q) for j,s in enumerate(previous+paths) for k,(p,q) in enumerate(zip(s,s[1:]))
                           if (j,k) not in ((len(previous)-1,len(previous[-1])-2),(len(previous),0))]
                if all(segment_distance(u,v,p,q)>=min(size*.015,dx*.08)
                       for u,v in zip(curve,curve[1:]) for p,q in obstacles):
                    from backend.glyph_fallback import Stroke
                    result.append(Stroke(curve,getattr(previous[-1],'fallback',None) or getattr(paths[0],'fallback',None),connector=True)); run+=1
                else: run=0
            else: run=0
        else: run=0
        result.extend(paths)
        previous=paths if eligible else None
    return result
