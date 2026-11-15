"""Merge the converted standing-man and seated-man worlds into one VRML file.

Each world keeps its own HUD, controls and landmark system inside one choice
of a top-level Switch. World B's DEF names get a B_ prefix. A toggle button
in each HUD flips the Switch and flies to that body's Home view.
"""
import re, sys

A_PATH, B_PATH, OUT = sys.argv[1:4]
PFX = 'B_'

def split(path):
    t = open(path).read()
    g = re.search(r'^Group \{', t, re.M).start()
    r = re.search(r'^ROUTE ', t, re.M).start()
    return t[:g], t[g:r], t[r:]

def toggle_button(ts_name, label):
    # centred between DRAG RESET (ends x=-.0217) and CONTROLS (starts x~.0215)
    x0, x1 = -.0125, .0125
    return f'''# Body-toggle button (added): switches between standing and seated man.
Shape {{
appearance USE CI_DRAGRESET_BACKPLATE_APP
geometry IndexedFaceSet {{
coord Coordinate {{
point [ {x0} -.055 -.15 {x1} -.055 -.15 {x1} -.0522 -.15 {x0} -.0522 -.15 ] }}
coordIndex [ 0 1 2 3 -1 ]
}}
}}
Transform {{
translation {x0 + .0002} -.0545 -.1499
children Shape {{
appearance USE WTXT_APP
geometry Text {{
fontStyle FontStyle {{
family "SANS"
size 0.0027
}}
string "{label}"
}}
}}
}}
Group {{
children [
DEF {ts_name} TouchSensor {{ }}
Shape {{
appearance USE INVISPLATE_APP
geometry IndexedFaceSet {{
coord Coordinate {{
point [ {x0} -.055 -.1498 {x1} -.055 -.1498 {x1} -.0522 -.1498 {x0} -.0522 -.1498 ] }}
coordIndex [ 0 1 2 3 -1 ]
}}
}}
]
}}
'''

def add_button(nodes, ts_name, label):
    anchor = 'DEF DRAGRESET_SCR Script {'
    assert nodes.count(anchor) == 1
    return nodes.replace(anchor, toggle_button(ts_name, label) + anchor)

headA, nodesA, routesA = split(A_PATH)
_, nodesB, routesB = split(B_PATH)

nodesA = add_button(nodesA, 'BODYTOGGLE_TS', 'SHOW SEATED')
nodesB = add_button(nodesB, 'BODYTOGGLE_TS', 'SHOW STANDING')

# shared Background and NavigationInfo go outside the Switch, so they stay bound
bg_re = re.compile(r'# A uniform tan background\.\nBackground \{.*?\n\}\n', re.S)
nav_re = re.compile(r'NavigationInfo \{.*?\n\}\n', re.S)
bg = bg_re.search(nodesA).group(0); nav = nav_re.search(nodesA).group(0)
assert bg_re.search(nodesB) and nav_re.search(nodesB)
nodesA = bg_re.sub('', nodesA, count=1); nodesB = bg_re.sub('', nodesB, count=1)
nodesA = nav_re.sub('', nodesA, count=1); nodesB = nav_re.sub('', nodesB, count=1)

# prefix every DEF/USE name in world B, and the node names in its ROUTEs
nodesB = re.sub(r'\b(DEF|USE)(\s+)([A-Za-z_][\w-]*)', lambda m: f'{m.group(1)}{m.group(2)}{PFX}{m.group(3)}', nodesB)
routesB = re.sub(r'^ROUTE (\S+?)\.(\S+) TO (\S+?)\.(\S+)\s*$',
                 lambda m: f'ROUTE {PFX}{m.group(1)}.{m.group(2)} TO {PFX}{m.group(3)}.{m.group(4)}',
                 routesB, flags=re.M)

# sanity: no DEF name collisions remain
da = set(re.findall(r'DEF\s+(\S+)', nodesA)); db = set(re.findall(r'DEF\s+(\S+)', nodesB))
assert not (da & db), sorted(da & db)[:10]

headA = headA.replace('title "AnthroGloss: Standing Man"', 'title "AnthroGloss: Standing Man and Man in Wheelchair"')

toggle_script = f'''# Body toggle (added): flips BODY_SWITCH and binds the other body's Home view.
DEF BODYTOGGLE_SCR Script {{
eventIn SFBool toggle
field SFNode sw USE BODY_SWITCH
field SFNode aHomeA USE HOME_A
field SFNode aHomeB USE HOME_B
field SFNode bHomeA USE {PFX}HOME_A
field SFNode bHomeB USE {PFX}HOME_B
directOutput TRUE
url "javascript:
function bindHome(h1, h2) {{
var bound = false;
try {{ bound = h1.isBound; }} catch (e) {{}}
if (bound) h2.set_bind = TRUE; else h1.set_bind = TRUE;
}}
function toggle(value, time) {{
if (!value) return;
if (sw.whichChoice == 0) {{
sw.whichChoice = 1;
bindHome(bHomeA, bHomeB);
}} else {{
sw.whichChoice = 0;
bindHome(aHomeA, aHomeB);
}}
}}
"
}}
'''

out = (headA
       + nav + bg
       + '# Both bodies; choice 0 = standing man (default), choice 1 = man in wheelchair.\n'
       + 'DEF BODY_SWITCH Switch {\nwhichChoice 0\nchoice [\n'
       + '# ===== Standing man =====\nGroup {\nchildren [\n' + nodesA + ']\n}\n'
       + '# ===== Man in wheelchair =====\nGroup {\nchildren [\n' + nodesB + ']\n}\n'
       + ']\n}\n'
       + toggle_script
       + routesA.rstrip('\n') + '\n'
       + routesB.rstrip('\n') + '\n'
       + f'ROUTE BODYTOGGLE_TS.isActive TO BODYTOGGLE_SCR.toggle\n'
       + f'ROUTE {PFX}BODYTOGGLE_TS.isActive TO BODYTOGGLE_SCR.toggle\n')
open(OUT, 'w').write(out)
print('A defs', len(da), 'B defs', len(db), 'size', len(out))
