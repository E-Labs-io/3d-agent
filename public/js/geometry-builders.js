// Procedural geometry library — exports GeometryBuilders object consumed by app.js
import * as THREE from 'three';

export const GeometryBuilders = {

  // ── Primitives ──────────────────────────────────────────────────────────

  box({ width = 10, height = 10, depth = 10, widthSegments = 1, heightSegments = 1, depthSegments = 1 } = {}) {
    return new THREE.BoxGeometry(width, height, depth, widthSegments, heightSegments, depthSegments);
  },

  sphere({ radius = 5, widthSegments = 32, heightSegments = 16, phiStart = 0, phiLength = Math.PI * 2, thetaStart = 0, thetaLength = Math.PI } = {}) {
    return new THREE.SphereGeometry(radius, widthSegments, heightSegments, phiStart, phiLength, thetaStart, thetaLength);
  },

  cylinder({ radiusTop = 5, radiusBottom = 5, height = 10, radialSegments = 32, heightSegments = 1, openEnded = false } = {}) {
    return new THREE.CylinderGeometry(radiusTop, radiusBottom, height, radialSegments, heightSegments, openEnded);
  },

  cone({ radius = 5, height = 10, radialSegments = 32 } = {}) {
    return new THREE.ConeGeometry(radius, height, radialSegments);
  },

  torus({ radius = 8, tube = 2, radialSegments = 16, tubularSegments = 64, arc = Math.PI * 2 } = {}) {
    return new THREE.TorusGeometry(radius, tube, radialSegments, tubularSegments, arc);
  },

  torusKnot({ radius = 8, tube = 2, tubularSegments = 128, radialSegments = 16, p = 2, q = 3 } = {}) {
    return new THREE.TorusKnotGeometry(radius, tube, tubularSegments, radialSegments, p, q);
  },

  plane({ width = 20, height = 20, widthSegments = 1, heightSegments = 1 } = {}) {
    return new THREE.PlaneGeometry(width, height, widthSegments, heightSegments);
  },

  circle({ radius = 5, segments = 32 } = {}) {
    return new THREE.CircleGeometry(radius, segments);
  },

  capsule({ radius = 3, length = 8, capSegments = 4, radialSegments = 16 } = {}) {
    return new THREE.CapsuleGeometry(radius, length, capSegments, radialSegments);
  },

  // ── Pipe / tube ────────────────────────────────────────────────────────

  pipe({ outerRadius = 5, innerRadius = 4, height = 20, segments = 32 } = {}) {
    const shape = new THREE.Shape();
    shape.absarc(0, 0, outerRadius, 0, Math.PI * 2, false);
    const hole = new THREE.Path();
    hole.absarc(0, 0, innerRadius, 0, Math.PI * 2, true);
    shape.holes.push(hole);
    const geo = new THREE.ExtrudeGeometry(shape, { depth: height, bevelEnabled: false });
    geo.rotateX(-Math.PI / 2);
    geo.translate(0, height / 2, 0);
    return geo;
  },

  // ── Rounded box ────────────────────────────────────────────────────────

  roundedBox({ width = 10, height = 10, depth = 10, radius = 1, segments = 3 } = {}) {
    // Build via rounded edges shape
    const r = Math.min(radius, width / 2, height / 2, depth / 2);
    const shape = new THREE.Shape();
    const w = width / 2, h = height / 2;
    shape.moveTo(-w + r, -h);
    shape.lineTo(w - r, -h);
    shape.quadraticCurveTo(w, -h, w, -h + r);
    shape.lineTo(w, h - r);
    shape.quadraticCurveTo(w, h, w - r, h);
    shape.lineTo(-w + r, h);
    shape.quadraticCurveTo(-w, h, -w, h - r);
    shape.lineTo(-w, -h + r);
    shape.quadraticCurveTo(-w, -h, -w + r, -h);
    const geo = new THREE.ExtrudeGeometry(shape, {
      depth: depth, bevelEnabled: true, bevelThickness: r, bevelSize: r,
      bevelOffset: -r, bevelSegments: segments
    });
    geo.translate(0, 0, -depth / 2);
    geo.computeVertexNormals();
    return geo;
  },

  // ── Involute Spur Gear ─────────────────────────────────────────────────

  gear({
    teeth = 20,
    module_ = 1,       // tooth size (use module_ to avoid JS reserved word)
    thickness = 5,
    pressureAngle = 20,
    profileShift = 0,
    holeRadius = 0,
  } = {}) {
    const m = module_;
    const pa = pressureAngle * Math.PI / 180;
    const pitchRadius = (m * teeth) / 2;
    const addendum = m * (1 + profileShift);
    const dedendum = m * (1.25 - profileShift);
    const outerRadius = pitchRadius + addendum;
    const rootRadius = Math.max(0.1, pitchRadius - dedendum);
    const baseRadius = pitchRadius * Math.cos(pa);
    const toothAngle = (2 * Math.PI) / teeth;

    // Generate involute from baseRadius to outerRadius
    function involute(angle) {
      return { x: baseRadius * (Math.cos(angle) + angle * Math.sin(angle)), y: baseRadius * (Math.sin(angle) - angle * Math.cos(angle)) };
    }
    function involuteAt(r) {
      const a = Math.sqrt((r / baseRadius) ** 2 - 1);
      return involute(a);
    }

    const shape = new THREE.Shape();
    const steps = 8;

    for (let t = 0; t < teeth; t++) {
      const baseAngle = t * toothAngle;
      const halfTooth = toothAngle / 4;

      // Root arc start
      const rootStart = baseAngle - halfTooth - (m * 0.3 / rootRadius);
      const flankStartAngle = baseRadius < rootRadius ? 0 : Math.sqrt((rootRadius / baseRadius) ** 2 - 1);
      const flankEndAngle = Math.sqrt(Math.max(0, (outerRadius / baseRadius) ** 2 - 1));

      // Left flank (ascending involute, mirrored)
      const leftPoints = [];
      for (let i = 0; i <= steps; i++) {
        const a = flankStartAngle + (flankEndAngle - flankStartAngle) * (i / steps);
        const p = involute(a);
        leftPoints.push({ x: p.x * Math.cos(-halfTooth) - p.y * Math.sin(-halfTooth), y: p.x * Math.sin(-halfTooth) + p.y * Math.cos(-halfTooth) });
      }
      // Right flank (descending involute)
      const rightPoints = [];
      for (let i = steps; i >= 0; i--) {
        const a = flankStartAngle + (flankEndAngle - flankStartAngle) * (i / steps);
        const p = involute(a);
        rightPoints.push({ x: p.x * Math.cos(halfTooth) + p.y * Math.sin(halfTooth), y: -p.x * Math.sin(halfTooth) + p.y * Math.cos(halfTooth) });
      }

      // Rotate all points by baseAngle
      const rotate = (p) => ({
        x: p.x * Math.cos(baseAngle) - p.y * Math.sin(baseAngle),
        y: p.x * Math.sin(baseAngle) + p.y * Math.cos(baseAngle),
      });

      if (t === 0) shape.moveTo(...Object.values(rotate(leftPoints[0])));
      else shape.lineTo(...Object.values(rotate(leftPoints[0])));

      leftPoints.forEach(p => shape.lineTo(...Object.values(rotate(p))));
      rightPoints.forEach(p => shape.lineTo(...Object.values(rotate(p))));

      // Root arc to next tooth
      const rootEnd = (t + 1) * toothAngle - halfTooth - (m * 0.3 / rootRadius);
      const arcSteps = 4;
      for (let i = 1; i <= arcSteps; i++) {
        const a = rootStart + ((rootEnd - rootStart) * i / arcSteps) + halfTooth * 2 + (m * 0.3 / rootRadius);
        shape.lineTo(rootRadius * Math.cos(a), rootRadius * Math.sin(a));
      }
    }
    shape.closePath();

    // Optional center hole
    if (holeRadius > 0) {
      const hole = new THREE.Path();
      hole.absarc(0, 0, holeRadius, 0, Math.PI * 2, true);
      shape.holes.push(hole);
    }

    const geo = new THREE.ExtrudeGeometry(shape, {
      depth: thickness, bevelEnabled: false,
      curveSegments: 4
    });
    geo.rotateX(-Math.PI / 2);
    geo.translate(0, thickness / 2, 0);
    geo.computeVertexNormals();
    return geo;
  },

  // ── Helical Spring ─────────────────────────────────────────────────────

  spring({ coilRadius = 8, wireRadius = 1.2, turns = 6, height = 30, segments = 20 } = {}) {
    const points = [];
    const totalSteps = turns * segments;
    for (let i = 0; i <= totalSteps; i++) {
      const t = i / totalSteps;
      const angle = t * turns * Math.PI * 2;
      points.push(new THREE.Vector3(
        coilRadius * Math.cos(angle),
        height * t - height / 2,
        coilRadius * Math.sin(angle)
      ));
    }
    const path = new THREE.CatmullRomCurve3(points);
    return new THREE.TubeGeometry(path, totalSteps, wireRadius, 8, false);
  },

  // ── Hex Bolt ───────────────────────────────────────────────────────────

  hex_bolt({ drive = 8, shankDiameter = 5, shankLength = 20, headHeight = 4 } = {}) {
    const geo = new THREE.BufferGeometry();
    const positions = [];
    const indices = [];
    const sides = 6;
    const headR = drive / 2 / Math.cos(Math.PI / sides);

    // Hex head vertices
    const headVerts = [];
    for (let i = 0; i < sides; i++) {
      const a = (i / sides) * Math.PI * 2 + Math.PI / 6;
      headVerts.push([headR * Math.cos(a), 0, headR * Math.sin(a)]);
      headVerts.push([headR * Math.cos(a), headHeight, headR * Math.sin(a)]);
    }
    // Center top/bottom
    headVerts.push([0, 0, 0]);        // idx: sides*2
    headVerts.push([0, headHeight, 0]); // idx: sides*2+1

    headVerts.forEach(v => positions.push(...v));

    // Hex sides
    for (let i = 0; i < sides; i++) {
      const a = i * 2, b = ((i + 1) % sides) * 2;
      indices.push(a, b, a + 1, b, b + 1, a + 1);
    }
    // Bottom cap
    for (let i = 0; i < sides; i++) {
      indices.push(sides * 2, ((i + 1) % sides) * 2, i * 2);
    }
    // Top cap
    for (let i = 0; i < sides; i++) {
      indices.push(sides * 2 + 1, i * 2 + 1, ((i + 1) % sides) * 2 + 1);
    }

    geo.setAttribute('position', new THREE.Float32BufferAttribute(positions, 3));
    geo.setIndex(indices);
    geo.computeVertexNormals();

    // Merge with shank cylinder
    const shankGeo = new THREE.CylinderGeometry(shankDiameter / 2, shankDiameter / 2, shankLength, 24);
    shankGeo.translate(0, headHeight + shankLength / 2, 0);

    return mergeGeometries([geo, shankGeo]);
  },

  // ── Hex Nut ────────────────────────────────────────────────────────────

  nut({ drive = 8, thickness = 4, holeRadius = 2.5 } = {}) {
    const sides = 6;
    const r = drive / 2 / Math.cos(Math.PI / sides);
    const shape = new THREE.Shape();
    for (let i = 0; i < sides; i++) {
      const a = (i / sides) * Math.PI * 2 + Math.PI / 6;
      if (i === 0) shape.moveTo(r * Math.cos(a), r * Math.sin(a));
      else shape.lineTo(r * Math.cos(a), r * Math.sin(a));
    }
    shape.closePath();
    const hole = new THREE.Path();
    hole.absarc(0, 0, holeRadius, 0, Math.PI * 2, true);
    shape.holes.push(hole);
    const geo = new THREE.ExtrudeGeometry(shape, { depth: thickness, bevelEnabled: false });
    geo.rotateX(-Math.PI / 2);
    geo.translate(0, thickness / 2, 0);
    geo.computeVertexNormals();
    return geo;
  },

  // ── Lathe / revolution solid ───────────────────────────────────────────

  lathe({ points = [[0,0],[5,0],[5,10],[0,10]], segments = 32, phiStart = 0, phiLength = Math.PI * 2 } = {}) {
    const pts = points.map(([x, y]) => new THREE.Vector2(x, y));
    return new THREE.LatheGeometry(pts, segments, phiStart, phiLength);
  },

  // ── Extrude from 2D path ───────────────────────────────────────────────

  extrude({ pathPoints = [[0,0],[10,0],[10,10],[0,10]], depth = 5, bevel = false, bevelThickness = 1, bevelSize = 1 } = {}) {
    const shape = new THREE.Shape();
    pathPoints.forEach(([x, y], i) => {
      if (i === 0) shape.moveTo(x, y);
      else shape.lineTo(x, y);
    });
    shape.closePath();
    const geo = new THREE.ExtrudeGeometry(shape, {
      depth, bevelEnabled: bevel, bevelThickness, bevelSize, bevelSegments: 3
    });
    geo.rotateX(-Math.PI / 2);
    geo.translate(0, depth / 2, 0);
    geo.computeVertexNormals();
    return geo;
  },

  // ── Custom code ───────────────────────────────────────────────────────

  custom_code({ geometry_code = '' } = {}) {
    try {
      const fn = new Function('THREE', `"use strict";\n${geometry_code}`);
      const result = fn(THREE);
      if (result instanceof THREE.BufferGeometry) return result;
      console.warn('custom_code did not return a BufferGeometry');
      return new THREE.BoxGeometry(5, 5, 5);
    } catch (e) {
      console.error('custom_code error:', e);
      return new THREE.BoxGeometry(5, 5, 5);
    }
  },

};

// ── Utility: merge multiple geometries ─────────────────────────────────────
export function mergeGeometries(geos) {
  let totalVerts = 0;
  let totalIndices = 0;
  const offsets = [];
  geos.forEach(g => {
    offsets.push({ vert: totalVerts, idx: totalIndices });
    totalVerts += g.getAttribute('position').count;
    totalIndices += (g.index?.count ?? 0);
  });

  const positions = new Float32Array(totalVerts * 3);
  const normals = new Float32Array(totalVerts * 3);
  const indicesArr = new Uint32Array(totalIndices);

  geos.forEach((g, gi) => {
    const { vert: vOff, idx: iOff } = offsets[gi];
    const pos = g.getAttribute('position').array;
    const nrm = g.getAttribute('normal')?.array;
    positions.set(pos, vOff * 3);
    if (nrm) normals.set(nrm, vOff * 3);
    if (g.index) {
      const src = g.index.array;
      for (let i = 0; i < src.length; i++) indicesArr[iOff + i] = src[i] + vOff;
    }
  });

  const merged = new THREE.BufferGeometry();
  merged.setAttribute('position', new THREE.BufferAttribute(positions, 3));
  merged.setAttribute('normal', new THREE.BufferAttribute(normals, 3));
  if (totalIndices > 0) merged.setIndex(new THREE.BufferAttribute(indicesArr, 1));
  merged.computeVertexNormals();
  return merged;
}

// ── Analysis utilities ──────────────────────────────────────────────────────

export function analyzeGeometry(geo) {
  geo.computeBoundingBox();
  const box = geo.boundingBox;
  const size = new THREE.Vector3();
  box.getSize(size);

  // Volume via divergence theorem (for closed meshes)
  let volume = 0;
  const pos = geo.getAttribute('position');
  const idx = geo.index;
  const a = new THREE.Vector3(), b = new THREE.Vector3(), c = new THREE.Vector3();
  const faces = idx ? idx.count / 3 : pos.count / 3;
  for (let i = 0; i < faces; i++) {
    const ia = idx ? idx.getX(i * 3) : i * 3;
    const ib = idx ? idx.getX(i * 3 + 1) : i * 3 + 1;
    const ic = idx ? idx.getX(i * 3 + 2) : i * 3 + 2;
    a.fromBufferAttribute(pos, ia);
    b.fromBufferAttribute(pos, ib);
    c.fromBufferAttribute(pos, ic);
    volume += a.dot(b.clone().cross(c)) / 6;
  }
  volume = Math.abs(volume);

  // Surface area
  let surfaceArea = 0;
  for (let i = 0; i < faces; i++) {
    const ia = idx ? idx.getX(i * 3) : i * 3;
    const ib = idx ? idx.getX(i * 3 + 1) : i * 3 + 1;
    const ic = idx ? idx.getX(i * 3 + 2) : i * 3 + 2;
    a.fromBufferAttribute(pos, ia);
    b.fromBufferAttribute(pos, ib);
    c.fromBufferAttribute(pos, ic);
    const ab = b.clone().sub(a);
    const ac = c.clone().sub(a);
    surfaceArea += ab.cross(ac).length() / 2;
  }

  // Overhang detection (simplified — count faces with normal Y component < -0.5)
  const nrm = geo.getAttribute('normal');
  let overhangFaces = 0;
  if (nrm) {
    for (let i = 0; i < nrm.count; i++) {
      if (nrm.getY(i) < -0.5) overhangFaces++;
    }
  }
  const overhangPercent = nrm ? ((overhangFaces / nrm.count) * 100).toFixed(1) : 'N/A';

  return {
    width: size.x.toFixed(2),
    height: size.y.toFixed(2),
    depth: size.z.toFixed(2),
    volume: volume.toFixed(2),
    surfaceArea: surfaceArea.toFixed(2),
    triangles: faces,
    overhangPercent,
    printable: overhangFaces / (nrm?.count || 1) < 0.2,
  };
}
