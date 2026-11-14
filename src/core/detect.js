// Classify package.json content — substring matching on the raw file text.
// Checks raw text rather than parsing dependencies (works even on broken JSON).
// Input is the raw package.json string. Order matters.
export function classifyPackageText(raw) {
  const s = String(raw || "");
  if (s.includes("@react-native") || s.includes("react-native")) {
    return s.includes("expo") ? "react-native-expo" : "react-native";
  }
  // The next type was merged into react in v4.1.0 — a "next" dependency still classifies as react
  if (s.includes('"react"') || s.includes('"next"')) return "react";
  return "node";
}

// Convenience: for a parsed object, re-serialize to text and apply the rules above
export function classifyPackageJson(pkgOrRaw) {
  const raw = typeof pkgOrRaw === "string" ? pkgOrRaw : JSON.stringify(pkgOrRaw || {});
  return classifyPackageText(raw);
}

// Marker scan (behavior spec §3.1). Injects has(relpath)=>bool. node is not added when another type exists.
// Receives raw package.json via read(relpath)=>string|null and passes it to classifyPackageText.
export function detectTypesFromMarkers({ has, read }) {
  const types = [];
  if (has("pubspec.yaml")) types.push("flutter");
  if (has("build.gradle") || has("build.gradle.kts") || has("pom.xml")) types.push("spring");
  if (has("pyproject.toml") || has("setup.py") || has("requirements.txt")) types.push("python");
  if (has("package.json")) {
    const cls = classifyPackageText(read ? read("package.json") : "");
    if (cls === "node") { if (types.length === 0) types.push("node"); }
    else types.push(cls);
  }
  return types.length ? [...new Set(types)] : ["basic"];
}

const VERSION_RE = /^\d+\.\d+\.\d+$/;

// Version detection (behavior spec §3.3) — first success in order. Injects read(relpath)=>string|null.
export function detectVersionFromFiles({ read, readJson, hasJq, gitTag }) {
  const pkg = readJson?.("package.json");
  if (hasJq && pkg?.version && VERSION_RE.test(pkg.version)) return pkg.version;
  const grab = (content, re) => {
    for (const line of (content || "").split("\n")) {
      const m = line.match(re);
      if (m && VERSION_RE.test(m[1])) return m[1];
    }
    return null;
  };
  let v;
  if ((v = grab(read("build.gradle"), /version\s*=\s*["']?(\d+\.\d+\.\d+)/))) return v;
  if ((v = grab(read("pubspec.yaml"), /^version:\s*(\d+\.\d+\.\d+)/))) return v;
  if ((v = grab(read("pyproject.toml"), /version\s*=\s*["']?(\d+\.\d+\.\d+)/))) return v;
  if (gitTag) { const t = String(gitTag).replace(/^v/, ""); if (VERSION_RE.test(t)) return t; }
  return "0.0.1";
}

export function markerForType(type) {
  return { flutter: "pubspec.yaml", "react-native-expo": "app.json", python: "pyproject.toml", spring: "build.gradle" }[type] || "package.json";
}

export function extraMarkers(type) {
  return { python: ["setup.py", "requirements.txt"], spring: ["build.gradle.kts", "pom.xml"] }[type] || [];
}

// Extension frequency scan recommendation (step 2 when there are no markers, #458).
// Secondary recommendation used only when there are no markers at all (= basic fallback). files = pruned relative paths.
// Thresholds: dart≥1→flutter, java+kt+gradle≥3→spring, tsx+jsx≥3→react, py≥3→python,
//       none of those and ts+js≥3→node. Returned in menu definition order.
export function suggestTypesByExtScan(files) {
  const count = (re) => files.filter((f) => re.test(f)).length;
  const found = new Set();
  if (count(/\.dart$/) >= 1) found.add("flutter");
  if (count(/\.java$/) + count(/\.kt$/) + count(/\.gradle$/) >= 3) found.add("spring");
  if (count(/\.tsx$/) + count(/\.jsx$/) >= 3) found.add("react");
  if (count(/\.py$/) >= 3) found.add("python");
  if (found.size === 0 && count(/\.ts$/) + count(/\.js$/) >= 3) found.add("node");
  const order = ["spring", "flutter", "react", "react-native", "react-native-expo", "node", "python"];
  return order.filter((t) => found.has(t));
}
