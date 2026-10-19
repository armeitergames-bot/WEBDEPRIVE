# -*- coding: utf-8 -*-
"""
ESTADIO OASIS — Ciudad Ideal
============================
Generador procedural para Blender (probado en Blender 5.1; compatible con 4.2+).

Cómo usarlo:
  1. Abre Blender  ->  Archivo > Nuevo > General.
  2. Ve a la pestaña "Scripting", pulsa "Abrir" y elige este archivo.
  3. Pulsa "Ejecutar script" (▶).  Tarda ~10-40 s según tu equipo.
  ¡OJO! El script BORRA todo lo que haya en la escena antes de construir.

Concepto: un estadio para 100,000 personas que "brota" de una colina-parque.
La colina sube con pendiente de 4.7 % hasta el vestíbulo principal (acceso
universal sin escaleras), la cubierta es un campo de hojas (ETFE translúcido
+ paneles solares) sostenido por árboles estructurales, y el agua de lluvia
baja por una cascada hasta un lago que enfría el entorno.

Todas las medidas están en metros. Cambia los PARÁMETROS para experimentar.
"""

import bpy
import bmesh
import math
import random
from mathutils import Vector

random.seed(2026)

# --------------------------------------------------------------------------
# PARÁMETROS
# --------------------------------------------------------------------------
A, B, NEXP = 62.5, 42.0, 2.6   # semiejes de la zona de campo y forma superelipse
SEG = 384                      # divisiones alrededor del estadio
AISLE_EVERY = 16               # cada cuántas divisiones hay un pasillo
SEAT_W, ROW_D = 0.52, 0.85     # ancho de butaca y profundidad de fila
ACC_W = 2.6                    # plataforma para sillas de ruedas (+ acompañante)
Z_FIELD = -8.0                 # el campo está hundido 8 m (menos masa visual, más fresco)
Z_CONC = 7.0                   # vestíbulo principal = cima de la colina
FACADE_D = 90.5                # fachada de vidrio
FIN_D = 94.0                   # aletas paramétricas
TREE_D = 99.0                  # árboles estructurales
BERM_END = 238.0               # fin de la colina (z = 0)
PLAZA_W = 32.0
ROOF_IN, ROOF_OUT = 12.0, 106.0
N_TREES = 24
ENTRIES = [math.pi / 8 + k * math.pi / 4 for k in range(8)]   # 8 accesos

# gradas: (nombre, d0, z0, filas, contrahuella, z frente inferior, z trasera inferior,
#          plataforma accesible al frente, atrás, frente LED)
TIERS = [
    ("Grada_1_Baja",  8.0, Z_CONC - 32 * 0.42, 32, 0.42, Z_FIELD, Z_FIELD, False, True,  False),
    ("Grada_2_Media", 39.5, 15.0,              24, 0.52, 11.0,    14.0,    True,  False, True),
    ("Grada_3_Alta",  60.5, 36.0,              30, 0.62, 33.0,    20.0,    True,  False, True),
]


# --------------------------------------------------------------------------
# GEOMETRÍA BASE
# --------------------------------------------------------------------------
def se(t, d):
    """Punto de la superelipse desplazada 'd' metros desde el borde del campo."""
    a, b = A + d, B + d
    c, s = math.cos(t), math.sin(t)
    return (a * math.copysign(abs(c) ** (2 / NEXP), c),
            b * math.copysign(abs(s) ** (2 / NEXP), s))


def perim(d, n=720):
    pts = [se(2 * math.pi * i / n, d) for i in range(n)]
    return sum(math.dist(pts[i], pts[i - 1]) for i in range(n))


def d_of(x, y):
    """Inverso aproximado de se(): qué tan lejos está (x, y) del campo."""
    def f(d):
        return (abs(x) / (A + d)) ** NEXP + (abs(y) / (B + d)) ** NEXP - 1
    lo, hi = -min(A, B) + 0.01, 5000.0
    if f(lo) <= 0:
        return lo
    for _ in range(50):
        mid = (lo + hi) / 2
        if f(mid) > 0:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def r_eff(d):
    return (A + B) / 2 + d


def ang_dist(a, b):
    return abs((a - b + math.pi) % (2 * math.pi) - math.pi)


def z_roof(d, t):
    """Cubierta en silla de montar: más alta en los laterales largos."""
    u = (d - ROOF_IN) / (ROOF_OUT - ROOF_IN)
    return 70.0 - 4.0 * u - 3.0 * math.cos(2 * t)


def z_berm(d):
    if d <= FACADE_D:
        return Z_CONC
    if d >= BERM_END:
        return 0.0
    return Z_CONC * (1 - (d - FACADE_D) / (BERM_END - FACADE_D))


def outward(t, d):
    """Vector normal (hacia afuera) y tangente de la superelipse."""
    e = 1e-4
    p0, p1 = se(t - e, d), se(t + e, d)
    tan = Vector((p1[0] - p0[0], p1[1] - p0[1], 0)).normalized()
    return Vector((tan.y, -tan.x, 0)), tan


# --------------------------------------------------------------------------
# MATERIALES
# --------------------------------------------------------------------------
def _set(node, names, val):
    for n in names:
        sock = node.inputs.get(n)
        if sock is not None:
            sock.default_value = val
            return


def make_mat(name, color, rough=0.5, metal=0.0, emit=0.0, trans=0.0, alpha=1.0):
    m = bpy.data.materials.new(name)
    try:
        m.use_nodes = True
    except Exception:
        pass
    m.diffuse_color = (*color, alpha)
    m.roughness = rough
    nt = m.node_tree
    bsdf = next((n for n in nt.nodes if n.type == 'BSDF_PRINCIPLED'), None)
    if bsdf is None:
        bsdf = nt.nodes.new('ShaderNodeBsdfPrincipled')
        out = next((n for n in nt.nodes if n.type == 'OUTPUT_MATERIAL'), None)
        if out is None:
            out = nt.nodes.new('ShaderNodeOutputMaterial')
        nt.links.new(bsdf.outputs[0], out.inputs[0])
    _set(bsdf, ["Base Color"], (*color, 1.0))
    _set(bsdf, ["Roughness"], rough)
    _set(bsdf, ["Metallic"], metal)
    if trans:
        _set(bsdf, ["Transmission Weight", "Transmission"], trans)
        _set(bsdf, ["IOR"], 1.45)
    if alpha < 1.0:
        _set(bsdf, ["Alpha"], alpha)
    if emit:
        _set(bsdf, ["Emission Color", "Emission"], (*color, 1.0))
        _set(bsdf, ["Emission Strength"], emit)
    return m


def hexc(h):
    """'#rrggbb' -> color lineal."""
    h = h.lstrip('#')
    srgb = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    return tuple(c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in srgb)


def build_materials():
    M = {}
    M['concreto'] = make_mat("Concreto_Claro", hexc('#c9c3b8'), 0.8)
    M['pasillo'] = make_mat("Pasillo_Escalera", hexc('#e6e1d6'), 0.7)
    # butacas: gradiente bosque -> oasis -> desierto/sol
    seat_hex = ['#1f4d2c', '#2f7d3a', '#5f9e3d', '#2a9d8f', '#d9b26f', '#efcf7a']
    M['butacas'] = [make_mat(f"Butaca_{i}", hexc(h), 0.45) for i, h in enumerate(seat_hex)]
    M['led'] = make_mat("LED_Cinta", hexc('#3ef0c8'), 0.3, emit=3.0)
    M['accesible'] = make_mat("Plataforma_Accesible", hexc('#2a6fdb'), 0.5)
    M['vidrio'] = make_mat("Vidrio_Fachada", hexc('#9fd3e0'), 0.05, trans=1.0, alpha=0.35)
    M['etfe'] = make_mat("ETFE_Translucido", hexc('#f4f8f6'), 0.25, trans=0.75, alpha=0.6)
    M['solar'] = make_mat("Panel_Solar", hexc('#14263f'), 0.15, metal=0.6)
    M['acero'] = make_mat("Acero_Blanco", hexc('#f2f2ee'), 0.35, metal=0.4)
    M['madera'] = make_mat("Madera_Laminada", hexc('#b07a46'), 0.6)
    M['jardin_v'] = make_mat("Jardin_Vertical", hexc('#3d7a35'), 0.9)
    M['halo'] = make_mat("Pantalla_Halo_360", hexc('#2f8fd8'), 0.3, emit=2.5)
    M['cesped_a'] = make_mat("Cesped_Campo_A", hexc('#3f8f3a'), 0.9)
    M['cesped_b'] = make_mat("Cesped_Campo_B", hexc('#367e33'), 0.9)
    M['linea'] = make_mat("Lineas_Campo", hexc('#ffffff'), 0.6)
    M['pasto'] = make_mat("Pasto_Colina", hexc('#6a9f45'), 0.95)
    M['seto'] = make_mat("Seto_Terraza", hexc('#3e7334'), 0.95)
    M['lavanda'] = make_mat("Flores_Lavanda", hexc('#9b7fc7'), 0.9)
    M['amarillo'] = make_mat("Flores_Amarillas", hexc('#e8c547'), 0.9)
    M['piedra'] = make_mat("Piedra_Sendero", hexc('#ddd2bd'), 0.8)
    M['plaza'] = make_mat("Plaza_Piedra", hexc('#e9e1d0'), 0.75)
    M['terreno'] = make_mat("Terreno", hexc('#8c9a58'), 0.95)
    M['agua'] = make_mat("Agua", hexc('#1d6f8a'), 0.03, metal=0.1)
    M['asfalto'] = make_mat("Asfalto_Permeable", hexc('#4a4a4f'), 0.85)
    M['riel'] = make_mat("Riel", hexc('#8a8a8a'), 0.3, metal=1.0)
    M['tren'] = make_mat("Tren_Ligero", hexc('#f7f7f7'), 0.3)
    M['tren_vent'] = make_mat("Tren_Ventanas", hexc('#1c2b36'), 0.1, metal=0.3)
    M['acento'] = make_mat("Acento_Ambar", hexc('#ffb100'), 0.4, emit=1.5)
    M['corteza'] = make_mat("Corteza", hexc('#5b4330'), 0.9)
    M['hoja'] = [make_mat(f"Follaje_{i}", hexc(h), 0.9)
                 for i, h in enumerate(['#2f6b2f', '#4f8a35', '#6f9f3f', '#8f6fc7', '#3b7d4a'])]
    M['texto'] = make_mat("Etiqueta", hexc('#ffffff'), 0.5, emit=2.0)
    return M


# --------------------------------------------------------------------------
# AYUDANTES DE MALLA
# --------------------------------------------------------------------------
def new_coll(name):
    c = bpy.data.collections.new(name)
    bpy.context.scene.collection.children.link(c)
    return c


def finish(name, bm, mats, coll, smooth=False, recalc=True):
    if recalc:
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    if smooth:
        for f in bm.faces:
            f.smooth = True
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    for m in mats:
        me.materials.append(m)
    ob = bpy.data.objects.new(name, me)
    coll.objects.link(ob)
    return ob


def sweep(bm, prof_fn, seg, mat_fn, closed=True):
    """Barre un perfil (d, z) alrededor de la superelipse."""
    rings = []
    for j in range(seg):
        t = 2 * math.pi * j / seg
        ring = []
        for d, z in prof_fn(t):
            x, y = se(t, d)
            ring.append(bm.verts.new((x, y, z)))
        rings.append(ring)
    m = len(rings[0])
    nseg = m if closed else m - 1
    for j in range(seg):
        r0, r1 = rings[j], rings[(j + 1) % seg]
        for i in range(nseg):
            i2 = (i + 1) % m
            f = bm.faces.new((r0[i], r1[i], r1[i2], r0[i2]))
            f.material_index = mat_fn(i, j)


def add_obox(bm, c, ax, ay, az, hx, hy, hz, mat):
    """Caja orientada: centro c, ejes unitarios ax/ay/az y medias medidas."""
    c = Vector(c)
    vs = []
    for sx in (-1, 1):
        for sy in (-1, 1):
            for sz in (-1, 1):
                vs.append(bm.verts.new(c + ax * (sx * hx) + ay * (sy * hy) + az * (sz * hz)))
    for q in ((0, 1, 3, 2), (4, 6, 7, 5), (0, 4, 5, 1), (2, 3, 7, 6), (0, 2, 6, 4), (1, 5, 7, 3)):
        f = bm.faces.new([vs[i] for i in q])
        f.material_index = mat


def add_box(bm, c, size, mat, rotz=0.0):
    ca, sa = math.cos(rotz), math.sin(rotz)
    add_obox(bm, c, Vector((ca, sa, 0)), Vector((-sa, ca, 0)), Vector((0, 0, 1)),
             size[0] / 2, size[1] / 2, size[2] / 2, mat)


def add_cyl(bm, p1, p2, r1, r2, mat, sides=10, caps=True):
    p1, p2 = Vector(p1), Vector(p2)
    axis = p2 - p1
    if axis.length < 1e-6:
        return
    n = axis.normalized()
    tmp = Vector((0, 0, 1)) if abs(n.z) < 0.9 else Vector((1, 0, 0))
    u = n.cross(tmp).normalized()
    v = n.cross(u)
    r_a, r_b = [], []
    for k in range(sides):
        a = 2 * math.pi * k / sides
        off = u * math.cos(a) + v * math.sin(a)
        r_a.append(bm.verts.new(p1 + off * r1))
        r_b.append(bm.verts.new(p2 + off * r2))
    for k in range(sides):
        k2 = (k + 1) % sides
        bm.faces.new((r_a[k], r_a[k2], r_b[k2], r_b[k])).material_index = mat
    if caps:
        bm.faces.new(list(reversed(r_a))).material_index = mat
        bm.faces.new(r_b).material_index = mat


def add_blob(bm, c, rx, ry, rz, mat, segs=7, rings=4, jit=0.12):
    """Esfera low-poly irregular (copa de árbol)."""
    cx, cy, cz = c
    top = bm.verts.new((cx, cy, cz + rz))
    bot = bm.verts.new((cx, cy, cz - rz * 0.7))
    layers = []
    for r in range(1, rings):
        phi = math.pi * r / rings
        ring = []
        for s in range(segs):
            th = 2 * math.pi * s / segs + r * 0.4
            k = 1 + random.uniform(-jit, jit)
            ring.append(bm.verts.new((cx + rx * k * math.sin(phi) * math.cos(th),
                                      cy + ry * k * math.sin(phi) * math.sin(th),
                                      cz + rz * math.cos(phi))))
        layers.append(ring)
    for s in range(segs):
        s2 = (s + 1) % segs
        bm.faces.new((top, layers[0][s], layers[0][s2])).material_index = mat
        bm.faces.new((bot, layers[-1][s2], layers[-1][s])).material_index = mat
        for r in range(len(layers) - 1):
            bm.faces.new((layers[r][s], layers[r + 1][s], layers[r + 1][s2],
                          layers[r][s2])).material_index = mat


def add_ring(bm, c, r_in, r_out, z, mat, segs=64, a0=0.0, a1=2 * math.pi):
    full = abs(a1 - a0 - 2 * math.pi) < 1e-6
    n = segs if full else segs + 1
    vi, vo = [], []
    for k in range(n):
        a = a0 + (a1 - a0) * k / segs
        vi.append(bm.verts.new((c[0] + r_in * math.cos(a), c[1] + r_in * math.sin(a), z)))
        vo.append(bm.verts.new((c[0] + r_out * math.cos(a), c[1] + r_out * math.sin(a), z)))
    for k in range(segs):
        k2 = (k + 1) % n
        bm.faces.new((vi[k], vo[k], vo[k2], vi[k2])).material_index = mat


def add_disc(bm, c, rx, ry, z, mat, segs=64):
    center = bm.verts.new((c[0], c[1], z))
    ring = [bm.verts.new((c[0] + rx * math.cos(2 * math.pi * k / segs),
                          c[1] + ry * math.sin(2 * math.pi * k / segs), z)) for k in range(segs)]
    for k in range(segs):
        bm.faces.new((center, ring[k], ring[(k + 1) % segs])).material_index = mat


# --------------------------------------------------------------------------
# 1. CAMPO
# --------------------------------------------------------------------------
def build_field(M, coll):
    bm = bmesh.new()
    zf = Z_FIELD
    add_box(bm, (0, 0, zf - 0.25), (2 * (A + 10), 2 * (B + 10), 0.5), 0)       # base
    n = 18
    for i in range(n):                                                          # franjas
        x0 = -52.5 + 105 * i / n
        add_box(bm, (x0 + 105 / n / 2, 0, zf + 0.01), (105 / n, 68, 0.02), 1 + i % 2)
    zl, w = zf + 0.03, 0.12
    L = 3
    for y in (-34, 34):
        add_box(bm, (0, y, zl), (105, w, 0.02), L)
    for x in (-52.5, 0, 52.5):
        add_box(bm, (x, 0, zl), (w, 68, 0.02), L)
    add_ring(bm, (0, 0), 9.15 - w / 2, 9.15 + w / 2, zl, L, 64)
    add_disc(bm, (0, 0), 0.2, 0.2, zl + 0.001, L, 12)
    for sgn in (-1, 1):
        gx = 52.5 * sgn
        for depth, half in ((16.5, 20.16), (5.5, 9.16)):                         # áreas
            add_box(bm, (gx - sgn * depth, 0, zl), (w, 2 * half, 0.02), L)
            for y in (-half, half):
                add_box(bm, (gx - sgn * depth / 2, y, zl), (depth, w, 0.02), L)
        spot = gx - sgn * 11
        add_disc(bm, (spot, 0), 0.2, 0.2, zl + 0.001, L, 12)
        a_c = 0.0 if sgn < 0 else math.pi
        add_ring(bm, (spot, 0), 9.15 - w / 2, 9.15 + w / 2, zl, L, 24, a_c - 0.927, a_c + 0.927)
        for y in (-3.66, 3.66):                                                  # porterías
            add_box(bm, (gx + sgn * 0.06, y, zf + 1.22), (0.12, 0.12, 2.44), L)
        add_box(bm, (gx + sgn * 0.06, 0, zf + 2.44), (0.12, 7.44, 0.12), L)
        add_box(bm, (gx + sgn * 1.5, 0, zf + 2.44), (3.0, 7.44, 0.05), L)
    finish("Campo_105x68", bm, [M['cesped_b'], M['cesped_a'], M['cesped_b'], M['linea']],
           coll, recalc=False)

    # anillo de publicidad LED a ras de campo
    bm = bmesh.new()
    sweep(bm, lambda t: [(5.5, zf), (5.5, zf + 0.9)], SEG, lambda i, j: 0, closed=False)
    ob = finish("LED_Perimetral", bm, [M['led']], coll, recalc=False)
    ob.modifiers.new("Grosor", 'SOLIDIFY').thickness = 0.3


# --------------------------------------------------------------------------
# 2. GRADAS (100,000 personas)
# --------------------------------------------------------------------------
def tier_profile(d0, z0, rows, rise, zf_bot, zb_bot, acc_front, acc_back):
    P, K = [], []

    def add(d, z, k):
        P.append((d, z))
        K.append(k)

    add(d0, zf_bot, 'front')
    add(d0, z0 + 1.1, 'ptop')
    add(d0 + 0.3, z0 + 1.1, 'pin')
    d, z = d0 + 0.3, z0
    if acc_front:
        add(d, z, 'acc')
        d += ACC_W
    for r in range(rows):
        add(d, z, ('tread', r))
        d += ROW_D
        if r < rows - 1:
            add(d, z, ('riser', r + 1))
            z += rise
    if acc_back:
        add(d, z, 'riser')
        z += rise
        add(d, z, 'acc')
        d += ACC_W
    add(d, z, 'back')
    add(d, z + 1.2, 'btop')
    add(d + 0.3, z + 1.2, 'bout')
    add(d + 0.3, zb_bot, 'soffit')
    return P, K


def seat_index(tier, r, rows, j):
    t = 2 * math.pi * j / SEG
    f = r / max(1, rows - 1)
    v = (0.30 * tier + 0.35 * f + 0.10 * math.sin(3 * t + 2 * f + tier)
         + 0.06 * math.sin(11 * t - 5 * f) + random.uniform(-0.08, 0.08))
    return max(0, min(5, int(v / 1.2 * 6)))


def build_stands(M, coll):
    mats = [M['concreto']] + M['butacas'] + [M['pasillo'], M['led'], M['accesible']]
    I_AISLE, I_LED, I_ACC = 7, 8, 9
    seats = 0.0
    wheel = 0.0
    for ti, (name, d0, z0, rows, rise, zfb, zbb, accf, accb, ledf) in enumerate(TIERS):
        P, K = tier_profile(d0, z0, rows, rise, zfb, zbb, accf, accb)
        pattern = {(r, j): seat_index(ti, r, rows, j) for r in range(rows) for j in range(SEG)}

        def mat_fn(i, j, K=K, pattern=pattern, ledf=ledf):
            k = K[i]
            aisle = (j % AISLE_EVERY == 0)
            if isinstance(k, tuple):        # huella o respaldo de butaca
                return I_AISLE if aisle else 1 + pattern[(k[1], j)]
            if k == 'riser':
                return I_AISLE if aisle else 0
            if k == 'acc':
                return I_ACC
            if k == 'front' and ledf:
                return I_LED
            return 0

        bm = bmesh.new()
        sweep(bm, lambda t, P=P: P, SEG, mat_fn)
        finish(name, bm, mats, coll)

        # aforo: butacas por fila (descontando pasillos y vomitorios)
        usable = (1 - 1 / AISLE_EVERY) * 0.96
        d = d0 + 0.3 + (ACC_W if accf else 0)
        for r in range(rows):
            seats += perim(d + (r + 0.5) * ROW_D) / SEAT_W * usable
        if accf:
            wheel += perim(d0 + 0.3 + ACC_W / 2) / 1.6 * usable
        if accb:
            wheel += perim(d + rows * ROW_D + ACC_W / 2) / 1.6 * usable
    return int(seats), int(wheel)


def build_concourse(M, coll):
    bm = bmesh.new()
    sweep(bm, lambda t: [(38.0, Z_CONC - 0.05), (FACADE_D, Z_CONC - 0.05)], SEG,
          lambda i, j: 0, closed=False)
    finish("Vestibulo_Principal", bm, [M['plaza']], coll, recalc=False)

    bm = bmesh.new()   # palcos / suites con vidrio entre grada media y alta
    sweep(bm, lambda t: [(63.3, 28.0), (63.3, 33.6)], SEG, lambda i, j: 0, closed=False)
    finish("Palcos_Vidrio", bm, [M['vidrio']], coll, recalc=False)

    bm = bmesh.new()   # columnas
    for d, top in ((42.0, 11.3), (55.0, 12.8), (66.0, 33.5), (77.0, 27.5), (87.0, 21.5)):
        for k in range(48):
            t = 2 * math.pi * (k + 0.5) / 48
            x, y = se(t, d)
            add_cyl(bm, (x, y, Z_CONC), (x, y, top), 0.6, 0.6, 0, sides=8)
    finish("Columnas", bm, [M['acero']], coll, smooth=True)


# --------------------------------------------------------------------------
# 3. CUBIERTA DE HOJAS + HALO
# --------------------------------------------------------------------------
def build_roof(M, coll):
    NPET, SUB, RAD = 72, 4, 16
    PV_FROM = 70.0
    bm = bmesh.new()
    area_pv = 0.0
    area_etfe = 0.0
    for p in range(NPET):
        t0 = 2 * math.pi * p / NPET
        dt = 2 * math.pi / NPET
        ta, tb = t0, t0 + dt * 1.05                         # hojas traslapadas (tejas)
        grid = []
        for a in range(SUB + 1):
            u = a / SUB
            t = ta + (tb - ta) * u
            col = []
            for k in range(RAD + 1):
                d = ROOF_IN + (ROOF_OUT - ROOF_IN) * k / RAD
                if k == RAD:
                    d += 4.0 * math.sin(math.pi * u)          # borde festoneado
                x, y = se(t, d)
                # escamas: un borde de cada hoja sube 1.8 m -> ventilación natural
                z = z_roof(d, t) + 1.8 * u + 0.6 * math.sin(math.pi * u)
                col.append(bm.verts.new((x, y, z)))
            grid.append(col)
        for a in range(SUB):
            for k in range(RAD):
                f = bm.faces.new((grid[a][k], grid[a + 1][k], grid[a + 1][k + 1], grid[a][k + 1]))
                dm = ROOF_IN + (ROOF_OUT - ROOF_IN) * (k + 0.5) / RAD
                f.material_index = 1 if dm > PV_FROM else 0
                if dm > PV_FROM:
                    area_pv += f.calc_area()
                else:
                    area_etfe += f.calc_area()
    ob = finish("Cubierta_Hojas_ETFE_Solar", bm, [M['etfe'], M['solar']], coll, smooth=True)
    sol = ob.modifiers.new("Grosor", 'SOLIDIFY')
    sol.thickness = 0.5

    bm = bmesh.new()   # anillo de compresión
    sweep(bm, lambda t: [(11.0, z_roof(12, t) - 1.2), (13.6, z_roof(12, t) - 1.2),
                         (13.6, z_roof(12, t) + 0.8), (11.0, z_roof(12, t) + 0.8)],
          SEG, lambda i, j: 0)
    finish("Anillo_Compresion", bm, [M['acero']], coll)

    bm = bmesh.new()   # pantalla 360°
    sweep(bm, lambda t: [(11.3, z_roof(12, t) - 13.0), (11.3, z_roof(12, t) - 4.0)], SEG,
          lambda i, j: 0, closed=False)
    ob = finish("Pantalla_Halo_360", bm, [M['halo']], coll, recalc=False)
    ob.modifiers.new("Grosor", 'SOLIDIFY').thickness = 0.6
    return area_etfe / 1.05, area_pv / 1.05     # descuenta el traslape de las hojas


# --------------------------------------------------------------------------
# 4. ÁRBOLES ESTRUCTURALES
# --------------------------------------------------------------------------
def build_structural_trees(M, coll):
    bm = bmesh.new()
    dt = math.pi / N_TREES * 0.9
    for k in range(N_TREES):
        t = 2 * math.pi * k / N_TREES
        bx, by = se(t, TREE_D)
        z0 = z_berm(TREE_D)
        top = Vector((*se(t, TREE_D - 1), 36.0))
        add_cyl(bm, (bx, by, z0 - 1), (bx, by, z0 + 3), 3.2, 1.9, 0, sides=12)   # raíz
        add_cyl(bm, (bx, by, z0 + 3), top, 1.9, 1.3, 0, sides=12)                 # tronco
        mids = [(t, 93.0, 54.0), (t - dt, 97.0, 50.0), (t + dt, 97.0, 50.0), (t, 104.0, 48.0)]
        for (tm, dm, zm) in mids:
            mid = Vector((*se(tm, dm), zm))
            add_cyl(bm, top, mid, 1.15, 0.75, 0, sides=10)
            for sd, st in ((-6.0, -0.35), (5.0, 0.35)):
                tr = tm + st * dt
                dr = min(104.0, max(80.0, dm + sd))
                tip = Vector((*se(tr, dr), z_roof(dr, tr) - 0.2))
                add_cyl(bm, mid, tip, 0.7, 0.35, 0, sides=8)
                add_cyl(bm, tip - Vector((0, 0, 0.25)), tip + Vector((0, 0, 0.6)), 1.6, 1.6, 1, sides=10)
    finish("Arboles_Estructurales", bm, [M['madera'], M['acero']], coll, smooth=True)


# --------------------------------------------------------------------------
# 5. FACHADA: vidrio + aletas paramétricas + jardines verticales + accesos
# --------------------------------------------------------------------------
def near_entry(t, d, half):
    return any(ang_dist(t, e) * r_eff(d) < half for e in ENTRIES)


def build_facade(M, coll):
    bm = bmesh.new()
    sweep(bm, lambda t: [(FACADE_D, Z_CONC), (FACADE_D, z_roof(FACADE_D, t) - 0.3)], SEG,
          lambda i, j: 0, closed=False)
    finish("Fachada_Vidrio", bm, [M['vidrio']], coll, recalc=False)

    bm = bmesh.new()
    NF = 320
    tree_ts = [2 * math.pi * k / N_TREES for k in range(N_TREES)]
    for k in range(NF):
        t = 2 * math.pi * k / NF
        if near_entry(t, FIN_D, 14.0):
            continue
        if any(ang_dist(t, tt) * r_eff(FIN_D) < 3.0 for tt in tree_ts):
            continue
        n, tan = outward(t, FIN_D)
        phi = 0.75 * math.sin(5 * t)                      # giro paramétrico
        ax = n * math.cos(phi) + tan * math.sin(phi)
        ay = tan * math.cos(phi) - n * math.sin(phi)
        depth = 1.6 + 0.9 * (0.5 + 0.5 * math.sin(8 * t))
        ztop = z_roof(FIN_D, t) - 1.0
        x, y = se(t, FIN_D)
        mat = 1 if k % 3 == 0 else 0
        add_obox(bm, (x, y, (Z_CONC + ztop) / 2), ax, ay, Vector((0, 0, 1)),
                 depth / 2, 0.18, (ztop - Z_CONC) / 2, mat)
    finish("Aletas_Parametricas", bm, [M['madera'], M['jardin_v']], coll)

    # marquesinas de acceso + elevadores panorámicos
    bm_c = bmesh.new()
    bm_e = bmesh.new()
    for e in ENTRIES:
        n, tan = outward(e, 98.0)
        x, y = se(e, 98.0)
        add_obox(bm_c, (x, y, 14.0), n, tan, Vector((0, 0, 1)), 8.0, 14.0, 0.35, 0)
        for s in (-1, 1):
            c = Vector((x, y, 0)) + n * 5.5 + tan * (s * 10.0)
            add_cyl(bm_c, (c.x, c.y, z_berm(103.5)), (c.x, c.y, 14.0), 0.45, 0.45, 0, sides=8)
            ce = Vector((x, y, 0)) + n * 2.0 + tan * (s * 8.5)
            add_cyl(bm_e, (ce.x, ce.y, Z_CONC), (ce.x, ce.y, 57.0), 2.6, 2.6, 0, sides=16)
            hz = random.uniform(12, 50)
            add_box(bm_e, (ce.x, ce.y, hz), (2.2, 2.2, 2.6), 1)
    finish("Marquesinas_Acceso", bm_c, [M['acero']], coll)
    finish("Elevadores_Panoramicos", bm_e, [M['vidrio'], M['acento']], coll)


# --------------------------------------------------------------------------
# 6. COLINA-PARQUE, AGUA Y PLAZA
# --------------------------------------------------------------------------
def berm_ds():
    ds = [FACADE_D + 0.0]
    while ds[-1] < BERM_END:
        ds.append(min(BERM_END, ds[-1] + 5.0))
    return ds


def on_path(t, d):
    if near_entry(t, d, 7.0):
        return True
    if 160.0 < d < 166.0:                       # paseo anular
        return True
    if ang_dist(t, -math.pi / 2) * r_eff(d) < 8.0:
        return True                             # canal / cascada
    return False


def build_landscape(M, coll_land, coll_water):
    SB = 256
    ds = berm_ds()
    mats = [M['pasto'], M['seto'], M['lavanda'], M['amarillo'], M['piedra']]
    rnd = {}

    def mat_fn(i, j):
        t = 2 * math.pi * (j + 0.5) / SB
        d = (ds[i] + ds[i + 1]) / 2
        if on_path(t, d):
            return 4
        if i % 4 == 1:
            return 1
        key = (i // 2, j // 6)
        if key not in rnd:
            r = random.random()
            rnd[key] = 2 if r < 0.10 else 3 if r < 0.18 else 0
        return rnd[key]

    bm = bmesh.new()
    sweep(bm, lambda t: [(d, z_berm(d)) for d in ds], SB, mat_fn, closed=False)
    finish("Colina_Parque", bm, mats, coll_land, recalc=False)

    bm = bmesh.new()
    sweep(bm, lambda t: [(BERM_END, 0.0), (BERM_END + PLAZA_W, 0.0)], SB, lambda i, j: 0,
          closed=False)
    finish("Plaza_Perimetral", bm, [M['plaza']], coll_land, recalc=False)

    bm = bmesh.new()   # terreno con hueco: el estadio está hundido
    sweep(bm, lambda t: [(BERM_END + PLAZA_W - 0.5, -0.03), (1600.0, -0.03)], SB,
          lambda i, j: 0, closed=False)
    finish("Terreno", bm, [M['terreno']], coll_land, recalc=False)

    # canal + cascada de agua pluvial que baja de la fachada al lago
    bm = bmesh.new()
    t = -math.pi / 2
    rows = []
    d = FACADE_D + 4.0
    while d <= BERM_END + PLAZA_W + 2:
        hw = 5.0 / r_eff(d)
        z = z_berm(d) + 0.12
        rows.append([bm.verts.new((*se(t - hw, d), z)), bm.verts.new((*se(t + hw, d), z))])
        d += 4.0
    for a in range(len(rows) - 1):
        bm.faces.new((rows[a][0], rows[a][1], rows[a + 1][1], rows[a + 1][0]))
    finish("Canal_Cascada", bm, [M['agua']], coll_water, recalc=False)

    bm = bmesh.new()
    lake_c, lake_r = (0.0, -(B + BERM_END + PLAZA_W + 95.0)), (175.0, 72.0)
    add_disc(bm, lake_c, lake_r[0], lake_r[1], 0.04, 0, 96)
    finish("Lago_Enfriamiento", bm, [M['agua']], coll_water, recalc=False)
    bm = bmesh.new()
    segs = 96
    for k in range(segs):
        a0, a1 = 2 * math.pi * k / segs, 2 * math.pi * (k + 1) / segs
        vs = []
        for a, s in ((a0, 1.0), (a1, 1.0), (a1, 1.12), (a0, 1.12)):
            vs.append(bm.verts.new((lake_c[0] + lake_r[0] * s * math.cos(a),
                                    lake_c[1] + lake_r[1] * s * math.sin(a), 0.02)))
        bm.faces.new(vs)
    finish("Lago_Malecon", bm, [M['piedra']], coll_water, recalc=False)
    return lake_c, lake_r


# --------------------------------------------------------------------------
# 7. MOVILIDAD: tren ligero, calle de buses eléctricos, bicipuertos
# --------------------------------------------------------------------------
STATION_Y = B + BERM_END + PLAZA_W + 70.0
ROAD_X = A + BERM_END + PLAZA_W + 45.0


def build_mobility(M, coll):
    bm = bmesh.new()
    mats = [M['plaza'], M['riel'], M['solar'], M['acero'], M['tren'], M['tren_vent'],
            M['asfalto'], M['accesible'], M['seto']]
    sy = STATION_Y
    add_box(bm, (0, sy, 0.5), (180, 10, 1.0), 0)                  # andén a nivel
    for yc in (sy - 8.0, sy + 8.0):
        for off in (-0.72, 0.72):
            add_box(bm, (0, yc + off, 0.08), (3000, 0.15, 0.16), 1)
    add_box(bm, (0, sy, 8.0), (196, 26, 0.4), 2)                  # cubierta solar
    for x in range(-90, 91, 15):
        add_cyl(bm, (x, sy, 1.0), (x, sy, 7.8), 0.35, 0.35, 3, sides=8)
    for x0, yc in ((-25.0, sy - 8.0), (55.0, sy + 8.0)):         # trenes
        add_box(bm, (x0, yc, 2.0), (46, 2.65, 3.2), 4)
        add_box(bm, (x0, yc, 2.4), (46.1, 2.7, 1.1), 5)
    # pasarela con pérgola verde de la estación a la plaza
    y_pl = B + BERM_END + PLAZA_W - 2
    add_box(bm, (0, (sy - 5 + y_pl) / 2, 0.03), (12, sy - 5 - y_pl, 0.06), 0)
    add_box(bm, (0, (sy - 5 + y_pl) / 2, 5.0), (14, sy - 5 - y_pl, 0.5), 8)
    for y in range(int(y_pl) + 4, int(sy - 6), 8):
        for x in (-6.5, 6.5):
            add_cyl(bm, (x, y, 0), (x, y, 4.8), 0.25, 0.25, 3, sides=8)
    # calle de buses eléctricos / ascenso-descenso accesible (lado este)
    add_box(bm, (ROAD_X, 0, 0.02), (16, 3000, 0.04), 6)
    add_box(bm, (ROAD_X - 18, 0, 0.03), (20, 120, 0.04), 6)
    for k in range(10):
        add_box(bm, (ROAD_X - 18, -54 + k * 12, 0.06), (4.5, 1.2, 0.02), 7)
    # bicipuertos
    for x in (-120.0, 120.0):
        add_box(bm, (x, sy - 22, 3.2), (40, 12, 0.3), 2)
        for k in range(8):
            add_box(bm, (x - 17.5 + k * 5, sy - 22, 0.6), (0.1, 10, 1.2), 3)
    finish("Movilidad", bm, mats, coll)


# --------------------------------------------------------------------------
# 8. VEGETACIÓN
# --------------------------------------------------------------------------
def build_vegetation(M, coll, lake_c, lake_r):
    bm = bmesh.new()
    mats = [M['corteza']] + M['hoja']
    count = 0

    def tree(x, y, z, kind):
        h = random.uniform(5, 9)
        leaf = random.choice((1, 1, 2, 3, 5)) if random.random() > 0.08 else 4   # 8 % jacarandas
        if kind == 'palma':
            add_cyl(bm, (x, y, z), (x, y, z + 11), 0.35, 0.25, 0, sides=6, caps=False)
            add_blob(bm, (x, y, z + 11), 3.6, 3.6, 1.1, 5, segs=8, jit=0.3)
        elif kind == 'cipres':
            add_cyl(bm, (x, y, z), (x, y, z + 2), 0.3, 0.25, 0, sides=6, caps=False)
            add_blob(bm, (x, y, z + 6), 1.5, 1.5, 5.0, 1, segs=6)
        else:
            add_cyl(bm, (x, y, z), (x, y, z + h * 0.6), 0.45, 0.3, 0, sides=6, caps=False)
            r = random.uniform(2.8, 4.8)
            add_blob(bm, (x, y, z + h * 0.6 + r * 0.6), r, r, r * 0.8, leaf)

    # árboles en la colina
    for _ in range(1400):
        t = random.uniform(0, 2 * math.pi)
        d = random.uniform(108.0, BERM_END - 4)
        if on_path(t, d + 2) or on_path(t, d - 2):
            continue
        x, y = se(t, d)
        tree(x, y, z_berm(d) - 0.2, random.choice(('copa', 'copa', 'copa', 'cipres')))
        count += 1

    # bosque urbano alrededor
    for _ in range(2600):
        x, y = random.uniform(-900, 900), random.uniform(-900, 900)
        if d_of(x, y) < BERM_END + PLAZA_W + 6:
            continue
        ex = ((x - lake_c[0]) / (lake_r[0] * 1.15)) ** 2 + ((y - lake_c[1]) / (lake_r[1] * 1.15)) ** 2
        if ex < 1.0:
            continue
        if abs(y - STATION_Y) < 34 or abs(x - ROAD_X) < 32 or (abs(x) < 12 and y > 0):
            continue
        kind = 'palma' if ex < 1.9 else random.choice(('copa', 'copa', 'cipres'))
        tree(x, y, 0.0, kind)
        count += 1
    finish("Vegetacion_Nativa", bm, mats, coll, smooth=False)
    return count


# --------------------------------------------------------------------------
# 9. ETIQUETAS, CÁMARAS, LUZ
# --------------------------------------------------------------------------
def look_at(ob, target):
    d = Vector(target) - ob.location
    ob.rotation_euler = d.to_track_quat('-Z', 'Y').to_euler()


def add_camera(name, loc, target, lens, coll):
    cam = bpy.data.cameras.new(name)
    cam.lens = lens
    cam.clip_end = 8000
    ob = bpy.data.objects.new(name, cam)
    ob.location = loc
    look_at(ob, target)
    coll.objects.link(ob)
    return ob


def add_label(text, loc, size, M, coll, cam):
    cu = bpy.data.curves.new(text[:20], 'FONT')
    cu.body = text
    cu.size = size
    cu.align_x = 'CENTER'
    ob = bpy.data.objects.new("Etiqueta_" + text[:24], cu)
    ob.location = loc
    ob.data.materials.append(M['texto'])
    con = ob.constraints.new('TRACK_TO')
    con.target = cam
    con.track_axis = 'TRACK_Z'
    con.up_axis = 'UP_Y'
    ob.hide_render = True
    coll.objects.link(ob)


def setup_world_and_render(cam):
    sc = bpy.context.scene
    sc.camera = cam
    for eng in ('BLENDER_EEVEE_NEXT', 'BLENDER_EEVEE'):
        try:
            sc.render.engine = eng
            break
        except Exception:
            pass
    sc.render.resolution_x, sc.render.resolution_y = 1920, 1080
    try:
        sc.view_settings.look = 'AgX - Medium High Contrast'
    except Exception:
        pass

    world = sc.world or bpy.data.worlds.new("Mundo")
    sc.world = world
    try:
        world.use_nodes = True
    except Exception:
        pass
    nt = world.node_tree
    bg = next((n for n in nt.nodes if n.type == 'BACKGROUND'), None)
    if bg is None:
        bg = nt.nodes.new('ShaderNodeBackground')
        out = next((n for n in nt.nodes if n.type == 'OUTPUT_WORLD'), None) or \
            nt.nodes.new('ShaderNodeOutputWorld')
        nt.links.new(bg.outputs[0], out.inputs[0])
    try:
        sky = nt.nodes.new('ShaderNodeTexSky')
        try:
            sky.sun_elevation = math.radians(32)
            sky.sun_rotation = math.radians(215)
        except Exception:
            pass
        nt.links.new(sky.outputs[0], bg.inputs[0])
        bg.inputs[1].default_value = 0.22
    except Exception:
        bg.inputs[0].default_value = (0.55, 0.72, 0.95, 1)
        bg.inputs[1].default_value = 1.0

    sun = bpy.data.lights.new("Sol", 'SUN')
    sun.energy = 3.2
    sun.angle = math.radians(1.5)
    sun.color = (1.0, 0.95, 0.88)
    ob = bpy.data.objects.new("Sol", sun)
    ob.rotation_euler = (math.radians(58), 0, math.radians(215 - 180 + 90))
    sc.collection.objects.link(ob)

    # vista 3D: que no se recorte la escena grande y se vean los colores
    for screen in bpy.data.screens:
        for area in screen.areas:
            if area.type == 'VIEW_3D':
                for sp in area.spaces:
                    if sp.type == 'VIEW_3D':
                        sp.clip_end = 20000
                        try:
                            sp.shading.color_type = 'MATERIAL'
                        except Exception:
                            pass


def clear_scene():
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob, do_unlink=True)
    for c in list(bpy.data.collections):
        bpy.data.collections.remove(c)
    for coll in (bpy.data.meshes, bpy.data.materials, bpy.data.curves,
                 bpy.data.cameras, bpy.data.lights):
        for b in list(coll):
            if b.users == 0:
                coll.remove(b)


# --------------------------------------------------------------------------
# MAIN
# --------------------------------------------------------------------------
def main():
    clear_scene()
    M = build_materials()
    C = {k: new_coll(v) for k, v in (
        ('campo', "01_Campo"), ('gradas', "02_Gradas_y_Vestibulos"),
        ('cubierta', "03_Cubierta_Hojas_y_Halo"), ('arboles', "04_Arboles_Estructurales"),
        ('fachada', "05_Fachada_Accesos_Elevadores"), ('paisaje', "06_Colina_Parque_Plaza"),
        ('agua', "07_Agua_Cascada_Lago"), ('movilidad', "08_Movilidad"),
        ('vegetacion', "09_Vegetacion"), ('camaras', "10_Camaras"),
        ('etiquetas', "11_Etiquetas_Info"))}

    build_field(M, C['campo'])
    seats, wheel = build_stands(M, C['gradas'])
    build_concourse(M, C['gradas'])
    a_etfe, a_pv = build_roof(M, C['cubierta'])
    build_structural_trees(M, C['arboles'])
    build_facade(M, C['fachada'])
    lake_c, lake_r = build_landscape(M, C['paisaje'], C['agua'])
    build_mobility(M, C['movilidad'])
    n_trees = build_vegetation(M, C['vegetacion'], lake_c, lake_r)

    cams = C['camaras']
    cam_air = add_camera("CAM_Aerea", (-520, -640, 330), (0, 0, 5), 42, cams)
    tp = ENTRIES[6]
    add_camera("CAM_Llegada_Peaton", (*se(tp, 175), z_berm(175) + 1.7), (*se(tp, 60), 32), 20, cams)
    add_camera("CAM_Grada_Baja", (*se(-math.pi / 2 + 0.05, 22), 2.6), (0, 10, -4), 20, cams)
    add_camera("CAM_Interior_Grada", (-30, -(B + 86), 58), (20, 10, -8), 18, cams)
    add_camera("CAM_Lago_Atardecer", (-260, lake_c[1] - 120, 6), (0, 0, 35), 28, cams)
    add_camera("CAM_Estacion", (-150, STATION_Y + 40, 12), (0, 0, 30), 24, cams)

    total = seats + 2 * wheel
    mw = a_pv * 0.21 / 1000
    lab = C['etiquetas']
    L = [
        (f"ESTADIO OASIS · {total:,} personas", (0, 0, 135), 14),
        ("Cubierta de hojas: ETFE (luz natural) + "
         f"{a_pv:,.0f} m² solares ≈ {mw:.1f} MWp", (0, 60, 100), 7),
        ("Halo LED 360° (todos ven la repetición)", (0, 0, 52), 5),
        ("Árboles estructurales de madera laminada", (*se(math.pi * 0.75, TREE_D + 30), 70), 6),
        ("Colina-parque abierta 365 días · pendiente 4.7 % sin escaleras",
         (*se(math.pi * 1.25, 170), 30), 7),
        ("Cascada + canal de agua pluvial reciclada", (*se(-math.pi / 2, 170), 25), 6),
        ("Lago de enfriamiento y retención", (lake_c[0], lake_c[1], 20), 7),
        ("Estación de tren ligero a nivel (sin escalones)", (0, STATION_Y, 25), 7),
        ("Bus eléctrico + ascenso/descenso accesible", (ROAD_X, 0, 18), 6),
        (f"16 elevadores panorámicos · {wheel:,} lugares para silla de ruedas",
         (*se(ENTRIES[2], 112), 62), 6),
        ("Túnel de emergencias y servicio a nivel de campo", (A + 30, 0, 25), 5),
    ]
    for text, loc, size in L:
        add_label(text, loc, size, M, lab, cam_air)

    setup_world_and_render(cam_air)
    sc = bpy.context.scene
    sc["aforo_butacas"] = seats
    sc["aforo_sillas_ruedas"] = wheel
    sc["aforo_total"] = total
    print("=" * 60)
    print("ESTADIO OASIS generado")
    print(f"  Butacas:                 {seats:,}")
    print(f"  Lugares silla de ruedas: {wheel:,} (+ {wheel:,} acompañantes)")
    print(f"  Aforo total:             {total:,}")
    print(f"  Cubierta ETFE:           {a_etfe:,.0f} m²")
    print(f"  Cubierta solar:          {a_pv:,.0f} m²  (~{mw:.1f} MWp)")
    print(f"  Árboles plantados:       {n_trees:,}")
    print("=" * 60)


main()
