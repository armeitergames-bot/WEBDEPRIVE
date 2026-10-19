"""Genera la skin estilo Fortnite en Blender (1.80 m, Z arriba, mira hacia -Y).
Uso: blender --background --python crear_skin.py   (o con el modulo bpy de pip)
"""
import bpy, bmesh, math, os
from mathutils import Vector

OUT = os.path.dirname(os.path.abspath(__file__))
bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene

# ---------- materiales ----------
def mat(name, color, rough=0.6, metal=0.0, sss=0.0):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*color, 1)
    b.inputs["Roughness"].default_value = rough
    b.inputs["Metallic"].default_value = metal
    if sss:
        b.inputs["Subsurface Weight"].default_value = sss
        b.inputs["Subsurface Radius"].default_value = (0.9, 0.4, 0.25)
        b.inputs["Subsurface Scale"].default_value = 0.01
    m.diffuse_color = (*color, 1)
    return m

M = {
    "piel":    mat("Piel_Morena",     (0.22, 0.105, 0.05), 0.45, sss=0.1),
    "chamarra":mat("Chamarra_Rojo",   (0.55, 0.012, 0.018), 0.75),
    "manga":   mat("Chamarra_Blanco", (0.90, 0.89, 0.86), 0.8),
    "sudadera":mat("Sudadera_Azul",   (0.012, 0.045, 0.28), 0.85),
    "jeans":   mat("Mezclilla_Clara", (0.22, 0.38, 0.62), 0.9),
    "tenis":   mat("Tenis_Blanco",    (0.93, 0.93, 0.93), 0.5),
    "suela":   mat("Suela",           (0.80, 0.80, 0.78), 0.7),
    "cinturon":mat("Cinturon_Blanco", (0.92, 0.91, 0.88), 0.35),
    "oro":     mat("Hebilla_Oro",     (0.83, 0.62, 0.22), 0.25, metal=1.0),
    "pelo":    mat("Pelo_Negro",      (0.012, 0.010, 0.010), 0.45),
    "ojo_b":   mat("Ojo_Blanco",      (0.90, 0.90, 0.88), 0.2),
    "iris":    mat("Iris_Cafe",       (0.06, 0.025, 0.01), 0.1),
    "labios":  mat("Labios",          (0.16, 0.055, 0.04), 0.5),
}

def add_mat(ob, *mats):
    for m in mats:
        ob.data.materials.append(m)

def smooth(ob, sub=2):
    for p in ob.data.polygons:
        p.use_smooth = True
    if sub:
        ob.modifiers.new("Subdiv", "SUBSURF").levels = sub

def sphere(name, loc, scale, m, seg=32, rings=16, sub=1):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=seg, ring_count=rings, location=loc)
    ob = bpy.context.object; ob.name = name; ob.scale = scale
    bpy.ops.object.transform_apply(scale=True)
    add_mat(ob, m); smooth(ob, sub)
    return ob

def rot_local(ob, euler):
    """Gira la malla sobre su propio centro (los helpers ya aplicaron la transformacion)."""
    from mathutils import Euler, Matrix
    c = sum((v.co for v in ob.data.vertices), Vector()) / len(ob.data.vertices)
    m = Matrix.Translation(c) @ Euler(euler).to_matrix().to_4x4() @ Matrix.Translation(-c)
    ob.data.transform(m)

def cube(name, loc, scale, m, bevel=0.0, sub=2, rot=(0, 0, 0)):
    bpy.ops.mesh.primitive_cube_add(location=loc, rotation=rot)
    ob = bpy.context.object; ob.name = name; ob.scale = scale
    bpy.ops.object.transform_apply(scale=True)
    add_mat(ob, m)
    if bevel:
        bv = ob.modifiers.new("Bevel", "BEVEL"); bv.width = bevel; bv.segments = 3
    smooth(ob, sub)
    return ob

def cyl(name, p1, p2, r, m, verts=16):
    p1, p2 = Vector(p1), Vector(p2)
    d = p2 - p1
    bpy.ops.mesh.primitive_cylinder_add(vertices=verts, radius=r, depth=d.length,
                                        location=(p1 + p2) / 2)
    ob = bpy.context.object; ob.name = name
    ob.rotation_euler = d.to_track_quat("Z", "Y").to_euler()
    add_mat(ob, m); smooth(ob, 0)
    return ob

# ---------- cuerpo (modificador Skin) ----------
# (pos, radio_x, radio_y)
P = {
    "pelvis": ((0, 0, 0.98), 0.165, 0.115),
    "spine":  ((0, 0, 1.13), 0.165, 0.120),
    "chest":  ((0, 0, 1.30), 0.195, 0.130),
    "upper":  ((0, 0, 1.43), 0.185, 0.115),
    "neck":   ((0, 0, 1.53), 0.058, 0.058),
    "neck2":  ((0, 0, 1.585), 0.052, 0.050),
}
for s, sx in (("L", 1), ("R", -1)):
    P["shoulder" + s] = ((0.20 * sx, 0, 1.43), 0.072, 0.072)
    P["elbow" + s]    = ((0.32 * sx, 0.01, 1.19), 0.060, 0.060)
    P["wrist" + s]    = ((0.42 * sx, -0.01, 0.97), 0.050, 0.050)
    P["hand" + s]     = ((0.445 * sx, -0.015, 0.92), 0.030, 0.045)
    P["handE" + s]    = ((0.47 * sx, -0.02, 0.84), 0.022, 0.040)
    P["hip" + s]      = ((0.095 * sx, 0, 0.93), 0.085, 0.085)
    P["knee" + s]     = ((0.105 * sx, -0.01, 0.52), 0.060, 0.062)
    P["ankle" + s]    = ((0.11 * sx, 0, 0.13), 0.058, 0.058)
names = list(P)
edges = [("pelvis", "spine"), ("spine", "chest"), ("chest", "upper"),
         ("upper", "neck"), ("neck", "neck2")]
for s in "LR":
    edges += [("upper", "shoulder" + s), ("shoulder" + s, "elbow" + s),
              ("elbow" + s, "wrist" + s), ("wrist" + s, "hand" + s),
              ("hand" + s, "handE" + s), ("pelvis", "hip" + s),
              ("hip" + s, "knee" + s), ("knee" + s, "ankle" + s)]

me = bpy.data.meshes.new("Cuerpo")
me.from_pydata([P[n][0] for n in names], [(names.index(a), names.index(b)) for a, b in edges], [])
body = bpy.data.objects.new("Cuerpo", me)
scene.collection.objects.link(body)
bpy.context.view_layer.objects.active = body
body.select_set(True)
sk = body.modifiers.new("Skin", "SKIN")
sk.use_smooth_shade = True
for i, n in enumerate(names):
    v = me.skin_vertices[0].data[i]
    v.radius = (P[n][1], P[n][2])
me.skin_vertices[0].data[names.index("pelvis")].use_root = True
sub = body.modifiers.new("Sub", "SUBSURF"); sub.levels = 4
bpy.ops.object.modifier_apply(modifier="Skin")
bpy.ops.object.modifier_apply(modifier="Sub")

order = ["chamarra", "manga", "sudadera", "jeans", "piel"]
add_mat(body, *[M[k] for k in order])
idx = {k: i for i, k in enumerate(order)}

def nearest_edge(c):
    best = None
    for a, b in edges:
        pa, pb = Vector(P[a][0]), Vector(P[b][0])
        d = pb - pa
        t = max(0.0, min(1.0, (c - pa).dot(d) / d.length_squared))
        dist = (c - (pa + d * t)).length
        if best is None or dist < best[0]:
            best = (dist, a, b, t)
    return best

def region(c):
    x, y, z = c
    ax = abs(x)
    _, a, b, t = nearest_edge(Vector(c))
    if b.startswith(("knee", "ankle")) or (b.startswith("hip") and z < 0.99):
        return "jeans"
    if b.startswith(("hand", "handE")):
        return "piel"
    if b.startswith("wrist"):             # puno de rib blanco/rojo/blanco
        return "chamarra" if 0.55 < t < 0.75 else "manga"
    if b.startswith("elbow") or (b.startswith("shoulder") and ax > 0.205):
        return "manga"
    if b == "neck2" or (b == "neck" and z > 1.52):
        return "piel"
    if z < 0.99:
        return "jeans"
    if z < 1.015:                          # sudadera asomando bajo la chamarra
        return "sudadera"
    if z < 1.06:                           # rib de cintura
        return "manga" if 1.03 < z < 1.042 else "chamarra"
    if y < -0.04 and ax < 0.045 and z < 1.46:   # chamarra abierta -> sudadera azul
        return "sudadera"
    if y < -0.04 and ax < 0.058 and z < 1.46:   # vista blanca con broches
        return "manga"
    if z > 1.455 and math.hypot(x, y) < 0.11:   # cuello de rib
        return "chamarra" if 1.475 < z < 1.49 else "manga"
    return "chamarra"

for p in me.polygons:
    p.material_index = idx[region(p.center)]
    p.use_smooth = True
body.modifiers.new("Subdiv", "SUBSURF").levels = 0

for sx in (-1, 1):
    th = sphere("Pulgar", (0.44 * sx, -0.045, 0.915), (0.014, 0.014, 0.032), M["piel"], 16, 8)
    rot_local(th, (math.radians(20), math.radians(15 * sx), 0))

# ---------- capucha + cordones ----------
hood = sphere("Capucha", (0, 0.105, 1.47), (0.15, 0.075, 0.085), M["sudadera"])
for sx in (-1, 1):
    cyl("Cordon", (0.035 * sx, -0.135, 1.43), (0.04 * sx, -0.14, 1.27), 0.006, M["manga"], 8)
    sphere("Cordon_Punta", (0.04 * sx, -0.14, 1.265), (0.009, 0.009, 0.014), M["manga"], 12, 6, 0)
# parche de letra varsity en el pecho
bpy.ops.object.text_add(location=(0.11, -0.128, 1.29), rotation=(math.radians(90), 0, 0))
letra = bpy.context.object; letra.name = "Parche_Letra"
letra.data.body = "D"; letra.data.size = 0.11; letra.data.extrude = 0.004
letra.data.align_x = "CENTER"; letra.data.align_y = "CENTER"
letra.data.bevel_depth = 0.002
add_mat(letra, M["manga"])

# ---------- cinturon LV ----------
bpy.ops.mesh.primitive_torus_add(major_radius=1, minor_radius=0.05, location=(0, 0, 0.965))
belt = bpy.context.object; belt.name = "Cinturon"
belt.scale = (0.185, 0.128, 0.22); bpy.ops.object.transform_apply(scale=True)
add_mat(belt, M["cinturon"]); smooth(belt, 1)
buckle = cube("Hebilla", (0, -0.132, 0.965), (0.035, 0.006, 0.022), M["oro"], bevel=0.004, sub=0)
bpy.ops.object.text_add(location=(0, -0.139, 0.965), rotation=(math.radians(90), 0, 0))
lv = bpy.context.object; lv.name = "Hebilla_LV"
lv.data.body = "LV"; lv.data.size = 0.034; lv.data.extrude = 0.002
lv.data.align_x = "CENTER"; lv.data.align_y = "CENTER"
lv.data.shear = 0.1
add_mat(lv, M["oro"])

# ---------- tenis ----------
shoes = []
for sx in (-1, 1):
    x = 0.11 * sx
    up = cube("Tenis", (x, -0.035, 0.075), (0.058, 0.135, 0.05), M["tenis"], bevel=0.03, sub=2)
    # punta mas baja
    bm = bmesh.new(); bm.from_mesh(up.data)
    for v in bm.verts:
        if v.co.y < -0.05 and v.co.z > 0:
            v.co.z -= 0.035 * min(1, (-v.co.y - 0.05) / 0.08)
    bm.to_mesh(up.data); bm.free()
    sole = cube("Suela", (x, -0.035, 0.018), (0.064, 0.142, 0.018), M["suela"], bevel=0.015, sub=2)
    swoosh = cube("Franja", (x + 0.059 * sx, -0.03, 0.07), (0.003, 0.06, 0.008), M["suela"], sub=0,
                  rot=(math.radians(-15), 0, 0))
    lace = cube("Agujetas", (x, -0.085, 0.11), (0.025, 0.04, 0.006), M["suela"], bevel=0.004, sub=0,
                rot=(math.radians(-25), 0, 0))
    shoes += [up, sole, swoosh, lace]

# ---------- cabeza ----------
HZ = 1.665
head = sphere("Cabeza", (0, -0.005, HZ), (0.098, 0.112, 0.125), M["piel"], 48, 24, 1)
bm = bmesh.new(); bm.from_mesh(head.data)
for v in bm.verts:                     # mandibula mas angosta y menton
    t = max(0.0, (HZ - 0.02 - v.co.z) / 0.11)
    v.co.x *= 1 - 0.28 * t
    if v.co.y < 0:
        v.co.y *= 1 - 0.1 * t
bm.to_mesh(head.data); bm.free()
for sx in (-1, 1):
    sphere("Oreja", (0.097 * sx, 0.01, HZ - 0.005), (0.014, 0.025, 0.034), M["piel"], 16, 8)
    # ojos almendrados (rasgos asiaticos)
    ex, ez, ey = 0.038 * sx, HZ + 0.008, -0.094
    eye = sphere("Ojo", (ex, ey, ez), (0.024, 0.009, 0.012), M["ojo_b"], 24, 12)
    rot_local(eye, (0, math.radians(-8 * sx), 0))
    sphere("Iris", (ex, ey - 0.0085, ez - 0.001), (0.0105, 0.003, 0.0105), M["iris"], 16, 8)
    lid = sphere("Parpado", (ex, ey + 0.001, ez + 0.0085), (0.027, 0.0105, 0.0065), M["piel"], 24, 12)
    rot_local(lid, (0, math.radians(-8 * sx), 0))
    brow = cube("Ceja", (0.04 * sx, -0.099, HZ + 0.036), (0.025, 0.004, 0.0055), M["pelo"], sub=1,
                rot=(0, math.radians(-6 * sx), 0))
nose = sphere("Nariz", (0, -0.106, HZ - 0.03), (0.0105, 0.011, 0.016), M["piel"], 16, 8)
sphere("Boca", (0, -0.104, HZ - 0.062), (0.022, 0.006, 0.0045), M["labios"], 16, 8)

# ---------- pelo negro ----------
hair = sphere("Pelo", (0, 0.002, HZ + 0.012), (0.106, 0.121, 0.124), M["pelo"], 40, 20, 1)
bm = bmesh.new(); bm.from_mesh(hair.data)
cut = [v for v in bm.verts if v.co.z < HZ + 0.012 - 0.01 and not (v.co.y > 0.02 and v.co.z > HZ - 0.07)]
bmesh.ops.delete(bm, geom=[v for v in cut if v.co.y <= 0.02 or v.co.z < HZ - 0.07], context="VERTS")
for v in bm.verts:                     # frente despejada a la altura de las cejas
    if v.co.y < -0.06 and v.co.z < HZ + 0.06:
        v.co.z = max(v.co.z, HZ + 0.06)
bm.to_mesh(hair.data); bm.free()
hair.modifiers.new("Grosor", "SOLIDIFY").thickness = 0.008
hair.modifiers.move(1, 0)
# mechones del fleco
for i, (x, ang) in enumerate([(-0.06, 25), (-0.03, 10), (0.0, -5), (0.03, -18), (0.06, -30)]):
    bpy.ops.mesh.primitive_cone_add(vertices=10, radius1=0.021, radius2=0.003, depth=0.08,
                                    location=(x + 0.012, -0.104, HZ + 0.075))
    c = bpy.context.object; c.name = "Mechon"
    c.rotation_euler = (math.radians(-170), math.radians(-25), 0)
    c.scale = (1, 0.35, 1)
    add_mat(c, M["pelo"]); smooth(c, 1)
for i, (x, z) in enumerate([(-0.05, 0.12), (0.0, 0.135), (0.05, 0.12), (-0.025, 0.11), (0.03, 0.1)]):
    bpy.ops.mesh.primitive_cone_add(vertices=8, radius1=0.032, radius2=0.003, depth=0.05,
                                    location=(x, -0.02 + i * 0.012, HZ + z))
    c = bpy.context.object; c.name = "Mechon_Top"
    c.rotation_euler = (math.radians(-35 + i * 6), math.radians(x * 300), 0)
    add_mat(c, M["pelo"]); smooth(c, 1)

# ---------- esqueleto ----------
arm_data = bpy.data.armatures.new("Rig")
rig = bpy.data.objects.new("Rig", arm_data)
scene.collection.objects.link(rig)
bpy.context.view_layer.objects.active = rig
bpy.ops.object.mode_set(mode="EDIT")
eb = arm_data.edit_bones
def bone(n, h, t, parent=None, connect=False):
    b = eb.new(n); b.head = h; b.tail = t
    if parent:
        b.parent = eb[parent]; b.use_connect = connect
    return b
pos = lambda n: Vector(P[n][0])
bone("hips", pos("pelvis"), pos("spine"))
bone("spine", pos("spine"), pos("chest"), "hips", True)
bone("chest", pos("chest"), pos("upper"), "spine", True)
bone("neck", pos("upper"), pos("neck2"), "chest", True)
bone("head", pos("neck2"), (0, 0, 1.80), "neck", True)
for s in "LR":
    bone("upperarm." + s, pos("shoulder" + s), pos("elbow" + s), "chest")
    bone("forearm." + s, pos("elbow" + s), pos("wrist" + s), "upperarm." + s, True)
    bone("hand." + s, pos("wrist" + s), pos("handE" + s), "forearm." + s, True)
    bone("thigh." + s, pos("hip" + s), pos("knee" + s), "hips")
    bone("shin." + s, pos("knee" + s), pos("ankle" + s), "thigh." + s, True)
    a = pos("ankle" + s)
    bone("foot." + s, a, (a.x, -0.14, 0.04), "shin." + s, True)
bpy.ops.object.mode_set(mode="OBJECT")

def bind_auto(ob):
    bpy.ops.object.select_all(action="DESELECT")
    ob.select_set(True); rig.select_set(True)
    bpy.context.view_layer.objects.active = rig
    bpy.ops.object.parent_set(type="ARMATURE_AUTO")

def bind_bone(ob, bname):
    if ob.type == "MESH":
        bpy.ops.object.select_all(action="DESELECT")
        ob.select_set(True); bpy.context.view_layer.objects.active = ob
        bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)
    ob.vertex_groups.new(name=bname).add(range(len(ob.data.vertices)) if ob.type == "MESH" else [], 1.0, "REPLACE") \
        if ob.type == "MESH" else None
    if ob.type != "MESH":
        mw = ob.matrix_world.copy()
        ob.parent = rig; ob.parent_type = "BONE"; ob.parent_bone = bname
        ob.matrix_world = mw
        return
    md = ob.modifiers.new("Armature", "ARMATURE"); md.object = rig
    ob.modifiers.move(len(ob.modifiers) - 1, 0)
    ob.parent = rig

bind_auto(body)
head_parts = {"Cabeza", "Oreja", "Ojo", "Iris", "Parpado", "Ceja", "Nariz", "Boca", "Pelo",
              "Mechon", "Mechon_Top"}
def side(ob):  # la ubicacion ya se aplico a la malla, asi que se usa su centro
    if ob.type != "MESH":
        return ob.location.x
    return sum(v.co.x for v in ob.data.vertices) / len(ob.data.vertices)

for ob in list(scene.objects):
    if ob in (body, rig):
        continue
    base = ob.name.split(".")[0]
    if base in head_parts:
        bind_bone(ob, "head")
    elif base == "Pulgar":
        bind_bone(ob, "hand.L" if side(ob) > 0 else "hand.R")
    elif base in {"Capucha", "Cordon", "Cordon_Punta", "Parche_Letra"}:
        bind_bone(ob, "chest")
    elif base in {"Cinturon", "Hebilla", "Hebilla_LV"}:
        bind_bone(ob, "hips")
    elif base in {"Tenis", "Suela", "Franja", "Agujetas"}:
        bind_bone(ob, "foot.L" if side(ob) > 0 else "foot.R")

coll = bpy.data.collections.new("Skin")
scene.collection.children.link(coll)
for ob in list(scene.collection.objects):
    scene.collection.objects.unlink(ob); coll.objects.link(ob)

# ---------- escena para render de vista previa ----------
world = bpy.data.worlds.new("Mundo"); scene.world = world
world.use_nodes = True
world.node_tree.nodes["Background"].inputs[0].default_value = (0.55, 0.65, 0.85, 1)
world.node_tree.nodes["Background"].inputs[1].default_value = 0.35
prev = bpy.data.collections.new("Preview"); scene.collection.children.link(prev)
def light(name, loc, energy, size):
    ld = bpy.data.lights.new(name, "AREA"); ld.energy = energy; ld.size = size
    lo = bpy.data.objects.new(name, ld); lo.location = loc
    lo.rotation_euler = (Vector((0, 0, 1.0)) - Vector(loc)).to_track_quat("-Z", "Y").to_euler()
    prev.objects.link(lo)
light("Key", (-2.0, -2.5, 2.8), 220, 2)
light("Fill", (2.5, -1.5, 1.5), 70, 3)
light("Rim", (0.5, 3.0, 2.5), 180, 2)
cam_d = bpy.data.cameras.new("Cam"); cam_d.lens = 50
cam = bpy.data.objects.new("Camara", cam_d); prev.objects.link(cam)
cam.location = (1.6, -4.6, 1.25)
cam.rotation_euler = (Vector((0, 0, 0.92)) - cam.location).to_track_quat("-Z", "Y").to_euler()
scene.camera = cam
bpy.ops.mesh.primitive_plane_add(size=20)
floor = bpy.context.object; floor.name = "Piso"
for c in floor.users_collection: c.objects.unlink(floor)
prev.objects.link(floor)
add_mat(floor, mat("Piso", (0.35, 0.35, 0.38), 0.9))

scene.view_settings.view_transform = "Standard"
scene.view_settings.look = "None"
bpy.context.preferences.filepaths.save_version = 0
bpy.ops.wm.save_as_mainfile(filepath=os.path.join(OUT, "skin_chino_varsity.blend"))

# exportaciones para otros motores (solo la skin)
for ob in bpy.data.objects:
    ob.select_set(ob.name in coll.all_objects)
bpy.ops.export_scene.fbx(filepath=os.path.join(OUT, "skin_chino_varsity.fbx"),
                         use_selection=True, add_leaf_bones=False)
bpy.ops.export_scene.gltf(filepath=os.path.join(OUT, "skin_chino_varsity.glb"),
                          use_selection=True, export_format="GLB")
print("OK")
