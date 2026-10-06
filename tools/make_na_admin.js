// Canada provinces + Mexico states -> data/na-admin1.json (TopoJSON, simplified)
// Source: geoBoundaries gbOpen ADM1 (CAN: Statistics Canada Open Licence; MEX: geoBoundaries, CC BY 4.0)
// Usage: node tools/make_na_admin.js can.geojson mex.geojson   (needs topojson-server, topojson-simplify, topojson-client)
const fs = require('fs'), path = require('path');
const { topology } = require('topojson-server');
const ts = require('topojson-simplify');
const { quantize } = require('topojson-client');
const [can, mex] = process.argv.slice(2).map(f => JSON.parse(fs.readFileSync(f)));
const FIX = { 'CA-QB': 'CA-QC', 'Distrito Federal': 'MX-CMX' };
const feats = [...can.features, ...mex.features].map(f => {
  const p = f.properties, code = FIX[p.shapeName] || FIX[p.shapeISO] || p.shapeISO;
  return { type: 'Feature', id: code, properties: { name: p.shapeName.replace(' de Ocampo', '').replace(' de Zaragoza', '').replace(' de Arteaga', '').replace(' de Ignacio de la Llave', '').replace(/^Mexico$/, 'State of Mexico').replace('Distrito Federal', 'Mexico City') }, geometry: f.geometry };
});
let t = topology({ admin: { type: 'FeatureCollection', features: feats } });
t = ts.presimplify(t);
t = ts.simplify(t, ts.quantile(t, 0.04));
t = ts.filter(t, ts.filterWeight(t, 0.004));  // drop islets under ~0.004 sq deg
t.arcs = t.arcs.map(a => a.map(p => [p[0], p[1]]));
t = quantize(t, 3e4);
const out = path.join(__dirname, '..', 'data', 'na-admin1.json');
fs.writeFileSync(out, JSON.stringify(t));
console.log('wrote', out, (fs.statSync(out).size / 1e3).toFixed(0) + ' KB', t.objects.admin.geometries.map(g => g.id).join(' '));
