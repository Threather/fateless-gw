// 3D presentation scene for the war map — placement-driven.
// Every marker placed on the 2D map becomes a detailed 3D structure at the same spot.
// Objects are draggable in 3D; new positions sync back to the 2D markers live.
import * as THREE from './vendor/three.module.js';

let renderer, scene, camera, rafId = null, canvasEl = null;
let groundTex = null, objGroup = null, fxGroup = null;
let theta = -Math.PI / 4, phi = 1.05, radius = 150, lastInteract = 0;
let W = 140, H = 100, mapW = 1, mapH = 1;
let draggables = [];

const BLUE = 0x6285a8, RED = 0xc0453c, GOLD = 0xb8934a;
const mat = {
  stone:  () => new THREE.MeshStandardMaterial({ color: 0x8a8272, roughness: .9 }),
  stone2: () => new THREE.MeshStandardMaterial({ color: 0x6e675c, roughness: .95 }),
  wood:   () => new THREE.MeshStandardMaterial({ color: 0x6b5138, roughness: .9 }),
  woodDk: () => new THREE.MeshStandardMaterial({ color: 0x4a3826, roughness: .95 }),
  roof:   (tint) => new THREE.MeshStandardMaterial({ color: 0x262a38, roughness: .65, emissive: tint, emissiveIntensity: .18 }),
  cloth:  (c) => new THREE.MeshStandardMaterial({ color: c, roughness: .85, side: THREE.DoubleSide }),
  glowM:  (c, i = 1.4) => new THREE.MeshStandardMaterial({ color: c, emissive: c, emissiveIntensity: i }),
};

const pxToWx = px => (px / mapW - .5) * W;
const pxToWz = px => (px / mapH - .5) * H;
const wxToPx = wx => (wx / W + .5) * mapW;
const wzToPx = wz => (wz / H + .5) * mapH;

function pillarOfLight(color, r, h, opacity) {
  const m = new THREE.Mesh(
    new THREE.CylinderGeometry(r, r * 1.6, h, 12, 1, true),
    new THREE.MeshBasicMaterial({ color, transparent: true, opacity, blending: THREE.AdditiveBlending, side: THREE.DoubleSide, depthWrite: false }));
  m.position.y = h / 2;
  return m;
}

function groundRing(color, r) {
  const ring = new THREE.Mesh(
    new THREE.TorusGeometry(r, .16, 8, 48),
    new THREE.MeshBasicMaterial({ color, transparent: true, opacity: .55, blending: THREE.AdditiveBlending }));
  ring.rotation.x = -Math.PI / 2; ring.position.y = .35;
  ring.userData.tick = t => ring.scale.setScalar(1 + Math.sin(t * 1.6) * .1);
  return ring;
}

function teamFlag(color, poleH, x, z) {
  const g = new THREE.Group();
  const pole = new THREE.Mesh(new THREE.CylinderGeometry(.09, .11, poleH, 6), mat.woodDk());
  pole.position.y = poleH / 2; g.add(pole);
  const cloth = new THREE.Mesh(new THREE.PlaneGeometry(2.2, 1.3, 6, 1), mat.cloth(color));
  cloth.position.set(1.15, poleH - .9, 0);
  const base = cloth.geometry.attributes.position.array.slice();
  cloth.userData.tick = t => {
    const p = cloth.geometry.attributes.position.array;
    for (let i = 0; i < p.length; i += 3) {
      const xr = (base[i] + 1.1) / 2.2; // 0 at pole → 1 at tip
      p[i + 2] = Math.sin(t * 5 + xr * 4) * .28 * xr;
    }
    cloth.geometry.attributes.position.needsUpdate = true;
  };
  g.add(cloth);
  const fin = new THREE.Mesh(new THREE.SphereGeometry(.16, 8, 6), mat.glowM(GOLD, .8));
  fin.position.y = poleH; g.add(fin);
  g.position.set(x, 0, z);
  return g;
}

// ── TOWER — tiered pagoda turret with crystal + banners ──
function makeTurret(color) {
  const g = new THREE.Group();
  const plinth = new THREE.Mesh(new THREE.CylinderGeometry(3, 3.5, 1.4, 8), mat.stone2());
  plinth.position.y = .7; g.add(plinth);
  const body = new THREE.Mesh(new THREE.CylinderGeometry(1.9, 2.5, 6.5, 8), mat.stone());
  body.position.y = 4.6; g.add(body);
  const band = new THREE.Mesh(new THREE.TorusGeometry(2.15, .18, 6, 16), mat.wood());
  band.rotation.x = Math.PI / 2; band.position.y = 5.6; g.add(band);
  const balcony = new THREE.Mesh(new THREE.CylinderGeometry(2.9, 2.9, .5, 8), mat.wood());
  balcony.position.y = 8.1; g.add(balcony);
  // railing posts
  for (let i = 0; i < 8; i++) {
    const a = i / 8 * Math.PI * 2;
    const post = new THREE.Mesh(new THREE.CylinderGeometry(.07, .07, .9, 5), mat.woodDk());
    post.position.set(Math.cos(a) * 2.6, 8.8, Math.sin(a) * 2.6); g.add(post);
  }
  // two-tier roof
  const r1 = new THREE.Mesh(new THREE.ConeGeometry(3.6, 1.7, 4), mat.roof(color));
  r1.rotation.y = Math.PI / 4; r1.position.y = 10; g.add(r1);
  const cap = new THREE.Mesh(new THREE.BoxGeometry(1.8, 1.4, 1.8), mat.stone());
  cap.position.y = 11.3; g.add(cap);
  const r2 = new THREE.Mesh(new THREE.ConeGeometry(2, 1.4, 4), mat.roof(color));
  r2.rotation.y = Math.PI / 4; r2.position.y = 12.6; g.add(r2);
  // floating war crystal
  const crystal = new THREE.Mesh(new THREE.OctahedronGeometry(1.1), mat.glowM(color));
  crystal.position.y = 14.6;
  crystal.userData.tick = t => {
    crystal.rotation.y = t * 1.2;
    crystal.position.y = 14.6 + Math.sin(t * 2) * .25;
    crystal.material.emissiveIntensity = 1.2 + Math.sin(t * 3) * .5;
  };
  g.add(crystal);
  g.add(teamFlag(color, 5.5, 2.9, 2.9));
  g.add(teamFlag(color, 5.5, -2.9, -2.9));
  g.add(pillarOfLight(color, 1, 24, .09));
  g.add(groundRing(color, 4.2));
  const l = new THREE.PointLight(color, 45, 38); l.position.y = 14; g.add(l);
  return g;
}

// ── GOOSE — the actual base guardian: giant white goose on a shrine ──
function makeGoose(color) {
  const g = new THREE.Group();
  const ped = new THREE.Mesh(new THREE.CylinderGeometry(4, 4.8, 1.8, 10), mat.stone2());
  ped.position.y = .9; g.add(ped);
  const ped2 = new THREE.Mesh(new THREE.CylinderGeometry(3.2, 3.8, 1, 10), mat.stone());
  ped2.position.y = 2.3; g.add(ped2);

  const goose = new THREE.Group();
  const feather = new THREE.MeshStandardMaterial({ color: 0xf0ede2, roughness: .55 });
  // body
  const body = new THREE.Mesh(new THREE.SphereGeometry(2.3, 20, 14), feather);
  body.scale.set(1.45, 1.05, 1); body.position.y = 5.4; goose.add(body);
  // tail feathers — angled cone at the back
  const tail = new THREE.Mesh(new THREE.ConeGeometry(1.3, 2.6, 8), feather);
  tail.rotation.z = -1.1; tail.position.set(-3.2, 6.2, 0); goose.add(tail);
  // wings — flattened spheres tucked at the sides
  [-1, 1].forEach(s => {
    const wing = new THREE.Mesh(new THREE.SphereGeometry(1.7, 14, 10), feather);
    wing.scale.set(1.5, .55, .8);
    wing.position.set(-.4, 5.8, s * 1.9);
    wing.rotation.x = s * .25;
    goose.add(wing);
  });
  // S-curved neck
  const neckCurve = new THREE.CatmullRomCurve3([
    new THREE.Vector3(2.4, 5.9, 0),
    new THREE.Vector3(3.4, 7.4, 0),
    new THREE.Vector3(3.2, 9.2, 0),
    new THREE.Vector3(3.8, 10.6, 0),
  ]);
  const neck = new THREE.Mesh(new THREE.TubeGeometry(neckCurve, 16, .52, 8), feather);
  goose.add(neck);
  // head
  const head = new THREE.Mesh(new THREE.SphereGeometry(.78, 14, 10), feather);
  head.scale.set(1.25, 1, 1); head.position.set(4, 10.8, 0); goose.add(head);
  // orange beak
  const beak = new THREE.Mesh(new THREE.ConeGeometry(.34, 1.1, 8),
    new THREE.MeshStandardMaterial({ color: 0xe07a28, roughness: .6 }));
  beak.rotation.z = -Math.PI / 2; beak.position.set(5.1, 10.7, 0); goose.add(beak);
  // knob above beak (goose forehead bump)
  const knob = new THREE.Mesh(new THREE.SphereGeometry(.26, 8, 6),
    new THREE.MeshStandardMaterial({ color: 0xe07a28, roughness: .6 }));
  knob.position.set(4.7, 11.3, 0); goose.add(knob);
  // glowing team-colored eyes (demon-goose energy)
  [-1, 1].forEach(s => {
    const eye = new THREE.Mesh(new THREE.SphereGeometry(.14, 8, 6), mat.glowM(color, 2));
    eye.position.set(4.4, 11, s * .45); goose.add(eye);
  });
  // idle animation: breathe + neck sway + occasional head turn
  goose.userData.tick = t => {
    goose.position.y = Math.sin(t * 1.3) * .18;
    goose.rotation.y = Math.sin(t * .4) * .35;
    body.scale.y = 1.05 + Math.sin(t * 2.2) * .03;
  };
  g.add(goose);

  g.add(pillarOfLight(color, 2, 44, .12));
  g.add(groundRing(color, 6.5));
  g.add(teamFlag(color, 6, 4.2, 4.2));
  g.add(teamFlag(color, 6, -4.2, -4.2));
  const l = new THREE.PointLight(color, 110, 65); l.position.y = 9; g.add(l);
  return g;
}

// ── LORD / BOSS — armored war statue with greatsword ──
function makeBoss() {
  const g = new THREE.Group();
  const dais = new THREE.Mesh(new THREE.CylinderGeometry(5, 5.8, 1.6, 10), mat.stone2());
  dais.position.y = .8; g.add(dais);

  const lord = new THREE.Group();
  const armor = new THREE.MeshStandardMaterial({ color: 0x2c2733, roughness: .5, metalness: .55 });
  const trim  = mat.glowM(GOLD, .7);
  // legs
  [-1, 1].forEach(s => {
    const leg = new THREE.Mesh(new THREE.CylinderGeometry(.75, .95, 4.4, 8), armor);
    leg.position.set(0, 3.8, s * 1.1); lord.add(leg);
  });
  // waist + belt
  const waist = new THREE.Mesh(new THREE.CylinderGeometry(1.9, 1.6, 1.4, 10), armor);
  waist.position.y = 6.4; lord.add(waist);
  const belt = new THREE.Mesh(new THREE.TorusGeometry(1.85, .22, 6, 16), trim);
  belt.rotation.x = Math.PI / 2; belt.position.y = 6.9; lord.add(belt);
  // torso
  const torso = new THREE.Mesh(new THREE.CylinderGeometry(2.5, 1.9, 3.6, 10), armor);
  torso.position.y = 9; lord.add(torso);
  // chest sigil
  const sigil = new THREE.Mesh(new THREE.CircleGeometry(.75, 12), trim);
  sigil.position.set(2.2, 9.4, 0); sigil.rotation.y = Math.PI / 2; lord.add(sigil);
  // pauldrons
  [-1, 1].forEach(s => {
    const p = new THREE.Mesh(new THREE.SphereGeometry(1.35, 12, 8, 0, Math.PI * 2, 0, Math.PI / 2), armor);
    p.position.set(0, 10.8, s * 2.5); lord.add(p);
    const spike = new THREE.Mesh(new THREE.ConeGeometry(.3, 1.2, 6), trim);
    spike.position.set(0, 11.9, s * 2.5); lord.add(spike);
  });
  // head + war helm
  const head = new THREE.Mesh(new THREE.SphereGeometry(.95, 12, 10), armor);
  head.position.y = 12.1; lord.add(head);
  const helm = new THREE.Mesh(new THREE.ConeGeometry(1.05, 1.8, 8), armor);
  helm.position.y = 13.2; lord.add(helm);
  const plume = new THREE.Mesh(new THREE.ConeGeometry(.22, 1.6, 6), mat.glowM(0xc0453c, .9));
  plume.position.y = 14.4; lord.add(plume);
  // glowing eyes
  [-1, 1].forEach(s => {
    const eye = new THREE.Mesh(new THREE.BoxGeometry(.1, .16, .34), mat.glowM(0x9a6ff0, 2.4));
    eye.position.set(.88, 12.2, s * .34); lord.add(eye);
  });
  // greatsword planted in the ground
  const sword = new THREE.Group();
  const blade = new THREE.Mesh(new THREE.BoxGeometry(.28, 7.5, 1.15),
    new THREE.MeshStandardMaterial({ color: 0xb8bcc8, roughness: .3, metalness: .8 }));
  blade.position.y = 4.4; sword.add(blade);
  const edge = new THREE.Mesh(new THREE.BoxGeometry(.1, 7.5, .18), mat.glowM(0x9a6ff0, 1.2));
  edge.position.set(0, 4.4, .58); sword.add(edge);
  const guard = new THREE.Mesh(new THREE.BoxGeometry(.5, .4, 2.4), trim);
  guard.position.y = 8.2; sword.add(guard);
  const grip = new THREE.Mesh(new THREE.CylinderGeometry(.18, .18, 1.6, 8), mat.woodDk());
  grip.position.y = 9.2; sword.add(grip);
  const pommel = new THREE.Mesh(new THREE.SphereGeometry(.32, 8, 6), trim);
  pommel.position.y = 10.1; sword.add(pommel);
  sword.position.set(1.2, 1.4, 4);
  lord.add(sword);
  // arm resting on the pommel
  const arm = new THREE.Mesh(new THREE.CylinderGeometry(.5, .6, 4.4, 8), armor);
  arm.position.set(.7, 10, 2.6); arm.rotation.x = .75; lord.add(arm);

  lord.userData.tick = t => {
    lord.scale.y = 1 + Math.sin(t * 1.1) * .008; // breathing
  };
  g.add(lord);

  g.add(pillarOfLight(0x9a6ff0, 2.4, 46, .1));
  g.add(groundRing(0x9a6ff0, 7));
  const l = new THREE.PointLight(0x9a6ff0, 110, 70); l.position.y = 12; g.add(l);
  const l2 = new THREE.PointLight(GOLD, 40, 30); l2.position.y = 6; g.add(l2);
  return g;
}

// ── LUCKY TREE — blossoming escort tree with falling petals ──
function makeTree(color) {
  const g = new THREE.Group();
  const mound = new THREE.Mesh(new THREE.CylinderGeometry(3, 3.8, 1, 10), mat.stone2());
  mound.position.y = .5; g.add(mound);
  // gnarled trunk: two leaning segments
  const t1 = new THREE.Mesh(new THREE.CylinderGeometry(.75, 1.15, 4.5, 8), mat.wood());
  t1.position.y = 3.2; t1.rotation.z = .12; g.add(t1);
  const t2 = new THREE.Mesh(new THREE.CylinderGeometry(.5, .75, 3.4, 8), mat.wood());
  t2.position.set(.55, 6.6, 0); t2.rotation.z = -.22; g.add(t2);
  // branches
  [[.4, 7.8, 0, .9], [-.2, 7.2, .5, -.7], [.2, 8.2, -.5, .4]].forEach(([x, y, z, rz]) => {
    const br = new THREE.Mesh(new THREE.CylinderGeometry(.16, .3, 2.6, 6), mat.wood());
    br.position.set(x + Math.sin(rz), y, z); br.rotation.z = rz + 1.2; br.rotation.x = z; g.add(br);
  });
  // blossom canopy — cluster of glowing blossom orbs
  const blossom = new THREE.MeshStandardMaterial({ color: 0xe8a8c0, roughness: .75, emissive: color, emissiveIntensity: .3 });
  const canopy = new THREE.Group();
  [[0, 9.6, 0, 2.6], [1.8, 8.8, .8, 1.8], [-1.6, 8.9, -.6, 1.9], [.6, 8.6, -1.6, 1.6], [-.5, 8.7, 1.6, 1.7], [.3, 10.8, .3, 1.5]].forEach(([x, y, z, r]) => {
    const b = new THREE.Mesh(new THREE.SphereGeometry(r, 12, 9), blossom);
    b.position.set(x, y, z); canopy.add(b);
  });
  canopy.userData.tick = t => { canopy.rotation.y = Math.sin(t * .5) * .06; };
  g.add(canopy);
  // falling petals
  const NP = 60, pp = new Float32Array(NP * 3), seeds = new Float32Array(NP);
  for (let i = 0; i < NP; i++) {
    pp[i*3] = (Math.random() - .5) * 8; pp[i*3+1] = Math.random() * 10; pp[i*3+2] = (Math.random() - .5) * 8;
    seeds[i] = Math.random() * 6.28;
  }
  const pg = new THREE.BufferGeometry();
  pg.setAttribute('position', new THREE.BufferAttribute(pp, 3));
  const petals = new THREE.Points(pg, new THREE.PointsMaterial({ color: 0xf0b8cc, size: .35, transparent: true, opacity: .85, depthWrite: false }));
  petals.userData.tick = t => {
    const p = pg.attributes.position.array;
    for (let i = 0; i < NP; i++) {
      p[i*3+1] -= .018;
      p[i*3] += Math.sin(t * 1.5 + seeds[i]) * .008;
      if (p[i*3+1] < 0) { p[i*3+1] = 10; p[i*3] = (Math.random() - .5) * 8; }
    }
    pg.attributes.position.needsUpdate = true;
  };
  g.add(petals);
  g.add(groundRing(color, 4.5));
  const l = new THREE.PointLight(color, 40, 36); l.position.y = 9; g.add(l);
  return g;
}

// ── OUTPOST — walled fort with watchtower and banners ──
function makeOutpost(color) {
  const g = new THREE.Group();
  const yard = new THREE.Mesh(new THREE.BoxGeometry(9, .6, 9), mat.stone2());
  yard.position.y = .3; g.add(yard);
  // perimeter walls
  [[0, -4.2, 9, 0], [0, 4.2, 9, 0], [-4.2, 0, 9, Math.PI / 2], [4.2, 0, 9, Math.PI / 2]].forEach(([x, z, len, ry]) => {
    const w = new THREE.Mesh(new THREE.BoxGeometry(len, 2.6, .7), mat.stone());
    w.position.set(x, 1.9, z); w.rotation.y = ry; g.add(w);
  });
  // main hall
  const hall = new THREE.Mesh(new THREE.BoxGeometry(5, 3.2, 4), mat.wood());
  hall.position.set(-1, 2.2, -1); g.add(hall);
  const hallRoof = new THREE.Mesh(new THREE.ConeGeometry(4, 2, 4), mat.roof(color));
  hallRoof.rotation.y = Math.PI / 4; hallRoof.position.set(-1, 4.8, -1); g.add(hallRoof);
  // watchtower
  const tw = new THREE.Mesh(new THREE.CylinderGeometry(1, 1.3, 6.5, 7), mat.wood());
  tw.position.set(2.6, 3.5, 2.4); g.add(tw);
  const twRoof = new THREE.Mesh(new THREE.ConeGeometry(1.8, 1.5, 7), mat.roof(color));
  twRoof.position.set(2.6, 7.5, 2.4); g.add(twRoof);
  const lantern = new THREE.Mesh(new THREE.SphereGeometry(.35, 8, 6), mat.glowM(0xf0b060, 1.5));
  lantern.position.set(2.6, 6.4, 3.5);
  lantern.userData.tick = t => lantern.material.emissiveIntensity = 1.3 + Math.sin(t * 7) * .25;
  g.add(lantern);
  g.add(teamFlag(color, 6, -4.2, 4.2));
  g.add(teamFlag(color, 6, 4.2, -4.2));
  g.add(groundRing(color, 6.5));
  const l = new THREE.PointLight(color, 40, 36); l.position.y = 7; g.add(l);
  return g;
}

// ── JUNGLE — creep camp: campfire + straw-hat bandit mobs ──
function makeCreep(hatColor, x, z, facing) {
  const c = new THREE.Group();
  // legs
  [-1, 1].forEach(s => {
    const leg = new THREE.Mesh(new THREE.CylinderGeometry(.16, .2, 1.1, 6),
      new THREE.MeshStandardMaterial({ color: 0x3a3430, roughness: 1 }));
    leg.position.set(0, .55, s * .24); c.add(leg);
  });
  // robe body
  const body = new THREE.Mesh(new THREE.CylinderGeometry(.42, .6, 1.5, 8),
    new THREE.MeshStandardMaterial({ color: 0x5a5248, roughness: .95 }));
  body.position.y = 1.85; c.add(body);
  // sash
  const sash = new THREE.Mesh(new THREE.TorusGeometry(.48, .07, 5, 12),
    new THREE.MeshStandardMaterial({ color: 0x8a2f2f, roughness: .9 }));
  sash.rotation.x = Math.PI / 2; sash.position.y = 1.6; c.add(sash);
  // arms
  [-1, 1].forEach(s => {
    const arm = new THREE.Mesh(new THREE.CylinderGeometry(.11, .13, 1.1, 6),
      new THREE.MeshStandardMaterial({ color: 0x5a5248, roughness: .95 }));
    arm.position.set(0, 2, s * .55); arm.rotation.x = s * .35; c.add(arm);
  });
  // head
  const head = new THREE.Mesh(new THREE.SphereGeometry(.34, 10, 8),
    new THREE.MeshStandardMaterial({ color: 0xd8b090, roughness: .8 }));
  head.position.y = 2.95; c.add(head);
  // straw hat
  const hat = new THREE.Mesh(new THREE.ConeGeometry(.62, .3, 12),
    new THREE.MeshStandardMaterial({ color: hatColor, roughness: 1 }));
  hat.position.y = 3.25; c.add(hat);
  // spear
  const spear = new THREE.Mesh(new THREE.CylinderGeometry(.045, .045, 3.4, 5), mat.woodDk());
  spear.position.set(.35, 1.9, .62); spear.rotation.x = .12; c.add(spear);
  const tip = new THREE.Mesh(new THREE.ConeGeometry(.09, .4, 6),
    new THREE.MeshStandardMaterial({ color: 0xb8bcc8, metalness: .8, roughness: .3 }));
  tip.position.set(.35, 3.7, .82); c.add(tip);
  c.position.set(x, 0, z);
  c.rotation.y = facing;
  const seed = Math.random() * 6.28;
  c.userData.tick = t => {
    c.position.y = Math.abs(Math.sin(t * 1.4 + seed)) * .06; // idle shuffle
    c.rotation.y = facing + Math.sin(t * .6 + seed) * .12;
  };
  return c;
}

function makeJungleCamp() {
  const g = new THREE.Group();
  // fire pit — stone ring
  for (let i = 0; i < 7; i++) {
    const a = i / 7 * Math.PI * 2;
    const rock = new THREE.Mesh(new THREE.DodecahedronGeometry(.32), mat.stone2());
    rock.position.set(Math.cos(a) * 1.1, .25, Math.sin(a) * 1.1);
    rock.rotation.set(i, i * 2, 0); g.add(rock);
  }
  // crossed logs
  [[.5, 0], [-.4, 1.1], [.1, 2.2]].forEach(([o, ry]) => {
    const log = new THREE.Mesh(new THREE.CylinderGeometry(.13, .13, 1.7, 6), mat.woodDk());
    log.rotation.z = Math.PI / 2 - .3; log.rotation.y = ry; log.position.set(o * .3, .35, 0); g.add(log);
  });
  // flames — layered cones
  const flameO = new THREE.Mesh(new THREE.ConeGeometry(.55, 1.6, 8), mat.glowM(0xe06820, 1.6));
  flameO.position.y = 1.1; g.add(flameO);
  const flameI = new THREE.Mesh(new THREE.ConeGeometry(.28, 1, 8), mat.glowM(0xf5c542, 2));
  flameI.position.y = 1; g.add(flameI);
  const fire = new THREE.PointLight(0xe58a30, 50, 26); fire.position.y = 1.8; g.add(fire);
  flameO.userData.tick = t => {
    const f = 1 + Math.sin(t * 11) * .18 + Math.sin(t * 23) * .08;
    flameO.scale.set(f, 1 + Math.sin(t * 9) * .22, f);
    flameI.scale.set(f, 1 + Math.cos(t * 13) * .25, f);
    fire.intensity = 42 + Math.sin(t * 17) * 12;
  };
  // bandit creeps around the fire
  g.add(makeCreep(0xc9b06a, 2.6, .4, -Math.PI / 2 - .3));
  g.add(makeCreep(0xb09a55, -2.2, 1.4, Math.PI / 3));
  g.add(makeCreep(0x9a8848, .2, -2.8, .3));
  // supply crates + banner
  const crate = new THREE.Mesh(new THREE.BoxGeometry(1, 1, 1), mat.wood());
  crate.position.set(-1.8, .5, -1.8); crate.rotation.y = .5; g.add(crate);
  const crate2 = new THREE.Mesh(new THREE.BoxGeometry(.8, .8, .8), mat.wood());
  crate2.position.set(-2.5, .4, -.9); g.add(crate2);
  g.add(teamFlag(0x6b9b78, 4.5, 2.8, -2.2));
  g.add(groundRing(0x6b9b78, 4.6));
  return g;
}

// ── PLAYER — role disc with light column ──
function makePlayer(role, initials) {
  const g = new THREE.Group();
  const roleColor = { heal: '#6b9b78', tank: '#b07c45', dps: '#6285a8' };
  const c = document.createElement('canvas'); c.width = c.height = 96;
  const x = c.getContext('2d');
  x.fillStyle = roleColor[role] || '#b8934a';
  x.beginPath(); x.arc(48, 48, 40, 0, 7); x.fill();
  x.strokeStyle = 'rgba(255,255,255,.75)'; x.lineWidth = 5; x.stroke();
  x.fillStyle = '#fff'; x.font = '700 34px Outfit,sans-serif';
  x.textAlign = 'center'; x.textBaseline = 'middle';
  x.fillText(initials || '?', 48, 50);
  const sp = new THREE.Sprite(new THREE.SpriteMaterial({ map: new THREE.CanvasTexture(c), transparent: true, depthWrite: false }));
  sp.position.y = 5; sp.scale.setScalar(5);
  sp.userData.tick = t => { sp.position.y = 5 + Math.sin(t * 1.8 + sp.id) * .3; };
  g.add(sp);
  const stem = new THREE.Mesh(new THREE.CylinderGeometry(.09, .09, 4.5, 6),
    new THREE.MeshBasicMaterial({ color: 0xffffff, transparent: true, opacity: .35 }));
  stem.position.y = 2.25; g.add(stem);
  const col = new THREE.Color(roleColor[role] || '#b8934a');
  g.add(pillarOfLight(col, .7, 14, .08));
  g.add(groundRing(col.getHex(), 2));
  return g;
}

function makeGeneric(src) {
  const g = new THREE.Group();
  const sp = new THREE.Sprite(new THREE.SpriteMaterial({ map: new THREE.TextureLoader().load(src), transparent: true, depthWrite: false }));
  sp.position.y = 4; sp.scale.setScalar(6); g.add(sp);
  const stem = new THREE.Mesh(new THREE.CylinderGeometry(.09, .09, 4, 6),
    new THREE.MeshBasicMaterial({ color: 0xffffff, transparent: true, opacity: .35 }));
  stem.position.y = 2; g.add(stem);
  return g;
}

function labelSprite(text, y) {
  const c = document.createElement('canvas'); c.width = 256; c.height = 56;
  const x = c.getContext('2d');
  x.fillStyle = 'rgba(0,0,0,.65)';
  x.beginPath(); x.roundRect(28, 4, 200, 48, 24); x.fill();
  x.fillStyle = '#fff'; x.font = '600 26px Outfit,sans-serif';
  x.textAlign = 'center'; x.textBaseline = 'middle';
  x.fillText(text.slice(0, 14), 128, 30);
  const sp = new THREE.Sprite(new THREE.SpriteMaterial({ map: new THREE.CanvasTexture(c), transparent: true, depthWrite: false }));
  sp.position.y = y; sp.scale.set(9, 2, 1);
  return sp;
}

function buildStructure(el) {
  const isPlayer = el.classList.contains('pmarker');
  if (isPlayer) {
    const inner = el.querySelector('.pmarker-inner');
    const role = ['heal', 'tank', 'dps'].find(r => inner.classList.contains(r));
    const g = makePlayer(role, inner.textContent);
    g.add(labelSprite(el.querySelector('.pmlabel')?.textContent || '', 8));
    return g;
  }
  const src = el.querySelector('img')?.src || '';
  const label = el.querySelector('.mlabel')?.textContent || '';
  const team = src.includes('blue') ? BLUE : src.includes('red') ? RED : GOLD;
  let g, labelY = 15;
  if (src.includes('boss'))         { g = makeBoss(); labelY = 18; }
  else if (src.includes('tower'))   { g = makeTurret(team); labelY = 17; }
  else if (src.includes('goose'))   { g = makeGoose(team); labelY = 15; }
  else if (src.includes('tree'))    { g = makeTree(team); labelY = 14; }
  else if (src.includes('outpost')) { g = makeOutpost(team); labelY = 11; }
  else if (src.includes('jungle'))  { g = makeJungleCamp(); labelY = 8; }
  else                              { g = makeGeneric(src); labelY = 8; }
  g.add(labelSprite(label, labelY));
  return g;
}

// ── SCENE ───────────────────────────────────────────
export function enter3D({ container, mapCanvas, markerEls }) {
  canvasEl = document.getElementById('scene3d');
  const vw = container.clientWidth, vh = container.clientHeight;
  mapW = mapCanvas.width; mapH = mapCanvas.height;
  H = W * mapH / mapW;

  if (!renderer) {
    renderer = new THREE.WebGLRenderer({ canvas: canvasEl, antialias: true });
    renderer.setPixelRatio(Math.min(devicePixelRatio, 1.75));

    scene = new THREE.Scene();
    scene.background = new THREE.Color(0x07080c);
    scene.fog = new THREE.FogExp2(0x07080c, .005);
    camera = new THREE.PerspectiveCamera(55, vw / vh, .1, 600);

    scene.add(new THREE.HemisphereLight(0x3a4468, 0x14161f, 1.15));
    const moon = new THREE.DirectionalLight(0xbfc8e8, 1.2);
    moon.position.set(60, 90, -40); scene.add(moon);

    groundTex = new THREE.CanvasTexture(mapCanvas);
    groundTex.anisotropy = 8; groundTex.colorSpace = THREE.SRGBColorSpace;
    const ground = new THREE.Mesh(
      new THREE.PlaneGeometry(W, H),
      new THREE.MeshStandardMaterial({ map: groundTex, roughness: 1 }));
    ground.rotation.x = -Math.PI / 2;
    scene.add(ground);

    const N = 350, pos = new Float32Array(N * 3);
    for (let i = 0; i < N; i++) { pos[i*3] = (Math.random()-.5)*W*1.2; pos[i*3+1] = Math.random()*40; pos[i*3+2] = (Math.random()-.5)*H*1.2; }
    const eg = new THREE.BufferGeometry();
    eg.setAttribute('position', new THREE.BufferAttribute(pos, 3));
    fxGroup = new THREE.Points(eg, new THREE.PointsMaterial({ color: GOLD, size: .5, transparent: true, opacity: .7, blending: THREE.AdditiveBlending, depthWrite: false }));
    scene.add(fxGroup);

    initControls();
  }

  renderer.setSize(vw, vh);
  camera.aspect = vw / vh; camera.updateProjectionMatrix();
  groundTex.image = mapCanvas; groundTex.needsUpdate = true;

  if (objGroup) scene.remove(objGroup);
  objGroup = new THREE.Group();
  draggables = [];
  (markerEls || []).forEach(el => {
    const g = buildStructure(el);
    g.position.set(pxToWx(parseFloat(el.style.left)), 0, pxToWz(parseFloat(el.style.top)));
    g.userData.el = el;
    g.userData.isStructure = true;
    g.userData.born = performance.now();
    g.scale.setScalar(.01);
    draggables.push(g);
    objGroup.add(g);
  });
  scene.add(objGroup);

  canvasEl.style.display = 'block';
  const clock = new THREE.Clock();
  cancelAnimationFrame(rafId);
  (function loop() {
    rafId = requestAnimationFrame(loop);
    const t = clock.getElapsedTime(), now = performance.now();
    if (now - lastInteract > 3000 && !dragObj) theta += .0016;
    camera.position.set(
      Math.sin(theta) * Math.cos(Math.PI/2 - phi) * radius,
      Math.sin(phi) * radius * .9,
      Math.cos(theta) * Math.cos(Math.PI/2 - phi) * radius);
    camera.lookAt(0, 2, 0);
    draggables.forEach(g => {
      const age = (now - g.userData.born) / 450;
      if (age < 1) g.scale.setScalar(.01 + .99 * (1 - Math.pow(1 - age, 3)));
      else if (g.scale.x !== 1) g.scale.setScalar(1);
    });
    scene.traverse(o => { if (o.userData.tick) o.userData.tick(t); });
    const p = fxGroup.geometry.attributes.position.array;
    for (let i = 1; i < p.length; i += 3) { p[i] += .02; if (p[i] > 42) p[i] = 0; }
    fxGroup.geometry.attributes.position.needsUpdate = true;
    renderer.render(scene, camera);
  })();
}

// ── CONTROLS: orbit + drag-objects, synced back to 2D ──
const ray = new THREE.Raycaster(), ndc = new THREE.Vector2();
const groundPlane = new THREE.Plane(new THREE.Vector3(0, 1, 0), 0);
let dragObj = null;

function setNdc(e) {
  const r = canvasEl.getBoundingClientRect();
  ndc.x = ((e.clientX - r.left) / r.width) * 2 - 1;
  ndc.y = -((e.clientY - r.top) / r.height) * 2 + 1;
}
function rootOf(o) { while (o && !o.userData.isStructure) o = o.parent; return o; }

function initControls() {
  canvasEl.addEventListener('mousedown', e => {
    e.stopPropagation(); lastInteract = performance.now();
    setNdc(e); ray.setFromCamera(ndc, camera);
    const hits = ray.intersectObjects(draggables, true);
    if (hits.length) {
      dragObj = rootOf(hits[0].object);
      canvasEl.style.cursor = 'move';
      return;
    }
    const sx = e.clientX, sy = e.clientY, st = theta, sp = phi;
    const mv = ev => {
      theta = st - (ev.clientX - sx) * .006;
      phi = Math.min(1.45, Math.max(.3, sp - (ev.clientY - sy) * .004));
      lastInteract = performance.now();
    };
    const up = () => { removeEventListener('mousemove', mv); removeEventListener('mouseup', up); };
    addEventListener('mousemove', mv); addEventListener('mouseup', up);
  });

  canvasEl.addEventListener('mousemove', e => {
    if (!dragObj) return;
    lastInteract = performance.now();
    setNdc(e); ray.setFromCamera(ndc, camera);
    const pt = new THREE.Vector3();
    if (ray.ray.intersectPlane(groundPlane, pt)) {
      pt.x = Math.min(W / 2, Math.max(-W / 2, pt.x));
      pt.z = Math.min(H / 2, Math.max(-H / 2, pt.z));
      dragObj.position.set(pt.x, 0, pt.z);
      const el = dragObj.userData.el;
      if (el) { el.style.left = wxToPx(pt.x) + 'px'; el.style.top = wzToPx(pt.z) + 'px'; }
    }
  });

  addEventListener('mouseup', () => {
    if (dragObj) { dragObj = null; canvasEl.style.cursor = 'grab'; }
  });

  canvasEl.addEventListener('wheel', e => {
    e.preventDefault(); e.stopPropagation();
    radius = Math.min(280, Math.max(40, radius * (e.deltaY > 0 ? 1.08 : .93)));
    lastInteract = performance.now();
  }, { passive: false });
}

export function exit3D() {
  cancelAnimationFrame(rafId); rafId = null;
  if (canvasEl) canvasEl.style.display = 'none';
}
