"""Linear static stress analysis of a built part (STEP -> tetrahedra -> displacement, stress, safety factor).

Route "skfem": gmsh meshes the STEP in a child process (gmsh is GPL, so it is never imported by
the server), scikit-fem solves 3D linear elasticity with quadratic tetrahedra.
Route "ccx": CalculiX, detected but not implemented yet.

Units: mm, N, MPa, g/cm3. Also registers the hand-calculation tools from tb.mechanics.
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from . import mechanics
from .common import TOOLBOX, load_json, project_dir, save_json, which

CCX_INSTALL = "conda install -c conda-forge calculix   (https://anaconda.org/conda-forge/calculix)"
MAX_DOF = 450_000
AXES = "xyz"
SIDES = {f"{a}{m}": (i, m) for i, a in enumerate(AXES) for m in ("min", "max")}
_VOIGT = [(0, 0), (1, 1), (2, 2), (1, 2), (0, 2), (0, 1)]


class FeaError(Exception):
    pass


# --- meshing (child process) ----------------------------------------------------------------


def _fit_cylinder(gmsh, np, tag):
    """Axis, radius and axial extent of a cylindrical CAD face from sampled points and normals."""
    (u0, v0), (u1, v1) = gmsh.model.getParametrizationBounds(2, tag)
    uv = np.array([[u, v] for u in np.linspace(u0, u1, 9)[:-1] for v in (v0, v1)]).ravel()
    pts = np.array(gmsh.model.getValue(2, tag, uv)).reshape(-1, 3)
    nrm = np.array(gmsh.model.getNormal(tag, uv)).reshape(-1, 3)
    axis = np.linalg.svd(nrm)[2][-1]
    e1 = np.cross(axis, [1.0, 0, 0] if abs(axis[0]) < 0.9 else [0, 1.0, 0])
    e1 /= np.linalg.norm(e1)
    e2 = np.cross(axis, e1)
    x, y, t = pts @ e1, pts @ e2, pts @ axis
    sol = np.linalg.lstsq(np.c_[2 * x, 2 * y, np.ones_like(x)], x * x + y * y, rcond=None)[0]
    radius = float(np.sqrt(max(sol[2] + sol[0] ** 2 + sol[1] ** 2, 0)))
    a = sol[0] * e1 + sol[1] * e2
    return {"axis_dir": axis.tolist(), "axis_start": (a + t.min() * axis).tolist(),
            "axis_end": (a + t.max() * axis).tolist(), "radius_mm": radius,
            "full_circle": bool(abs((u1 - u0) - 2 * np.pi) < 1e-6)}


def _mesh_worker(step: str, size: float, out: str) -> None:
    """Runs in a child process: import the STEP, describe its faces, mesh it, save arrays to out (.npz)."""
    import gmsh
    import numpy as np

    gmsh.initialize(interruptible=False)
    gmsh.option.setNumber("General.Terminal", 0)
    gmsh.model.occ.importShapes(step)
    gmsh.model.occ.synchronize()
    faces = []
    for _, tag in gmsh.model.getEntities(2):
        kind = gmsh.model.getType(2, tag)
        info = {"tag": tag, "type": kind, "bbox": [round(v, 4) for v in gmsh.model.getBoundingBox(2, tag)],
                "area_mm2": round(gmsh.model.occ.getMass(2, tag), 3)}
        if kind == "Cylinder":
            try:
                info.update(_fit_cylinder(gmsh, np, tag))
            except Exception:  # noqa: BLE001 - a face we cannot fit is still selectable by box
                pass
        faces.append(info)
    data = {"faces": np.array(json.dumps(faces)), "bbox": np.array(gmsh.model.getBoundingBox(-1, -1))}
    if size > 0:
        gmsh.option.setNumber("Mesh.MeshSizeMax", size)
        gmsh.option.setNumber("Mesh.MeshSizeMin", size / 4)
        gmsh.option.setNumber("Mesh.MeshSizeFromCurvature", 12)
        gmsh.model.mesh.generate(3)
        tags, xyz, _ = gmsh.model.mesh.getNodes()
        lookup = np.zeros(int(tags.max()) + 1, dtype=np.int64)
        lookup[tags.astype(np.int64)] = np.arange(len(tags))
        _, tet = gmsh.model.mesh.getElementsByType(4)
        tri, tri_face = [], []
        for _, tag in gmsh.model.getEntities(2):
            _, nodes = gmsh.model.mesh.getElementsByType(2, tag)
            tri.append(lookup[nodes.astype(np.int64)].reshape(-1, 3))
            tri_face.append(np.full(len(nodes) // 3, tag))
        data.update(p=xyz.reshape(-1, 3), t=lookup[tet.astype(np.int64)].reshape(-1, 4),
                    tri=np.vstack(tri), tri_face=np.concatenate(tri_face))
    gmsh.finalize()
    np.savez(out, **data)


def _run_mesher(step: Path, size: float) -> dict:
    import numpy as np

    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "mesh.npz"
        proc = subprocess.run([sys.executable, "-m", "tb.fea", str(step), str(size), str(out)],
                              cwd=TOOLBOX, capture_output=True, text=True, timeout=600)
        if proc.returncode != 0 or not out.exists():
            raise FeaError(f"gmsh could not mesh {step.name}: {proc.stderr.strip()[-600:] or 'no output'}")
        with np.load(out) as z:
            data = {k: z[k] for k in z.files}
    data["faces"] = json.loads(str(data["faces"]))
    return data


# --- regions --------------------------------------------------------------------------------


class Model:
    """Mesh plus the lookups needed to turn a region description into boundary facets."""

    def __init__(self, raw: dict):
        import numpy as np
        from skfem import MeshTet

        used = np.unique(raw["t"])
        remap = np.full(len(raw["p"]), -1, dtype=np.int64)
        remap[used] = np.arange(len(used))
        self.mesh = MeshTet(np.ascontiguousarray(raw["p"][used].T), np.ascontiguousarray(remap[raw["t"]].T))
        self.faces = {f["tag"]: f for f in raw["faces"]}
        m = self.mesh
        self.bfacets = m.boundary_facets()
        self.lo, self.hi = m.p.min(axis=1), m.p.max(axis=1)
        n = m.p.shape[1]
        key = lambda a: (a[0] * n + a[1]) * n + a[2]  # noqa: E731
        fkeys = key(m.facets.astype(np.int64))
        order = np.argsort(fkeys)
        tri = np.sort(remap[raw["tri"]], axis=1).T
        pos = np.searchsorted(fkeys[order], key(tri))
        pos = np.clip(pos, 0, len(order) - 1)
        hit = fkeys[order][pos] == key(tri)
        self.facet_face = np.zeros(m.facets.shape[1], dtype=np.int64)
        self.facet_face[order[pos[hit]]] = raw["tri_face"][hit]
        p = m.p[:, m.facets]  # (3, 3 vertices, nfacets)
        self.facet_area = 0.5 * np.linalg.norm(np.cross((p[:, 1] - p[:, 0]).T, (p[:, 2] - p[:, 0]).T), axis=1)

    def select(self, spec: dict) -> tuple:
        """Boundary facets for a region description, and a plain-English note of what was picked."""
        import numpy as np

        m = self.mesh
        tol = float(spec.get("tol_mm", 0) or 0)
        pts = m.p[:, m.facets[:, self.bfacets]]  # (3, 3, nb)
        if "side" in spec:
            side = str(spec["side"]).lower()
            if side not in SIDES:
                raise FeaError(f"Unknown side '{spec['side']}': use one of {sorted(SIDES)}")
            ax, which_end = SIDES[side]
            tol = tol or 1e-3 * float((self.hi - self.lo).max())
            plane = self.lo[ax] if which_end == "min" else self.hi[ax]
            keep = (np.abs(pts[ax] - plane) <= tol).all(axis=0)
            note = f"faces within {tol:.3g} mm of {side} ({AXES[ax]} = {plane:.3f})"
        elif "box" in spec:
            b = np.asarray(spec["box"], dtype=float).ravel()
            if b.size != 6:
                raise FeaError("box needs [xmin, ymin, zmin, xmax, ymax, zmax]")
            lo, hi = np.minimum(b[:3], b[3:]) - tol - 1e-9, np.maximum(b[:3], b[3:]) + tol + 1e-9
            keep = ((pts >= lo[:, None, None]) & (pts <= hi[:, None, None])).all(axis=(0, 1))
            note = f"surface triangles wholly inside box {b.round(3).tolist()}"
        elif "hole" in spec:
            keep, note = self._hole(spec, tol or 0.5)
        else:
            raise FeaError(f"Region {spec} needs one of: side, box, hole")
        facets = self.bfacets[keep]
        if facets.size == 0:
            raise FeaError(f"Region {({k: spec[k] for k in ('side', 'box', 'hole') if k in spec})} selects no surface. "
                           f"Part spans {self.lo.round(3).tolist()} to {self.hi.round(3).tolist()}; "
                           "list selectable faces with fea_faces")
        return facets, f"{note}: {facets.size} triangles, {self.facet_area[facets].sum():.2f} mm2"

    def _hole(self, spec: dict, tol: float):
        import numpy as np

        q = np.asarray(spec["hole"], dtype=float).ravel()
        if q.size != 3:
            raise FeaError("hole needs a point [x, y, z] on or near the hole axis")
        want_r = float(spec.get("radius_mm", 0) or 0)
        cands = []
        for f in self.faces.values():
            if "radius_mm" not in f or (want_r and abs(f["radius_mm"] - want_r) > max(0.05, 0.02 * want_r)):
                continue
            a, b = np.array(f["axis_start"]), np.array(f["axis_end"])
            d = b - a
            s = np.clip((q - a) @ d / max(d @ d, 1e-12), 0, 1)
            cands.append((float(np.linalg.norm(q - (a + s * d))), f))
        if not cands:
            raise FeaError("No cylindrical face" + (f" of radius {want_r} mm" if want_r else "") + " in this part")
        best = min(c[0] for c in cands)
        picked = [f for dist, f in cands if dist <= best + tol]
        tags = [f["tag"] for f in picked]
        keep = np.isin(self.facet_face[self.bfacets], tags)
        radii = sorted({round(f["radius_mm"], 3) for f in picked})
        return keep, (f"{len(picked)} cylindrical face(s), radius {radii} mm, axis {best:.2f} mm from {q.tolist()}"
                      + ("" if want_r or len(radii) == 1 else " (coaxial bores all taken; pass radius_mm to pick one)"))


# --- material -------------------------------------------------------------------------------


def _stiffness_matrix(E: float, nu: float, z_ratio: float, build_axis: int):
    """6x6 Voigt stiffness (MPa). Transversely isotropic about the build axis when z_ratio != 1."""
    import numpy as np

    Ez = E * z_ratio
    nu_zp = nu * z_ratio  # reciprocity: nu_zp / Ez = nu_pz / Ep with nu_pz taken equal to nu
    Gp = E / (2 * (1 + nu))
    Gz = Gp if z_ratio == 1 else np.sqrt(E * Ez) / (2 * (1 + np.sqrt(nu * nu_zp)))  # Huber estimate
    S = np.zeros((6, 6))
    inplane = [i for i in range(3) if i != build_axis]
    for i in range(3):
        S[i, i] = 1 / (Ez if i == build_axis else E)
    p, q = inplane
    S[p, q] = S[q, p] = -nu / E
    for i in inplane:
        S[i, build_axis] = S[build_axis, i] = -nu / E
    for k, (i, j) in enumerate(_VOIGT[3:], start=3):
        S[k, k] = 1 / (Gz if build_axis in (i, j) else Gp)
    return np.linalg.inv(S), float(Gz)


def _voigt_strain(g):
    return [g[0][0], g[1][1], g[2][2], g[1][2] + g[2][1], g[0][2] + g[2][0], g[0][1] + g[1][0]]


def _von_mises(s):
    import numpy as np

    return np.sqrt(0.5 * ((s[0] - s[1]) ** 2 + (s[1] - s[2]) ** 2 + (s[2] - s[0]) ** 2) + 3 * (s[3] ** 2 + s[4] ** 2 + s[5] ** 2))


# --- solve ----------------------------------------------------------------------------------


def _solve_system(K, f, fixed_dofs):
    """Direct solve on the free dofs; conjugate gradients when the system is too big to factorise quickly."""
    import numpy as np
    from scipy.sparse.linalg import cg, splu

    free = np.setdiff1d(np.arange(K.shape[0]), fixed_dofs)
    Kff = K[free][:, free].tocsc()
    u = np.zeros(K.shape[0])
    if free.size <= 220_000:
        u[free] = splu(Kff, permc_spec="MMD_AT_PLUS_A", diag_pivot_thresh=0.0,
                       options={"SymmetricMode": True}).solve(f[free])
        return u, "sparse direct (SuperLU, symmetric mode)"
    d = Kff.diagonal()
    from scipy.sparse.linalg import LinearOperator

    x, info = cg(Kff, f[free], rtol=1e-8, maxiter=20000, M=LinearOperator(Kff.shape, lambda r: r / d))
    if info != 0:
        raise FeaError("Iterative solver did not converge; use a larger mesh_size_mm")
    u[free] = x
    return u, "conjugate gradients, Jacobi preconditioner, rtol 1e-8"


def _case(model: Model, mat: dict, fixed: list, loads: list, order: int, C, build_axis: int, h: float,
          probes: list | None) -> dict:
    import numpy as np
    from scipy.spatial import cKDTree
    from skfem import Basis, BilinearForm, ElementTetP1, ElementTetP2, ElementVector, FacetBasis, LinearForm

    t0 = time.perf_counter()
    mesh = model.mesh
    elem = ElementVector(ElementTetP2() if order == 2 else ElementTetP1())
    basis = Basis(mesh, elem, intorder=2 if order == 2 else 1)
    if basis.N > MAX_DOF:
        raise FeaError(f"{basis.N} unknowns is over the {MAX_DOF} limit: use a larger mesh_size_mm")
    terms = [(i, j, float(C[i, j])) for i in range(6) for j in range(6) if abs(C[i, j]) > 1e-9]

    @BilinearForm
    def stiffness(u, v, _):
        eu, ev = _voigt_strain(u.grad), _voigt_strain(v.grad)
        return sum(c * eu[i] * ev[j] for i, j, c in terms)

    K = stiffness.assemble(basis)
    comp_dofs = [np.concatenate([basis.nodal_dofs[c], basis.edge_dofs[c]]) if order == 2 else basis.nodal_dofs[c]
                 for c in range(3)]

    # supports
    fixed_dofs, support_nodes, notes, constrained_axes = [], [], [], set()
    for spec in fixed:
        facets, note = model.select(spec)
        axes = str(spec.get("axes", "xyz")).lower()
        if not axes or set(axes) - set(AXES):
            raise FeaError(f"axes '{spec.get('axes')}' must be some of x, y, z")
        dofs = basis.get_dofs(facets)
        fixed_dofs.append(np.concatenate([dofs.all([f"u^{AXES.index(a) + 1}"]) for a in axes]))
        support_nodes.append(np.unique(mesh.facets[:, facets]))
        constrained_axes |= set(axes)
        notes.append(f"fixed {axes}: {note}")
    if not fixed_dofs:
        raise FeaError("No supports: give at least one fixed region, e.g. [{'side': 'zmin'}]")
    if constrained_axes != set(AXES):
        raise FeaError(f"Nothing restrains {sorted(set(AXES) - constrained_axes)}: the part would slide freely")
    fixed_dofs = np.unique(np.concatenate(fixed_dofs))

    # loads
    f = np.zeros(basis.N)
    requested = np.zeros(3)
    load_nodes = []
    for spec in loads:
        if "gravity_g" in spec:
            rho = mat["density_g_cm3"]
            if not rho:
                raise FeaError("Gravity / self-weight needs a density: pass density_g_cm3 or a material with one")
            d = np.asarray(spec.get("direction", [0, 0, -1]), dtype=float)
            body = rho * 1e-9 * mechanics.G_MM_S2 * float(spec["gravity_g"]) * d / np.linalg.norm(d)  # N/mm3

            @LinearForm
            def weight(v, _):
                return body[0] * v[0] + body[1] * v[1] + body[2] * v[2]

            f += weight.assemble(basis)
            requested += body * model_volume(mesh)
            notes.append(f"gravity {spec['gravity_g']} g along {d.tolist()}, density {rho} g/cm3")
            continue
        facets, note = model.select(spec)
        fb = FacetBasis(mesh, elem, facets=facets, intorder=2 if order == 2 else 1)
        area = float(model.facet_area[facets].sum())
        if "force_n" in spec:
            force = np.asarray(spec["force_n"], dtype=float).ravel()
            if force.size != 3:
                raise FeaError("force_n needs [Fx, Fy, Fz] in newtons (the TOTAL force on the region)")
            tr = force / area

            @LinearForm
            def traction(v, _):
                return tr[0] * v[0] + tr[1] * v[1] + tr[2] * v[2]

            f += traction.assemble(fb)
            requested += force
            notes.append(f"force {force.tolist()} N as uniform traction on {note}")
        elif "pressure_mpa" in spec:
            pr = float(spec["pressure_mpa"])

            @LinearForm
            def pressure(v, w):
                return -pr * (w.n[0] * v[0] + w.n[1] * v[1] + w.n[2] * v[2])

            fp = pressure.assemble(fb)
            f += fp
            requested += np.array([fp[d].sum() for d in comp_dofs])
            notes.append(f"pressure {pr} MPa pushing into {note}")
        else:
            raise FeaError(f"Load {spec} needs force_n, pressure_mpa or gravity_g")
        load_nodes.append(np.unique(mesh.facets[:, facets]))
    applied = np.array([f[d].sum() for d in comp_dofs])
    if not np.abs(f).max() > 0:
        raise FeaError("No loads: give at least one of force_n, pressure_mpa, gravity_g")
    t_asm = time.perf_counter() - t0

    t1 = time.perf_counter()
    u, solver = _solve_system(K, f, fixed_dofs)
    t_solve = time.perf_counter() - t1
    span = float(np.linalg.norm(model.hi - model.lo))
    if not np.isfinite(u).all() or np.abs(u).max() > 100 * span:
        raise FeaError("Solution is unbounded: the supports leave the part free to move or spin. Fix more faces or axes")

    # reactions
    resid = K @ u - f
    mask = np.zeros(basis.N, dtype=bool)
    mask[fixed_dofs] = True
    reaction = np.array([resid[d][mask[d]].sum() for d in comp_dofs])
    imbalance = float(np.linalg.norm(reaction + applied))
    scale = float(np.linalg.norm(applied)) or float(np.abs(f).sum())

    # stress at element vertices, volume-averaged to nodes
    verts = np.array([[0.0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]])
    vb = Basis(mesh, elem, quadrature=(verts, np.full(4, 1 / 24)))
    eps = _voigt_strain(vb.interpolate(u).grad)
    sig = [sum(C[i, j] * eps[j] for j in range(6) if abs(C[i, j]) > 1e-9) for i in range(6)]  # (nel, 4) each
    p = mesh.p
    e = p[:, mesh.t[1:]] - p[:, mesh.t[0]][:, None, :]
    vol = np.abs(np.einsum("in,in->n", e[:, 0], np.cross(e[:, 1].T, e[:, 2].T).T)) / 6
    conn = mesh.t.T.ravel()
    wsum = np.bincount(conn, weights=np.repeat(vol, 4), minlength=p.shape[1])
    nodal = np.array([np.bincount(conn, weights=(s * vol[:, None]).ravel(), minlength=p.shape[1]) / wsum for s in sig])
    vm = _von_mises(nodal)
    vm_raw = float(_von_mises(np.array(sig)).max())
    disp = u[basis.nodal_dofs]  # (3, nverts)
    mag = np.linalg.norm(disp, axis=0)

    # nodes close to a support or a load: stress there is mesh dependent
    special = np.unique(np.concatenate(support_nodes + load_nodes))
    near = cKDTree(p.T[special]).query(p.T, distance_upper_bound=1.01 * h)[0] <= h
    on_support = np.zeros(p.shape[1], dtype=bool)
    on_support[np.unique(np.concatenate(support_nodes))] = True

    def where(i):
        return [round(float(x), 3) for x in p[:, i]]

    i_d, i_s = int(mag.argmax()), int(vm.argmax())
    out = {
        "max_displacement_mm": float(mag[i_d]), "max_displacement_at": where(i_d),
        "max_displacement_vector_mm": [float(x) for x in disp[:, i_d]],
        "max_von_mises_mpa": float(vm[i_s]), "max_von_mises_at": where(i_s),
        "max_von_mises_unaveraged_mpa": vm_raw,
        "peak_is_near_support_or_load": bool(near[i_s]),
    }
    if (~near).any():
        j = int(np.where(~near, vm, -1).argmax())
        out["max_von_mises_away_mpa"] = float(vm[j])
        out["max_von_mises_away_at"] = where(j)
    sn = nodal[build_axis]
    shear = np.sqrt(sum(nodal[k] ** 2 for k, (a, b) in enumerate(_VOIGT) if a != b and build_axis in (a, b)))
    k = int(sn.argmax())
    out["interlayer"] = {
        "max_tension_normal_to_layers_mpa": max(float(sn[k]), 0.0), "max_tension_at": where(k),
        "max_interlayer_shear_mpa": float(shear.max()), "max_interlayer_shear_at": where(int(shear.argmax())),
    }
    if (~near).any():
        out["interlayer"]["max_tension_normal_to_layers_away_mpa"] = max(float(np.where(~near, sn, -1e30).max()), 0.0)
    out.update({
        "applied_force_n": applied.tolist(), "requested_force_n": requested.tolist(), "reaction_force_n": reaction.tolist(),
        "equilibrium_error_pct": 100 * imbalance / scale if scale else 0.0,
        "mesh": {"nodes": int(p.shape[1]), "tetrahedra": int(mesh.t.shape[1]), "unknowns": int(basis.N),
                 "element": "10-node quadratic tetrahedron (straight edges)" if order == 2 else "4-node linear tetrahedron",
                 "mesh_size_mm": h, "volume_mm3": float(vol.sum()),
                 "min_edge_mm": float(_edge_lengths(mesh).min()),
                 "mean_edge_mm": float(_edge_lengths(mesh).mean())},
        "solver": solver, "assemble_time_s": t_asm, "solve_time_s": t_solve, "selections": notes,
    })
    if probes:
        tree = cKDTree(p.T)
        out["probes"] = []
        for q in probes:
            dist, i = tree.query(np.asarray(q, dtype=float))
            out["probes"].append({"asked": list(q), "node_at": where(i), "distance_mm": float(dist),
                                  "displacement_mm": [float(x) for x in disp[:, i]], "von_mises_mpa": float(vm[i]),
                                  "stress_mpa": {n: float(nodal[c, i]) for c, n in enumerate(("xx", "yy", "zz", "yz", "xz", "xy"))}})
    out["_fields"] = {"displacement": disp.T, "von_mises": vm, "stress": nodal.T, "near": near.astype(float),
                      "normal_to_layers": sn}
    return out


def model_volume(mesh) -> float:
    import numpy as np

    p = mesh.p
    e = p[:, mesh.t[1:]] - p[:, mesh.t[0]][:, None, :]
    return float(np.abs(np.einsum("in,in->n", e[:, 0], np.cross(e[:, 1].T, e[:, 2].T).T)).sum() / 6)


def _edge_lengths(mesh):
    import numpy as np

    return np.linalg.norm(mesh.p[:, mesh.edges[0]] - mesh.p[:, mesh.edges[1]], axis=0)


def _round(obj, sig: int = 5):
    if isinstance(obj, float):
        return float(f"{obj:.{sig}g}")
    if isinstance(obj, dict):
        return {k: _round(v, sig) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_round(v, sig) for v in obj]
    return obj


# --- tools ----------------------------------------------------------------------------------


def _step_path(project: str, part: str) -> Path:
    d = project_dir(project)
    step = d / "out" / f"{part}.step"
    if not part.replace("-", "").replace("_", "").isalnum() or not step.exists():
        have = sorted(p.stem for p in (d / "out").glob("*.step"))
        raise FeaError(f"No STEP for part '{part}' in project '{project}'. Built parts: {have}. Run cad_build first")
    return step


def fea_faces(project: str, part: str) -> dict:
    """List a part's CAD faces so regions can be chosen for fea_static: bounding box (mm), holes with axis and radius.

    Returns the part bounding box, every cylindrical face (axis ends, radius_mm, full_circle) and a
    summary of planar faces. Use a cylinder's axis point as {"hole": [x, y, z]}.
    """
    try:
        raw = _run_mesher(_step_path(project, part), 0)
    except (FeaError, ValueError, FileNotFoundError, subprocess.TimeoutExpired) as e:
        return {"ok": False, "error": str(e)}
    cyl = [{"radius_mm": round(f["radius_mm"], 3), "axis_start": [round(v, 3) for v in f["axis_start"]],
            "axis_end": [round(v, 3) for v in f["axis_end"]], "full_circle": f["full_circle"], "area_mm2": f["area_mm2"]}
           for f in raw["faces"] if "radius_mm" in f]
    planes = [{"bbox_min": f["bbox"][:3], "bbox_max": f["bbox"][3:], "area_mm2": f["area_mm2"]}
              for f in raw["faces"] if f["type"] == "Plane"]
    planes.sort(key=lambda f: -f["area_mm2"])
    b = [round(float(v), 3) for v in raw["bbox"]]
    kinds: dict[str, int] = {}
    for f in raw["faces"]:
        kinds[f["type"]] = kinds.get(f["type"], 0) + 1
    return {"ok": True, "bbox_min": b[:3], "bbox_max": b[3:], "face_counts": kinds, "cylinders": cyl,
            "largest_planes": planes[:12],
            "region_help": "{'side': 'zmin'} | {'box': [x0,y0,z0,x1,y1,z1]} | {'hole': [x,y,z], 'radius_mm': r}"}


def fea_static(project: str, part: str, fixed: list[dict], loads: list[dict], material: str = "",
               mesh_size_mm: float = 0, case: str = "case", route: str = "auto", order: int = 2,
               E_mpa: float = 0, nu: float = 0, yield_mpa: float = 0, density_g_cm3: float = 0,
               build_direction: str = "", z_stiffness_ratio: float = 0, z_strength_ratio: float = 0,
               convergence: bool = False, probes: list[list[float]] | None = None) -> dict:
    """Linear static FEA of one built part: max displacement (mm), von Mises stress (MPa), safety factors, reactions (N).

    Regions (model coordinates, mm): {"side": "zmin"|"xmax"|..., "tol_mm": 0.1} |
    {"box": [x0,y0,z0,x1,y1,z1]} | {"hole": [x,y,z], "radius_mm": r} (cylindrical faces whose axis is nearest the point).
    fixed: regions, each optionally with "axes": "xyz" (default) or e.g. "z".
    loads: a region plus "force_n": [Fx,Fy,Fz] (total, spread evenly) or "pressure_mpa": p (pushes into the face);
    or {"gravity_g": 1, "direction": [0,0,-1]} for self-weight.
    material: name for tb.materials (default: the part's material in build.json); E_mpa, nu, yield_mpa,
    density_g_cm3 override it. Printed parts: build_direction "x"|"y"|"z" plus z_stiffness_ratio and
    z_strength_ratio (Z over XY, 0-1) give a layered material and an interlayer safety factor.
    convergence=True solves again on a finer mesh and reports the change. probes: points to sample.
    Writes a .vtu (ParaView) and .json under out/fea/. Small-strain, elastic, static only.
    """
    t_start = time.perf_counter()
    route = (route or "auto").lower()
    if route == "ccx":
        if not which("ccx"):
            return {"ok": False, "error": "CalculiX (ccx) is not installed. Use route='skfem', or install it",
                    "install": CCX_INSTALL}
        return {"ok": False, "error": "route 'ccx' is not implemented yet: CalculiX was found but this tool does not "
                                      "write .inp decks. Use route='skfem'"}
    if route not in ("auto", "skfem"):
        return {"ok": False, "error": f"Unknown route '{route}': use auto, skfem or ccx"}
    try:
        import numpy as np

        if order not in (1, 2):
            raise FeaError("order must be 1 (linear) or 2 (quadratic)")
        if not case.replace("-", "").replace("_", "").isalnum():
            raise FeaError("case: letters, digits, '-' and '_' only")
        step = _step_path(project, part)
        pdir = project_dir(project)
        built = ((load_json(pdir / "out" / "build.json") or {}).get("parts") or {}).get(part, {})
        mat_name = material or built.get("material", "")
        mat = mechanics.material_props(mat_name, E_mpa=E_mpa, nu=nu, yield_mpa=yield_mpa, density_g_cm3=density_g_cm3)
        if not mat["E_mpa"]:
            raise FeaError(f"No Young's modulus for material '{mat_name}'. Pass E_mpa (and yield_mpa, density_g_cm3), "
                           "or use a material known to tb.materials. " + " ".join(mat["notes"]))
        assumptions = ["Linear elastic, small displacement, static load; no contact, creep, fatigue or buckling",
                       "Supports are perfectly rigid; a force is spread as uniform traction over its region"] + mat["notes"]
        warnings = []

        # layered (printed) material
        printed = bool(build_direction) or built.get("process") in ("fdm", "sla", "sls")
        axis_name = (build_direction or "z").lower()
        if axis_name not in AXES:
            raise FeaError("build_direction must be x, y or z")
        b_axis = AXES.index(axis_name)
        zk = z_stiffness_ratio or (mat["E_z_mpa"] / mat["E_mpa"] if mat.get("E_z_mpa") else 0)
        if zk and not 0 < zk <= 1.5:
            raise FeaError("z_stiffness_ratio must be between 0 and 1.5")
        C, Gz = _stiffness_matrix(mat["E_mpa"], mat["nu"], zk or 1.0, b_axis)
        if zk and abs(zk - 1) > 1e-9:
            layered = (f"Transversely isotropic elasticity solved in full: E in-plane {mat['E_mpa']:.0f} MPa, "
                       f"E along build axis {axis_name} {mat['E_mpa'] * zk:.0f} MPa, interlayer shear modulus {Gz:.0f} MPa "
                       "(Huber estimate, not measured), Poisson's ratio the same in and out of plane")
        else:
            layered = "Isotropic stiffness (no Z stiffness ratio given)"
        if printed:
            layered += f"; stress normal to the layers (build axis {axis_name}) is reported separately"
            assumptions.append(f"Build direction taken as model {axis_name.upper()}; infill and perimeters are not modelled, "
                               "the part is treated as solid")
        z_strength = None
        if z_strength_ratio and mat["yield_mpa"]:
            z_strength = mat["yield_mpa"] * z_strength_ratio
        elif mat.get("strength_z_mpa"):
            z_strength = mat["strength_z_mpa"]

        # mesh
        t0 = time.perf_counter()
        geo = _run_mesher(step, 0) if mesh_size_mm <= 0 else None
        if mesh_size_mm <= 0:
            bb = np.asarray(geo["bbox"])
            dims = bb[3:] - bb[:3]
            mesh_size_mm = float(np.clip(min(dims.min() / 2, np.linalg.norm(dims) / 30), 0.3, None))
            assumptions.append(f"mesh_size_mm chosen automatically: {mesh_size_mm:.3g}")
        sizes = [mesh_size_mm] + ([mesh_size_mm * 0.7] if convergence else [])
        runs, t_mesh = [], 0.0
        for h in sizes:
            t0 = time.perf_counter()
            model = Model(_run_mesher(step, h))
            t_mesh += time.perf_counter() - t0
            runs.append((model, _case(model, mat, fixed, loads, order, C, b_axis, h, probes)))
        model, res = runs[0]
        fields = res.pop("_fields")

        # checks
        area = float(model.facet_area[model.bfacets].sum())
        thickness = 2 * res["mesh"]["volume_mm3"] / area
        res["mesh"]["characteristic_thickness_mm"] = thickness
        res["mesh"]["elements_through_thickness"] = thickness / mesh_size_mm
        if mesh_size_mm > thickness * (1.0 if order == 2 else 0.34):
            warnings.append(f"Coarse mesh: size {mesh_size_mm:.3g} mm against a typical wall of about {thickness:.3g} mm "
                            f"(2 x volume / surface area). Use mesh_size_mm <= {thickness / (2 if order == 2 else 4):.2g} "
                            "or convergence=True")
        if order == 1:
            warnings.append("Linear tetrahedra are too stiff in bending: stresses and deflections read low. Prefer order=2")
        if res["peak_is_near_support_or_load"]:
            warnings.append("Peak stress is within one element of a support or load region: it is likely a singularity "
                            "that grows as the mesh is refined. Judge the part on max_von_mises_away_mpa")
        gap = res["max_von_mises_unaveraged_mpa"] / res["max_von_mises_mpa"] - 1 if res["max_von_mises_mpa"] else 0
        if gap > 0.5:
            warnings.append(f"Stress jumps {100 * gap:.0f} % between neighbouring elements at the peak: mesh too coarse there")
        if res["equilibrium_error_pct"] > 1:
            warnings.append(f"Reactions do not balance the load ({res['equilibrium_error_pct']:.2g} %): result is unreliable")

        sy = mat["yield_mpa"]
        sf = {"against": mat["sources"].get("yield_mpa"), "yield_mpa": sy}
        if sy:
            sf["at_peak"] = sy / res["max_von_mises_mpa"] if res["max_von_mises_mpa"] else None
            if res.get("max_von_mises_away_mpa"):
                sf["away_from_supports_and_loads"] = sy / res["max_von_mises_away_mpa"]
        else:
            warnings.append("No yield strength: pass yield_mpa to get a safety factor")
        inter = res["interlayer"]
        inter["build_direction"] = axis_name
        if z_strength:
            inter["z_strength_mpa"] = z_strength
            tens = inter["max_tension_normal_to_layers_mpa"]
            inter["safety_factor_interlayer"] = z_strength / tens if tens > 1e-9 else None
            away = inter.get("max_tension_normal_to_layers_away_mpa")
            if away and away > 1e-9:
                inter["safety_factor_interlayer_away"] = z_strength / away
            inter["note"] = "Tension across layers against the Z strength; interlayer shear is reported but not rated"
        elif printed:
            inter["note"] = "No Z strength given (z_strength_ratio or material Z data): interlayer safety factor not computed"

        conv = None
        if convergence:
            fine = runs[1][1]
            fine.pop("_fields")

            def pct(key):
                return 100 * (fine[key] / res[key] - 1) if res.get(key) and fine.get(key) else None

            conv = {"mesh_sizes_mm": sizes, "unknowns": [res["mesh"]["unknowns"], fine["mesh"]["unknowns"]],
                    "max_displacement_change_pct": pct("max_displacement_mm"),
                    "max_von_mises_change_pct": pct("max_von_mises_mpa"),
                    "max_von_mises_away_change_pct": pct("max_von_mises_away_mpa"),
                    "fine": {k: fine.get(k) for k in ("max_displacement_mm", "max_von_mises_mpa", "max_von_mises_away_mpa")},
                    "solve_time_s": fine["solve_time_s"]}
            dv = abs(conv["max_von_mises_away_change_pct"] or conv["max_von_mises_change_pct"] or 0)
            conv["converged"] = bool(abs(conv["max_displacement_change_pct"] or 0) < 2 and dv < 5)
            if not conv["converged"]:
                warnings.append("Not mesh-converged (displacement moved more than 2 % or stress more than 5 %): refine mesh_size_mm")

        # files
        import meshio

        out_dir = pdir / "out" / "fea"
        out_dir.mkdir(parents=True, exist_ok=True)
        vtu = out_dir / f"{part}-{case}.vtu"
        meshio.write_points_cells(vtu, model.mesh.p.T, [("tetra", model.mesh.t.T)], point_data={
            "displacement_mm": fields["displacement"], "von_mises_mpa": fields["von_mises"],
            "stress_mpa_xx_yy_zz_yz_xz_xy": fields["stress"], "stress_normal_to_layers_mpa": fields["normal_to_layers"],
            "near_support_or_load": fields["near"]})
        result = {"ok": True, "route": "skfem", "project": project, "part": part, "case": case}
        result.update(res)
        result.update({
            "safety_factor_yield": sf.get("away_from_supports_and_loads") if res["peak_is_near_support_or_load"] and sf.get("away_from_supports_and_loads") else sf.get("at_peak"),
            "safety_factors": sf, "layered_material": layered, "convergence": conv,
            "material": {k: mat[k] for k in ("name", "E_mpa", "nu", "yield_mpa", "density_g_cm3", "sources")},
            "assumptions": assumptions, "warnings": warnings,
            "mesh_time_s": t_mesh, "total_time_s": time.perf_counter() - t_start,
            "result_file": str(vtu), "summary_file": str(out_dir / f"{part}-{case}.json"),
            "inputs": {"fixed": fixed, "loads": loads, "mesh_size_mm": mesh_size_mm, "order": order,
                       "build_direction": axis_name, "z_stiffness_ratio": z_stiffness_ratio, "z_strength_ratio": z_strength_ratio},
        })
        result = _round(result)
        save_json(out_dir / f"{part}-{case}.json", result)
        return result
    except (FeaError, ValueError, FileNotFoundError, KeyError, TypeError) as e:
        return {"ok": False, "error": f"{e}" if isinstance(e, (FeaError, FileNotFoundError)) else f"{type(e).__name__}: {e}"}
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "Meshing timed out after 600 s: use a larger mesh_size_mm"}
    except MemoryError:
        return {"ok": False, "error": "Out of memory in the solver: use a larger mesh_size_mm"}


def register(mcp) -> None:
    for fn in (fea_static, fea_faces) + mechanics.TOOLS:
        mcp.tool()(fn)


if __name__ == "__main__":
    _mesh_worker(sys.argv[1], float(sys.argv[2]), sys.argv[3])
