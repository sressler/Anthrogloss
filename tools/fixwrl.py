"""Rewrite AnthroGloss landmark logic so it works in X_ITE.

- One central LANDMARKS script does clear-then-highlight in a single function,
  so event order no longer matters.
- Text-ball clicks bind the landmark Viewpoint directly (SCR1_xx scripts);
  the Anchor wrappers become plain Groups.
"""
import re, sys
from collections import defaultdict

src, dst = sys.argv[1], sys.argv[2]
t = open(src).read()

routes = re.findall(r'^ROUTE (\S+)\.(\S+) TO (\S+)\.(\S+)\s*$', t, re.M)
mats = defaultdict(list)   # idx -> material DEF names
fnsw = {}                  # idx -> FNTEXT switch
vpb = {}                   # idx -> viewpoint DEF
for a, af, b, bf in routes:
    m = re.fullmatch(r'SCR0_(\d+)', a)
    if m:
        i = m.group(1)
        if af == 'theColor': mats[i].append(b)
        if af == 'fullnameChoice': fnsw[i] = b
    m = re.fullmatch(r'SCR0_(\d+)', b)
    if m and af == 'isBound':
        vpb[m.group(1)] = a

# fullname value each script set when activated
fnval = {}
for i, body in re.findall(r'DEF SCR0_(\d+) Script \{(.*?)\n"\n\}', t, re.S):
    fnval[i] = int(re.search(r'function isActive.*?fullnameChoice = (-?\d+);', body, re.S).group(1))

idx = sorted(fnval)
assert all(len(mats[i]) == 4 for i in idx), {i: mats[i] for i in idx if len(mats[i]) != 4}
assert set(fnsw) == set(idx) and set(vpb) == set(idx)

# 1. replace SCR0_xx scripts
def scr0(m):
    i = m.group(1)
    return f'''DEF SCR0_{i} Script {{
eventIn SFBool isOver
eventIn SFBool isActive
eventOut SFInt32 radiusChoice
eventOut SFInt32 sel
url "javascript:
function initialize () {{ radiusChoice = 0; }}
function isOver(value,time) {{ radiusChoice = value ? 1 : 0; }}
function isActive(value,time) {{ if (value) sel = {int(i)}; }}
"
}}'''
t, n0 = re.subn(r'DEF SCR0_(\d+) Script \{.*?\n"\n\}', scr0, t, flags=re.S)

# 2. replace SCR1_xx (text-ball hover) scripts: add click -> bind viewpoint
def scr1(m):
    i = m.group(1)
    return f'''DEF SCR1_{i} Script {{
eventIn SFBool isOver
eventIn SFBool isActive
eventOut SFInt32 radiusChoice
field SFNode vp USE {vpb[i]}
directOutput TRUE
url "javascript:
function initialize () {{ radiusChoice = 0; }}
function isOver(value,time) {{ radiusChoice = value ? 1 : 0; }}
function isActive(value,time) {{ if (value) vp.set_bind = TRUE; }}
"
}}'''
t, n1 = re.subn(r'DEF SCR1_(\d+) Script \{.*?\n"\n\}', scr1, t, flags=re.S)

# 3. Anchors -> Groups (drop the #VPBnn url)
t, na = re.subn(r'children Anchor \{', 'children Group {', t)
t, nu = re.subn(r'^url "#VPB\d+"\n', '', t, flags=re.M)

# 4. drop the old order-sensitive routes
drop = re.compile(r'^ROUTE SCR0_\d+\.(clearAll|theColor|toClearfullnames|fullnameChoice) TO .*\n', re.M)
t, nr = drop.subn('', t)

# 5. central controller + new routes
sws = sorted(set(fnsw.values()))
mat_list = ' '.join(f'USE {m}' for i in idx for m in mats[i])
landmarks = f'''# Central landmark selector (added for X_ITE): clears all, then highlights one.
DEF LANDMARKS Script {{
eventIn SFInt32 select
field SFColor green 0 0.5 0
field SFColor red 1 0 0
field SFInt32 current -1
field MFNode mats [ {mat_list} ]
field MFNode sws [ {' '.join('USE ' + s for s in sws)} ]
field MFInt32 swOf [ {' '.join(str(sws.index(fnsw[i])) for i in idx)} ]
field MFInt32 fnVal [ {' '.join(str(fnval[i]) for i in idx)} ]
directOutput TRUE
url "javascript:
function select(i, time) {{
  if (i === current) return;
  current = i;
  for (var j = 0; j < mats.length; j++) mats[j].diffuseColor = green;
  for (var k = 0; k < sws.length; k++) sws[k].whichChoice = -1;
  for (var j = 4 * i; j < 4 * i + 4; j++) mats[j].diffuseColor = red;
  sws[swOf[i]].whichChoice = fnVal[i];
}}
"
}}
'''
new_routes = ''.join(f'ROUTE SCR0_{i}.sel TO LANDMARKS.select\nROUTE TBALLTS{i}.isActive TO SCR1_{i}.isActive\n' for i in idx)
first = re.search(r'^ROUTE ', t, re.M).start()
t = t[:first] + landmarks + new_routes + t[first:]

# 6. shrink the two HUD landmark columns to 50%, anchored at their outer top corners
for name, cx in (('LEFTCOL_TRANSFORM', -0.098), ('RIGHTCOL_TRANSFORM', 0.1032)):
    t, k = re.subn(rf'DEF {name} Transform {{\n',
                   f'DEF {name} Transform {{\ncenter {cx} 0.056 -0.152\nscale 0.5 0.5 0.5\n', t)
    assert k == 1, name

# 7. default (home) positions captured from the user's display
LEFT_HOME = '0.04271 -0.003044 0'
RIGHT_HOME = '-0.048248 -0.004922 0'
HOME_POS = '-1.72 -8.07 120.29'
HOME_ORI = '0 -1 0 0.0174557'
import os
if os.environ.get('HOME_POS'): HOME_POS = os.environ['HOME_POS']

for name, home in (('LEFTCOL', LEFT_HOME), ('RIGHTCOL', RIGHT_HOME)):
    t, k = re.subn(rf'(DEF {name}_DRAG PlaneSensor {{\n)', rf'\1offset {home}\n', t); assert k == 1
    t, k = re.subn(rf'(DEF {name}_TRANSFORM Transform {{\n)', rf'\1translation {home}\n', t); assert k == 1

new_reset = f'''DEF DRAGRESET_SCR Script {{
eventIn SFBool isActive
eventOut SFVec3f resetTrans
eventOut SFVec3f resetLeft
eventOut SFVec3f resetRight
field SFVec3f zeroTrans 0 0 0
field SFVec3f leftHome {LEFT_HOME}
field SFVec3f rightHome {RIGHT_HOME}
url "javascript:
function initialize() {{
resetTrans = zeroTrans; resetLeft = leftHome; resetRight = rightHome;
}}
function isActive(value,time) {{
if (value) {{ resetTrans = zeroTrans; resetLeft = leftHome; resetRight = rightHome; }}
}}
"
}}'''
t, k = re.subn(r'DEF DRAGRESET_SCR Script \{.*?\n"\n\}', lambda m: new_reset, t, flags=re.S); assert k == 1
t = t.replace('ROUTE DRAGRESET_SCR.resetTrans TO LEFTCOL_TRANSFORM.translation',
              'ROUTE DRAGRESET_SCR.resetLeft TO LEFTCOL_TRANSFORM.translation')
t = t.replace('ROUTE DRAGRESET_SCR.resetTrans TO RIGHTCOL_TRANSFORM.translation',
              'ROUTE DRAGRESET_SCR.resetRight TO RIGHTCOL_TRANSFORM.translation')

# 8. home viewpoints (first in file => bound at load). Two identical copies so
#    BODY RESET can always re-bind one even if the other is already bound.
home_vps = f'''# Default (home) view of the body. HOME_B is an identical twin used by BODY RESET.
DEF HOME_A Viewpoint {{
position {HOME_POS}
orientation {HOME_ORI}
description "Home"
}}
DEF HOME_B Viewpoint {{
position {HOME_POS}
orientation {HOME_ORI}
}}
'''
t, k = re.subn(r'(# General viewpoints\.\n)', lambda m: home_vps + m.group(1), t, count=1); assert k == 1

# 9. One RESET control group replaces the separate DRAG RESET / BODY RESET buttons:
#    a darker frame labelled RESET holding three buttons, BODY | MENUS | ALL.
Y0, Y1, Z = -.055, -.0522, -.15

def quad(x0, x1, y0, y1, z):
    return f'{x0} {y0} {z} {x1} {y0} {z} {x1} {y1} {z} {x0} {y1} {z}'

def button(ts, label, x0, x1):
    tw = 0.00185 * len(label)                        # approx. text width at size .0027
    tx = round((x0 + x1) / 2 - tw / 2, 5)
    return f"""Shape {{
appearance USE CI_DRAGRESET_BACKPLATE_APP
geometry IndexedFaceSet {{
coord Coordinate {{ point [ {quad(x0, x1, Y0, Y1, Z)} ] }}
coordIndex [ 0 1 2 3 -1 ]
}}
}}
Transform {{
translation {tx} -.0545 -.1499
children Shape {{
appearance USE WTXT_APP
geometry Text {{
fontStyle FontStyle {{ family "SANS" size 0.0027 }}
string "{label}"
}}
}}
}}
Group {{
children [
DEF {ts} TouchSensor {{ }}
Shape {{
appearance USE INVISPLATE_APP
geometry IndexedFaceSet {{
coord Coordinate {{ point [ {quad(x0, x1, Y0, Y1, Z + .0002)} ] }}
coordIndex [ 0 1 2 3 -1 ]
}}
}}
]
}}
"""

FX0, FX1 = -.0627, -.0215                            # frame spans the old two buttons
reset_group = f"""# RESET control group (added): BODY flies back to the home view, MENUS returns
# the dragged menus to their home positions, ALL does both.
Shape {{
appearance DEF RESETFRAME_APP Appearance {{ material Material {{ diffuseColor 0 .3 0 }} }}
geometry IndexedFaceSet {{
coord Coordinate {{ point [ {quad(FX0, FX1, Y0 - .0004, Y1 + .0004, Z - .0002)} ] }}
coordIndex [ 0 1 2 3 -1 ]
}}
}}
Transform {{
translation {FX0 + .0006} -.0545 -.1499
children Shape {{
appearance USE WTXT_APP
geometry Text {{
fontStyle FontStyle {{ family "SANS" size 0.0027 }}
string "RESET"
}}
}}
}}
""" + button('BODYRESET_TS', 'BODY', -.0520, -.0428) \
    + button('DRAGRESET_TS', 'MENUS', -.0423, -.0310) \
    + button('ALLRESET_TS', 'ALL', -.0305, -.0220)

# drop the original DRAG RESET visuals (backplate, text, touch-plate)
t, k = re.subn(r'# Drag-reset button and script\..*?(?=DEF DRAGRESET_SCR Script \{)',
               lambda m: reset_group, t, count=1, flags=re.S); assert k == 1

body_reset_script = """DEF BODYRESET_SCR Script {
eventIn SFBool isActive
eventIn SFBool aBound
field SFBool aIsBound FALSE
field SFNode homeA USE HOME_A
field SFNode homeB USE HOME_B
directOutput TRUE
url "javascript:
function aBound(value, time) { aIsBound = value; }
function isActive(value, time) {
if (!value) return;
var a = aIsBound;
try { a = a || homeA.isBound; } catch (e) {}
if (a) homeB.set_bind = TRUE;
else homeA.set_bind = TRUE;
}
"
}
"""
t, k = re.subn(r'(DEF DRAGRESET_SCR Script \{)', lambda m: body_reset_script + m.group(1), t, count=1); assert k == 1
t = t.replace('ROUTE DRAGRESET_TS.isActive TO DRAGRESET_SCR.isActive',
              'ROUTE DRAGRESET_TS.isActive TO DRAGRESET_SCR.isActive\n'
              'ROUTE BODYRESET_TS.isActive TO BODYRESET_SCR.isActive\n'
              'ROUTE ALLRESET_TS.isActive TO DRAGRESET_SCR.isActive\n'
              'ROUTE ALLRESET_TS.isActive TO BODYRESET_SCR.isActive\n'
              'ROUTE HOME_A.isBound TO BODYRESET_SCR.aBound')

open(dst, 'w').write(t)
print(f'landmarks={len(idx)} scr0={n0} scr1={n1} anchors={na} urls={nu} routes_dropped={nr} switches={len(sws)}')
