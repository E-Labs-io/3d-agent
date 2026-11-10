"""MIF4 cradle: mounting box for a Rosendahl MIF4 timecode interface.

Units are millimetres, Z is up. Front and rear (Y faces) stay open for connectors.
Every thread is a captive hex nut that pulls against a 3 mm shoulder.
"""
from build123d import *
from tb.model import part

# Device and fit
DEV = (168.0, 110.0, 44.0)      # MIF4 width, depth, height
FIT = 0.5                        # clearance per side
WALL = 12.0                      # sized for a 3/8" nut (8.73 thick) plus shoulder
SHOULDER = 3.0
TAB = 4.0                        # rear backstop thickness, behind the device

# Unified hex nuts: (across-flats + clearance, thickness, thread clearance dia)
NUT_3_8 = (14.29 + 0.3, 8.73, 10.2)
NUT_1_4 = (11.11 + 0.3, 5.56, 7.0)

cav_x, cav_y, cav_z = DEV[0] + 2 * FIT, DEV[1] + 2 * FIT, DEV[2] + FIT
ext_x = cav_x + 2 * WALL
ext_y = cav_y + TAB               # body runs TAB past the rear of the device
Y0 = TAB / 2                     # body centre in Y; the device stays centred on 0
body_h = WALL + cav_z


def nut_cutter(nut, depth, point_up=False):
    """Hex pocket `depth` deep on +Z from the origin, plus a through hole.

    point_up turns the hexagon so a corner faces local +Y. Used on vertical walls so the
    pocket roof is two 30 degree slopes that print without support, not a flat ceiling.
    """
    af, _, dia = nut
    profile = RegularPolygon(af / 2, 6, major_radius=False, rotation=30 if point_up else 0)
    if point_up:
        # teardrop roof: 45 degree slopes from the top of the vertical flats to an apex
        r = af / 2 / 0.8660254
        profile += Polygon((-af / 2, r / 2), (af / 2, r / 2), (0, r / 2 + af / 2), align=None)
    hexagon = extrude(profile, depth)
    return hexagon + Cylinder(dia / 2, 60, align=(Align.CENTER, Align.CENTER, Align.CENTER))


# --- body: floor plus two side walls --------------------------------------
body = Pos(0, Y0, 0) * Box(ext_x, ext_y, body_h, align=(Align.CENTER, Align.CENTER, Align.MIN))
body -= Pos(0, Y0, WALL) * Box(cav_x, ext_y, cav_z, align=(Align.CENTER, Align.CENTER, Align.MIN))

# wall mounts: one 3/8" between two 1/4", pockets open into the cavity
mount_z = WALL + cav_z / 2
for side in (-1, 1):
    # x_dir flips with the side so local +Y is world +Z on both walls (teardrops point up)
    inner = Plane(origin=(side * cav_x / 2, 0, mount_z), x_dir=(0, side, 0), z_dir=(side, 0, 0))
    body -= inner * nut_cutter(NUT_3_8, WALL - SHOULDER, point_up=True)
    for y in (-30, 30):
        body -= inner * Pos(y, 0, 0) * nut_cutter(NUT_1_4, NUT_1_4[1] + 0.4, point_up=True)

# floor vents
for x in (-52, -26, 0, 26, 52):
    body -= Pos(x, 0, 0) * Box(14, 60, WALL * 3)

# heat-set insert holes (M4, 5.6 dia x 8 deep) in the wall tops for the plate
PLATE_FIX = [(sx * (cav_x / 2 + WALL / 2), sy * 38) for sx in (-1, 1) for sy in (-1, 1)]
for x, y in PLATE_FIX:
    body -= Pos(x, y, body_h) * Cylinder(2.8, 8, align=(Align.CENTER, Align.CENTER, Align.MAX))

# rear backstop tabs, leaving the middle clear for cabling
for sx in (-1, 1):
    body += Pos(sx * 58, cav_y / 2 + TAB / 2, WALL) * Box(26, TAB, 14, align=(Align.CENTER, Align.CENTER, Align.MIN))

body = fillet(body.edges().filter_by(Axis.Y).group_by(Axis.Z)[0], 2)

# --- top plate: spigot mounts, pockets open downward -----------------------
plate = Pos(0, Y0, 0) * Box(ext_x, ext_y, WALL, align=(Align.CENTER, Align.CENTER, Align.MIN))
for x in (-50, 0, 50):
    plate -= Pos(x, 0, 0) * nut_cutter(NUT_3_8, WALL - SHOULDER)
for x in (-70, 70):
    for y in (-32, 32):
        plate -= Pos(x, y, 0) * nut_cutter(NUT_1_4, NUT_1_4[1] + 0.4)
for x, y in PLATE_FIX:
    plate -= Pos(x, y, 0) * Cylinder(2.25, 40)
    # M4 countersunk (90 degree): a cone prints clean face-down, a counterbore roof would not
    plate -= Pos(x, y, WALL) * Cone(2.25, 4.5, 2.25, align=(Align.CENTER, Align.CENTER, Align.MAX))
for x in (-26, 8):
    for y in (-31, 31):
        plate -= Pos(x + 9, y, 0) * Box(18, 22, 40)
plate = Pos(0, 0, body_h) * plate

mif4 = Pos(0, 0, WALL) * Box(*DEV, align=(Align.CENTER, Align.CENTER, Align.MIN))

PARTS = {
    "body": part(body, material="petg", color="#3a3f4a"),
    "top-plate": part(plate, material="petg", color="#cc5500", print_flip=True),
    "mif4": part(mif4, reference=True, color="#6fa8dc", opacity=0.25, process="bought",
                 note="Rosendahl MIF4, 168 x 110 x 44 mm"),
}

HARDWARE = [
    {"name": "Hex nut 3/8\"-16 UNC", "qty": 5, "spec": "ASME B18.2.2, steel, zinc plated", "use": "3 in top plate, 1 per wall"},
    {"name": "Hex nut 1/4\"-20 UNC", "qty": 8, "spec": "ASME B18.2.2, steel, zinc plated", "use": "4 in top plate, 2 per wall"},
    {"name": "Heat-set insert M4", "qty": 4, "spec": "brass, for 5.6 mm hole, 8 mm long", "use": "wall tops"},
    {"name": "Countersunk screw M4 x 16", "qty": 4, "spec": "ISO 10642, A2 stainless", "use": "plate to body"},
]
