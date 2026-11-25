// Full-stage fragment shader: ambient aurora + living orb + state effects.
// Coordinates are in orb units: the orb's edge sits at r = 1.

export const VERT = `
attribute vec2 aPos;
void main() { gl_Position = vec4(aPos, 0.0, 1.0); }
`

export const FRAG = `
precision highp float;
uniform vec2 uCenter;      // orb centre, canvas px (origin bottom-left)
uniform float uRadius;     // orb radius, canvas px
uniform float uTime;
uniform vec3 uC1, uC2, uC3; // highlight, body, depth (eased per state)
uniform vec3 uBg;
uniform float uAmp;        // overall loudness of whoever is speaking
uniform float uLow, uMid, uHigh; // speech bands
uniform float uGlow;       // ambient aurora strength
uniform float uRipple;     // user voice rings
uniform float uShimmer;    // thinking: rim sweep
uniform float uArc;        // connecting: travelling arc
uniform float uBloom;      // bank confirmed: 1 -> 0
uniform vec3 uAccent;      // second hue per state (blobs + stage glow)
uniform float uPebble;     // pebble drop progress 0 -> 1 (>= 1 when idle)
uniform vec3 uPebbleCol;   // ripple tint

float hash(vec2 p) {
  p = fract(p * vec2(123.34, 456.21));
  p += dot(p, p + 45.32);
  return fract(p.x * p.y);
}
float noise(vec2 p) {
  vec2 i = floor(p), f = fract(p);
  vec2 u = f * f * (3.0 - 2.0 * f);
  return mix(mix(hash(i), hash(i + vec2(1.0, 0.0)), u.x),
             mix(hash(i + vec2(0.0, 1.0)), hash(i + vec2(1.0, 1.0)), u.x), u.y);
}
float fbm(vec2 p) {
  float v = 0.0, a = 0.5;
  mat2 m = mat2(1.6, 1.2, -1.2, 1.6);
  for (int i = 0; i < 4; i++) { v += a * noise(p); p = m * p; a *= 0.5; }
  return v;
}

void main() {
  vec2 frag = gl_FragCoord.xy;
  vec2 p = (frag - uCenter) / uRadius;
  float r = length(p);
  float ang = atan(p.y, p.x);
  float t = uTime;
  const vec3 GREEN = vec3(0.29, 0.87, 0.5);

  // This canvas is a transparent light layer over the page gradient (premultiplied alpha).
  vec3 col = vec3(0.0);
  float a = 0.0;

  // ---- pebble: soft water rings spreading from the orb
  float wave = 0.0;
  float rings = 0.0;
  if (uPebble < 1.0) {
    float fade = 1.0 - uPebble;
    for (int k = 0; k < 3; k++) {
      float R = 1.05 + uPebble * 3.4 - float(k) * 0.42;
      float d = r - R;
      float env = exp(-d * d * 22.0) * fade * step(1.05, R);
      wave += sin(d * 22.0) * env;
      rings += smoothstep(0.06, 0.0, abs(d)) * env;
    }
  }
  vec2 pw = p * (1.0 + wave * 0.035);
  float rw = length(pw);

  // ---- ambient aurora around the orb
  vec2 q = pw * 0.32;
  float n1 = fbm(q * 1.4 + vec2(t * 0.04, -t * 0.03));
  float n2 = fbm(q * 2.1 - vec2(t * 0.03, t * 0.04) + n1 * 1.3);
  vec3 aur = mix(uC3, uC2, smoothstep(0.25, 0.8, n1));
  aur = mix(aur, uAccent, smoothstep(0.45, 0.9, n2) * 0.4);
  float fog = exp(-pow(rw / 2.1, 2.0)) * (0.22 + uGlow * 0.25);
  col += aur * fog; a += fog;

  col += uPebbleCol * rings * 0.25; a += rings * 0.25;

  // user voice: faint rings travelling outward
  for (int k = 0; k < 3; k++) {
    float ph = fract(t * 0.5 + float(k) / 3.0);
    float ring = smoothstep(0.03, 0.0, abs(r - (1.08 + ph * 0.9))) * (1.0 - ph) * uRipple * 0.3;
    col += uC1 * ring; a += ring;
  }

  // bank confirmed: a soft green wash
  float gw = exp(-pow(r / 2.2, 2.0)) * uBloom * 0.18;
  col += GREEN * gw; a += gw;

  // ---- the orb: always a perfect circle
  float aa = 1.5 / uRadius;
  float inside = smoothstep(1.0 + aa, 1.0 - aa, r);

  float h = exp(-pow(max(r - 1.0, 0.0) / 0.22, 2.0)) * 0.16 * (1.0 - inside);
  col += mix(uC2, uAccent, 0.35) * h; a += h;

  // interior: a slowly rotating gradient with colour drifting through it
  float rot = t * 0.22;
  vec2 axis = vec2(cos(rot + 2.1), sin(rot + 2.1));
  float gy = clamp(0.5 - dot(p, axis) * 0.5, 0.0, 1.0);
  vec3 orb = mix(uC1, uC2, smoothstep(0.05, 0.55, gy));
  orb = mix(orb, uC3, smoothstep(0.5, 1.0, gy));
  float sp = 1.0 + uMid * 0.5;
  vec2 b1 = 0.48 * vec2(cos(t * 0.31 * sp + 1.0), sin(t * 0.27 * sp));
  vec2 b2 = 0.52 * vec2(cos(t * 0.23 * sp + 3.0), sin(t * 0.35 * sp + 2.0));
  vec2 b3 = 0.42 * vec2(cos(t * 0.41 * sp + 5.0), sin(t * 0.19 * sp + 4.0));
  orb = mix(orb, uAccent, exp(-dot(p - b1, p - b1) / 0.2) * 0.75);
  orb = mix(orb, uC1, exp(-dot(p - b2, p - b2) / 0.14) * 0.45);
  orb = mix(orb, uC3, exp(-dot(p - b3, p - b3) / 0.16) * 0.45);
  orb += (fbm(p * 1.3 + vec2(t * 0.22 * sp, -t * 0.15 * sp)) - 0.5) * 0.16; // visible flow

  float rn = min(r, 1.0);
  float z = sqrt(max(0.0, 1.0 - rn * rn));
  orb *= (0.8 + 0.2 * z) * 0.9;                                                  // gentle depth, never glaring
  orb += vec3(1.0) * exp(-pow(length(p - vec2(-0.36, 0.42)) / 0.34, 2.0)) * 0.08; // soft glass highlight
  orb += mix(uC1, uAccent, 0.4) * smoothstep(0.75, 1.0, rn) * 0.14;              // steady rim
  orb += vec3(1.0) * pow(0.5 + 0.5 * cos(ang - t * 1.4), 14.0) * smoothstep(0.7, 1.0, rn) * uShimmer * 0.3;
  orb += GREEN * uBloom * 0.15 * z;

  col = mix(col, orb, inside);
  a = mix(a, 1.0, inside);

  // connecting: a thin arc travelling around the orb
  if (uArc > 0.0) {
    float a2 = mod(ang - t * 2.2, 6.2831853);
    float arc = smoothstep(0.02, 0.0, abs(r - 1.15)) * smoothstep(2.0, 0.0, a2) * uArc * 0.6;
    col += uC1 * arc; a += arc;
  }

  col += (hash(frag + fract(t) * 91.7) - 0.5) * 0.014 * a;  // grain where there is light
  a = clamp(max(a, max(col.r, max(col.g, col.b))), 0.0, 1.0);
  gl_FragColor = vec4(col, a);
}
`
