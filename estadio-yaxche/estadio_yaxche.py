# -*- coding: utf-8 -*-
"""
ESTADIO YAXCHÉ + PLAZA SAKBÉ  —  Centro de la Ciudad Ideal  (versión 3)
Yaxché = la ceiba sagrada maya (raíces, tronco y copa: los tres niveles del mundo).
Sakbé  = "camino blanco" maya: el anillo es un camino-parque elevado alrededor del estadio.
===========================================================================
Generador procedural para Blender (probado en Blender 4.2 LTS y 5.1).

Cómo usarlo:
  1. Abre Blender  ->  Archivo > Nuevo > General.
  2. Pestaña "Scripting"  ->  "Abrir"  ->  este archivo  ->  "Ejecutar script" (▶).
  3. Tarda unos segundos. ¡OJO! Borra todo lo que haya en el archivo antes de construir.

Qué genera:
  * Estadio para ~100,000 personas: 3 gradas diseñadas por visibilidad (C-value),
    butacas individuales (instancias ligeras), vomitorios, 4 vestíbulos, 8 torres de
    circulación con escalera de doble hélice, escaleras eléctricas, núcleos de
    escape, zona de jugadores, techo retráctil animado (frame 1 abierto,
    frame 120 cerrado) y modos: fútbol, fútbol americano, rugby, concierto y
    arena central.
  * Plaza Sakbé (anillo estilo "The Line"): plaza comercial y de servicios con espejo exterior,
    cañón verde interior, parque en la azotea, 8 brechas + 8 portales +
    16 ventanas urbanas hacia la ciudad, núcleos de circulación vertical.
  * Estacionamiento subterráneo, rutas de evacuación, puntos de reunión,
    explanada perimetral. (La ciudad de alrededor no se modela.)
  * Dos escenas: "Dia" y "Noche" (selector de escena arriba a la derecha).

Todas las medidas en metros. Al terminar, la consola imprime aforo, revisión de
normas (visibilidad, evacuación, accesibilidad) y consumos estimados.
"""

import bpy
import bmesh
import math
import random
from mathutils import Vector

random.seed(2026)

# ==========================================================================
# PARÁMETROS
# ==========================================================================
A, B, NEXP = 62.5, 42.0, 2.6     # semiejes zona de campo (125 x 84 m) y forma
SEG = 432                        # divisiones alrededor (múltiplo de 6, 8, 9, 18)
SEAT_W, ROW_D, ACC_W = 0.52, 0.85, 2.6
EYE, C_TARGET, FOCUS_D = 1.20, 0.090, -8.0     # visibilidad: ojo, C-value meta, línea de banda
MAX_RISE = ROW_D * math.tan(math.radians(34))  # pendiente máxima de grada: 34°

# niveles (0 = plaza = calle)
Z_FIELD = -12.0                  # campo y nivel de servicio
Z_P1, Z_P2 = -6.0, -12.0         # estacionamiento
Z_L0, Z_L05, Z_L2 = 0.0, 9.5, 27.0   # vestíbulo principal, mezzanine, vestíbulo alto (L1 se calcula)

FACADE_D, FIN_D, TREE_D = 98.5, 102.0, 107.0
TOWER_D, TOWER_R = 108.5, 8.0
ROOF_IN, ROOF_OUT, ROOF_Z = 12.0, 114.0, 63.0
N_TREES = 24
ENTRIES = [math.pi / 8 + k * math.pi / 4 for k in range(8)]
CORES = [math.radians(a + 45 * k) for k in range(8) for a in (10, 40)]   # entre vomitorios y accesos
VOMS = [math.radians(2.5 + 15 * k) for k in range(24)]                   # centros de los vomitorios

# Plaza Sakbé (anillo estilo "The Line")
RING_IN, CANYON_IN, CANYON_OUT, RING_OUT = 160.0, 176.0, 190.0, 206.0
RING_H, FLOOR_H = 45.0, 4.5
GAP_W, PORTAL_W, PORTAL_H = 30.0, 24.0, 13.5
WIN_W, WIN_Z = 20.0, (22.5, 31.5)
EXPLANADA_OUT = 236.0                    # explanada peatonal alrededor del anillo
MIRADOR_T = -math.pi / 4 + 0.18          # mirador del parque en la azotea

TIERS = [
    dict(name="Grada_1_Baja", z0=Z_FIELD + 1.4, rows=34, aisle=9, led=False,
         under="solid", acc="back_L0"),
    dict(name="Grada_2_Media", z0=6.5, rows=28, aisle=8, led=True,
         under="raked", front_drop=3.0, acc="back"),
    dict(name="Grada_3_Alta", z0=27.5, rows=32, aisle=6, led=True,
         under="raked", front_drop=3.5, acc="mid", mid_row=9,
         vom=dict(every=18, segs=(1, 2, 3, 4), flat=(2, 3, 4), rows=range(10, 16))),
]

# supuestos de consumo (ajústalos)
EVENTS_PER_YEAR = 60
PV_KWP_M2, PV_YIELD = 0.18, 1460          # kWp/m² y kWh/kWp·año en cubierta (con pérdidas reales, ver Modelo_Financiero)
BIPV_KWP_M2, BIPV_YIELD = 0.12, 555       # fachada fotovoltaica vertical (~38 % de la cubierta)
RAIN_M = 0.70                             # lluvia anual (m)

STATS = {}
AREAS = {}


# ==========================================================================
# GEOMETRÍA BASE
# ==========================================================================
def se(t, d):
    a, b = A + d, B + d
    c, s = math.cos(t), math.sin(t)
    return (a * math.copysign(abs(c) ** (2 / NEXP), c),
            b * math.copysign(abs(s) ** (2 / NEXP), s))


def P(t, d, z):
    x, y = se(t, d)
    return Vector((x, y, z))


def perim(d, n=1440):
    pts = [se(2 * math.pi * i / n, d) for i in range(n)]
    return sum(math.dist(pts[i], pts[i - 1]) for i in range(n))


def speed(t, d):
    e = 1e-4
    return math.dist(se(t - e, d), se(t + e, d)) / (2 * e)


def dt_w(width, t, d):
    """Incremento de parámetro t equivalente a 'width' metros de arco."""
    return width / max(1e-6, speed(t, d))


def d_of(x, y):
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


def AREAS_ring(d0, d1):
    """Área entre dos curvas (superelipses) en m²."""
    k = math.gamma(1 + 1 / NEXP) ** 2 / math.gamma(1 + 2 / NEXP)
    return 4 * k * ((A + d1) * (B + d1) - (A + d0) * (B + d0))


def r_eff(d):
    return (A + B) / 2 + d


def ang_dist(a, b):
    return abs((a - b + math.pi) % (2 * math.pi) - math.pi)


def z_roof(d, t):
    u = (d - ROOF_IN) / (ROOF_OUT - ROOF_IN)
    return ROOF_Z - 4.0 * u - 3.0 * math.cos(2 * t)


def outward(t, d):
    e = 1e-4
    p0, p1 = se(t - e, d), se(t + e, d)
    tan = Vector((p1[0] - p0[0], p1[1] - p0[1], 0)).normalized()
    return Vector((tan.y, -tan.x, 0)), tan


def tri_area(a, b, c):
    return (Vector(b) - Vector(a)).cross(Vector(c) - Vector(a)).length / 2


# ==========================================================================
# MATERIALES
# ==========================================================================
def _set(node, names, val):
    for n in names:
        sock = node.inputs.get(n)
        if sock is not None:
            sock.default_value = val
            return


def hexc(h):
    h = h.lstrip('#')
    srgb = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    return tuple(c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in srgb)


def make_mat(name, hx, rough=0.5, metal=0.0, emit=0.0, trans=0.0, alpha=1.0, ior=1.45):
    color = hexc(hx)
    m = bpy.data.materials.new(name)
    try:
        m.use_nodes = True
    except Exception:
        pass
    m.diffuse_color = (*color, alpha)
    m.roughness = rough
    m.metallic = metal
    nt = m.node_tree
    bsdf = next((n for n in nt.nodes if n.type == 'BSDF_PRINCIPLED'), None)
    if bsdf is None:
        bsdf = nt.nodes.new('ShaderNodeBsdfPrincipled')
        out = next((n for n in nt.nodes if n.type == 'OUTPUT_MATERIAL'), None) or \
            nt.nodes.new('ShaderNodeOutputMaterial')
        nt.links.new(bsdf.outputs[0], out.inputs[0])
    _set(bsdf, ["Base Color"], (*color, 1.0))
    _set(bsdf, ["Roughness"], rough)
    _set(bsdf, ["Metallic"], metal)
    if trans:
        _set(bsdf, ["Transmission Weight", "Transmission"], trans)
        _set(bsdf, ["IOR"], ior)
    if alpha < 1.0:
        _set(bsdf, ["Alpha"], alpha)
    if emit:
        _set(bsdf, ["Emission Color", "Emission"], (*color, 1.0))
        _set(bsdf, ["Emission Strength"], emit)
    return m


def build_materials():
    D = {
        'concreto': ("Concreto_Claro", '#c9c3b8', 0.8),
        'grada': ("Grada_Concreto", '#9d978c', 0.85),
        'pasillo': ("Pasillo_Escalera", '#e6e1d6', 0.7),
        'vomitorio': ("Vomitorio_Sombra", '#1d1d22', 0.9),
        'hueco': ("Hueco_Abierto", '#000000', 0.5, 0, 0, 0, 0.0),
        'led': ("LED_Cinta", '#3ef0c8', 0.3, 0, 3.0),
        'accesible': ("Plataforma_Accesible", '#2a6fdb', 0.5),
        'vidrio': ("Vidrio_Fachada", '#9fd3e0', 0.05, 0, 0, 1.0, 0.35),
        'etfe': ("ETFE_Translucido", '#f4f8f6', 0.25, 0, 0, 0.75, 0.6),
        'etfe_mov': ("ETFE_Techo_Retractil", '#e8f4ff', 0.2, 0, 0, 0.7, 0.55),
        'solar': ("Panel_Solar", '#14263f', 0.15, 0.6),
        'acero': ("Acero_Blanco", '#f2f2ee', 0.35, 0.4),
        'madera': ("Madera_Laminada", '#b07a46', 0.6),
        'plafon': ("Plafon_Acustico_Madera", '#c89a66', 0.85),
        'jardin_v': ("Jardin_Vertical", '#3d7a35', 0.9),
        'halo': ("Pantalla_Halo_360", '#2f8fd8', 0.3, 0, 2.5),
        'cesped_a': ("Cesped_Campo_A", '#3f8f3a', 0.9),
        'cesped_b': ("Cesped_Campo_B", '#367e33', 0.9),
        'linea': ("Lineas_Campo", '#ffffff', 0.6),
        'amarillo_gp': ("Postes_Amarillos", '#f2c230', 0.4, 0.3),
        'zona_a': ("Zona_Anotacion_A", '#1f4fa3', 0.8),
        'zona_b': ("Zona_Anotacion_B", '#b5302a', 0.8),
        'pasto': ("Pasto_Jardin", '#6a9f45', 0.95),
        'seto': ("Seto_Jardin", '#3e7334', 0.95),
        'lavanda': ("Flores_Lavanda", '#9b7fc7', 0.9),
        'flor_am': ("Flores_Amarillas", '#e8c547', 0.9),
        'piedra': ("Piedra_Sendero", '#ddd2bd', 0.8),
        'plaza': ("Plaza_Piedra", '#e9e1d0', 0.75),
        'bomberos': ("Carril_Bomberos", '#c4553f', 0.8),
        'agua': ("Agua", '#1d6f8a', 0.03, 0.1),
        'cascada': ("Cascada", '#dff4ff', 0.05, 0, 0.6, 0.6, 0.7),
        'asfalto': ("Asfalto_Permeable", '#4a4a4f', 0.85),
        'tren_vent': ("Vidrio_Oscuro_Autos", '#1c2b36', 0.1, 0.3),
        'acento': ("Acento_Ambar", '#ffb100', 0.4, 0, 1.5),
        'corteza': ("Corteza", '#5b4330', 0.9),
        'texto': ("Etiqueta", '#ffffff', 0.5, 0, 2.0),
        'espejo': ("Vidrio_Espejo_Sakbe", '#c9d6de', 0.02, 0.6, 0, 0.45, 1.0, 1.8),
        'losa': ("Losa_Piso_Interior", '#d8d2c6', 0.7),
        'luz_int': ("Luz_Interior", '#fff1d6', 0.5, 0, 8.0),
        'vidrio_canon': ("Vidrio_Canon_Calido", '#efe2cc', 0.12, 0.25),
        'parque': ("Parque_Azotea", '#5f9a3c', 0.95),
        'sofito': ("Sofito_Madera", '#a9744a', 0.7),
        'pista': ("Pista_Trote", '#c8553d', 0.8),
        'escape': ("Nucleo_Escape_Protegido", '#d9633b', 0.7),
        'esc_elec': ("Escalera_Electrica", '#b9bec4', 0.3, 0.8),
        'evac': ("Ruta_Evacuacion", '#22d36b', 0.5, 0, 1.2),
        'reunion': ("Punto_Reunion", '#1fae5b', 0.6, 0, 0.6),
        'estac': ("Estacionamiento_Losa", '#8e8e8e', 0.9),
        'terreno': ("Terreno_Neutro", '#c9c5ba', 0.95),
        'luz_calida': ("Luz_Ventanas_Noche", '#ffcf8a', 0.5, 0, 6.0),
        'luz_fria': ("Luz_Linea_Noche", '#bfe8ff', 0.5, 0, 5.0),
        'escenario': ("Escenario", '#2b2b30', 0.6),
        'pantalla_esc': ("Pantalla_Escenario", '#ff4fa3', 0.3, 0, 4.0),
        'piso_proteccion': ("Piso_Proteccion_Cesped", '#5a5d62', 0.8),
        'duela': ("Duela_Arena", '#c99a5b', 0.5),
        'cisterna': ("Cisterna_Agua_Pluvial", '#5c8fb0', 0.5),
        'energia': ("Centro_Energia", '#e0b84a', 0.5),
        'bus': ("Autobus_Electrico", '#2e9e6a', 0.4),
        'sanit': ("Modulo_Sanitarios", '#7da7c9', 0.6),
        'comida': ("Modulo_Alimentos", '#f0a04b', 0.6),
        'medico': ("Modulo_Primeros_Auxilios", '#e2463f', 0.6),
        'sensorial': ("Modulo_Sala_Sensorial", '#a58ad6', 0.6),
        'lactancia': ("Modulo_Lactancia_Familia", '#f29bbf', 0.6),
        'control': ("Centro_Control", '#5ad1e6', 0.2, 0, 0.5, 0.5, 0.6),
        'cuarto': ("Cuarto_Jugadores", '#e9eef2', 0.6),
        'cuarto_b': ("Cuarto_Servicios", '#f3e6c4', 0.6),
        'tunel': ("Tunel_Jugadores", '#26262b', 0.6),
    }
    M = {}
    for k, v in D.items():
        name, hx = v[0], v[1]
        rest = list(v[2:])
        keys = ['rough', 'metal', 'emit', 'trans', 'alpha', 'ior']
        M[k] = make_mat(name, hx, **dict(zip(keys, rest)))
    seat_hex = ['#1f4d2c', '#2f7d3a', '#5f9e3d', '#2a9d8f', '#d9b26f', '#efcf7a']
    M['butacas'] = [make_mat(f"Butaca_{i}", h, 0.45) for i, h in enumerate(seat_hex)]
    M['hoja'] = [make_mat(f"Follaje_{i}", h, 0.9)
                 for i, h in enumerate(['#2f6b2f', '#4f8a35', '#6f9f3f', '#8f6fc7', '#3b7d4a'])]
    M['tiendas'] = [make_mat(f"Tienda_{i}", h, 0.6) for i, h in enumerate(
        ['#c98b6b', '#d8c3a5', '#8fa9a3', '#a7b59a', '#b9a2a8', '#e3d5c3'])]
    M['programa'] = {
        'comida': [make_mat("Restaurante_A", '#c07a4f', 0.6), make_mat("Restaurante_B", '#9c6b4e', 0.6)],
        'cine': [make_mat("Cine_Sala", '#4a3d5c', 0.7)],
        'deporte': [make_mat("Gimnasio_Centro_Deportivo", '#6f9c95', 0.6)],
        'salud': [make_mat("Clinica_Guarderia", '#f4f1ea', 0.6), make_mat("Museo_del_Deporte", '#c9a227', 0.6)],
        'oficina': [make_mat("Oficinas_Coworking", '#e8ecef', 0.6), make_mat("Coworking_Madera", '#c49a6c', 0.6)],
    }
    M['autos'] = [make_mat(f"Auto_{i}", h, 0.3, 0.5)
                  for i, h in enumerate(['#e9e9e9', '#2b2b2b', '#9aa3ad', '#b53a2e', '#2f5f9e'])]
    return M


# ==========================================================================
# AYUDANTES DE MALLA
# ==========================================================================
def new_coll(name, parent=None):
    c = bpy.data.collections.new(name)
    (parent or bpy.context.scene.collection).children.link(c)
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


def sweep(bm, prof_fn, seg, mat_fn, closed=True, t0=0.0, t1=None):
    """Barre un perfil (d, z) a lo largo de la superelipse (completa o un tramo)."""
    full = t1 is None
    if full:
        t1 = t0 + 2 * math.pi
    nr = seg if full else seg + 1
    rings = []
    for j in range(nr):
        t = t0 + (t1 - t0) * j / seg
        rings.append([bm.verts.new((*se(t, d), z)) for d, z in prof_fn(t)])
    m = len(rings[0])
    nseg = m if closed else m - 1
    for j in range(seg):
        r0 = rings[j]
        r1 = rings[(j + 1) % nr] if full else rings[j + 1]
        for i in range(nseg):
            i2 = (i + 1) % m
            f = bm.faces.new((r0[i], r1[i], r1[i2], r0[i2]))
            f.material_index = mat_fn(i, j)


def arc_block(bm, t0, t1, d0, d1, z0, z1, mats, tally=None, n=None):
    """Bloque sólido que sigue la curva: mats = (abajo, exterior, arriba, interior, tapa0, tapa1)."""
    if n is None:
        n = max(1, int(arc_len(t0, t1, (d0 + d1) / 2, 12) / 6.0) + 1)
    prof = [(d0, z0), (d1, z0), (d1, z1), (d0, z1)]
    rings = []
    for j in range(n + 1):
        t = t0 + (t1 - t0) * j / n
        rings.append([bm.verts.new((*se(t, d), z)) for d, z in prof])
    for j in range(n):
        for i in range(4):
            f = bm.faces.new((rings[j][i], rings[j + 1][i], rings[j + 1][(i + 1) % 4],
                              rings[j][(i + 1) % 4]))
            f.material_index = mats[i]
            if tally and tally[i]:
                AREAS[tally[i]] = AREAS.get(tally[i], 0.0) + f.calc_area()
    bm.faces.new(list(reversed(rings[0]))).material_index = mats[4]
    bm.faces.new(rings[-1]).material_index = mats[5]


def arc_strip(bm, t0, t1, d, z0, z1, mat, step=8.0):
    """Franja vertical de una sola cara que sigue la curva (ligera, para luces)."""
    n = max(1, int(arc_len(t0, t1, d, 12) / step) + 1)
    prev = None
    for j in range(n + 1):
        t = t0 + (t1 - t0) * j / n
        x, y = se(t, d)
        cur = (bm.verts.new((x, y, z0)), bm.verts.new((x, y, z1)))
        if prev:
            bm.faces.new((prev[0], cur[0], cur[1], prev[1])).material_index = mat
        prev = cur


def arc_len(t0, t1, d, n=40):
    pts = [se(t0 + (t1 - t0) * i / n, d) for i in range(n + 1)]
    return sum(math.dist(pts[i], pts[i + 1]) for i in range(n))


def add_obox(bm, c, ax, ay, az, hx, hy, hz, mat):
    c = Vector(c)
    vs = []
    for sx in (-1, 1):
        for sy in (-1, 1):
            for sz in (-1, 1):
                vs.append(bm.verts.new(c + ax * (sx * hx) + ay * (sy * hy) + az * (sz * hz)))
    for q in ((0, 1, 3, 2), (4, 6, 7, 5), (0, 4, 5, 1), (2, 3, 7, 6), (0, 2, 6, 4), (1, 5, 7, 3)):
        bm.faces.new([vs[i] for i in q]).material_index = mat


def add_box(bm, c, size, mat, rotz=0.0):
    ca, sa = math.cos(rotz), math.sin(rotz)
    add_obox(bm, c, Vector((ca, sa, 0)), Vector((-sa, ca, 0)), Vector((0, 0, 1)),
             size[0] / 2, size[1] / 2, size[2] / 2, mat)


def add_rbox(bm, t, d, z, len_t, len_d, h, mat):
    """Caja alineada a la curva en (t, d): len_t tangencial, len_d radial, base en z."""
    n, tan = outward(t, d)
    add_obox(bm, P(t, d, z + h / 2), tan, n, Vector((0, 0, 1)), len_t / 2, len_d / 2, h / 2, mat)


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


def add_helix(bm, c, r0, r1, z0, z1, turns, a0, mat, steps=96, thick=0.35):
    """Rampa/escalera helicoidal (para las torres de doble hélice)."""
    prev = None
    for k in range(steps + 1):
        f = k / steps
        a = a0 + 2 * math.pi * turns * f
        z = z0 + (z1 - z0) * f
        ca, sa = math.cos(a), math.sin(a)
        ring = [bm.verts.new((c[0] + r * ca, c[1] + r * sa, z + dz))
                for r, dz in ((r0, 0), (r1, 0), (r1, -thick), (r0, -thick))]
        if prev:
            for i in range(4):
                bm.faces.new((prev[i], ring[i], ring[(i + 1) % 4], prev[(i + 1) % 4])).material_index = mat
        prev = ring


# ==========================================================================
# 1. GRADAS: diseño por visibilidad (C-value) y normas
# ==========================================================================
def design_tier(spec, d0, z0):
    kinds = ['seat'] * spec['rows']
    if spec['acc'] == 'mid':
        kinds.insert(spec['mid_row'] + 1, 'acc')
    else:
        kinds.append('acc')
    steps, cvals = [], []
    d, z = d0 + 0.3, z0
    seat_row = 0
    for i, k in enumerate(kinds):
        w = ROW_D if k == 'seat' else ACC_W
        D = d + 0.45 - FOCUS_D
        R = z + EYE - Z_FIELD
        need = (w * R + C_TARGET * (D + w)) / D
        if k == 'acc':                  # muro detrás del pasillo transversal: no es grada, puede ser más alto
            n = min(2.5, max(0.30, need))
        else:
            n = min(MAX_RISE, max(0.30, need))
        steps.append(dict(kind=k, d=d, z=z, w=w, rise=n, row=seat_row if k == 'seat' else None))
        if i + 1 < len(kinds) and kinds[i + 1] == 'seat':
            cvals.append((D * n - w * R) / (D + w))
        if k == 'seat':
            seat_row += 1
        d += w
        z += n
    steps[-1]['rise'] = 0.0
    if spec['acc'] == 'back_L0':                 # la última grada remata exacto en el vestíbulo
        steps[-2]['rise'] = Z_L0 - steps[-2]['z']
        steps[-1]['z'] = Z_L0
    last = steps[-1]
    d_end, z_end = last['d'] + last['w'], last['z']
    if spec['under'] == 'solid':
        zf, zb = Z_FIELD, Z_FIELD
    else:
        zf, zb = z0 - spec['front_drop'], z_end - 3.5
    info = dict(spec=spec, d0=d0, z0=z0, steps=steps, back=d_end + 0.3, z_top=z_end,
                zf=zf, zb=zb, cmin=min(cvals),
                rake=max(math.degrees(math.atan(s['rise'] / s['w'])) for i, s in enumerate(steps[:-1])
                         if s['kind'] == 'seat' and steps[i + 1]['kind'] == 'seat'))
    info['under_at'] = lambda dd, i=info: i['zf'] + (i['zb'] - i['zf']) * (dd - i['d0']) / (i['back'] - i['d0'])
    return info


def tier_profile(info, hole=None):
    """Perfil (d, z) de la grada; idx[i] = (punto de huella, punto de contrahuella) del escalón i."""
    Pp, K, idx = [], [], {}

    def add(d, z, k):
        Pp.append((d, z))
        K.append(k)

    d0, z0 = info['d0'], info['z0']
    add(d0, info['zf'], 'front')
    add(d0, z0 + 1.1, 'ptop')
    add(d0 + 0.3, z0 + 1.1, 'pin')
    st = info['steps']
    for i, s in enumerate(st):
        ti = len(Pp)
        add(s['d'], s['z'], ('tread', i) if s['kind'] == 'seat' else 'acc')
        ri = None
        if i < len(st) - 1:
            ri = len(Pp)
            add(s['d'] + s['w'], s['z'], ('riser', i + 1))
        idx[i] = (ti, ri)
    d_end, z_end = info['back'] - 0.3, info['z_top']
    add(d_end, z_end, 'back')
    add(d_end, z_end + 1.2, 'btop')
    add(d_end + 0.3, z_end + 1.2, 'bout')
    add(d_end + 0.3, info['zb'], 'soffit')
    if hole:                                   # (d_exit, d_land): tramo de losa que se abre en los vomitorios
        ua = info['under_at']
        add(hole[1], ua(hole[1]), 'soffit_hole')
        add(hole[0], ua(hole[0]), 'soffit')
    return Pp, K, idx


def seat_color(tier, row, rows, j):
    t = 2 * math.pi * j / SEG
    f = row / max(1, rows - 1)
    v = (0.30 * tier + 0.35 * f + 0.10 * math.sin(3 * t + 2 * f + tier)
         + 0.06 * math.sin(11 * t - 5 * f) + random.uniform(-0.08, 0.08))
    return max(0, min(5, int(v / 1.2 * 6)))


def blocked_fn(spec):
    vom = spec.get('vom')

    def blocked(j, row):
        j %= SEG
        if j % spec['aisle'] == 0:
            return True
        if vom and row is not None and row in vom['rows'] and (j % vom['every']) in vom['segs']:
            return True
        return False
    return blocked


def walk_points(d, spacing, n_samp=SEG * 8):
    ts = [2 * math.pi * i / n_samp for i in range(n_samp + 1)]
    pts = [se(t, d) for t in ts]
    out, acc, target = [], 0.0, spacing / 2
    for i in range(n_samp):
        x0, y0 = pts[i]
        x1, y1 = pts[i + 1]
        L = math.hypot(x1 - x0, y1 - y0)
        while acc + L >= target:
            f = (target - acc) / L
            out.append((ts[i] + (ts[i + 1] - ts[i]) * f, x0 + (x1 - x0) * f, y0 + (y1 - y0) * f,
                        (y1 - y0) / L, -(x1 - x0) / L))
            target += spacing
        acc += L
    return out, acc


def build_stands(M, coll):
    mats = ([M['grada']] + M['butacas'] +
            [M['pasillo'], M['led'], M['accesible'], M['vomitorio'], M['concreto'], M['hueco']])
    I_AISLE, I_LED, I_ACC, I_VOM, I_CON, I_HOLE = 7, 8, 9, 10, 11, 12
    tiers = []
    d0 = 8.0
    for ti, spec in enumerate(TIERS):
        z0 = spec['z0']
        if ti == 1:
            d0 = tiers[0]['back'] + 1.1
        elif ti == 2:
            d0 = tiers[1]['back'] - 2.6
            z0 = max(z0, tiers[1]['z_top'] + 8.5)
        info = design_tier(spec, d0, z0)
        tiers.append(info)
        vom = spec.get('vom')
        hole = None
        if vom:
            acc = next(s for s in info['steps'] if s['kind'] == 'acc')
            d_s, z_p = acc['d'] + acc['w'], acc['z']
            slope = math.tan(math.radians(33))
            d_land = d_s + (z_p - Z_L2) / slope
            d_exit = d_s
            while z_p - slope * (d_exit - d_s) > info['under_at'](d_exit):
                d_exit += 0.05                     # donde la escalera atraviesa la losa
            hole = (d_exit, d_land)
            info['vom_stair'] = (d_s, z_p, slope)
            STATS['vom_stair'] = (d_s, z_p, slope, d_exit, d_land)
        Pp, K, idx = tier_profile(info, hole)
        steps = info['steps']
        blocked = blocked_fn(spec)
        rows = spec['rows']
        pattern = {}
        prof_v = None
        if vom:
            # vomitorio: zanja con escalera que baja del pasillo transversal, cruza la losa y llega a L2
            ua = info['under_at']
            prof_v = list(Pp)
            for i, s in enumerate(steps):
                if s['kind'] == 'seat' and s['row'] in vom['rows']:
                    for pi in idx[i]:
                        if pi is not None:
                            dd = Pp[pi][0]
                            prof_v[pi] = (dd, max(z_p - slope * (dd - d_s), ua(dd)))
        last_vom = max(vom['rows']) + 1 if vom else None

        def prof(t, Pp=Pp, prof_v=prof_v, vom=vom):
            if prof_v is None:
                return Pp
            j = int(round(t / (2 * math.pi) * SEG)) % SEG
            return prof_v if (j % vom['every']) in vom['flat'] else Pp

        def mat_fn(i, j, K=K, steps=steps, blocked=blocked, spec=spec, ti=ti, rows=rows, pattern=pattern,
                   vom=vom, last_vom=last_vom, hole=hole):
            k = K[i]
            jv = (j % SEG) % vom['every'] if vom else -1
            if k == 'soffit_hole':
                return I_HOLE if (vom and jv in vom['flat'][:-1]) else I_CON
            if isinstance(k, tuple):
                s = steps[k[1]]
                if s['kind'] != 'seat':
                    return I_CON
                if vom and jv in vom['segs']:
                    if s['row'] in vom['rows']:
                        if jv in vom['flat'][:-1]:
                            return I_HOLE if s['d'] >= hole[0] else I_AISLE
                        return I_VOM
                    if s['row'] == last_vom and k[0] == 'riser':
                        return I_VOM
                if blocked(j, s['row']):
                    return I_VOM if (j % spec['aisle']) else I_AISLE
                if k[0] == 'tread':
                    return 0
                key = (s['row'], j)
                if key not in pattern:
                    pattern[key] = seat_color(ti, s['row'], rows, j)
                return 1 + pattern[key]
            if k == 'acc':
                return I_ACC
            if k == 'front' and spec['led']:
                return I_LED
            return I_CON

        bm = bmesh.new()
        sweep(bm, prof, SEG, mat_fn)
        finish(spec['name'], bm, mats, coll)
        info['pattern'] = pattern
        if vom:                                          # escaleras de los vomitorios hasta L2
            bm = bmesh.new()
            d_s, z_p, slope = info['vom_stair']
            d_land = d_s + (z_p - Z_L2) / slope
            for k in range(SEG // vom['every']):
                jc = k * vom['every'] + vom['flat'][1]
                t = 2 * math.pi * jc / SEG
                n, tan = outward(t, (d_s + d_land) / 2)
                a, b = P(t, d_s, z_p), P(t, d_land, Z_L2)
                ax = (b - a).normalized()
                az = ax.cross(tan)
                if az.z < 0:
                    az = -az
                hw = perim((d_s + d_land) / 2, 360) / SEG
                add_obox(bm, (a + b) / 2 - az * 0.2, ax, tan, az, (b - a).length / 2, hw, 0.2, 0)
                for sgn in (-1, 1):
                    add_obox(bm, (a + b) / 2 + tan * (sgn * hw) + az * 0.55, ax, tan, az,
                             (b - a).length / 2, 0.08, 0.55, 1)
            finish("Vomitorios_Escaleras_a_L2", bm, [M['pasillo'], M['acero']], coll)
            STATS['vom_land'] = d_land
    return tiers


def place_seats(tiers):
    """Butacas individuales (cuenta exacta), lugares para silla de ruedas y público."""
    seats = {i: [] for i in range(6)}
    wheel = []
    per_tier = []
    for ti, info in enumerate(tiers):
        spec = info['spec']
        blocked = blocked_fn(spec)
        count = 0
        for s in info['steps']:
            if s['kind'] == 'seat':
                dl, spacing = s['d'] + 0.45, SEAT_W
            else:
                dl, spacing = s['d'] + ACC_W / 2, 1.6
            pts, total = walk_points(dl, spacing)
            seglen = total / SEG
            m = 0.27 / seglen if s['kind'] == 'seat' else 0.8 / seglen
            row = s['row']
            for (t, x, y, nx, ny) in pts:
                u = t / (2 * math.pi) * SEG
                j = int(u) % SEG
                fr = u - int(u)
                if blocked(j, row) or (fr < m and blocked(j - 1, row)) or (fr > 1 - m and blocked(j + 1, row)):
                    continue
                yaw = math.atan2(-ny, -nx)
                if s['kind'] == 'seat':
                    key = (row, j)
                    c = info['pattern'].get(key)
                    if c is None:
                        c = seat_color(ti, row, spec['rows'], j)
                    seats[c].append(((x, y, s['z']), yaw))
                    count += 1
                else:
                    wheel.append(((x, y, s['z']), yaw))
        per_tier.append(count)
    return seats, wheel, per_tier


# ---------- instancias (Geometry Nodes) ----------
def instancer_tree(name, src, use_scale=False):
    ng = bpy.data.node_groups.new(name, 'GeometryNodeTree')
    ng.interface.new_socket("Geometry", in_out='INPUT', socket_type='NodeSocketGeometry')
    ng.interface.new_socket("Geometry", in_out='OUTPUT', socket_type='NodeSocketGeometry')
    gi = ng.nodes.new('NodeGroupInput')
    go = ng.nodes.new('NodeGroupOutput')
    inst = ng.nodes.new('GeometryNodeInstanceOnPoints')
    oi = ng.nodes.new('GeometryNodeObjectInfo')
    oi.inputs['Object'].default_value = src
    attr = ng.nodes.new('GeometryNodeInputNamedAttribute')
    attr.data_type = 'FLOAT_VECTOR'
    attr.inputs['Name'].default_value = "rot"
    ng.links.new(gi.outputs[0], inst.inputs['Points'])
    ng.links.new(oi.outputs['Geometry'], inst.inputs['Instance'])
    ng.links.new(attr.outputs['Attribute'], inst.inputs['Rotation'])
    if use_scale:
        sc = ng.nodes.new('GeometryNodeInputNamedAttribute')
        sc.data_type = 'FLOAT_VECTOR'
        sc.inputs['Name'].default_value = "scl"
        ng.links.new(sc.outputs['Attribute'], inst.inputs['Scale'])
    ng.links.new(inst.outputs['Instances'], go.inputs[0])
    return ng


def make_instancer(name, items, src, coll, scales=None):
    """items = [(posición, giro_z)]; scales opcional = [escala uniforme]."""
    me = bpy.data.meshes.new(name)
    me.from_pydata([p for p, _ in items], [], [])
    attr = me.attributes.new("rot", 'FLOAT_VECTOR', 'POINT')
    flat = []
    for _, yaw in items:
        flat.extend((0.0, 0.0, yaw))
    attr.data.foreach_set("vector", flat)
    if scales is not None:
        sa = me.attributes.new("scl", 'FLOAT_VECTOR', 'POINT')
        sa.data.foreach_set("vector", [v for k in scales for v in (k, k, k)])
    ob = bpy.data.objects.new(name, me)
    coll.objects.link(ob)
    mod = ob.modifiers.new("Instancias", 'NODES')
    mod.node_group = instancer_tree("GN_" + name, src, scales is not None)
    return ob


def make_source(name, build, mats, coll):
    bm = bmesh.new()
    build(bm)
    ob = finish(name, bm, mats, coll)
    ob.location = (0, 0, -2000)
    ob.hide_render = True
    return ob


def seat_mesh(bm):
    prof = [(-0.22, 0.05), (-0.17, 0.05), (-0.17, 0.40), (0.24, 0.40), (0.24, 0.47),
            (-0.17, 0.47), (-0.17, 0.92), (-0.22, 0.92)]
    a = [bm.verts.new((x, -0.23, z)) for x, z in prof]
    b = [bm.verts.new((x, 0.23, z)) for x, z in prof]
    bm.faces.new(a)
    bm.faces.new(list(reversed(b)))
    for i in range(len(prof)):
        i2 = (i + 1) % len(prof)
        bm.faces.new((a[i], b[i], b[i2], a[i2]))


def wheel_mesh(bm):
    add_box(bm, (0.15, -0.45, 0.01), (1.3, 0.9, 0.02), 0)
    add_box(bm, (0.15, -0.45, 0.3), (0.7, 0.62, 0.55), 1)
    add_box(bm, (0.02, 0.45, 0.44), (0.42, 0.46, 0.06), 2)
    add_box(bm, (-0.2, 0.45, 0.68), (0.05, 0.46, 0.48), 2)


def car_mesh(bm):
    add_box(bm, (0, 0, 0.55), (4.4, 1.8, 0.75), 0)
    add_box(bm, (-0.2, 0, 1.15), (2.3, 1.6, 0.5), 1)


def build_seating_instances(M, tiers, coll_seats, coll_src):
    seats, wheel, per_tier = place_seats(tiers)
    for c in range(6):
        src = make_source(f"Fuente_Butaca_{c}", seat_mesh, [M['butacas'][c]], coll_src)
        make_instancer(f"Butacas_{c}", seats[c], src, coll_seats)
    src = make_source("Fuente_Silla_Ruedas", wheel_mesh,
                      [M['accesible'], M['acero'], M['butacas'][3]], coll_src)
    make_instancer("Lugares_Silla_de_Ruedas", wheel, src, coll_seats)
    STATS['butacas_por_grada'] = per_tier
    STATS['butacas'] = sum(per_tier)
    STATS['sillas_ruedas'] = len(wheel)


# ==========================================================================
# 2. VESTÍBULOS, CIRCULACIÓN VERTICAL, SERVICIOS
# ==========================================================================
def build_concourses(M, tiers, coll):
    t1, t2, t3 = tiers
    z_l1 = t2['z_top']
    STATS['Z_L1'] = z_l1
    d_l2 = t3['d0']
    while t3['under_at'](d_l2) < Z_L2 + 3.6:
        d_l2 += 0.5
    STATS['d_L2'] = d_l2
    floors = [("Vestibulo_L0_Principal", t1['back'] - 0.2, Z_L0),
              ("Vestibulo_L05_Mezzanine", t2['back'] + 1.0, Z_L05),
              ("Vestibulo_L1_Medio", t2['back'], z_l1),
              ("Vestibulo_L2_Alto", d_l2, Z_L2)]
    flights = [(Z_L0, Z_L05, 1), (Z_L05, z_l1, -1), (z_l1, Z_L2, 1)]
    STATS['flights'] = flights
    bm_r = bmesh.new()
    for name, din, z in floors:
        voids = []
        for (za, zb, side) in flights:
            if abs(zb - z) < 1e-6:                     # la escalera que llega a este piso lo atraviesa
                run = (zb - za) / math.tan(math.radians(30))
                for e in ENTRIES:
                    sp = speed(e, 89.2)
                    voids.append(tuple(sorted((e + side * 5.0 / sp, e + side * (7.0 + run) / sp))))
        bm = bmesh.new()
        ring_floor(bm, din, z, voids)
        finish(name, bm, [M['plaza']], coll)
        for (a, b) in voids:                           # barandal de vidrio alrededor del hueco
            for dd in (VOID_D[0], VOID_D[1]):
                arc_block(bm_r, a, b, dd - 0.03, dd + 0.03, z, z + 1.1, (0,) * 6)
            for tt in (a, b):
                n, tan = outward(tt, 89.5)
                add_obox(bm_r, P(tt, 89.5, z + 0.55), n, tan, Vector((0, 0, 1)),
                         (VOID_D[1] - VOID_D[0]) / 2, 0.03, 0.55, 0)
    finish("Barandales_Huecos_Escaleras", bm_r, [M['vidrio']], coll)

    bm = bmesh.new()   # luminarias lineales bajo cada losa y bajo las gradas
    for din, z in ((t2['back'] + 2.0, Z_L05 - 0.5), (t2['back'] + 2.0, z_l1 - 0.5), (d_l2 + 1.0, Z_L2 - 0.5)):
        for dd in (din + 3.0, (din + FACADE_D) / 2, FACADE_D - 4.0):
            sweep(bm, lambda t, dd=dd, z=z: [(dd - 0.3, z - 0.05), (dd + 0.3, z - 0.05)], SEG,
                  lambda i, j: 0, closed=False)
    for dd in (48.0, 58.0):
        sweep(bm, lambda t, dd=dd: [(dd - 0.3, t2['under_at'](dd) - 0.1), (dd + 0.3, t2['under_at'](dd) - 0.1)],
              SEG, lambda i, j: 0, closed=False)
    finish("Luminarias_Vestibulos", bm, [M['luz_calida']], coll, recalc=False)

    bm = bmesh.new()   # palcos con vidrio entre grada media y alta
    sweep(bm, lambda t: [(t2['back'] - 0.4, z_l1 + 1.2), (t2['back'] - 0.4, t3['zf'])], SEG,
          lambda i, j: 0, closed=False)
    finish("Palcos_Vidrio", bm, [M['vidrio']], coll, recalc=False)

    bm = bmesh.new()   # columnas
    for d in (46.0, 56.0):
        for k in range(48):
            t = 2 * math.pi * (k + 0.5) / 48
            add_cyl(bm, P(t, d, Z_L0), P(t, d, t2['under_at'](d)), 0.6, 0.6, 0, sides=8)
    for d in (70.0, 80.0, 90.0):
        for k in range(48):
            t = 2 * math.pi * (k + 0.5) / 48
            add_cyl(bm, P(t, d, Z_L0), P(t, d, t3['under_at'](d)), 0.7, 0.7, 0, sides=8)
    finish("Columnas", bm, [M['acero']], coll, smooth=True)


VOID_D = (85.5, 93.5)


def ring_floor(bm, din, z, voids, dout=FACADE_D - 0.2):
    """Losa anular; deja huecos (voids = tramos de t) en la franja VOID_D."""
    def prof(a, b):
        return lambda t: [(a, z - 0.45), (b, z - 0.45), (b, z), (a, z)]
    if not voids:
        sweep(bm, prof(din, dout), SEG, lambda i, j: 0)
        return
    sweep(bm, prof(din, VOID_D[0]), SEG, lambda i, j: 0)
    sweep(bm, prof(VOID_D[1], dout), SEG, lambda i, j: 0)
    voids = sorted(voids)
    for i, (a, b) in enumerate(voids):
        na = voids[(i + 1) % len(voids)][0] + (2 * math.pi if i == len(voids) - 1 else 0)
        arc_block(bm, b, na, VOID_D[0], VOID_D[1], z - 0.45, z, (0,) * 6)


def add_tube(bm, c, r, z0, z1, holes, mat, segs=48):
    """Cilindro (vidrio) con vanos de puerta: holes = [(ángulo, medio_ancho_rad, z_a, z_b)]."""
    for k in range(segs):
        a0, a1 = 2 * math.pi * k / segs, 2 * math.pi * (k + 1) / segs
        am = (a0 + a1) / 2
        cuts = sorted((za, zb) for (ac, hw, za, zb) in holes if ang_dist(am, ac) < hw)
        zc = z0
        for (za, zb) in cuts + [(z1, z1)]:
            if za > zc + 1e-6:
                v = [bm.verts.new((c[0] + r * math.cos(a), c[1] + r * math.sin(a), zz))
                     for a, zz in ((a0, zc), (a1, zc), (a1, za), (a0, za))]
                bm.faces.new(v).material_index = mat
            zc = max(zc, zb)


def add_arc_slab(bm, c, r0, r1, z, a0, a1, mat, thick=0.35):
    """Losa en forma de sector de anillo (descansos de las torres)."""
    segs = max(2, int((a1 - a0) / 0.12))
    rings = []
    for k in range(segs + 1):
        a = a0 + (a1 - a0) * k / segs
        ca, sa = math.cos(a), math.sin(a)
        rings.append([bm.verts.new((c[0] + r * ca, c[1] + r * sa, z + dz))
                      for r, dz in ((r0, 0), (r1, 0), (r1, -thick), (r0, -thick))])
    for k in range(segs):
        for i in range(4):
            bm.faces.new((rings[k][i], rings[k + 1][i], rings[k + 1][(i + 1) % 4],
                          rings[k][(i + 1) % 4])).material_index = mat
    bm.faces.new(list(reversed(rings[0]))).material_index = mat
    bm.faces.new(rings[-1]).material_index = mat


def build_vertical_circulation(M, tiers, coll):
    z_l1 = STATS['Z_L1']
    # (a) 8 torres de doble hélice en los accesos
    bm_g, bm_s, bm_c = bmesh.new(), bmesh.new(), bmesh.new()
    TURNS = 1.62
    levels = (Z_L05, z_l1, Z_L2)
    for e in ENTRIES:
        c = P(e, TOWER_D, 0)
        n, tan = outward(e, TOWER_D)
        a_out = math.atan2(n.y, n.x)
        a_in = a_out + math.pi
        hw = 2.3 / TOWER_R
        holes = [(a_out, hw, Z_L0, Z_L0 + 3.2), (a_in, hw, Z_L0, Z_L0 + 3.2)]
        holes += [(a_in, hw, z, z + 3.2) for z in levels]
        add_tube(bm_g, (c.x, c.y), TOWER_R, Z_L0, Z_L2 + 7, holes, 0)
        add_disc(bm_g, (c.x, c.y), TOWER_R + 0.6, TOWER_R + 0.6, Z_L2 + 7.4, 0, 32)
        add_cyl(bm_c, (c.x, c.y, Z_P2), (c.x, c.y, Z_L2 + 9), 2.6, 2.6, 0, sides=16)   # elevadores
        base = a_in - math.radians(127)          # la hélice deja libre el lado del puente
        for a0 in (0.0, math.pi):
            add_helix(bm_s, (c.x, c.y), 3.2, 6.2, Z_L0, Z_L2, TURNS, base + a0, 0, steps=64)
        for z in levels:                          # descansos: anillo con hueco donde pasa la hélice
            if z >= Z_L2 - 1e-6:
                add_arc_slab(bm_s, (c.x, c.y), 2.7, 7.8, z, 0.0, 2 * math.pi, 1)
                continue
            ah = base + 2 * math.pi * TURNS * (z - Z_L0) / (Z_L2 - Z_L0)
            gw = math.radians(45)
            for a0 in (0.0, math.pi):
                add_arc_slab(bm_s, (c.x, c.y), 2.7, 7.8, z, ah + a0 + gw, ah + a0 + math.pi - gw, 1)
        for z, side in [(z, a_in) for z in (Z_P2, Z_P1, Z_L0) + levels] + [(Z_L0, a_out)]:
            d2 = Vector((math.cos(side), math.sin(side), 0))
            add_obox(bm_c, Vector((c.x, c.y, z + 1.15)) + d2 * 2.62, d2, Vector((-d2.y, d2.x, 0)),
                     Vector((0, 0, 1)), 0.08, 0.7, 1.15, 1)
        for z in (Z_L05, z_l1, Z_L2):                          # puentes a cada vestíbulo
            add_obox(bm_s, P(e, (FACADE_D + TOWER_D - TOWER_R) / 2, z - 0.25), n, tan,
                     Vector((0, 0, 1)), (TOWER_D - TOWER_R - FACADE_D) / 2 + 1.2, 2.3, 0.25, 2)
    finish("Torres_Circulacion_Vidrio", bm_g, [M['vidrio'], M['acero']], coll, recalc=False)
    finish("Torres_Escalera_Doble_Helice_y_Descansos", bm_s, [M['madera'], M['plaza'], M['acero']], coll)
    finish("Torres_Nucleo_Elevadores", bm_c, [M['concreto'], M['tunel']], coll)

    # (b) escaleras eléctricas: L0 -> L0.5 -> L1 -> L2 junto a cada acceso
    bm = bmesh.new()
    for e in ENTRIES:
        for (za, zb, side) in STATS['flights']:
            run = (zb - za) / math.tan(math.radians(30))
            for d in (88.0, 90.4):
                n, tan = outward(e, d)
                a = P(e, d, za) + tan * (side * 6.0)
                b = a + tan * (side * run) + Vector((0, 0, zb - za))
                ax = (b - a).normalized()
                ay = n
                az = ax.cross(ay)
                if az.z < 0:
                    az = -az
                add_obox(bm, (a + b) / 2 + az * 0.5, ax, ay, az, (b - a).length / 2, 0.75, 0.55, 0)
    finish("Escaleras_Electricas", bm, [M['esc_elec']], coll)

    # (c) 16 núcleos de escape protegidos (escalera + elevador de evacuación)
    bm = bmesh.new()
    for t in CORES:
        add_rbox(bm, t, 83.0, Z_P2, 9.0, 12.0, Z_L2 + 4.0 - Z_P2, 0)
        for z in (Z_P2, Z_P1, Z_L0, Z_L05, z_l1, Z_L2):
            add_rbox(bm, t, 76.9, z, 1.9, 0.3, 2.3, 1)          # puerta cortafuego en cada nivel
    finish("Nucleos_Escape_Protegidos", bm, [M['escape'], M['tunel']], coll)

    STATS['elevadores_estadio'] = 8 * 4 + 16
    STATS['escaleras_electricas'] = 8 * 3 * 2


def build_service_pods(M, coll):
    """Módulos de sanitarios, alimentos, primeros auxilios, sala sensorial y lactancia."""
    mats = [M['sanit'], M['comida'], M['medico'], M['sensorial'], M['lactancia'], M['control']]
    cycle = [0, 1, 0, 0, 2, 0, 1, 0, 0, 3, 0, 1, 0, 4]
    names = ["sanitarios", "alimentos", "primeros_aux", "sala_sensorial", "lactancia_familia"]
    counts = [0] * 5
    bm = bmesh.new()
    d2 = max(78.0, STATS['d_L2'] + 4.0)
    levels = [(Z_L0, 76.0), (Z_L0, 89.0), (Z_L05, 76.0), (Z_L05, 89.0), (STATS['Z_L1'], 76.0),
              (STATS['Z_L1'], 89.0), (Z_L2, d2), (Z_L2, 91.0)]
    k = 0
    area_wc = 0.0
    for z, d in levels:
        n = 60
        for i in range(n):
            t = 2 * math.pi * (i + 0.5) / n
            if any(ang_dist(t, c) < math.radians(4.5) for c in CORES):
                continue
            if z == Z_L2 and any(ang_dist(t, v) < math.radians(4) for v in VOMS):
                continue
            if any(ang_dist(t, e) < math.radians(12 if d > 84 else 4) for e in ENTRIES):
                continue
            typ = cycle[k % len(cycle)]
            k += 1
            counts[typ] += 1
            depth = 10.0 if typ == 0 else 7.0
            if typ == 0:
                area_wc += 10.0 * depth
            add_rbox(bm, t, d, z, 10.0, depth, 3.6, typ)
    # kioscos de comida entre columnas (2 cajas c/u)
    kioscos = 0
    for z, d in ((Z_L0, 51.0), (Z_L05, 72.0), (STATS['Z_L1'], 72.0), (Z_L2, max(79.0, STATS['d_L2'] + 3.0))):
        for k in range(96):
            t = 2 * math.pi * (k + 0.5) / 96
            if any(ang_dist(t, c) < math.radians(3.5) for c in CORES) or \
               any(ang_dist(t, e) < math.radians(3.5) for e in ENTRIES) or \
               (z == Z_L2 and any(ang_dist(t, v) < math.radians(3.5) for v in VOMS)):
                continue
            if any(ang_dist(t, (kk + 0.5) * math.pi / 24) < math.radians(0.8) for kk in range(48)):
                continue                                   # no sobre las columnas
            add_rbox(bm, t, d, z, 3.5, 2.5, 2.8, 1)
            kioscos += 1
    STATS['kioscos'] = kioscos
    # centro de mando y control (seguridad / protección civil) en L1 norte
    add_rbox(bm, math.pi / 2, 70.0, STATS['Z_L1'], 30.0, 8.0, 4.0, 5)
    finish("Modulos_Servicio_Vestibulos", bm, mats, coll)
    STATS['modulos'] = dict(zip(names, counts))
    STATS['sanitarios_m2'] = area_wc
    STATS['muebles_sanitarios'] = int(area_wc / 3.0)


# ==========================================================================
# 3. CAMPO, ZONA DE JUGADORES Y MODOS DEPORTIVOS
# ==========================================================================
def build_field(M, coll):
    bm = bmesh.new()
    zf = Z_FIELD
    add_box(bm, (0, 0, zf - 0.25), (2 * (A + 10), 2 * (B + 10), 0.5), 0)
    n = 18
    for i in range(n):
        x0 = -52.5 + 105 * i / n
        add_box(bm, (x0 + 105 / n / 2, 0, zf + 0.01), (105 / n, 68, 0.02), 1 + i % 2)
    finish("Campo_Cesped", bm, [M['cesped_b'], M['cesped_a'], M['cesped_b']], coll, recalc=False)
    bm = bmesh.new()
    sweep(bm, lambda t: [(5.5, zf), (5.5, zf + 0.9)], SEG, lambda i, j: 0, closed=False)
    ob = finish("LED_Perimetral", bm, [M['led']], coll, recalc=False)
    ob.modifiers.new("Grosor", 'SOLIDIFY').thickness = 0.3


def line(bm, x0, y0, x1, y1, z, mat, w=0.12):
    L = math.hypot(x1 - x0, y1 - y0)
    add_box(bm, ((x0 + x1) / 2, (y0 + y1) / 2, z), (L + w, w, 0.02), mat, math.atan2(y1 - y0, x1 - x0))


def rect(bm, x0, y0, x1, y1, z, mat):
    line(bm, x0, y0, x1, y0, z, mat)
    line(bm, x1, y0, x1, y1, z, mat)
    line(bm, x1, y1, x0, y1, z, mat)
    line(bm, x0, y1, x0, y0, z, mat)


def build_modes(M, colls):
    zl = Z_FIELD + 0.03
    zf = Z_FIELD
    # --- fútbol (FIFA 105 x 68) ---
    bm = bmesh.new()
    rect(bm, -52.5, -34, 52.5, 34, zl, 0)
    line(bm, 0, -34, 0, 34, zl, 0)
    add_ring(bm, (0, 0), 9.09, 9.21, zl, 0, 64)
    for sgn in (-1, 1):
        gx = 52.5 * sgn
        for depth, half in ((16.5, 20.16), (5.5, 9.16)):
            rect(bm, gx, -half, gx - sgn * depth, half, zl, 0)
        spot = gx - sgn * 11
        a_c = 0.0 if sgn < 0 else math.pi
        add_ring(bm, (spot, 0), 9.09, 9.21, zl, 0, 24, a_c - 0.927, a_c + 0.927)
        for y in (-3.66, 3.66):
            add_box(bm, (gx + sgn * 0.06, y, zf + 1.22), (0.12, 0.12, 2.44), 0)
        add_box(bm, (gx + sgn * 0.06, 0, zf + 2.44), (0.12, 7.44, 0.12), 0)
        add_box(bm, (gx + sgn * 1.5, 0, zf + 2.44), (3.0, 7.44, 0.05), 0)
    finish("Futbol_Lineas_y_Porterias", bm, [M['linea']], colls['futbol'], recalc=False)

    # --- fútbol americano (120 x 53.3 yardas) ---
    yd = 0.9144
    bm = bmesh.new()
    L2, W2 = 60 * yd, 26.67 * yd
    rect(bm, -L2, -W2, L2, W2, zl, 0)
    for k in range(-10, 11):
        x = k * 5 * yd
        line(bm, x, -W2, x, W2, zl, 0)
    for sgn, mat in ((-1, 1), (1, 2)):
        add_box(bm, (sgn * 55 * yd, 0, zf + 0.02), (10 * yd, 2 * W2, 0.02), mat)
        gx = sgn * L2
        add_box(bm, (gx, 0, zf + 1.52), (0.25, 0.25, 3.05), 3)
        add_box(bm, (gx, 0, zf + 3.05), (0.2, 5.64, 0.2), 3)
        for y in (-2.82, 2.82):
            add_box(bm, (gx, y, zf + 3.05 + 5.35), (0.15, 0.15, 10.7), 3)
    finish("Futbol_Americano_Lineas_y_Postes", bm,
           [M['linea'], M['zona_a'], M['zona_b'], M['amarillo_gp']], colls['americano'], recalc=False)

    # --- rugby (100 + 2 x 10 in-goal, 68 de ancho) ---
    bm = bmesh.new()
    rect(bm, -60, -34, 60, 34, zl, 0)
    for x in (-50, -28, 0, 28, 50):
        line(bm, x, -34, x, 34, zl, 0)
    for x in (-10, 10):
        for y0 in range(-34, 34, 4):
            line(bm, x, y0, x, y0 + 2, zl, 0)
    for sgn in (-1, 1):
        gx = sgn * 50
        for y in (-2.8, 2.8):
            add_box(bm, (gx, y, zf + 8), (0.2, 0.2, 16), 0)
            add_box(bm, (gx, y, zf + 1), (0.5, 0.5, 2), 1)
        add_box(bm, (gx, 0, zf + 3.0), (0.2, 5.6, 0.2), 0)
    finish("Rugby_Lineas_y_Postes_H", bm, [M['linea'], M['zona_b']], colls['rugby'], recalc=False)

    # --- concierto: escenario, piso protector, pantalla ---
    bm = bmesh.new()
    add_box(bm, (0, 0, zf + 0.06), (105, 68, 0.1), 0)
    add_box(bm, (44, 0, zf + 1.1), (22, 60, 2.0), 1)
    add_box(bm, (54, 0, zf + 12), (2, 52, 20), 2)
    for y in (-30, 30):
        add_box(bm, (44, y, zf + 12), (1.2, 1.2, 24), 3)
    add_box(bm, (44, 0, zf + 24), (24, 62, 1.2), 3)
    add_box(bm, (-30, 0, zf + 1.5), (8, 12, 3), 1)         # mezcla (FOH)
    finish("Concierto_Escenario", bm, [M['piso_proteccion'], M['escenario'], M['pantalla_esc'], M['acero']],
           colls['concierto'], recalc=False)
    STATS['concierto_cancha'] = int(((31 + 48) * 64 - 8 * 12) * 2.0)   # de pie, 2 personas/m²

    # --- arena central: duela + gradas temporales ---
    bm = bmesh.new()
    add_box(bm, (0, 0, zf + 0.1), (40, 26, 0.2), 0)
    rect(bm, -14, -7.5, 14, 7.5, zf + 0.21, 1)
    line(bm, 0, -7.5, 0, 7.5, zf + 0.21, 1)
    add_ring(bm, (0, 0), 1.74, 1.86, zf + 0.21, 1, 32)
    temp = 0
    for r in range(12):                                     # gradas telescópicas a ras de campo
        h = 0.45 + r * 0.42
        for sgn in (-1, 1):
            add_box(bm, (0, sgn * (9.5 + r * 0.85), zf + h / 2), (44, 0.85, h), 2)
            add_box(bm, (sgn * (17.0 + r * 0.85), 0, zf + h / 2), (0.85, 30, h), 2)
            temp += int(44 / SEAT_W) + int(30 / SEAT_W)
    finish("Arena_Central_Duela_y_Gradas", bm, [M['duela'], M['linea'], M['grada']],
           colls['arena'], recalc=False)
    STATS['arena_temporal'] = temp


def build_players_zone(M, coll):
    """Nivel de campo (-12 m) bajo el lado norte: todo lo de los equipos."""
    z = Z_FIELD
    rooms = [
        ("Vestidor Local", -30, -6, 84, 100, 7), ("Vestidor Visitante", 6, 30, 84, 100, 8),
        ("Árbitros", -42, -30, 84, 100, 0), ("Árbitras", 30, 42, 84, 100, 0),
        ("Enfermería / Médico", -52, -42, 84, 100, 3), ("Antidopaje", 42, 52, 84, 100, 3),
        ("Utilería", -66, -52, 84, 100, 1), ("Fisio / Hidroterapia", 52, 66, 84, 100, 9),
        ("Calentamiento + pista 60 m", -66, -6, 104, 120, 2), ("Zona mixta", 6, 26, 104, 120, 1),
        ("Sala de prensa (250)", 26, 50, 104, 120, 1), ("Niños escolta / familias", 50, 66, 104, 120, 1),
    ]
    bm = bmesh.new()
    mats = [M['cuarto'], M['cuarto_b'], M['cesped_a'], M['medico'], M['tunel'], M['asfalto'], M['concreto'],
            M['zona_a'], M['zona_b'], M['agua']]
    labels = []
    for (name, x0, x1, y0, y1, m) in rooms:          # cuartos abiertos (muros + piso de color)
        cx, cy, w, h = (x0 + x1) / 2, (y0 + y1) / 2, x1 - x0, y1 - y0
        add_box(bm, (cx, cy, z + 0.06), (w - 0.4, h - 0.4, 0.12), m)
        for (bx, by, sx, sy) in ((cx, y0 + 0.2, w, 0.3), (cx, y1 - 0.2, w, 0.3),
                                 (x0 + 0.2, cy, 0.3, h), (x1 - 0.2, cy, 0.3, h)):
            add_box(bm, (bx, by, z + 1.75), (sx, sy, 3.5), 6)
        add_box(bm, (cx, y0 + 0.2, z + 1.2), (2.0, 0.4, 2.4), 4)          # puerta
        labels.append((name, (cx, cy, z + 6)))
    add_box(bm, (0, 92, z + 0.05), (12, 16, 0.1), 1)                       # pasillo de jugadores
    add_box(bm, (0, 102, z + 0.05), (132, 4, 0.1), 1)
    add_box(bm, (0, 67, z + 1.8), (6, 34, 3.6), 4)                          # túnel bajo la grada
    add_box(bm, (0, 46.5, z + 1.6), (6.5, 7, 3.2), 4)                       # manga telescópica
    finish("Zona_Jugadores_Nivel_Campo", bm, mats, coll)
    bm = bmesh.new()                                                        # anillo de servicio
    sweep(bm, lambda t: [(86.0, z + 0.02), (94.0, z + 0.02)], SEG, lambda i, j: 0, closed=False)
    finish("Anillo_Servicio_Autobuses_Emergencias", bm, [M['asfalto']], coll, recalc=False)
    return labels


# ==========================================================================
# 4. CUBIERTA FIJA, TECHO RETRÁCTIL, HALO, ACÚSTICA
# ==========================================================================
def build_roof(M, coll):
    NPET, SUB, RAD = 72, 4, 18
    PV_FROM = 70.0
    bm = bmesh.new()
    a_pv = a_etfe = 0.0
    for p in range(NPET):
        dt = 2 * math.pi / NPET
        ta, tb = dt * p, dt * p + dt * 1.05
        grid = []
        for a in range(SUB + 1):
            u = a / SUB
            t = ta + (tb - ta) * u
            col = []
            for k in range(RAD + 1):
                d = ROOF_IN + (ROOF_OUT - ROOF_IN) * k / RAD
                if k == RAD:
                    d += 4.0 * math.sin(math.pi * u)
                z = z_roof(d, t) + 1.8 * u + 0.6 * math.sin(math.pi * u)
                col.append(bm.verts.new((*se(t, d), z)))
            grid.append(col)
        for a in range(SUB):
            for k in range(RAD):
                f = bm.faces.new((grid[a][k], grid[a + 1][k], grid[a + 1][k + 1], grid[a][k + 1]))
                dm = ROOF_IN + (ROOF_OUT - ROOF_IN) * (k + 0.5) / RAD
                f.material_index = 1 if dm > PV_FROM else 0
                if dm > PV_FROM:
                    a_pv += f.calc_area()
                else:
                    a_etfe += f.calc_area()
    ob = finish("Cubierta_Hojas_ETFE_Solar", bm, [M['etfe'], M['solar']], coll, smooth=True)
    ob.modifiers.new("Grosor", 'SOLIDIFY').thickness = 0.5
    STATS['cubierta_etfe'] = a_etfe / 1.05
    STATS['cubierta_pv'] = a_pv / 1.05

    bm = bmesh.new()   # plafón acústico de madera bajo la zona solar
    sweep(bm, lambda t: [(PV_FROM, z_roof(PV_FROM, t) - 1.3), (ROOF_OUT - 3, z_roof(ROOF_OUT - 3, t) - 1.3)],
          SEG, lambda i, j: 0, closed=False)
    ob = finish("Plafon_Acustico", bm, [M['plafon']], coll, recalc=False)
    ob.modifiers.new("Grosor", 'SOLIDIFY').thickness = 0.25

    bm = bmesh.new()
    sweep(bm, lambda t: [(11.0, z_roof(12, t) - 1.2), (13.6, z_roof(12, t) - 1.2),
                         (13.6, z_roof(12, t) + 0.8), (11.0, z_roof(12, t) + 0.8)], SEG, lambda i, j: 0)
    finish("Anillo_Tension_Interior", bm, [M['acero']], coll)

    bm = bmesh.new()   # anillo de compresión exterior (sobre los árboles) + 36 armaduras radiales
    sweep(bm, lambda t: [(TREE_D - 9.0, z_roof(TREE_D - 9, t) - 3.2), (TREE_D - 6.0, z_roof(TREE_D - 6, t) - 3.2),
                         (TREE_D - 6.0, z_roof(TREE_D - 6, t) - 1.2), (TREE_D - 9.0, z_roof(TREE_D - 9, t) - 1.2)],
          SEG, lambda i, j: 0)
    for k in range(36):
        t = 2 * math.pi * k / 36
        d_out = TREE_D - 7.5
        top = [P(t, d, z_roof(d, t) - 0.7) for d in (13.0, d_out)]
        bot = [P(t, 13.0, z_roof(12, t) - 1.2), P(t, d_out, z_roof(d_out, t) - 3.2)]
        mid = P(t, (13.0 + d_out) / 2, (bot[0].z + bot[1].z) / 2 - 4.0)
        for (a, b) in ((bot[0], mid), (mid, bot[1])):
            add_cyl(bm, a, b, 0.2, 0.2, 0, sides=6)                    # cable inferior
        n_s = 10
        for i in range(n_s + 1):
            d = 13.0 + (d_out - 13.0) * i / n_s
            f = i / n_s
            zb = (bot[0].z + (mid.z - bot[0].z) * (f / 0.5)) if f <= 0.5 else (mid.z + (bot[1].z - mid.z) * ((f - 0.5) / 0.5))
            add_cyl(bm, P(t, d, zb), P(t, d, z_roof(d, t) - 0.7), 0.12, 0.12, 0, sides=4)   # montantes
        for i in range(n_s):
            d0, d1 = 13.0 + (d_out - 13.0) * i / n_s, 13.0 + (d_out - 13.0) * (i + 1) / n_s
            add_cyl(bm, P(t, d0, z_roof(d0, t) - 0.7), P(t, d1, z_roof(d1, t) - 0.7), 0.25, 0.25, 0, sides=6)
    finish("Cubierta_Anillo_Compresion_y_Armaduras_Radiales", bm, [M['acero']], coll)

    bm = bmesh.new()
    sweep(bm, lambda t: [(11.3, z_roof(12, t) - 13.0), (11.3, z_roof(12, t) - 4.0)], SEG,
          lambda i, j: 0, closed=False)
    ob = finish("Pantalla_Halo_360", bm, [M['halo']], coll, recalc=False)
    ob.modifiers.new("Grosor", 'SOLIDIFY').thickness = 0.6


def beam(bm, a, b, w, h, mat, up=Vector((0, 0, 1))):
    """Viga de sección rectangular de a a b (cara superior en la línea a-b)."""
    a, b = Vector(a), Vector(b)
    ax = (b - a).normalized()
    ay = up.cross(ax)
    if ay.length < 1e-6:
        ay = Vector((1, 0, 0))
    ay.normalize()
    az = ax.cross(ay)
    if az.z < 0:
        az, ay = -az, -ay
    add_obox(bm, (a + b) / 2 - az * (h / 2), ax, ay, az, (b - a).length / 2, w / 2, h / 2, mat)


def build_retractable(M, coll):
    """Techo retráctil de 16 hojas.

    Cómo se sostiene (todo está modelado):
      * Cada hoja tiene 2 carritos (bogies) en su eje que ruedan sobre 2 vigas-riel rectas.
      * Las vigas-riel interiores salen de un ANILLO CENTRAL (cubo) y llegan al anillo de
        tensión; abajo llevan cuerda inferior y montantes (armadura tipo rueda de bicicleta).
      * Sobre la cubierta fija, las vigas-riel se apoyan en postes cada ~12 m.
      * Al abrir, cada hoja sube 3 m y se desliza en línea recta a su "estacionamiento"
        sobre la cubierta fija. Frame 1 = abierto, frame 120 = cerrado.
    """
    NP = 16
    z_top = ROOF_Z + 3 + 1.0 + 4.0
    area = 0.0
    bm_s = bmesh.new()
    hub_top, hub_bot = [], []
    for k in range(NP):
        t0, t1 = 2 * math.pi * k / NP, 2 * math.pi * (k + 1) / NP
        bm = bmesh.new()
        center = bm.verts.new((0, 0, z_top))
        cols = []
        SUB, RS = 5, 6
        for a in range(SUB + 1):
            t = t0 + (t1 - t0) * a / SUB
            ex, ey = se(t, 12.6)
            ze = z_roof(12, t) + 1.0
            cols.append([bm.verts.new((ex * r / RS, ey * r / RS, ze + (z_top - ze) * (1 - (r / RS) ** 2)))
                         for r in range(1, RS + 1)])
        for a in range(SUB):
            f = bm.faces.new((center, cols[a][0], cols[a + 1][0]))
            area += f.calc_area()
            for r in range(RS - 1):
                f = bm.faces.new((cols[a][r], cols[a][r + 1], cols[a + 1][r + 1], cols[a + 1][r]))
                area += f.calc_area()
        tm = (t0 + t1) / 2
        mx, my = se(tm, 12.6)
        L = math.hypot(mx, my)
        ux, uy = mx / L, my / L
        ze_m = z_roof(12, tm) + 1.0
        mv = Vector((ux * (L + 3), uy * (L + 3), 3.0))
        dirv = mv.normalized()
        sup = []
        for sfr in (0.12, 0.9):                       # carritos (se mueven con la hoja)
            p = Vector((mx * sfr, my * sfr, ze_m + (z_top - ze_m) * (1 - sfr * sfr) - 1.0))
            sup.append(p)
            add_obox(bm, p + Vector((0, 0, 0.5)), Vector((ux, uy, 0)), Vector((-uy, ux, 0)),
                     Vector((0, 0, 1)), 1.8, 1.1, 0.5, 1)
        ob = finish(f"Techo_Retractil_Hoja_{k + 1:02d}", bm, [M['etfe_mov'], M['acero']], coll)
        ob.modifiers.new("Grosor", 'SOLIDIFY').thickness = 0.35
        ob.location = mv
        ob.keyframe_insert("location", frame=1)
        ob.keyframe_insert("location", frame=20)
        ob.location = (0, 0, 0)
        ob.keyframe_insert("location", frame=120)

        for si, p in enumerate(sup):                  # vigas-riel fijas
            a = p - dirv * 2.5
            b = p + mv + dirv * 2.5
            beam(bm_s, a, b, 1.0, 1.2, 0)
            n_post = int((b - a).length // 12)
            for q_i in range(n_post + 1):
                q = a + (b - a) * (q_i / max(1, n_post))
                rr = math.hypot(q.x, q.y)
                if rr < L - 0.5:
                    continue                          # sobre el hueco: lo resuelve la armadura
                d_here = 12.6 + (rr - L)
                if d_here > ROOF_OUT - 2:
                    continue
                z_base = z_roof(12, tm) + 0.8 if d_here < 14 else z_roof(d_here, tm) + 2.4
                if q.z - 1.2 - z_base > 0.3:
                    add_cyl(bm_s, (q.x, q.y, z_base), (q.x, q.y, q.z - 1.2), 0.35, 0.35, 1, sides=8)
            if si == 0:                               # armadura bajo el riel interior (cubo -> anillo)
                ring_pt = a + (b - a) * ((L - math.hypot(a.x, a.y)) /
                                         max(1e-6, math.hypot(b.x, b.y) - math.hypot(a.x, a.y)))
                ring_bot = Vector((ring_pt.x, ring_pt.y, z_roof(12, tm) - 1.2))
                a_bot = a - Vector((0, 0, 6.0))
                add_cyl(bm_s, a_bot, ring_bot, 0.3, 0.3, 1, sides=6)
                for f in [i / 8 for i in range(1, 8)]:
                    top_p = a + (ring_pt - a) * f - Vector((0, 0, 1.2))
                    bot_p = a_bot + (ring_bot - a_bot) * f
                    add_cyl(bm_s, bot_p, top_p, 0.18, 0.18, 1, sides=6)
                    if f < 0.9:
                        nxt = a + (ring_pt - a) * (f + 1 / 8) - Vector((0, 0, 1.2))
                        add_cyl(bm_s, bot_p, nxt, 0.12, 0.12, 1, sides=4)
                hub_top.append(a - Vector((0, 0, 1.2)))
                hub_bot.append(a_bot)
    for ring in (hub_top, hub_bot):                   # anillo central (cubo) de la rueda
        for i in range(NP):
            add_cyl(bm_s, ring[i], ring[(i + 1) % NP], 0.9, 0.9, 1, sides=8)
    for i in range(NP):
        add_cyl(bm_s, hub_top[i], hub_bot[i], 0.5, 0.5, 1, sides=8)
        add_cyl(bm_s, hub_top[i], hub_bot[(i + 1) % NP], 0.25, 0.25, 1, sides=6)
    finish("Techo_Retractil_Vigas_Riel_y_Cubo_Central", bm_s, [M['acero'], M['acero']], coll, smooth=False)
    STATS['techo_retractil'] = area
    sc = bpy.context.scene
    sc.frame_start, sc.frame_end, sc.frame_current = 1, 120, 1


# ==========================================================================
# 5. ÁRBOLES ESTRUCTURALES, FACHADA, ACCESOS
# ==========================================================================
def build_structural_trees(M, coll):
    bm = bmesh.new()
    dt = math.pi / N_TREES * 0.9
    for k in range(N_TREES):
        t = 2 * math.pi * k / N_TREES
        bx, by = se(t, TREE_D)
        top = P(t, TREE_D - 1, 30.0)
        add_cyl(bm, (bx, by, -1), (bx, by, 3), 3.2, 1.9, 0, sides=12)
        add_cyl(bm, (bx, by, 3), top, 1.9, 1.3, 0, sides=12)
        for (tm, dm, zm) in ((t, TREE_D - 6.5, 47.0), (t - dt, TREE_D - 2.5, 44.0), (t + dt, TREE_D - 2.5, 44.0),
                             (t, TREE_D + 4.5, 42.0)):
            mid = P(tm, dm, zm)
            add_cyl(bm, top, mid, 1.15, 0.75, 0, sides=10)
            for sd, st in ((-6.0, -0.35), (5.0, 0.35)):
                tr = tm + st * dt
                dr = min(ROOF_OUT - 4, max(86.0, dm + sd))
                tip = P(tr, dr, z_roof(dr, tr) - 0.2)
                add_cyl(bm, mid, tip, 0.7, 0.35, 0, sides=8)
                add_cyl(bm, tip - Vector((0, 0, 0.25)), tip + Vector((0, 0, 0.6)), 1.6, 1.6, 1, sides=10)
    finish("Arboles_Estructurales", bm, [M['madera'], M['acero']], coll, smooth=True)


def near_entry(t, d, half):
    return any(ang_dist(t, e) * r_eff(d) < half for e in ENTRIES)


def facade_strip(bm, t0, t1, d, za, zb, mat=0):
    """Franja vertical de fachada entre za y zb (zb=None: hasta la cubierta)."""
    n = max(1, int(arc_len(t0, t1, d, 8) / 3.0) + 1)
    prev = None
    for j in range(n + 1):
        t = t0 + (t1 - t0) * j / n
        top = z_roof(d, t) - 0.3 if zb is None else zb
        x, y = se(t, d)
        cur = (bm.verts.new((x, y, za)), bm.verts.new((x, y, top)))
        if prev:
            bm.faces.new((prev[0], cur[0], cur[1], prev[1])).material_index = mat
        prev = cur


def build_facade(M, coll):
    z_l1 = STATS['Z_L1']
    holes = []
    for e in ENTRIES:
        sp = speed(e, FACADE_D)
        for a, b in ((-24.5, -8.5), (8.5, 24.5)):                 # puertas principales
            holes.append((e + a / sp, e + b / sp, [(Z_L0, Z_L0 + 4.0)]))
        holes.append((e - 2.4 / sp, e + 2.4 / sp, [(z, z + 3.2) for z in (Z_L05, z_l1, Z_L2)]))  # puentes
    for c in CORES:                                               # salidas de emergencia
        sp = speed(c, FACADE_D)
        holes.append((c - 3.0 / sp, c + 3.0 / sp, [(Z_L0, Z_L0 + 3.0)]))
    holes.sort()
    bm, bm_f = bmesh.new(), bmesh.new()    # doble piel de vidrio acústico con vanos
    for dd in (FACADE_D, FACADE_D - 1.2):
        prev_end = holes[-1][1] - 2 * math.pi
        for (h0, h1, zs) in holes:
            if h0 > prev_end:
                facade_strip(bm, prev_end, h0, dd, Z_L0, None)
            zc = Z_L0
            for (za, zb) in zs:
                if za > zc:
                    facade_strip(bm, h0, h1, dd, zc, za)
                zc = zb
            facade_strip(bm, h0, h1, dd, zc, None)
            prev_end = h1
    for (h0, h1, zs) in holes:                                    # marcos de puerta
        tc, w = (h0 + h1) / 2, arc_len(h0, h1, FACADE_D)
        for (za, zb) in zs:
            add_rbox(bm_f, tc, FACADE_D - 0.6, zb, w + 0.6, 1.6, 0.35, 0)
            for tt in (h0, h1):
                add_rbox(bm_f, tt, FACADE_D - 0.6, za, 0.3, 1.6, zb - za, 0)
    finish("Fachada_Doble_Piel_Vidrio", bm, [M['vidrio']], coll, recalc=False)
    finish("Fachada_Marcos_Puertas", bm_f, [M['acero']], coll)

    bm = bmesh.new()
    NF = 330
    tree_ts = [2 * math.pi * k / N_TREES for k in range(N_TREES)]
    for k in range(NF):
        t = 2 * math.pi * k / NF
        if near_entry(t, FIN_D, 24.0) or any(ang_dist(t, tt) * r_eff(FIN_D) < 3.0 for tt in tree_ts):
            continue
        n, tan = outward(t, FIN_D)
        phi = 0.75 * math.sin(5 * t)
        ax = n * math.cos(phi) + tan * math.sin(phi)
        ay = tan * math.cos(phi) - n * math.sin(phi)
        depth = 1.6 + 0.9 * (0.5 + 0.5 * math.sin(8 * t))
        ztop = z_roof(FIN_D, t) - 1.0
        x, y = se(t, FIN_D)
        add_obox(bm, (x, y, (Z_L0 + ztop) / 2), ax, ay, Vector((0, 0, 1)),
                 depth / 2, 0.18, (ztop - Z_L0) / 2, 1 if k % 3 == 0 else 0)
    finish("Aletas_Parametricas", bm, [M['madera'], M['jardin_v']], coll)

    bm = bmesh.new()   # marquesinas de acceso (puertas a ambos lados de la torre)
    for e in ENTRIES:
        add_rbox(bm, e, FACADE_D + 8.0, 7.5, 46.0, 16.0, 0.6, 0)
        n, tan = outward(e, FACADE_D + 14.5)
        for s in (-1, 1):
            c = P(e, FACADE_D + 14.5, 0) + tan * (s * 21.0)
            add_cyl(bm, c, c + Vector((0, 0, 7.5)), 0.45, 0.45, 0, sides=8)
    finish("Marquesinas_Acceso", bm, [M['acero']], coll)


# ==========================================================================
# 6. PLAZA SAKBÉ: anillo comercial con parque en la azotea
# ==========================================================================
def ring_segments():
    """8 tramos separados por brechas alineadas con los accesos del estadio."""
    segs = []
    dm = (CANYON_IN + CANYON_OUT) / 2
    for k in range(8):
        g0, g1 = ENTRIES[k], ENTRIES[(k + 1) % 8] + (2 * math.pi if k == 7 else 0)
        ta = g0 + dt_w(GAP_W, g0, dm) / 2
        tb = g1 - dt_w(GAP_W, g1, dm) / 2
        tm = (g0 + g1) / 2
        hp = dt_w(PORTAL_W, tm, dm) / 2
        w1 = tm - (tm - ta) * 0.5
        w2 = tm + (tb - tm) * 0.5
        hw = dt_w(WIN_W, w1, dm) / 2
        pieces = [(ta, w1 - hw, 'full'), (w1 - hw, w1 + hw, 'window'), (w1 + hw, tm - hp, 'full'),
                  (tm - hp, tm + hp, 'portal'), (tm + hp, w2 - hw, 'full'),
                  (w2 - hw, w2 + hw, 'window'), (w2 + hw, tb, 'full')]
        segs.append(dict(ta=ta, tb=tb, tm=tm, pieces=pieces))
    return segs


PROGRAM = {0: 'tiendas', 1: 'tiendas', 2: 'tiendas', 3: 'comida', 4: 'comida', 5: 'cine',
           6: 'deporte', 7: 'salud', 8: 'oficina', 9: 'oficina'}
PROGRAM_TXT = {'tiendas': "Tiendas", 'comida': "Restaurantes y terrazas", 'cine': "Cines",
               'deporte': "Gimnasio y centro deportivo", 'salud': "Clínica, guardería y museo del deporte",
               'oficina': "Oficinas y coworking"}


def end_wall(bm, t, d0, d1, z0, z1, mat):
    v = [bm.verts.new((*se(t, d), z)) for d, z in ((d0, z0), (d1, z0), (d1, z1), (d0, z1))]
    bm.faces.new(v).material_index = mat


def ring_core_positions(sg):
    """Núcleos (escaleras protegidas + elevadores) cada ~60 m, fuera de portales y ventanas."""
    out = []
    for (d0, d1) in ((RING_IN, CANYON_IN), (CANYON_OUT, RING_OUT)):
        L = arc_len(sg['ta'], sg['tb'], (d0 + d1) / 2)
        n = max(2, round(L / 60))
        for i in range(n):
            t = sg['ta'] + (sg['tb'] - sg['ta']) * (i + 0.5) / n
            for (p0, p1, kd) in sg['pieces']:
                if kd != 'full' and p0 - dt_w(6, t, d0) < t < p1 + dt_w(6, t, d0):
                    t = p1 + dt_w(8, t, d0)
            out.append((t, d0, d1))
    return out


def build_ring(M, coll, coll_night):
    """Plaza Sakbé: anillo hueco con pisos, fachadas, programa por nivel y circulación vertical."""
    prog_keys = ['tiendas', 'comida', 'cine', 'deporte', 'salud', 'oficina']
    prog_mats = M['tiendas'] + [m for k in prog_keys[1:] for m in M['programa'][k]]
    prog_idx = {'tiendas': list(range(6))}
    off = 6
    for k in prog_keys[1:]:
        prog_idx[k] = list(range(off, off + len(M['programa'][k])))
        off += len(M['programa'][k])
    base = [M['espejo'], M['vidrio'], M['parque'], M['sofito'], M['losa'], M['madera'], M['luz_int'],
            M['tunel'], M['escape']]
    MIR, GLS, PARK, SOF, LOSA, WOOD, LUZ, DOOR, CORE = range(9)
    mats = base + prog_mats
    P0 = len(base)

    segs = ring_segments()
    STATS['anillo_segmentos'] = segs
    gfa = 0.0
    bm = bmesh.new()      # estructura y fachadas
    bm_p = bmesh.new()    # programa interior
    bm_e = bmesh.new()    # núcleos
    cores = 0
    slabs = [(RING_IN, CANYON_IN, 'fachada_estadio', RING_IN), (CANYON_OUT, RING_OUT, 'fachada_exterior', RING_OUT)]
    for sg in segs:
        core_pos = ring_core_positions(sg)
        for (t, d0, d1) in core_pos:
            add_rbox(bm_e, t, (d0 + d1) / 2, Z_P2, 10.0, 9.0, RING_H - 0.2 - Z_P2, CORE)
            add_rbox(bm_e, t, (d0 + d1) / 2, RING_H, 10.0, 9.0, 3.5, GLS)
            for f in range(int(RING_H / FLOOR_H)):
                zf = f * FLOOR_H
                n_, tan_ = outward(t, (d0 + d1) / 2)
                for sgn in (-1, 1):                      # puertas a cada piso (dos caras del núcleo)
                    add_obox(bm_e, P(t, (d0 + d1) / 2, zf + 1.2) + tan_ * (sgn * 5.05), tan_, n_,
                             Vector((0, 0, 1)), 0.1, 0.9, 1.15, DOOR)
            cores += 1
        for (ta, tb, kind) in sg['pieces']:
            for (d0, d1, tally_out, face_out) in slabs:
                face_can = CANYON_IN if d1 == CANYON_IN else CANYON_OUT
                if kind == 'full':
                    blocks = [(0.0, RING_H)]
                elif kind == 'portal':
                    blocks = [(PORTAL_H, RING_H)]
                else:
                    blocks = [(0.0, WIN_Z[0]), (WIN_Z[1], RING_H)]
                Lm = arc_len(ta, tb, (d0 + d1) / 2)
                for (z0, z1) in blocks:
                    gfa += Lm * (d1 - d0) * round((z1 - z0) / FLOOR_H)
                    # losas de entrepiso (la primera, si está en el aire, con plafón de madera)
                    for f in range(int(round((z1 - z0) / FLOOR_H))):
                        zf = z0 + f * FLOOR_H
                        arc_block(bm, ta, tb, d0 + 0.1, d1 - 0.1, zf - 0.35, zf,
                                  (SOF if (f == 0 and z0 > 0) else LOSA, LOSA, LOSA, LOSA, LOSA, LOSA))
                    # losa de azotea / terraza (parque)
                    arc_block(bm, ta, tb, d0 + 0.1, d1 - 0.1, z1 - 0.6, z1, (LOSA, LOSA, PARK, LOSA, LOSA, LOSA))
                    if z1 == RING_H:
                        AREAS['azotea'] = AREAS.get('azotea', 0.0) + Lm * (d1 - d0)
                    # fachadas: vidrio espejo hacia el estadio y la calle, vidrio claro hacia el cañón
                    arc_strip(bm, ta, tb, face_out, z0, z1, MIR, step=4.0)
                    arc_strip(bm, ta, tb, face_can, z0, z1, GLS, step=4.0)
                    AREAS[tally_out] = AREAS.get(tally_out, 0.0) + arc_len(ta, tb, face_out) * (z1 - z0)
                    AREAS['fachada_canon'] = AREAS.get('fachada_canon', 0.0) + arc_len(ta, tb, face_can) * (z1 - z0)
                    for tt in (ta, tb):                  # muros de cabecera
                        at_gap = abs(tt - sg['ta']) < 1e-9 or abs(tt - sg['tb']) < 1e-9
                        end_wall(bm, tt, d0, d1, z0, z1, MIR if at_gap else WOOD)
                    # programa: dos crujías de locales y pasillo central con luminaria
                    for f in range(int(round((z1 - z0) / FLOOR_H))):
                        zf = z0 + f * FLOOR_H
                        lvl = int(round(zf / FLOOR_H))
                        prog = PROGRAM[lvl]
                        mod = 22.0 if prog == 'cine' else 11.0
                        n_mod = max(1, int(Lm // mod))
                        for m_i in range(n_mod):
                            tm0 = ta + (tb - ta) * m_i / n_mod
                            tm1 = ta + (tb - ta) * (m_i + 1) / n_mod
                            tc = (tm0 + tm1) / 2
                            if any(ang_dist(tc, ct) < dt_w(9.0, tc, cd0) for (ct, cd0, cd1) in core_pos
                                   if cd0 == d0):
                                continue
                            g = dt_w(0.6, tc, d0) / 2
                            for (a, b, front) in ((d0 + 0.6, d0 + 6.0, 1), (d1 - 6.0, d1 - 0.6, 3)):
                                mi = P0 + random.choice(prog_idx[prog])
                                fm = [mi] * 6
                                fm[front] = GLS                 # aparador de vidrio hacia el pasillo
                                arc_block(bm_p, tm0 + g, tm1 - g, a, b, zf, zf + 3.5, tuple(fm), n=2)
                        for dl in (-1.4, 1.4):
                            arc_block(bm, ta, tb, (d0 + d1) / 2 + dl - 0.5, (d0 + d1) / 2 + dl + 0.5,
                                      zf + FLOOR_H - 0.5, zf + FLOOR_H - 0.42, (LUZ,) * 6)
    finish("Plaza_Sakbe_Estructura_y_Fachadas", bm, mats, coll, recalc=False)
    finish("Plaza_Sakbe_Locales_y_Programa", bm_p, mats, coll)
    finish("Plaza_Sakbe_Nucleos_Escaleras_y_Elevadores", bm_e, mats, coll)
    STATS['anillo_gfa'] = gfa
    STATS['anillo_nucleos'] = cores

    # cañón: balcones-pasillo en cada piso, escaleras eléctricas, elevadores panorámicos, puentes
    bm = bmesh.new()
    esc = 0
    for sg in segs:
        ta, tb = sg['ta'], sg['tb']
        for (pa, pb, kind) in sg['pieces']:
            for f in range(1, int(RING_H / FLOOR_H)):
                z = f * FLOOR_H
                if kind == 'portal' and z < PORTAL_H:
                    continue
                if kind == 'window' and WIN_Z[0] < z < WIN_Z[1]:
                    continue
                for (a, b, rail) in ((CANYON_IN, CANYON_IN + 1.8, CANYON_IN + 1.8),
                                     (CANYON_OUT - 1.8, CANYON_OUT, CANYON_OUT - 1.8)):
                    arc_block(bm, pa, pb, a, b, z - 0.3, z, (0,) * 6)
                    arc_strip(bm, pa, pb, rail, z, z + 1.1, 3, step=6.0)
                    if f % 2 == 0:
                        pc = rail - 0.35 if a == CANYON_IN else rail + 0.35
                        arc_block(bm, pa, pb, pc - 0.25, pc + 0.25, z, z + 0.6, (2,) * 6)
        # escaleras eléctricas en zigzag de planta baja a la azotea (una cadena por torre)
        for fpos, dlin, dirn in ((0.36, CANYON_IN + 2.7, 1), (0.64, CANYON_OUT - 2.7, -1)):
            t_s = ta + (tb - ta) * fpos
            run = FLOOR_H / math.tan(math.radians(30))
            sp = speed(t_s, dlin)
            for fl in range(int(RING_H / FLOOR_H)):
                za, zb = fl * FLOOR_H, (fl + 1) * FLOOR_H
                o0 = 0.0 if fl % 2 == 0 else run
                o1 = run if fl % 2 == 0 else 0.0
                for lane in (0.0, 1.8 * dirn):
                    a = P(t_s + o0 / sp, dlin + lane, za)
                    b = P(t_s + o1 / sp, dlin + lane, zb)
                    n_, tan_ = outward(t_s, dlin)
                    ax = (b - a).normalized()
                    az = ax.cross(n_)
                    if az.z < 0:
                        az = -az
                    add_obox(bm, (a + b) / 2 + az * 0.5, ax, n_, az, (b - a).length / 2, 0.75, 0.5, 5)
                    esc += 1
                edge = CANYON_IN + 1.8 if dirn > 0 else CANYON_OUT - 1.8
                far = dlin + 2.55 * dirn
                for oo, zz in ((o0, za), (o1, zb)):    # descansos que conectan con el balcón
                    if zz <= 0:
                        continue
                    add_rbox(bm, t_s + oo / sp, (edge + far) / 2, zz - 0.3, 3.2, abs(far - edge), 0.3, 0)
        for f, z in ((0.22, 13.5), (0.42, 27.0), (0.62, 13.5), (0.82, 27.0)):     # puentes entre torres
            t = ta + (tb - ta) * f
            h = dt_w(4.0, t, 183) / 2
            arc_block(bm, t - h, t + h, CANYON_IN, CANYON_OUT, z - 0.6, z, (0,) * 6)
        for f in (0.33, 0.7):                                                # puentes-parque arriba
            t = ta + (tb - ta) * f
            h = dt_w(10.0, t, 183) / 2
            arc_block(bm, t - h, t + h, CANYON_IN, CANYON_OUT, RING_H - 1.0, RING_H, (0, 0, 2, 0, 0, 0))
        for f in (0.08, 0.92):                                               # elevadores panorámicos
            t = ta + (tb - ta) * f
            c = P(t, 183.0, 0)
            add_cyl(bm, (c.x, c.y, Z_P2), (c.x, c.y, RING_H + 3), 1.8, 1.8, 3, sides=16)
            add_box(bm, (c.x, c.y, random.uniform(5, 40)), (1.6, 1.6, 2.6), 4)
            for fl in range(int(RING_H / FLOOR_H) + 1):
                z = fl * FLOOR_H
                h = dt_w(2.4, t, 183) / 2
                arc_block(bm, t - h, t + h, CANYON_IN + 1.8, 181.2, z - 0.3, z, (0,) * 6)
                arc_block(bm, t - h, t + h, 184.8, CANYON_OUT - 1.8, z - 0.3, z, (0,) * 6)
    finish("Canon_Balcones_Escaleras_Elevadores_Puentes", bm,
           [M['acero'], M['madera'], M['parque'], M['vidrio'], M['acento'], M['esc_elec']], coll)
    STATS['anillo_escaleras_electricas'] = esc
    STATS['anillo_elevadores_panoramicos'] = 16

    # azotea: pista de trote, sendero, barandales de vidrio, pérgolas solares, puentes sobre brechas
    bm = bmesh.new()
    pv = 0.0
    for k, sg in enumerate(segs):
        ta, tb = sg['ta'], sg['tb']
        nxt = segs[(k + 1) % 8]['ta'] + (2 * math.pi if k == 7 else 0)
        arc_block(bm, ta, tb, 195.5, 199.5, RING_H, RING_H + 0.05, (1,) * 6)
        arc_block(bm, ta, tb, 166.5, 169.5, RING_H, RING_H + 0.04, (2,) * 6)
        for dd in (RING_IN + 0.2, CANYON_IN - 0.2, CANYON_OUT + 0.2, RING_OUT - 0.2):
            arc_block(bm, ta, tb, dd - 0.03, dd + 0.03, RING_H, RING_H + 1.2, (0,) * 6)
        L = arc_len(ta, tb, 202.5)
        for i in range(int(L // 14)):
            t = ta + (tb - ta) * (i + 0.5) / int(L // 14)
            add_rbox(bm, t, 202.5, RING_H + 3.0, 10.0, 5.0, 0.15, 3)
            add_rbox(bm, t, 202.5, RING_H, 0.3, 0.3, 3.0, 4)
            pv += 50.0
        for (d0, d1) in ((RING_IN + 5, RING_IN + 11), (194.0, 202.0)):  # puentes sobre la brecha
            arc_block(bm, tb, nxt, d0, d1, RING_H - 0.8, RING_H, (4, 4, 2, 4, 4, 4))
            for dd in (d0, d1):
                arc_block(bm, tb, nxt, dd - 0.03, dd + 0.03, RING_H, RING_H + 1.2, (0,) * 6)
    finish("Parque_Azotea_Detalles", bm, [M['vidrio'], M['pista'], M['piedra'], M['solar'],
                                          M['acero']], coll)
    STATS['pergolas_pv'] = pv

    # cascada desde el parque hacia el estanque de la plaza interior
    bm = bmesh.new()
    tc = -math.pi / 2 + 0.16
    h = dt_w(14.0, tc, RING_IN) / 2
    sweep(bm, lambda t: [(RING_IN - 0.8, 0.4), (RING_IN - 0.8, RING_H)], 8, lambda i, j: 0,
          closed=False, t0=tc - h, t1=tc + h)
    finish("Cascada_Anillo", bm, [M['cascada']], coll, recalc=False)
    STATS['cascada_t'] = tc

    # noche: líneas de luz por piso (fachadas exteriores y cañón)
    bm = bmesh.new()
    for sg in segs:
        for (pa, pb, kind) in sg['pieces']:
            for f in range(1, int(RING_H / FLOOR_H)):
                z = f * FLOOR_H
                if kind == 'portal' and z < PORTAL_H:
                    continue
                if kind == 'window' and WIN_Z[0] - 0.5 <= z <= WIN_Z[1] + 0.5:
                    continue
                arc_strip(bm, pa, pb, RING_OUT + 0.05, z, z + 0.18, 1)
                arc_strip(bm, pa, pb, RING_IN - 0.05, z, z + 0.18, 1)
                arc_strip(bm, pa, pb, CANYON_IN + 0.05, z + 0.5, z + 3.2, 0)
                arc_strip(bm, pa, pb, CANYON_OUT - 0.05, z + 0.5, z + 3.2, 0)
    finish("Noche_Luz_Pisos_Anillo", bm, [M['luz_calida'], M['luz_fria']], coll_night, recalc=False)


# ==========================================================================
# 7. PLAZA INTERIOR, CAÑÓN Y EXPLANADA
# ==========================================================================
def in_ring_gap(t):
    for sg in STATS['anillo_segmentos']:
        ta, tb = sg['ta'], sg['tb']
        tt = t
        while tt < ta:
            tt += 2 * math.pi
        if tt <= tb:
            return False
    return True


def plaza_path(t, d):
    if near_entry(t, d, 9.0):
        return 'path'
    if any(ang_dist(t, math.pi / 4 * k) * r_eff(d) < 8.0 for k in range(8)):
        return 'path'
    if 140.0 < d < 146.0:
        return 'fire'
    return None


def build_ground(M, coll, coll_water):
    S = 288
    ds = [FACADE_D - 0.1] + [100.0 + 4.0 * i for i in range(16)] + [RING_IN]
    rnd = {}

    def mat_fn(i, j):
        t = 2 * math.pi * (j + 0.5) / S
        d = (ds[i] + ds[i + 1]) / 2
        p = plaza_path(t, d)
        if p == 'path':
            return 0
        if p == 'fire':
            return 5
        key = (i // 2, j // 5)
        if key not in rnd:
            r = random.random()
            rnd[key] = 1 if r < 0.45 else 2 if r < 0.62 else 3 if r < 0.70 else 4 if r < 0.76 else 0
        return rnd[key]

    bm = bmesh.new()
    sweep(bm, lambda t: [(d, 0.0) for d in ds], S, mat_fn, closed=False)
    finish("Plaza_Interior_Jardines", bm,
           [M['plaza'], M['pasto'], M['seto'], M['lavanda'], M['flor_am'], M['bomberos']], coll, recalc=False)

    bm = bmesh.new()   # piso de brechas y cañón
    for sg in STATS['anillo_segmentos']:
        sweep(bm, lambda t: [(CANYON_IN, 0.02), (182.2, 0.02)], 40, lambda i, j: 1, closed=False,
              t0=sg['ta'], t1=sg['tb'])
        sweep(bm, lambda t: [(182.2, 0.02), (183.8, 0.02)], 40, lambda i, j: 2, closed=False,
              t0=sg['ta'], t1=sg['tb'])
        sweep(bm, lambda t: [(183.8, 0.02), (CANYON_OUT, 0.02)], 40, lambda i, j: 1, closed=False,
              t0=sg['ta'], t1=sg['tb'])
    segs = STATS['anillo_segmentos']
    for k, sg in enumerate(segs):
        nxt = segs[(k + 1) % 8]['ta'] + (2 * math.pi if k == 7 else 0)
        sweep(bm, lambda t: [(RING_IN, 0.0), (RING_OUT, 0.0)], 8, lambda i, j: 0, closed=False,
              t0=sg['tb'], t1=nxt)
    finish("Piso_Brechas_y_Canon", bm, [M['plaza'], M['pasto'], M['agua']], coll, recalc=False)

    # estanque bajo la cascada
    bm = bmesh.new()
    tc = STATS['cascada_t']
    c = se(tc, 147.0)
    add_disc(bm, c, 22.0, 9.0, 0.05, 0, 48)
    finish("Estanque_Cascada", bm, [M['agua']], coll_water, recalc=False)

    bm = bmesh.new()   # explanada peatonal (zona de salida y puntos de reunión)
    sweep(bm, lambda t: [(RING_OUT, 0.01), (EXPLANADA_OUT, 0.01)], S, lambda i, j: 0, closed=False)
    finish("Explanada_Perimetral", bm, [M['plaza']], coll, recalc=False)

    bm = bmesh.new()   # terreno neutro (la ciudad no se modela)
    sweep(bm, lambda t: [(EXPLANADA_OUT, -0.02), (3000.0, -0.02)], 96, lambda i, j: 0, closed=False)
    finish("Terreno_Neutro", bm, [M['terreno']], coll, recalc=False)




def build_underground(M, coll, coll_src):
    """P1 (-6): autos.  P2 (-12): autobuses, bicis, energía, cisternas, servicio."""
    bm = bmesh.new()
    sweep(bm, lambda t: [(40.0, Z_P1 - 0.4), (RING_OUT, Z_P1 - 0.4), (RING_OUT, Z_P1), (40.0, Z_P1)],
          SEG, lambda i, j: 0)
    sweep(bm, lambda t: [(38.0, Z_P2 - 0.5), (RING_OUT, Z_P2 - 0.5), (RING_OUT, Z_P2), (38.0, Z_P2)],
          SEG, lambda i, j: 0)
    sweep(bm, lambda t: [(RING_OUT + 0.6, Z_P2 - 0.5), (RING_OUT + 0.6, 0.0)], SEG, lambda i, j: 0, closed=False)
    for d in [104.0 + 8.4 * i for i in range(12)]:
        nn = int(perim(d, 360) / 8.4)
        for k in range(nn):
            t = 2 * math.pi * k / nn
            add_cyl(bm, P(t, d, Z_P2), P(t, d, Z_L0), 0.4, 0.4, 0, sides=4, caps=False)
    finish("Estacionamiento_Losas_y_Columnas", bm, [M['estac']], coll)

    # cajones (cuenta) y autos
    rows = [103.5, 115.0, 120.0, 131.5, 136.5, 148.0, 153.0, 164.5, 169.5, 181.0, 186.0, 197.5, 202.5]
    cars = {i: [] for i in range(5)}
    stalls = 0
    for d in rows:
        pts, _ = walk_points(d, 2.5, 2400)
        for (t, x, y, nx, ny) in pts:
            if any(ang_dist(t, a) * r_eff(d) < 9 for a in (0.0, math.pi, math.pi / 2, -math.pi / 2)):   # llegada de rampas
                continue
            stalls += 1
            if random.random() < 0.55:
                cars[random.randrange(5)].append(((x, y, Z_P1), math.atan2(ny, nx)))
    stalls = int(stalls * 0.9)
    for c in range(5):
        src = make_source(f"Fuente_Auto_{c}", car_mesh, [M['autos'][c], M['tren_vent']], coll_src)
        make_instancer(f"Autos_P1_{c}", cars[c], src, coll)
    STATS['cajones'] = stalls
    STATS['cajones_accesibles'] = int(math.ceil(stalls * 0.03))

    bm = bmesh.new()   # P2: cisternas, centro de energía, autobuses, bicis
    for k in range(10):
        t = -math.pi / 2 - 0.35 + k * 0.07
        c = P(t, 150.0, 0)
        add_cyl(bm, (c.x, c.y, Z_P2), (c.x, c.y, Z_P2 + 5.2), 7.0, 7.0, 0, sides=20)
    for k in range(8):
        add_rbox(bm, 0.25 + k * 0.035, 160.0, Z_P2, 12.0, 3.0, 3.0, 1)
    for k in range(3):
        c = P(0.25 + k * 0.08, 130.0, 0)
        add_cyl(bm, (c.x, c.y, Z_P2), (c.x, c.y, Z_P2 + 5.5), 5.0, 5.0, 1, sides=20)
    for k in range(10):
        add_rbox(bm, math.pi / 2 - 0.25 + k * 0.05, 120.0, Z_P2, 3.0, 12.5, 3.4, 2)
    for k in range(14):
        add_rbox(bm, math.pi + 0.3 + k * 0.03, 140.0, Z_P2, 8.0, 20.0, 1.2, 3)
    finish("Subterraneo_Servicios", bm, [M['cisterna'], M['energia'], M['bus'], M['acero'], M['tunel']], coll)
    STATS['cisternas_m3'] = 10 * math.pi * 7.0 ** 2 * 5.0


# ==========================================================================
# 8. EVACUACIÓN
# ==========================================================================
def chevron(bm, t, d, z, mat, size=2.2):
    n, tan = outward(t, d)
    c = P(t, d, z)
    tip = c + n * size
    l = c - n * size * 0.2 + tan * size * 0.9
    r = c - n * size * 0.2 - tan * size * 0.9
    m = c + n * size * 0.35
    for tri in ((tip, l, m), (tip, m, r)):
        bm.faces.new([bm.verts.new(v) for v in tri]).material_index = mat


def build_evacuation(M, coll):
    bm = bmesh.new()
    for e in ENTRIES:                       # plaza interior -> brecha -> punto de reunión
        d = 116.0
        while d < EXPLANADA_OUT - 12:
            chevron(bm, e, d, 0.08 if d < RING_OUT else 0.1, 0)
            d += 9.0
    for k in range(8):                      # portales
        t = math.pi / 4 * k
        d = 116.0
        while d < EXPLANADA_OUT - 12:
            chevron(bm, t, d, 0.08, 0, 1.8)
            d += 11.0
    for t in ENTRIES + CORES:               # vestíbulo L0 hacia puertas
        d = 44.0
        while d < 94.0:
            chevron(bm, t, d, Z_L0 + 0.05, 0, 1.6)
            d += 8.0
    for z in (Z_L05, STATS['Z_L1'], Z_L2):  # vestíbulos altos hacia torres
        for e in ENTRIES:
            for d in (74.0, 82.0, 90.0):
                if z == Z_L2 and d < STATS['d_L2']:
                    continue
                chevron(bm, e, d, z + 0.05, 0, 1.6)
    for e in ENTRIES:                       # puntos de reunión
        c = se(e, EXPLANADA_OUT - 7)
        add_ring(bm, c, 5.5, 6.5, 0.06, 1, 40)
    finish("Rutas_Evacuacion_y_Puntos_Reunion", bm, [M['evac'], M['reunion']], coll, recalc=False)
    STATS['explanada_m2'] = AREAS_ring(RING_OUT, EXPLANADA_OUT)


# ==========================================================================
# 9. VEGETACIÓN
# ==========================================================================
def build_vegetation(M, coll, coll_src):
    """Árboles como instancias de 11 modelos (con giro y escala al azar): pesa ~1 % que antes."""
    buckets = {}
    count = 0

    def tree(x, y, z, kind, scale=1.0):
        if kind == 'cipres':
            key = 'cipres'
        else:
            leaf = random.choice((0, 0, 1, 2, 4)) if random.random() > 0.08 else 3
            key = f'copa_{leaf}_{random.randrange(2)}'
        buckets.setdefault(key, []).append((((x, y, z), random.uniform(0, 2 * math.pi)),
                                            scale * random.uniform(0.8, 1.25)))

    tc = STATS['cascada_t']
    for _ in range(900):                    # plaza interior
        t = random.uniform(0, 2 * math.pi)
        d = random.uniform(118.0, RING_IN - 5)
        if plaza_path(t, d) or plaza_path(t, d + 3) or plaza_path(t, d - 3):
            continue
        if ang_dist(t, tc) * r_eff(d) < 30 and d > 132:
            continue
        x, y = se(t, d)
        tree(x, y, 0.0, random.choice(('copa', 'copa', 'cipres')))
        count += 1
    for sg in STATS['anillo_segmentos']:    # parque en la azotea y cañón
        for _ in range(90):
            t = random.uniform(sg['ta'] + 0.01, sg['tb'] - 0.01)
            band = random.choice(((RING_IN + 2.5, 165.5), (170.5, CANYON_IN - 2.5), (CANYON_OUT + 2.5, 194.5)))
            d = random.uniform(*band)
            x, y = se(t, d)
            if math.dist((x, y), se(MIRADOR_T, 163.0)) < 32:
                continue
            tree(x, y, RING_H, random.choice(('copa', 'copa', 'cipres')), 0.75)
            count += 1
        for _ in range(16):
            t = random.uniform(sg['ta'] + 0.01, sg['tb'] - 0.01)
            d = random.choice((random.uniform(178.0, 181.5), random.uniform(184.5, 188.0)))
            x, y = se(t, d)
            if math.dist((x, y), se(0.95, 183)) < 45:
                continue
            tree(x, y, 0.0, 'copa', 0.7)
            count += 1
    for key, rows in sorted(buckets.items()):
        if key == 'cipres':
            def build(bm):
                add_cyl(bm, (0, 0, 0), (0, 0, 2), 0.3, 0.25, 0, sides=6, caps=False)
                add_blob(bm, (0, 0, 6), 1.5, 1.5, 5.0, 1, segs=6)
            mats = [M['corteza'], M['hoja'][0]]
        else:
            leaf = int(key.split('_')[1])
            def build(bm):
                add_cyl(bm, (0, 0, 0), (0, 0, 4.2), 0.45, 0.3, 0, sides=6, caps=False)
                add_blob(bm, (0, 0, 6.5), 3.8, 3.8, 3.0, 1)
            mats = [M['corteza'], M['hoja'][leaf]]
        src = make_source(f"Fuente_Arbol_{key}", build, mats, coll_src)
        make_instancer(f"Arboles_{key}", [r[0] for r in rows], src, coll, [r[1] for r in rows])
    STATS['arboles'] = count


# ==========================================================================
# 10. ETIQUETAS, CÁMARAS, LUZ, ESCENA DE NOCHE
# ==========================================================================
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
    ob = bpy.data.objects.new("Etiqueta_" + text[:28], cu)
    ob.location = loc
    ob.data.materials.append(M['texto'])
    con = ob.constraints.new('TRACK_TO')
    con.target = cam
    con.track_axis = 'TRACK_Z'
    con.up_axis = 'UP_Y'
    ob.hide_render = True
    coll.objects.link(ob)


def set_engine(sc):
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


def world_day(sc):
    world = bpy.data.worlds.new("Mundo_Dia")
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
    sun = bpy.data.lights.new("Sol", 'SUN')
    sun.energy = 3.2
    sun.angle = math.radians(1.5)
    sun.color = (1.0, 0.95, 0.88)
    ob = bpy.data.objects.new("Sol", sun)
    ob.rotation_euler = (math.radians(58), 0, math.radians(125))
    sc.collection.objects.link(ob)


def build_night(M, coll_night, colls_all, cam_night):
    """Escena 'Noche': mismas colecciones + luces de partido, fachada, parque."""
    night = bpy.data.scenes.new("Noche")
    for c in colls_all:
        night.collection.children.link(c)
    night.collection.children.link(coll_night)
    set_engine(night)
    night.camera = cam_night
    night.frame_start, night.frame_end, night.frame_current = 1, 120, 120   # techo cerrado
    world = bpy.data.worlds.new("Mundo_Noche")
    night.world = world
    try:
        world.use_nodes = True
    except Exception:
        pass
    bg = next((n for n in world.node_tree.nodes if n.type == 'BACKGROUND'), None)
    if bg:
        bg.inputs[0].default_value = (0.004, 0.008, 0.022, 1)
        bg.inputs[1].default_value = 1.0
    moon = bpy.data.lights.new("Luna", 'SUN')
    moon.energy = 0.08
    moon.color = (0.7, 0.8, 1.0)
    mo = bpy.data.objects.new("Luna", moon)
    mo.rotation_euler = (math.radians(50), 0, math.radians(-40))
    night.collection.objects.link(mo)

    def light(name, kind, loc, energy, color, target=None, size=None, radius=0.3):
        ld = bpy.data.lights.new(name, kind)
        ld.energy = energy
        ld.color = color
        if kind == 'SPOT':
            ld.spot_size = math.radians(size or 30)
            ld.spot_blend = 0.4
        try:
            ld.shadow_soft_size = radius
        except Exception:
            pass
        ob = bpy.data.objects.new(name, ld)
        ob.location = loc
        if target is not None:
            look_at(ob, target)
        coll_night.objects.link(ob)

    for k in range(64):                                     # reflectores del campo (LED)
        t = 2 * math.pi * (k + 0.5) / 64
        tgt = (random.uniform(-50, 50), random.uniform(-32, 32), Z_FIELD)
        light(f"Reflector_{k:02d}", 'SPOT', P(t, 13.0, z_roof(12, t) - 2.2), 22000,
              (1.0, 0.98, 0.95), tgt, 28)
    for k in range(N_TREES):                                # árboles estructurales
        t = 2 * math.pi * k / N_TREES
        light(f"Luz_Arbol_{k:02d}", 'SPOT', P(t, TREE_D + 4, 0.5), 30000, (1.0, 0.78, 0.5),
              P(t, TREE_D - 2, 40), 40)
    for k in range(48):                                     # plaza interior
        t = 2 * math.pi * k / 48
        light(f"Farol_Plaza_{k:02d}", 'POINT', P(t, 130.0, 4.5), 2500, (1.0, 0.82, 0.6))
    for sg in STATS['anillo_segmentos']:                    # parque azotea
        for f in (0.2, 0.5, 0.8):
            light("Farol_Azotea", 'POINT', P(sg['ta'] + (sg['tb'] - sg['ta']) * f, 182.0, RING_H + 4),
                  6000, (1.0, 0.85, 0.65))
    for e in ENTRIES:                                       # torres de circulación
        light("Luz_Torre", 'POINT', P(e, TOWER_D, 18.0), 40000, (1.0, 0.9, 0.75), radius=4)
    for k in range(32):                                     # bajo la cubierta
        t = 2 * math.pi * k / 32
        light("Luz_Cubierta", 'SPOT', P(t, 92.0, 30.0), 40000, (1.0, 0.85, 0.7), P(t, 70.0, 62.0), 60)
    bm = bmesh.new()                                        # anillo de luz bajo el techo retráctil
    sweep(bm, lambda t: [(14.5, z_roof(12, t) - 1.4), (15.5, z_roof(12, t) - 1.4)], SEG,
          lambda i, j: 0, closed=False)
    finish("Noche_Anillo_Luz_Cubierta", bm, [M['luz_fria']], coll_night, recalc=False)
    try:
        night.view_settings.exposure = 0.6
    except Exception:
        pass
    return night


def clear_scene():
    for sc in list(bpy.data.scenes)[1:]:
        bpy.data.scenes.remove(sc)
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob, do_unlink=True)
    for c in list(bpy.data.collections):
        bpy.data.collections.remove(c)
    for coll in (bpy.data.meshes, bpy.data.materials, bpy.data.curves, bpy.data.cameras,
                 bpy.data.lights, bpy.data.node_groups, bpy.data.worlds):
        for b in list(coll):
            if b.users == 0:
                coll.remove(b)
    bpy.context.scene.name = "Dia"


# ==========================================================================
# 11. REVISIÓN DE NORMAS Y CONSUMOS
# ==========================================================================
def checks_and_consumption(tiers):
    S = STATS
    lines = []
    seats = S['butacas']
    wheel = S['sillas_ruedas']
    total = seats + 2 * wheel
    S['aforo_total'] = total
    pt = S['butacas_por_grada']
    lines.append(f"AFORO: {seats:,} butacas + {wheel:,} sillas de ruedas + {wheel:,} acompañantes = {total:,}")
    for i, info in enumerate(tiers):
        sp = info['spec']
        n_ais = SEG // sp['aisle']
        seg_back = perim(info['back']) / SEG
        between = int((sp['aisle'] - 1) * seg_back / SEAT_W)
        lines.append(f"  {sp['name']}: {pt[i]:,} butacas | pendiente máx {info['rake']:.1f}° (≤34°) | "
                     f"C-value mín {info['cmin'] * 1000:.0f} mm (≥60) | {n_ais} pasillos | "
                     f"máx {between} butacas entre pasillos (≤28)")
    ada = 36 + math.ceil((total - 5000) / 200)
    lines.append(f"SANITARIOS: {S['sanitarios_m2']:,.0f} m² ≈ {S['muebles_sanitarios']:,} muebles "
                 f"(≈1 por {total / S['muebles_sanitarios']:.0f} personas)")
    pos = S['modulos']['alimentos'] * 8 + S['kioscos'] * 2
    lines.append(f"ALIMENTOS: {S['modulos']['alimentos']} módulos + {S['kioscos']} kioscos ≈ {pos} cajas "
                 f"(≈1 por {total / pos:.0f} personas)")
    lines.append(f"ACCESIBILIDAD: {wheel:,} lugares silla de ruedas (ADA pide {ada}) | "
                 f"{S['elevadores_estadio']} elevadores estadio | {S['cajones_accesibles']} cajones accesibles")
    # evacuación (Green Guide: 79 p/m/min escaleras, 109 p/m/min plano)
    t1, t2, t3 = tiers
    w1 = SEG // 9 * perim(t1['d0'] + 2) / SEG
    w2 = SEG // 8 * perim(t2['d0'] + 2) / SEG
    vom = t3['spec']['vom']
    n_vom = SEG // vom['every']
    w3 = n_vom * (len(vom['flat']) - 1) * perim(t3['d0'] + 9) / SEG
    e1, e2, e3 = pt[0] / (w1 * 79), pt[1] / (w2 * 79), pt[2] / (w3 * 79)
    stairs_w = 8 * 2 * 3.0 + 16 * 2 * 1.8
    up = pt[1] + pt[2]
    e_down = up / (stairs_w * 79)
    doors = 8 * 2 * 16.0 + 16 * 6.0
    e_doors = total / (doors * 109)
    openings = 8 * GAP_W + 8 * PORTAL_W
    e_ring = total / (openings * 109)
    S['evac'] = dict(e1=e1, e2=e2, e3=e3, down=e_down, doors=e_doors, ring=e_ring,
                     stairs_w=stairs_w, w3=w3, n_vom=n_vom, openings=openings, doors_w=doors)
    lines.append(f"EVACUACIÓN asiento→vestíbulo: G1 {e1:.1f} min, G2 {e2:.1f} min, "
                 f"G3 {e3:.1f} min por {n_vom} vomitorios ({w3:.0f} m)  [meta ≤ 8 min]")
    lines.append(f"  bajada a nivel plaza: {up:,} personas por {stairs_w:.0f} m de escaleras = {e_down:.1f} min")
    lines.append(f"  puertas fachada ({doors:.0f} m): {e_doors:.1f} min | brechas+portales del anillo "
                 f"({openings:.0f} m): {e_ring:.1f} min | explanada de reunión {S['explanada_m2']:,.0f} m² "
                 f"(≈ {S['explanada_m2'] / 0.5:,.0f} personas a 0.5 m²)")

    # consumo (estimado)
    gfa = S['anillo_gfa']
    pv_roof_kwp = S['cubierta_pv'] * PV_KWP_M2
    pv_perg_kwp = S['pergolas_pv'] * PV_KWP_M2
    bipv_kwp = AREAS.get('fachada_exterior', 0) * 0.5 * BIPV_KWP_M2
    gen_stadium = pv_roof_kwp * PV_YIELD / 1e6
    gen_ring = (pv_perg_kwp * PV_YIELD + bipv_kwp * BIPV_YIELD) / 1e6
    stadium = (EVENTS_PER_YEAR * 50.0 + 650 * 8760 / 1000) / 1000           # GWh
    ring = gfa * 115 / 1e6
    parking = (S['cajones'] * 28 * 2) * 12 / 1e6
    water_stadium = EVENTS_PER_YEAR * 1100 + 16000 + 12000
    water_ring = gfa * 0.55
    green = AREAS.get('azotea', 0) + 40000          # azotea + jardines de la plaza interior
    water_parks = green * 0.35
    roof_catch = (S['cubierta_etfe'] + S['cubierta_pv'] + AREAS.get('azotea', 0) * 0.3) * RAIN_M * 0.8
    S['consumo'] = dict(stadium=stadium, ring=ring, parking=parking, gen_stadium=gen_stadium,
                        gen_ring=gen_ring, pv_roof_kwp=pv_roof_kwp, pv_perg_kwp=pv_perg_kwp,
                        bipv_kwp=bipv_kwp, water_stadium=water_stadium, water_ring=water_ring,
                        water_parks=water_parks, rain=roof_catch, gfa=gfa)
    lines.append(f"ANILLO: {gfa:,.0f} m² construidos | {S['anillo_nucleos']} núcleos de circulación | "
                 f"azotea-parque {AREAS.get('azotea', 0):,.0f} m²")
    lines.append(f"ESTACIONAMIENTO: {S['cajones']:,} cajones (P1) + autobuses, bicis y servicios (P2)")
    lines.append(f"ENERGÍA estadio ≈ {stadium:.1f} GWh/año vs solar cubierta {gen_stadium:.1f} GWh/año "
                 f"({pv_roof_kwp / 1000:.1f} MWp)")
    lines.append(f"ENERGÍA anillo ≈ {ring:.1f} GWh/año (+ estac. {parking:.1f}) vs solar pérgolas+fachada "
                 f"{gen_ring:.1f} GWh/año")
    lines.append(f"AGUA estadio ≈ {water_stadium:,.0f} m³/año | anillo ≈ {water_ring:,.0f} m³/año | "
                 f"riego ≈ {water_parks:,.0f} m³/año | lluvia captada ≈ {roof_catch:,.0f} m³/año")
    return lines


# ==========================================================================
# MAIN
# ==========================================================================
def main():
    clear_scene()
    M = build_materials()
    names = [
        ('campo', "01_Campo"), ('modo_f', "02a_Modo_Futbol"), ('modo_a', "02b_Modo_Futbol_Americano"),
        ('modo_r', "02c_Modo_Rugby"), ('modo_c', "02d_Modo_Concierto"), ('modo_ar', "02e_Modo_Arena_Central"),
        ('gradas', "03_Gradas"), ('butacas', "04_Butacas_Individuales"),
        ('vest', "06_Vestibulos_y_Servicios"), ('circ', "07_Circulacion_Vertical"),
        ('jug', "08_Zona_Jugadores_Nivel_Campo"), ('cub', "09_Cubierta_Fija_y_Halo"),
        ('ret', "10_Techo_Retractil_(animado)"), ('arb', "11_Arboles_Estructurales"),
        ('fach', "12_Fachada_y_Accesos"), ('anillo', "13_Plaza_Sakbe"),
        ('suelo', "14_Plaza_Avenida_Suelo"), ('agua', "15_Agua"), ('sub', "16_Subterraneo_Estacionamiento"),
        ('evac', "17_Evacuacion"), ('veg', "18_Vegetacion"),
        ('cams', "19_Camaras"), ('etq', "20_Etiquetas_Info"),
        ('src', "00_Fuentes_Instancias"),
    ]
    C = {k: new_coll(v) for k, v in names}
    coll_night = bpy.data.collections.new("21_Luces_Noche")

    build_field(M, C['campo'])
    mode_colls = dict(futbol=C['modo_f'], americano=C['modo_a'], rugby=C['modo_r'],
                      concierto=C['modo_c'], arena=C['modo_ar'])
    build_modes(M, mode_colls)
    tiers = build_stands(M, C['gradas'])
    build_seating_instances(M, tiers, C['butacas'], C['src'])
    build_concourses(M, tiers, C['vest'])
    build_vertical_circulation(M, tiers, C['circ'])
    build_service_pods(M, C['vest'])
    player_labels = build_players_zone(M, C['jug'])
    build_roof(M, C['cub'])
    build_retractable(M, C['ret'])
    build_structural_trees(M, C['arb'])
    build_facade(M, C['fach'])
    build_ring(M, C['anillo'], coll_night)
    build_ground(M, C['suelo'], C['agua'])
    build_underground(M, C['sub'], C['src'])
    build_evacuation(M, C['evac'])
    build_vegetation(M, C['veg'], C['src'])
    report = checks_and_consumption(tiers)

    for key in ('modo_a', 'modo_r', 'modo_c', 'modo_ar'):
        C[key].hide_viewport = True
        C[key].hide_render = True

    cams = C['cams']
    cam_air = add_camera("CAM_Aerea", (-470, -590, 330), (0, -20, 0), 40, cams)
    e = ENTRIES[5]
    add_camera("CAM_Llegada_Por_Brecha", (*se(e, 228), 1.7), (*se(e, 60), 26), 22, cams)
    add_camera("CAM_Parque_Azotea", (*se(MIRADOR_T, 174), RING_H + 1.7), (*se(MIRADOR_T, 40), 34), 20, cams)
    add_camera("CAM_Canon_Interior", (*se(0.95, 183), 1.7), (*se(1.25, 183), 26), 16, cams)
    add_camera("CAM_Interior_Grada", (-30, -(B + 92), 47), (20, 10, -12), 18, cams)
    add_camera("CAM_Grada_Baja", (*se(-math.pi / 2, 22), -3.6), (0, 10, -10), 20, cams)
    add_camera("CAM_Vestibulo_L0", (*se(ENTRIES[0] - 0.12, 76), 1.7), (*se(ENTRIES[0] + 0.05, 92), 12), 18, cams)
    add_camera("CAM_Torre_Circulacion", (*se(ENTRIES[1], 142), 1.7), (*se(ENTRIES[1], TOWER_D), 17), 24, cams)
    add_camera("CAM_Subterraneo_Rayos_X", (-260, -330, 140), (0, 0, -10), 30, cams)
    add_camera("CAM_Zona_Jugadores", (0, 44, 42), (0, 104, -12), 20, cams)
    tv = VOMS[4]
    add_camera("CAM_Vomitorio_L2", (*se(tv + 0.05, 92.0), Z_L2 + 1.7), (*se(tv, 76.0), Z_L2 + 4.0), 18, cams)
    add_camera("CAM_Techo_Estructura", (60, -300, 175), (0, 0, 58), 30, cams)
    add_camera("CAM_Plaza_Sakbe_Interior", (*se(0.62, 168.0), 2 * FLOOR_H + 1.7), (*se(0.70, 168.0), 2 * FLOOR_H + 1.2), 18, cams)
    add_camera("CAM_Escalera_Electrica_Vestibulo", (*se(ENTRIES[0] + 0.02, 80.0), Z_L05 + 1.7),
               (*se(ENTRIES[0] + 0.10, 90.0), Z_L05 + 6.0), 18, cams)
    cam_night = add_camera("CAM_Noche_Aerea", (-430, -560, 260), (0, 0, 10), 38, cams)
    add_camera("CAM_Noche_Interior", (-30, -(B + 92), 47), (20, 10, -12), 18, cams)

    S = STATS
    lab = C['etq']
    L = [
        (f"ESTADIO YAXCHÉ · {S['aforo_total']:,} personas", (0, 0, 140), 14),
        ("Techo retráctil: 16 hojas ETFE (frame 1 abierto / 120 cerrado)", (0, 0, 92), 6),
        ("Halo LED 360°", (0, 0, 44), 5),
        ("Cubo central + 32 vigas-riel: sostienen y guían las hojas", (0, 30, 80), 5),
        ("Anillo de compresión + 36 armaduras radiales (cubierta fija)", (*se(math.pi * 0.6, 100), 70), 5),
        ("Vomitorio: escalera del pasillo transversal al vestíbulo L2", (*se(VOMS[4], 80), 40), 3.5),
        ("Escaleras eléctricas L0 → L0.5 → L1 → L2 (con huecos en losa)", (*se(ENTRIES[0], 90), 34), 4),
        ("Niveles: 0-2 tiendas · 3-4 restaurantes · 5 cines · 6 deporte · 7 clínica/guardería/museo · 8-9 oficinas",
         (*se(-math.pi / 4 - 0.3, 210), RING_H + 12), 4),
        ("Escaleras eléctricas del cañón: planta baja → parque", (*se(0.6, 183), 50), 4),
        ("Núcleos: escalera protegida + elevadores cada ~60 m", (*se(1.4, 168), 50), 4),
        ("Torres de circulación: escalera de doble hélice + 4 elevadores", (*se(ENTRIES[1], 120), 46), 5),
        ("16 núcleos de escape protegidos", (*se(CORES[3], 83), 50), 4),
        (f"PLAZA SAKBÉ · {S['anillo_gfa'] / 1e3:,.0f} mil m² · parque en la azotea",
         (*se(-math.pi / 4, 183), RING_H + 22), 8),
        ("Cañón verde: terrazas, puentes, elevadores", (*se(0.95, 183), 30), 5),
        ("Brecha 30 m: conexión peatonal y visual", (*se(ENTRIES[5], 183), 12), 5),
        ("Portal peatonal 24 m", (*se(math.pi * 5 / 4, 183), 18), 5),
        ("Ventana urbana (vista al estadio)", (*se(math.pi * 5 / 4 - 0.22, 183), 36), 4),
        ("Cascada + estanque (enfría y enmascara ruido)", (*se(S['cascada_t'], 150), 20), 5),
        ("Punto de reunión (explanada)", (*se(ENTRIES[4], EXPLANADA_OUT - 7), 10), 5),
        ("Carril de bomberos", (*se(1.0, 143), 6), 4),
        (f"Estacionamiento P1 {S['cajones']:,} cajones (-6 m)", (*se(math.pi + 0.4, 150), -2), 6),
        ("P2 (-12 m): autobuses, bicis, energía, cisternas", (*se(-math.pi / 2, 150), -8), 6),
    ]
    for name, loc in player_labels:
        L.append((name, loc, 2.2))
    for text, loc, size in L:
        add_label(text, loc, size, M, lab, cam_air)

    sc = bpy.context.scene
    set_engine(sc)
    sc.camera = cam_air
    world_day(sc)
    main_colls = [C[k] for k, _ in names]
    build_night(M, coll_night, main_colls, cam_night)

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
    for k in ('aforo_total', 'butacas', 'sillas_ruedas', 'cajones'):
        sc[k] = S[k]
    print("=" * 78)
    print("ESTADIO YAXCHÉ + PLAZA SAKBÉ — generado")
    for ln in report:
        print(ln)
    print(f"Árboles: {S['arboles']:,} | "
          f"Módulos de servicio: {S['modulos']}")
    print("=" * 78)


main()
