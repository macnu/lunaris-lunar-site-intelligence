/* Visor 3D del terreno lunar (three.js r147 vendorizado). Autocontenido: ninguna petición de red.
 * Convenciones de la escena: origen = observador (a la altura de su suelo); X = x del plano estereográfico polar sur,
 * Z = -y del plano (el norte de rejilla queda en -Z), Y = altura (m) menos la caída por curvatura lunar.
 * Azimut de rejilla g = lon + A (A = azimut N→E local): dirección en el plano (sin g, -cos g).
 * La luz y las sombras NO son de three.js: las sombras vienen de la máscara calculada por lsi.terrain.shadows (canal B de la textura).
 * Tres mallas: el recorte (foto + sombras), el TERRENO DE CONTEXTO (DEM LOLA de 80 m, sin foto, con su propia iluminación, degradado a negro
 * en el borde) y un PARCHE FINO junto al observador (5 m nativos interpolados a 2,5 m; microrrelieve procedural = solo sombreado, no es dato). */
(function () {
  'use strict';
  var D = JSON.parse(document.getElementById('lsi-data').textContent);
  var $ = function (id) { return document.getElementById(id); };
  var DEG = Math.PI / 180, R_M = D.R_m;

  function setText(id, t) { var e = $(id); if (e) e.textContent = t; }
  function fail(msg) {
    $('stage').hidden = true; $('fallback').hidden = false; setText('fallback-msg', msg);
  }
  if (typeof THREE === 'undefined') { fail('No se pudo cargar la librería 3D.'); return; }
  var renderer;
  try {
    renderer = new THREE.WebGLRenderer({ canvas: $('gl'), antialias: true, powerPreference: 'high-performance' });
    if (!renderer.getContext()) throw new Error('sin contexto');
  } catch (e) {
    fail('Este navegador no tiene WebGL disponible (o está desactivado), así que no se puede dibujar el visor 3D. ' +
         'Abre la «Vista alternativa» (3D de Plotly) justo debajo.');
    return;
  }
  renderer.setClearColor(0x000000, 1);

  /* ------------------------------------------------------------------ estado (se recuerda entre recargas) */
  var S = { layers: { relief: true, photo: true, shadow: true, slope: false, names: true, stars: true, horizon: true, ctx: true, micro: true },
            mode: 'oblique', az: D.view_az, exag: D.exag0, bigEarth: false };
  var KEY = 'lsi_terrain_viewer_v1';
  try {
    var saved = JSON.parse(sessionStorage.getItem(KEY) || 'null');
    if (saved) {
      Object.keys(S.layers).forEach(function (k) { if (saved.layers && typeof saved.layers[k] === 'boolean') S.layers[k] = saved.layers[k]; });
      if (['top', 'oblique', 'wide', 'observer'].indexOf(saved.mode) >= 0) S.mode = saved.mode;
      if (isFinite(saved.az)) S.az = saved.az;
      if (isFinite(saved.exag)) S.exag = Math.min(8, Math.max(1, saved.exag));
      if (typeof saved.bigEarth === 'boolean') S.bigEarth = saved.bigEarth;
    }
  } catch (e) { /* sessionStorage puede no estar disponible: el visor funciona igual */ }
  function persist() { try { sessionStorage.setItem(KEY, JSON.stringify(S)); } catch (e) { /* idem */ } }

  /* ------------------------------------------------------------------ datos */
  function b64(s) { var bin = atob(s), n = bin.length, u = new Uint8Array(n); for (var i = 0; i < n; i++) u[i] = bin.charCodeAt(i); return u; }
  var nx = D.nx, ny = D.ny, px = D.px_m, OX = D.obs.x, OY = D.obs.y;
  var Z16 = new Uint16Array(b64(D.z.b64).buffer);
  var H = new Float32Array(nx * ny), OK = new Uint8Array(nx * ny);
  (function () {
    var span = D.z.max - D.z.min;
    for (var k = 0; k < nx * ny; k++) { var q = Z16[k]; if (q === 65535) { H[k] = 0; OK[k] = 0; } else { H[k] = D.z.min + span * q / 65534; OK[k] = 1; } }
  })();
  var EXT = Math.max(nx, ny) * px;                                  // lado del recorte (m)
  function jOf(X) { return (X + OX - D.x0_m) / px; }
  function iOf(Z) { return (D.y0_m - OY + Z) / px; }                // Z = -(y - OY)
  function sampleH(X, Z) {                                           // altura física (bilineal) o NaN
    var j = jOf(X), i = iOf(Z);
    if (!(j >= 0 && i >= 0 && j <= nx - 1 && i <= ny - 1)) return NaN;
    var j0 = Math.min(Math.floor(j), nx - 2), i0 = Math.min(Math.floor(i), ny - 2), fx = j - j0, fy = i - i0, k = i0 * nx + j0;
    if (!(OK[k] && OK[k + 1] && OK[k + nx] && OK[k + nx + 1])) return NaN;
    return H[k] * (1 - fx) * (1 - fy) + H[k + 1] * fx * (1 - fy) + H[k + nx] * (1 - fx) * fy + H[k + nx + 1] * fx * fy;
  }
  var GZ = sampleH(0, 0); if (!isFinite(GZ)) GZ = D.obs.z;
  var CTXC = D.ctx || null, PAT = D.patch || null, OBS_GY = 0, FEATHER = 100;     // OBS_GY: suelo bajo el observador (parche) respecto al del recorte
  if (S.mode === 'wide' && !CTXC) S.mode = 'oblique';
  function curv(X, Z) { return (X * X + Z * Z) / (2 * R_M); }
  function smooth01(t) { t = Math.max(0, Math.min(1, t)); return t * t * (3 - 2 * t); }
  function terrainY(X, Z) { var h = sampleH(X, Z); return isFinite(h) ? (h - GZ - curv(X, Z)) * exagNow : -1e9; }
  function gridDir(azLocal, el) {                                    // vector unitario de escena para (azimut N→E, elevación)
    var g = (D.north_deg + azLocal) * DEG, e = el * DEG;
    return new THREE.Vector3(Math.sin(g) * Math.cos(e), Math.sin(e), -Math.cos(g) * Math.cos(e));
  }
  var exagNow = S.mode === 'observer' ? 1 : S.exag;

  /* ------------------------------------------------------------------ escena */
  var scene = new THREE.Scene();
  var camera = new THREE.PerspectiveCamera(45, 1, 3, 150000);
  var SKY_R = 60000;

  /* textura: R = foto (relleno por vecino más cercano), G = máscara de foto, B = iluminación calculada (0 sombra, 255 Sol) */
  var tex = null;
  var texImg = new Image();
  var ready = false;
  texImg.onload = function () {
    tex = new THREE.Texture(texImg);
    tex.minFilter = THREE.LinearMipmapLinearFilter; tex.magFilter = THREE.LinearFilter;
    tex.anisotropy = Math.min(8, renderer.capabilities.getMaxAnisotropy());
    tex.generateMipmaps = true; tex.flipY = true; tex.needsUpdate = true;
    ready = true; matP.uniforms.uTex.value = tex; buildPatch(); buildContext(); buildTerrain(1); applyAll(); startLoop();
  };
  texImg.onerror = function () { fail('No se pudo decodificar la textura del terreno.'); };
  texImg.src = 'data:image/png;base64,' + D.tex_png;

  var sunLocal = gridDir(D.sun.az_deg, D.sun.el_deg);               // el Sol visto por el observador
  var sunLight = new THREE.Vector3(Math.sin(D.sun.grid_az_deg * DEG) * Math.cos(D.sun.el_c_deg * DEG), Math.sin(D.sun.el_c_deg * DEG),
                                   -Math.cos(D.sun.grid_az_deg * DEG) * Math.cos(D.sun.el_c_deg * DEG));  // el Sol en el centro del recorte (sombras)
  var expo = 1 / Math.max(Math.sin(Math.max(D.sun.el_c_deg, 0) * DEG), 0.10);   // exposición automática: con el Sol rasante el relieve sigue legible

  var VERT = 'attribute vec3 nrm; varying vec3 vN; varying vec2 vUv; varying vec2 vXZ; varying float vD;\n' +
    'void main(){ vN = nrm; vUv = uv; vXZ = position.xz; vec4 mv = modelViewMatrix * vec4(position, 1.0); vD = length(mv.xyz); gl_Position = projectionMatrix * mv; }';
  var NOISE = [
    'float hash(vec2 p){ return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453); }',
    'float vn(vec2 p){ vec2 i = floor(p), f = fract(p); f = f * f * (3.0 - 2.0 * f);',
    '  return mix(mix(hash(i), hash(i + vec2(1.0, 0.0)), f.x), mix(hash(i + vec2(0.0, 1.0)), hash(i + vec2(1.0, 1.0)), f.x), f.y); }'].join('\n');
  var FRAG = [
    'precision highp float;',
    'uniform sampler2D uTex; uniform vec3 uSun; uniform float uExpo; uniform float uAmb; uniform vec4 uFlags; uniform vec2 uSize; uniform float uMicro;',
    'varying vec3 vN; varying vec2 vUv; varying vec2 vXZ; varying float vD;',
    NOISE,
    '#ifdef MICRO',
    'float mh(vec2 p){ return vn(p / 0.8) * 0.5 + vn(p / 2.3) * 0.35 + vn(p / 6.5) * 0.5; }',     // microrrelieve PROCEDURAL (no es dato): solo cambia la normal de sombreado
    '#endif',
    'vec3 ramp(float s){',
    '  vec3 c = mix(vec3(0.15,0.65,0.35), vec3(0.75,0.85,0.25), smoothstep(3.0, 9.0, s));',
    '  c = mix(c, vec3(1.0,0.75,0.2), smoothstep(9.0, 15.0, s));',
    '  c = mix(c, vec3(0.95,0.3,0.15), smoothstep(15.0, 25.0, s));',
    '  return c; }',
    'void main(){',
    '  vec3 n = normalize(vN);',
    '  vec4 t = texture2D(uTex, vUv);',
    '  float hasP = step(0.5, t.g) * uFlags.y;',
    '  float g = (hash(floor(vUv * uSize)) - 0.5) * 0.07;',                      // granulosidad muy sutil, solo donde no hay foto
    '  float alb = hasP > 0.5 ? pow(t.r, 2.2) * 1.15 : 0.17 * (1.0 + g);',
    '  float sl = degrees(acos(clamp(n.y, -1.0, 1.0)));',
    '#ifdef MICRO',
    '  float md = uMicro * (1.0 - smoothstep(60.0, 500.0, vD));',                // solo se nota de cerca
    '  if (md > 0.001) { vec2 e = vec2(0.25, 0.0);',
    '    float gx = (mh(vXZ + e) - mh(vXZ - e)) / 0.5, gz = (mh(vXZ + e.yx) - mh(vXZ - e.yx)) / 0.5;',
    '    n = normalize(n + md * 0.03 * vec3(-gx, 0.0, -gz)); }',
    '#endif',
    '  float ndl = max(dot(n, uSun), 0.0);',
    '  float lam = 1.0 - exp(-uExpo * ndl * 1.3);',
    '  float flt = 1.0 - exp(-uExpo * max(uSun.y, 0.0) * 1.3);',
    '  float dl = uFlags.x > 0.5 ? lam : flt;',
    '  float sh = uFlags.z > 0.5 ? t.b : 1.0;',
    '  float L = uAmb + dl * sh;',
    '  vec3 col = vec3(clamp(alb * L * 1.15, 0.0, 1.0));',
    '  col = pow(col, vec3(1.0 / 2.2));',
    '  if (uFlags.w > 0.5) { col = mix(col, ramp(sl) * (0.55 + 0.45 * sh), 0.6); }',
    '  gl_FragColor = vec4(col, 1.0);',
    '}'].join('\n');
  function terrainUniforms() {
    return { uTex: { value: null }, uSun: { value: sunLight.clone().normalize() }, uExpo: { value: expo }, uAmb: { value: 0.012 },
             uFlags: { value: new THREE.Vector4(1, 1, 1, 0) }, uSize: { value: new THREE.Vector2(nx, ny) }, uMicro: { value: 1 } };
  }
  var mat = new THREE.ShaderMaterial({ vertexShader: VERT, fragmentShader: FRAG, uniforms: terrainUniforms() });
  var matP = new THREE.ShaderMaterial({ vertexShader: VERT, fragmentShader: FRAG, uniforms: terrainUniforms(), defines: { MICRO: 1 },
                                        polygonOffset: true, polygonOffsetFactor: -2, polygonOffsetUnits: -2 });
  // contexto: gris oscuro sin foto, iluminación por vértice (calculada sobre el DEM de 80 m) y degradado hacia el color del fondo en el borde
  var VERT_C = 'attribute vec3 nrm; attribute float lit; varying vec3 vN; varying float vL; varying vec2 vXZ;\n' +
    'void main(){ vN = nrm; vL = lit; vXZ = position.xz; gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0); }';
  var FRAG_C = [
    'precision highp float;',
    'uniform vec3 uSun; uniform float uExpo; uniform float uAmb; uniform vec4 uFlags; uniform vec2 uCtr; uniform float uHalf; uniform vec3 uFade;',
    'varying vec3 vN; varying float vL; varying vec2 vXZ;',
    'void main(){',
    '  vec3 n = normalize(vN);',
    '  float ndl = max(dot(n, uSun), 0.0);',
    '  float lam = 1.0 - exp(-uExpo * ndl * 1.3);',
    '  float flt = 1.0 - exp(-uExpo * max(uSun.y, 0.0) * 1.3);',
    '  float dl = uFlags.x > 0.5 ? lam : flt;',
    '  float sh = uFlags.z > 0.5 ? vL : 1.0;',
    '  float L = uAmb + dl * sh;',
    '  vec3 col = pow(vec3(clamp(0.115 * L * 1.15, 0.0, 1.0)), vec3(1.0 / 2.2));',
    '  float r = max(abs(vXZ.x - uCtr.x), abs(vXZ.y - uCtr.y)) / uHalf;',
    '  col = mix(uFade, col, 1.0 - smoothstep(0.55, 0.98, r));',
    '  gl_FragColor = vec4(col, 1.0);',
    '}'].join('\n');
  var matC = new THREE.ShaderMaterial({ vertexShader: VERT_C, fragmentShader: FRAG_C, polygonOffset: true, polygonOffsetFactor: 3, polygonOffsetUnits: 3,
    uniforms: { uSun: { value: sunLight.clone().normalize() }, uExpo: { value: Math.min(expo, 1.0) }, uAmb: { value: 0.03 }, uFlags: { value: new THREE.Vector4(1, 0, 1, 0) },
                uCtr: { value: new THREE.Vector2() }, uHalf: { value: 1 }, uFade: { value: new THREE.Vector3(0, 0, 0) } } });
  var FADE_OBS = [0.047, 0.051, 0.067];                              // = color de la silueta del horizonte calculado (0x0c0d11)
  var ctxMesh = null, patchMesh = null, ctxLblP = null;
  function decode16(q) { return new Uint16Array(q.buffer, q.byteOffset, q.byteLength >> 1); }
  function buildContext() {                                          // malla de contexto: agujero donde está el recorte (sus alturas coinciden en el borde)
    if (!CTXC) return;
    var n = CTXC.n, Zq = decode16(b64(CTXC.z.b64)), Lq = b64(CTXC.lit_b64), span = CTXC.z.max - CTXC.z.min, st = CTXC.step_m;
    var h = new Float32Array(n * n), pos = new Float32Array(n * n * 3), nrm = new Float32Array(n * n * 3), lit = new Float32Array(n * n), r, c, k;
    for (k = 0; k < n * n; k++) { h[k] = CTXC.z.min + span * Zq[k] / 65534; lit[k] = Lq[k] / 255; }
    var xa = D.x0_m, xb = D.x0_m + (nx - 1) * px, yb = D.y0_m - (ny - 1) * px, ya = D.y0_m, inside = new Uint8Array(n * n);
    for (r = 0; r < n; r++) for (c = 0; c < n; c++) {
      k = r * n + c; var x = CTXC.x0_m + c * st, y = CTXC.y0_m - r * st, X = x - OX, Z = OY - y;
      pos[3 * k] = X; pos[3 * k + 1] = h[k] - GZ - curv(X, Z); pos[3 * k + 2] = Z;
      var cl = Math.max(c - 1, 0), cr = Math.min(c + 1, n - 1), ru = Math.max(r - 1, 0), rd = Math.min(r + 1, n - 1);
      var dxj = (h[r * n + cr] - h[r * n + cl]) / ((cr - cl) * st), dzi = (h[rd * n + c] - h[ru * n + c]) / ((rd - ru) * st), l = Math.sqrt(dxj * dxj + 1 + dzi * dzi);
      nrm[3 * k] = -dxj / l; nrm[3 * k + 1] = 1 / l; nrm[3 * k + 2] = -dzi / l;
      inside[k] = (x >= xa && x <= xb && y >= yb && y <= ya) ? 1 : 0;
    }
    var idx = [];
    for (r = 0; r < n - 1; r++) for (c = 0; c < n - 1; c++) {
      var a = r * n + c, b = a + 1, d = a + n, e = d + 1;
      if (inside[a] && inside[b] && inside[d] && inside[e]) continue;
      idx.push(a, d, b, b, d, e);
    }
    var g = new THREE.BufferGeometry();
    g.setAttribute('position', new THREE.BufferAttribute(pos, 3)); g.setAttribute('nrm', new THREE.BufferAttribute(nrm, 3));
    g.setAttribute('lit', new THREE.BufferAttribute(lit, 1)); g.setIndex(new THREE.BufferAttribute(new Uint32Array(idx), 1));
    ctxMesh = new THREE.Mesh(g, matC); ctxMesh.frustumCulled = false; scene.add(ctxMesh);
    var ccx = CTXC.x0_m + (n - 1) / 2 * st - OX, ccz = OY - (CTXC.y0_m - (n - 1) / 2 * st);
    matC.uniforms.uCtr.value.set(ccx, ccz); matC.uniforms.uHalf.value = CTXC.half_m;
    var kl = Math.floor(n * 0.12) * n + Math.floor(n * 0.3); ctxLblP = new THREE.Vector3(pos[3 * kl], pos[3 * kl + 1] + 600, pos[3 * kl + 2]);
  }
  function buildPatch() {                                            // suelo fino junto al observador; en su borde se funde con la malla del recorte
    if (!PAT) return;
    var n = PAT.n, Zq = decode16(b64(PAT.z.b64)), span = PAT.z.max - PAT.z.min, st = PAT.step_m, half = PAT.half_m, r, c, k;
    var hh = new Float32Array(n * n), X = new Float32Array(n * n), Z = new Float32Array(n * n);
    for (r = 0; r < n; r++) for (c = 0; c < n; c++) {
      k = r * n + c; X[k] = PAT.x0_m + c * st - OX; Z[k] = OY - (PAT.y0_m - r * st);
      var hp = PAT.z.min + span * Zq[k] / 65534, hc = sampleH(X[k], Z[k]), w = smooth01((half - Math.max(Math.abs(X[k]), Math.abs(Z[k]))) / FEATHER);
      hh[k] = isFinite(hc) ? hc + (hp - hc) * w : hp;
    }
    var pos = new Float32Array(n * n * 3), nrm = new Float32Array(n * n * 3), uv = new Float32Array(n * n * 2);
    for (r = 0; r < n; r++) for (c = 0; c < n; c++) {
      k = r * n + c;
      pos[3 * k] = X[k]; pos[3 * k + 1] = hh[k] - GZ - curv(X[k], Z[k]); pos[3 * k + 2] = Z[k];
      var cl = Math.max(c - 1, 0), cr = Math.min(c + 1, n - 1), ru = Math.max(r - 1, 0), rd = Math.min(r + 1, n - 1);
      var dxj = (hh[r * n + cr] - hh[r * n + cl]) / ((cr - cl) * st), dzi = (hh[rd * n + c] - hh[ru * n + c]) / ((rd - ru) * st), l = Math.sqrt(dxj * dxj + 1 + dzi * dzi);
      nrm[3 * k] = -dxj / l; nrm[3 * k + 1] = 1 / l; nrm[3 * k + 2] = -dzi / l;
      var j = (X[k] + OX - D.x0_m) / px, i = (D.y0_m - OY + Z[k]) / px;
      uv[2 * k] = Math.max(0, Math.min(1, (j + 0.5) / nx)); uv[2 * k + 1] = Math.max(0, Math.min(1, 1 - (i + 0.5) / ny));
    }
    var idx = new Uint32Array((n - 1) * (n - 1) * 6), q = 0;
    for (r = 0; r < n - 1; r++) for (c = 0; c < n - 1; c++) { var a = r * n + c, b = a + 1, d = a + n, e = d + 1; idx[q++] = a; idx[q++] = d; idx[q++] = b; idx[q++] = b; idx[q++] = d; idx[q++] = e; }
    var g = new THREE.BufferGeometry();
    g.setAttribute('position', new THREE.BufferAttribute(pos, 3)); g.setAttribute('nrm', new THREE.BufferAttribute(nrm, 3));
    g.setAttribute('uv', new THREE.BufferAttribute(uv, 2)); g.setIndex(new THREE.BufferAttribute(idx, 1));
    patchMesh = new THREE.Mesh(g, matP); patchMesh.frustumCulled = false; scene.add(patchMesh);
    OBS_GY = hh[(n >> 1) * n + (n >> 1)] - GZ;
  }
  var terrain = null, stride = 1;
  function inPatch(pos, v) { return Math.abs(pos[3 * v]) <= PAT.half_m && Math.abs(pos[3 * v + 2]) <= PAT.half_m; }
  function buildTerrain(st) {
    stride = st;
    var rows = [], cols = [], i, j;
    for (i = 0; i < ny; i += st) rows.push(i); if (rows[rows.length - 1] !== ny - 1) rows.push(ny - 1);
    for (j = 0; j < nx; j += st) cols.push(j); if (cols[cols.length - 1] !== nx - 1) cols.push(nx - 1);
    var nr = rows.length, nc = cols.length, n = nr * nc;
    var pos = new Float32Array(n * 3), nrm = new Float32Array(n * 3), uv = new Float32Array(n * 2), okv = new Uint8Array(n);
    function hv(ii, jj, fb) { ii = Math.min(Math.max(ii, 0), ny - 1); jj = Math.min(Math.max(jj, 0), nx - 1); var k = ii * nx + jj; return OK[k] ? H[k] : fb; }
    for (var r = 0; r < nr; r++) for (var c = 0; c < nc; c++) {
      i = rows[r]; j = cols[c]; var k = i * nx + j, v = r * nc + c;
      var X = D.x0_m + j * px - OX, Z = OY - D.y0_m + i * px;
      okv[v] = OK[k];
      pos[3 * v] = X; pos[3 * v + 1] = OK[k] ? H[k] - GZ - curv(X, Z) : 0; pos[3 * v + 2] = Z;
      var h0 = H[k], dxj = (hv(i, j + st, h0) - hv(i, j - st, h0)) / ((Math.min(j + st, nx - 1) - Math.max(j - st, 0)) * px),
          dzi = (hv(i + st, j, h0) - hv(i - st, j, h0)) / ((Math.min(i + st, ny - 1) - Math.max(i - st, 0)) * px);
      var l = Math.sqrt(dxj * dxj + 1 + dzi * dzi);
      nrm[3 * v] = -dxj / l; nrm[3 * v + 1] = 1 / l; nrm[3 * v + 2] = -dzi / l;
      uv[2 * v] = (j + 0.5) / nx; uv[2 * v + 1] = 1 - (i + 0.5) / ny;
    }
    var idx = [];
    for (r = 0; r < nr - 1; r++) for (c = 0; c < nc - 1; c++) {
      var a = r * nc + c, b = a + 1, d = a + nc, e = d + 1;
      if (!(okv[a] && okv[b] && okv[d] && okv[e])) continue;
      if (PAT && inPatch(pos, a) && inPatch(pos, b) && inPatch(pos, d) && inPatch(pos, e)) continue;       // ahí se dibuja el parche fino
      idx.push(a, d, b, b, d, e);
    }
    var g = new THREE.BufferGeometry();
    g.setAttribute('position', new THREE.BufferAttribute(pos, 3));
    g.setAttribute('nrm', new THREE.BufferAttribute(nrm, 3));
    g.setAttribute('uv', new THREE.BufferAttribute(uv, 2));
    g.setIndex(new THREE.BufferAttribute(new Uint32Array(idx), 1));
    if (terrain) { terrain.geometry.dispose(); terrain.geometry = g; }
    else { terrain = new THREE.Mesh(g, mat); terrain.frustumCulled = false; scene.add(terrain); }
    mat.uniforms.uTex.value = tex;
    applyExag();
    setText('mesh-info', 'Malla ' + nc + '×' + nr + ' vértices (' + (px * st).toFixed(0) + ' m)');
  }

  /* ------------------------------------------------------------------ cielo: estrellas, Sol, Tierra, horizonte calculado */
  var sky = new THREE.Group(); scene.add(sky);
  function mulberry(a) { return function () { a |= 0; a = a + 0x6D2B79F5 | 0; var t = Math.imul(a ^ a >>> 15, 1 | a); t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t; return ((t ^ t >>> 14) >>> 0) / 4294967296; }; }
  var stars;
  (function () {
    var rnd = mulberry(20260614), N = 2600, p = new Float32Array(N * 3), col = new Float32Array(N * 3);
    for (var i = 0; i < N; i++) {
      var u = rnd() * 2 - 1, th = rnd() * 2 * Math.PI, s = Math.sqrt(1 - u * u), b = 0.25 + 0.75 * Math.pow(rnd(), 3), w = rnd();
      p[3 * i] = s * Math.cos(th) * SKY_R * 0.98; p[3 * i + 1] = u * SKY_R * 0.98; p[3 * i + 2] = s * Math.sin(th) * SKY_R * 0.98;
      col[3 * i] = b * (0.85 + 0.15 * w); col[3 * i + 1] = b * 0.92; col[3 * i + 2] = b * (1.0 - 0.15 * w);
    }
    var g = new THREE.BufferGeometry();
    g.setAttribute('position', new THREE.BufferAttribute(p, 3)); g.setAttribute('color', new THREE.BufferAttribute(col, 3));
    stars = new THREE.Points(g, new THREE.PointsMaterial({ size: 1.7, sizeAttenuation: false, vertexColors: true }));
    stars.frustumCulled = false; sky.add(stars);
  })();
  function radialTex(stops, size) {
    var c = document.createElement('canvas'); c.width = c.height = size || 128; var x = c.getContext('2d'), h = c.width / 2;
    var g = x.createRadialGradient(h, h, 0, h, h, h); stops.forEach(function (s) { g.addColorStop(s[0], s[1]); });
    x.fillStyle = g; x.fillRect(0, 0, c.width, c.height); return new THREE.CanvasTexture(c);
  }
  var sunR = SKY_R * Math.tan(D.sun.radius_deg * DEG);
  var sunDisc = new THREE.Sprite(new THREE.SpriteMaterial({ map: radialTex([[0, '#fff'], [0.9, '#fff8e0'], [1, 'rgba(255,240,200,0)']]), transparent: true, depthWrite: false }));
  sunDisc.scale.set(sunR * 2.2, sunR * 2.2, 1);
  var sunGlow = new THREE.Sprite(new THREE.SpriteMaterial({ map: radialTex([[0, 'rgba(255,230,170,.9)'], [0.12, 'rgba(255,200,120,.45)'], [0.4, 'rgba(255,170,90,.12)'], [1, 'rgba(255,150,80,0)']], 256),
                                                          transparent: true, depthWrite: false, blending: THREE.AdditiveBlending }));
  sunGlow.scale.set(sunR * 40, sunR * 40, 1);
  var sunPos = sunLocal.clone().multiplyScalar(SKY_R); sunDisc.position.copy(sunPos); sunGlow.position.copy(sunPos);
  sky.add(sunGlow); sky.add(sunDisc);

  function earthTexture() {                                           // Tierra procedural (sin imágenes externas): océano, continentes, nubes, casquetes
    var W = 512, Hh = 256, c = document.createElement('canvas'); c.width = W; c.height = Hh; var x = c.getContext('2d'), rnd = mulberry(1971);
    var g = x.createLinearGradient(0, 0, 0, Hh); g.addColorStop(0, '#3d6fb5'); g.addColorStop(0.5, '#1a4f9f'); g.addColorStop(1, '#3d6fb5');
    x.fillStyle = g; x.fillRect(0, 0, W, Hh);
    function blob(cx, cy, r, color, a, n) { x.fillStyle = color; x.globalAlpha = a; for (var i = 0; i < n; i++) { x.beginPath(); x.ellipse(cx + (rnd() - 0.5) * r * 1.6, cy + (rnd() - 0.5) * r, r * (0.2 + rnd() * 0.5), r * (0.15 + rnd() * 0.4), rnd() * 3, 0, 6.3); x.fill(); } }
    [[110, 90, 55], [180, 150, 45], [300, 100, 60], [340, 160, 40], [430, 80, 40], [250, 60, 28]].forEach(function (b) { blob(b[0], b[1], b[2], '#5b7f3b', 0.95, 14); blob(b[0], b[1], b[2] * 0.7, '#a58b55', 0.55, 7); });
    blob(256, 6, 30, '#f4f8ff', 1, 16); blob(256, 250, 34, '#f4f8ff', 1, 18);
    for (var k = 0; k < 7; k++) blob(rnd() * W, 40 + rnd() * 176, 40, '#ffffff', 0.5, 12);
    x.globalAlpha = 1; return new THREE.CanvasTexture(c);
  }
  var earthAng = D.earth.radius_deg, earthMat = new THREE.MeshLambertMaterial({ map: earthTexture() });
  var earth = new THREE.Mesh(new THREE.SphereGeometry(1, 48, 24), earthMat);
  var earthDir = gridDir(D.earth.az_deg, D.earth.el_deg);
  earth.position.copy(earthDir.clone().multiplyScalar(SKY_R)); sky.add(earth);
  function sizeEarth() { var s = SKY_R * Math.tan(earthAng * DEG) * (S.bigEarth ? 7 : 1); earth.scale.set(s, s, s); }
  var sunLamp = new THREE.DirectionalLight(0xffffff, 1.35); sunLamp.position.copy(sunLocal); scene.add(sunLamp);
  scene.add(new THREE.AmbientLight(0x6f86a8, 0.12));

  // horizonte calculado (terreno FUERA del recorte): silueta oscura a 55 km que tapa el Sol y la Tierra cuando están bajo él
  var horizon = null;
  (function () {
    var A = D.horizon.az, E = D.horizon.el, n = A.length; if (!n) return;
    var pos = [], idx = [], RH = SKY_R * 0.92, bottom = -RH * 3;
    for (var i = 0; i <= n; i++) {
      var k = i % n, g = (D.north_deg + A[k]) * DEG, top = Math.tan(Math.max(E[k], -20) * DEG) * RH;
      var X = Math.sin(g) * RH, Z = -Math.cos(g) * RH;
      pos.push(X, top, Z, X, bottom, Z);
      if (i < n) { var a = 2 * i, b = a + 1, c = a + 2, d = a + 3; idx.push(a, b, c, c, b, d); }
    }
    var g2 = new THREE.BufferGeometry();
    g2.setAttribute('position', new THREE.BufferAttribute(new Float32Array(pos), 3)); g2.setIndex(idx);
    horizon = new THREE.Mesh(g2, new THREE.MeshBasicMaterial({ color: 0x0c0d11, side: THREE.DoubleSide }));
    horizon.frustumCulled = false; sky.add(horizon);
  })();
  function horizonAt(az) {                                            // elevación (°) del horizonte calculado en el acimut N→E dado
    var A = D.horizon.az, E = D.horizon.el, n = A.length; if (!n) return -90;
    var a = ((az % 360) + 360) % 360, step = 360 / n, f = a / step, i0 = Math.floor(f) % n, i1 = (i0 + 1) % n, t = f - Math.floor(f);
    return E[i0] * (1 - t) + E[i1] * t;
  }

  /* ------------------------------------------------------------------ marcador del observador */
  var marker = new THREE.Group(); scene.add(marker);
  (function () {
    var beamH = EXT * 0.28, rad = EXT * 0.0016;
    var beam = new THREE.Mesh(new THREE.CylinderGeometry(rad, rad * 1.8, beamH, 12, 1, true),
      new THREE.MeshBasicMaterial({ color: 0x66ccff, transparent: true, opacity: 0.55, blending: THREE.AdditiveBlending, depthWrite: false }));
    beam.position.y = beamH / 2; marker.add(beam);
    var core = new THREE.Sprite(new THREE.SpriteMaterial({ map: radialTex([[0, 'rgba(255,255,255,1)'], [0.25, 'rgba(120,210,255,.8)'], [1, 'rgba(60,160,255,0)']]),
      transparent: true, depthTest: false, depthWrite: false, blending: THREE.AdditiveBlending }));
    core.scale.set(EXT * 0.05, EXT * 0.05, 1); core.position.y = EXT * 0.004; core.renderOrder = 10; marker.add(core);
    [0.014, 0.026].forEach(function (f, n) {
      var ring = new THREE.Mesh(new THREE.RingGeometry(EXT * f, EXT * (f + 0.0016), 64),
        new THREE.MeshBasicMaterial({ color: 0x4cc2ff, transparent: true, opacity: 0.85 - 0.3 * n, side: THREE.DoubleSide, depthTest: false, depthWrite: false, blending: THREE.AdditiveBlending }));
      ring.rotation.x = -Math.PI / 2; ring.position.y = EXT * 0.0008; ring.renderOrder = 9; marker.add(ring);
    });
  })();

  /* ------------------------------------------------------------------ etiquetas flotantes (DOM, textContent: nada de HTML) */
  var LBL = [], labelsBox = $('labels');
  function addLabel(text, cls, pos, extra) {
    var e = document.createElement('div'); e.className = 'lbl ' + cls; e.textContent = text; labelsBox.appendChild(e);
    var o = { el: e, p: pos, cls: cls, kind: extra && extra.kind, lift: extra && extra.lift, X: extra && extra.X, Z: extra && extra.Z }; LBL.push(o); return o;
  }
  var obsLbl = addLabel(D.obs.label, 'obs', new THREE.Vector3(0, EXT * 0.3, 0), { kind: 'obs' });
  D.names.forEach(function (n) { addLabel(n[0], 'name', new THREE.Vector3(), { kind: 'name', X: n[1] - OX, Z: OY - n[2], lift: EXT * 0.012 }); });
  var noPhotoLbl = null;
  if (D.photo.nophoto_xz) noPhotoLbl = addLabel(D.photo.psr_pct >= 50 ? 'sin foto: sombra permanente' : 'sin foto en esta zona', 'nophoto', new THREE.Vector3(), { kind: 'nophoto', X: D.photo.nophoto_xz[0], Z: D.photo.nophoto_xz[1], lift: EXT * 0.01 });
  var ctxLbl = CTXC ? addLabel('Terreno lejano: modelo LOLA de 80 m', 'ctxl', new THREE.Vector3(), { kind: 'ctx' }) : null;
  var sunLbl = addLabel('Sol', 'sky', new THREE.Vector3(), { kind: 'sun' });
  var earthLbl = addLabel('Tierra', 'earth', new THREE.Vector3(), { kind: 'earth' });
  function placeLabels() {
    var W = renderer.domElement.clientWidth, Hh = renderer.domElement.clientHeight, obsView = S.mode === 'observer', v = new THREE.Vector3();
    LBL.forEach(function (o) {
      var show = true;
      if (o.kind === 'obs') { show = !obsView; o.p.set(0, EXT * 0.3 * 1, 0); }
      else if (o.kind === 'name' || o.kind === 'nophoto') {
        show = S.layers.names && (o.kind === 'name' || S.layers.photo);
        if (show) { var ty = terrainY(o.X, o.Z); if (ty < -1e8) show = false; else { o.p.set(o.X, ty + o.lift, o.Z); show = visibleFrom(o.p); } }
      } else if (o.kind === 'ctx') {
        show = S.mode !== 'observer' && S.layers.ctx && !!ctxLblP; if (show) o.p.set(ctxLblP.x, ctxLblP.y * exagNow, ctxLblP.z);
      } else if (o.kind === 'sun' || o.kind === 'earth') {
        var d = o.kind === 'sun' ? sunLocal : earthDir, az = o.kind === 'sun' ? D.sun.az_deg : D.earth.az_deg, el = o.kind === 'sun' ? D.sun.el_deg : D.earth.el_deg;
        show = obsView && el > horizonAt(az) + 0.05;
        o.p.copy(d).multiplyScalar(SKY_R).add(camera.position);
      }
      if (!show) { o.el.hidden = true; return; }
      v.copy(o.p).project(camera);
      if (v.z > 1 || v.z < -1 || Math.abs(v.x) > 1.05 || Math.abs(v.y) > 1.05) { o.el.hidden = true; return; }
      o.el.hidden = false; o.el.style.left = ((v.x * 0.5 + 0.5) * W) + 'px'; o.el.style.top = ((-v.y * 0.5 + 0.5) * Hh) + 'px';
    });
  }
  function visibleFrom(p) {                                           // oclusión por el propio relieve (marcha por el mapa de alturas)
    var c = camera.position, n = 36;
    for (var s = 1; s < n; s++) {
      var t = s / n, x = c.x + (p.x - c.x) * t, y = c.y + (p.y - c.y) * t, z = c.z + (p.z - c.z) * t;
      if (terrainY(x, z) > y + EXT * 0.0015) return false;
    }
    return true;
  }

  /* ------------------------------------------------------------------ cámara */
  var controls = new THREE.OrbitControls(camera, renderer.domElement);
  controls.enableDamping = true; controls.dampingFactor = 0.12; controls.screenSpacePanning = false;
  controls.minDistance = Math.max(40, EXT * 0.012); controls.maxPolarAngle = 86 * DEG;
  var CTX_EXT = CTXC ? 2 * CTXC.half_m : 0;
  controls.maxDistance = CTXC ? CTX_EXT * 1.15 : EXT * 2.6;      // con contexto: la cámara no se aleja lo bastante para ver el borde del terreno lejano
  var obsAz = S.az, obsPitch = 1.5, obsFov = 62;
  function setMode(m, silent) {
    if (m === 'wide' && !CTXC) m = 'oblique';
    S.mode = m; exagNow = m === 'observer' ? 1 : S.exag;
    applyExag();
    camera.up.set(0, 1, 0);
    if (m === 'observer') {
      controls.enabled = false; camera.near = 0.3; camera.far = 150000; camera.fov = obsFov;
      camera.position.set(0, OBS_GY + D.obs.h, 0); orientObserver();
    } else {
      controls.enabled = true; camera.near = Math.max(EXT * 0.0006, 2); camera.far = 150000; camera.fov = 45;
      var d = m === 'wide' ? CTX_EXT * 0.55 : EXT * (m === 'top' ? 1.2 : 0.95), pol = (m === 'top' ? 1.0 : m === 'wide' ? 52 : 62) * DEG;
      controls.target.set(0, 0, 0);
      camera.position.set(0, d * Math.cos(pol), d * Math.sin(pol));
      camera.lookAt(controls.target); controls.update();
    }
    camera.updateProjectionMatrix(); applyAll(); updateUi(); dirty = true; persist();
  }
  function applyExag() { [terrain, patchMesh, ctxMesh].forEach(function (o) { if (o) o.scale.y = exagNow; }); }
  function orientObserver() {
    var d = gridDir(obsAz, obsPitch); camera.lookAt(camera.position.clone().add(d)); dirty = true;
  }
  var drag = null; var cv = $('gl');
  cv.addEventListener('pointerdown', function (e) { if (S.mode === 'observer') { drag = { x: e.clientX, y: e.clientY }; cv.setPointerCapture(e.pointerId); cv.style.cursor = 'grabbing'; } });
  cv.addEventListener('pointermove', function (e) {
    if (!drag) return; var k = obsFov / 62;
    obsAz = ((obsAz - (e.clientX - drag.x) * 0.2 * k) % 360 + 360) % 360; obsPitch = Math.max(-30, Math.min(60, obsPitch + (e.clientY - drag.y) * 0.15 * k));
    drag = { x: e.clientX, y: e.clientY }; S.az = obsAz; $('az').value = Math.round(obsAz); updateUi(); orientObserver();
  });
  cv.addEventListener('pointerup', function () { drag = null; cv.style.cursor = ''; persist(); });
  cv.addEventListener('wheel', function (e) {
    if (S.mode !== 'observer') return; e.preventDefault();
    obsFov = Math.max(15, Math.min(100, obsFov * (e.deltaY > 0 ? 1.08 : 0.92))); camera.fov = obsFov; camera.updateProjectionMatrix(); dirty = true;
  }, { passive: false });
  cv.addEventListener('dblclick', function () { obsFov = 62; obsPitch = 1.5; setMode(S.mode); });
  cv.addEventListener('keydown', function (e) {
    if (S.mode !== 'observer') return;
    if (e.key === 'ArrowLeft' || e.key === 'ArrowRight') { obsAz = (obsAz + (e.key === 'ArrowRight' ? 3 : -3) + 360) % 360; S.az = obsAz; $('az').value = Math.round(obsAz); updateUi(); orientObserver(); e.preventDefault(); }
  });
  controls.addEventListener('change', function () { dirty = true; });
  controls.addEventListener('end', function () { /* recorta el desplazamiento al recorte */
    var t = controls.target, m = EXT / 2; t.x = Math.max(-m, Math.min(m, t.x)); t.z = Math.max(-m, Math.min(m, t.z)); t.y = Math.max(-200, Math.min(EXT * 0.2, t.y));
  });

  /* ------------------------------------------------------------------ interfaz */
  function fmt(x, d) { return (isFinite(x) ? x : NaN).toFixed(d).replace('.', ','); }
  function applyAll() {
    var L = S.layers; mat.uniforms.uFlags.value.set(L.relief ? 1 : 0, L.photo ? 1 : 0, L.shadow ? 1 : 0, L.slope ? 1 : 0);
    matC.uniforms.uFlags.value.set(L.relief ? 1 : 0, 0, L.shadow ? 1 : 0, 0); matC.uniforms.uFade.value.fromArray(S.mode === 'observer' ? FADE_OBS : [0, 0, 0]);
    matP.uniforms.uMicro.value = L.micro ? 1 : 0; if (ctxMesh) ctxMesh.visible = L.ctx;
    stars.visible = L.stars; if (horizon) horizon.visible = L.horizon && S.mode === 'observer';   // la silueta solo tiene sentido desde el observador
    sunGlow.visible = D.sun.el_deg > horizonAt(D.sun.az_deg) || S.mode !== 'observer';   // sin atmósfera no hay resplandor del Sol tapado
    marker.visible = S.mode !== 'observer';                       // el observador no se ve a sí mismo
    sizeEarth(); dirty = true;
  }
  function updateUi() {
    ['top', 'oblique', 'wide', 'observer'].forEach(function (m) { $('m-' + m).setAttribute('aria-pressed', S.mode === m ? 'true' : 'false'); });
    $('obs-ctl').hidden = S.mode !== 'observer'; $('exag-ctl').hidden = S.mode === 'observer';
    $('scale').hidden = S.mode === 'observer';
    setText('az-val', Math.round(obsAz) + '° (N 0°, E 90°)');
    setText('exag-val', '×' + fmt(S.exag, 1));
    var hz = horizonAt(D.sun.az_deg), covered = D.sun.el_deg <= hz;
    var el = $('sun-state'); el.textContent = D.sun.el_deg < 0 ? 'bajo el horizonte local' : (covered ? 'tapado por el horizonte (a ' + fmt(hz, 1) + '°) en este instante; la ventana de misión puede tenerlo visible otras horas' : 'visible');
    el.className = covered ? 'hid' : '';
    var hz2 = horizonAt(D.earth.az_deg), cov2 = D.earth.el_deg <= hz2;
    var e2 = $('earth-state'); e2.textContent = D.earth.el_deg < 0 ? 'bajo el horizonte local' : (cov2 ? 'tapada por el horizonte (a ' + fmt(hz2, 1) + '°)' : 'visible');
    e2.className = cov2 ? 'hid' : '';
    if (S.mode === 'observer') setText('hud-top', 'Vista del observador a ' + fmt(D.obs.h, 1) + ' m · mirando al acimut ' + Math.round(obsAz) + '° · campo ' + Math.round(obsFov) + '°');
    else setText('hud-top', S.mode === 'top' ? 'Vista cenital' : S.mode === 'wide' ? 'Vista orbital amplia: recorte y terreno lejano' : 'Vista oblicua');
    var lg = [];
    if (CTXC && S.layers.ctx) lg.push('Terreno lejano: modelo LOLA de 80 m, sin foto.');
    if (PAT && S.layers.micro) lg.push('Suelo cercano: relieve de 5 m interpolado a ' + PAT.step_m + ' m; microrrelieve procedural: no es dato.');
    setText('legend', lg.join(' '));
  }
  function nice(m) { var p = Math.pow(10, Math.floor(Math.log10(m))), f = m / p; return (f >= 5 ? 5 : f >= 2 ? 2 : 1) * p; }
  function updateScaleNorth() {
    if (S.mode !== 'observer') {
      var dist = camera.position.distanceTo(controls.target), mpp = 2 * dist * Math.tan(camera.fov * DEG / 2) / renderer.domElement.clientHeight;
      var len = nice(mpp * 110); $('scale-bar').style.width = (len / mpp) + 'px'; setText('scale-txt', len >= 1000 ? (len / 1000) + ' km' : len + ' m');
    }
    var a = new THREE.Vector3(0, 0, 0), b = new THREE.Vector3(Math.sin(D.north_deg * DEG), 0, -Math.cos(D.north_deg * DEG)).multiplyScalar(EXT * 0.05);
    if (S.mode === 'observer') { a.copy(camera.position); b.add(a); b.y = a.y; }
    a.project(camera); b.project(camera);
    var ang = Math.atan2((b.x - a.x) * renderer.domElement.clientWidth, (b.y - a.y) * renderer.domElement.clientHeight) * 180 / Math.PI;
    $('north-i').style.transform = 'rotate(' + ang + 'deg)';
  }
  [['relief', 'l-relief'], ['photo', 'l-photo'], ['shadow', 'l-shadow'], ['slope', 'l-slope'], ['names', 'l-names'], ['stars', 'l-stars'], ['horizon', 'l-horizon'], ['ctx', 'l-ctx'], ['micro', 'l-micro']].forEach(function (p) {
    var cb = $(p[1]); cb.checked = S.layers[p[0]];
    if ((p[0] === 'ctx' && !CTXC) || (p[0] === 'micro' && !PAT)) { cb.disabled = true; cb.checked = false; cb.title = 'No hay datos para esta capa en este punto'; return; }
    cb.addEventListener('change', function () {
      S.layers[p[0]] = cb.checked; applyAll(); updateUi(); persist();
      if (p[0] === 'names') for (var i = 0; i < LBL.length; i++) if (LBL[i].kind === 'name') LBL[i].el.hidden = !cb.checked;
    });
  });
  var bigCb = $('l-big'); bigCb.checked = S.bigEarth; bigCb.addEventListener('change', function () { S.bigEarth = bigCb.checked; sizeEarth(); dirty = true; persist(); });
  ['top', 'oblique', 'wide', 'observer'].forEach(function (m) { $('m-' + m).addEventListener('click', function () { setMode(m); }); });
  if (!CTXC) { $('m-wide').disabled = true; $('m-wide').title = 'No hay terreno lejano (falta el DEM de 80 m)'; }
  var azIn = $('az'); azIn.value = Math.round(S.az);
  azIn.addEventListener('input', function () { obsAz = +azIn.value; S.az = obsAz; updateUi(); if (S.mode === 'observer') orientObserver(); persist(); });
  $('az-sun').addEventListener('click', function () { obsAz = D.sun.az_deg; azIn.value = Math.round(obsAz); S.az = obsAz; updateUi(); orientObserver(); persist(); });
  $('az-earth').addEventListener('click', function () { obsAz = D.earth.az_deg; azIn.value = Math.round(obsAz); S.az = obsAz; updateUi(); orientObserver(); persist(); });
  var exIn = $('exag'); exIn.value = S.exag;
  exIn.addEventListener('input', function () { S.exag = +exIn.value; if (S.mode !== 'observer') { exagNow = S.exag; applyExag(); } updateUi(); dirty = true; persist(); });
  $('reset').addEventListener('click', function () { obsFov = 62; obsPitch = 1.5; setMode(S.mode); });
  $('read').addEventListener('click', function () { var d = $('desc'); d.hidden = !d.hidden; $('read').setAttribute('aria-pressed', d.hidden ? 'false' : 'true'); });
  setText('desc-txt', D.description); setText('sr-desc', D.description);
  setText('i-name', D.obs.label); setText('i-when', D.when_utc);
  setText('i-sun', 'az ' + fmt(D.sun.az_deg, 1) + '° · el ' + fmt(D.sun.el_deg, 2) + '°');
  setText('i-earth', 'az ' + fmt(D.earth.az_deg, 1) + '° · el ' + fmt(D.earth.el_deg, 2) + '°');
  setText('i-lit', fmt(D.lit_pct, 0) + ' %');
  setText('i-pos', D.obs.pos_text); setText('notice', D.photo.notice);
  setText('chip', 'Foto: ' + fmt(D.photo.photo_pct, 0) + ' % del recorte' + (D.photo.psr_pct >= 50 && D.photo.photo_pct < 97 ? ' · lo que falta es sombra permanente (PSR)' : ''));
  setText('photo-detail', D.photo.detail);
  obsAz = S.az;

  /* ------------------------------------------------------------------ bucle y rendimiento */
  var dirty = true, started = false;
  function resize() {
    var w = $('stage').clientWidth, h = $('stage').clientHeight; if (!w || !h) return;
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2)); renderer.setSize(w, h, false);
    camera.aspect = w / h; camera.updateProjectionMatrix(); dirty = true;
  }
  if (window.ResizeObserver) new ResizeObserver(resize).observe($('stage')); window.addEventListener('resize', resize);
  function timeRender() {                                             // ms por imagen (con vaciado de la cola de la GPU)
    var gl = renderer.getContext(), t0 = performance.now(), n = 4;
    for (var i = 0; i < n; i++) renderer.render(scene, camera);
    gl.finish(); return (performance.now() - t0) / n;
  }
  function startLoop() {
    if (started) return; started = true; resize(); setMode(S.mode, true); applyAll();
    var ms = timeRender(), tries = 0;
    while (ms > 70 && stride < 4 && tries < 2) { buildTerrain(stride * 2); setText('perf-info', 'WebGL lento (' + Math.round(ms) + ' ms/imagen): malla reducida'); ms = timeRender(); tries++; }
    renderer.domElement.addEventListener('webglcontextlost', function (e) { e.preventDefault(); fail('Se perdió el contexto WebGL. Recarga la página o usa la «Vista alternativa» de Plotly.'); });
    (function loop() {
      requestAnimationFrame(loop);
      var ch = controls.enabled ? controls.update() : false;
      if (dirty || ch) {
        if (S.mode !== 'observer') {                              // plano cercano proporcional a la distancia: sin z-fighting en las vistas lejanas
          var nr = Math.min(Math.max(camera.position.distanceTo(controls.target) * 0.01, 2), 400);
          if (Math.abs(nr - camera.near) > camera.near * 0.2) { camera.near = nr; camera.updateProjectionMatrix(); }
        }
        sky.position.copy(camera.position); marker.position.set(0, 0, 0);
        renderer.render(scene, camera); placeLabels(); updateScaleNorth(); dirty = false;
      }
    })();
    window.__lsiReady = { stride: stride, ms: ms, nx: nx, ny: ny, ctx: !!ctxMesh, patch: !!patchMesh };
  }
  window.__lsi = { setMode: setMode, get state() { return S; }, camera: camera, scene: scene };
})();
