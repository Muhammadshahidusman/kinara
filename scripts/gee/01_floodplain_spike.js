// =====================================================================
// Ravi floodplain construction spike, Lahore District
// Open Buildings 2.5D Temporal: 2016 vs 2023 (+ yearly series 2016-2023)
// Platform: Google Earth Engine Code Editor (code.earthengine.google.com)
//
// STATUS: written without access to Earth Engine, NOT EXECUTED.
//         Run section by section and check every print() before exporting.
//
// HOW TO RUN
//   1. Paste into a new Code Editor script and press Run.
//   2. Check the Console: tiles per year, river reaches kept, zone areas.
//   3. Look at the map layers over the satellite basemap.
//   4. Open the Tasks tab and run the 5 exports (all go to Google Drive).
//
// This is a first look, not the paper's method. The floodplain here is a
// HAND-based PROXY; your final analysis should use three definitions
// (bunds, HAND, JRC hazard) and report results across all of them.
// =====================================================================


// ---------- 1. PARAMETERS ---------------------------------------------
var YEAR_A = 2016;
var YEAR_B = 2023;
var THRESHOLDS = [0.4, 0.5, 0.6];  // building_presence cut-offs (sensitivity)
var MAIN_THR = 0.5;                // cut-off used for map layers and series
var RIVER_BUFFER_M = 4000;         // max distance from the Ravi channel (m)
var HAND_MAX_M = 5;                // Height Above Nearest Drainage cut-off (m)
var MIN_UPLAND_KM2 = 10000;        // keeps the Ravi, drops small drains/nullahs
var SCALE = 4;                     // effective resolution of the dataset (m)
var CRS = 'EPSG:32643';            // WGS 84 / UTM zone 43N (Lahore)
var COUNT_FACTOR = 64;             // (4 m / 0.5 m)^2, see note in section 6
var DRIVE_FOLDER = 'ravi_floodplain_spike';

// Leave empty to fall back to FAO GAUL 2015. Better: upload your official
// Dataset/Processed/shapefiles/Lahore_District_Boundary.shp as an asset
// and paste its ID, e.g. 'projects/<your-project>/assets/Lahore_District_Boundary'
var DISTRICT_ASSET = '';


// ---------- 2. STUDY AREA ---------------------------------------------
var districtSource = (DISTRICT_ASSET !== '') ? DISTRICT_ASSET : 'FAO/GAUL/2015/level2';
var district = (DISTRICT_ASSET !== '')
  ? ee.FeatureCollection(DISTRICT_ASSET).geometry()
  : ee.FeatureCollection('FAO/GAUL/2015/level2')
      .filter(ee.Filter.eq('ADM0_NAME', 'Pakistan'))
      .filter(ee.Filter.eq('ADM2_NAME', 'Lahore'))
      .geometry();

print('District area km2 (your official boundary is 1,793.8)',
      district.area(10).divide(1e6));


// ---------- 3. FLOODPLAIN PROXY: HAND <= 5 m within 4 km of the Ravi ---
var rivers = ee.FeatureCollection('WWF/HydroSHEDS/v1/FreeFlowingRivers')
  .filterBounds(district.buffer(20000))
  .filter(ee.Filter.gte('UPLAND_SKM', MIN_UPLAND_KM2));
print('River reaches kept (should trace only the Ravi)', rivers.size());

var corridor = rivers.geometry().buffer(RIVER_BUFFER_M, 100);
var corridorImg = ee.Image(0)
  .paint(ee.FeatureCollection([ee.Feature(corridor)]), 1);

var hand = ee.Image('MERIT/Hydro/v1_0_1').select('hnd');
var fpMask = hand.lte(HAND_MAX_M).and(corridorImg.eq(1)).selfMask();

var fpGeom = fpMask.reduceToVectors({
    geometry: district,
    scale: 90,
    geometryType: 'polygon',
    eightConnected: true,
    labelProperty: 'fp',
    maxPixels: 1e10
  })
  .geometry(100)
  .intersection(district, 100);


// ---------- 4. OPEN BUILDINGS 2.5D TEMPORAL ----------------------------
var ob = ee.ImageCollection('GOOGLE/Research/open-buildings-temporal/v1')
  .filterBounds(district)
  .map(function (img) {
    var yr = ee.Date(ee.Number(img.get('inference_time_epoch_s')).multiply(1000))
      .get('year');
    return img.set('ob_year', yr);
  });

print('Tiles per year (expect every year 2016-2023)',
      ob.aggregate_histogram('ob_year'));
print('Band names', ob.first().bandNames());

// One mosaic per year, unmasked to 0, keeping the native 0.5 m projection.
function obYear(y) {
  var col = ob.filter(ee.Filter.eq('ob_year', y));
  return col.mosaic()
    .unmask(0)
    .setDefaultProjection(col.first().projection());
}

var A = obYear(YEAR_A);
var B = obYear(YEAR_B);


// ---------- 5. BUILT AREA, NEW AND "LOST" PER THRESHOLD ---------------
// "Lost" buildings are rare in reality, so lost area is your NOISE FLOOR.
// If lost is a big fraction of new, the growth signal is not trustworthy.
var px = ee.Image.pixelArea();  // m2 per pixel at the reduction scale

var stack = ee.Image.cat(
  A.select('building_fractional_count').rename('count_A'),
  B.select('building_fractional_count').rename('count_B')
);

THRESHOLDS.forEach(function (t) {
  var tag = '_t' + Math.round(t * 100);
  var a = A.select('building_presence').gte(t);
  var b = B.select('building_presence').gte(t);
  stack = stack.addBands(ee.Image.cat(
    a.multiply(px).rename('builtA_m2' + tag),
    b.multiply(px).rename('builtB_m2' + tag),
    b.and(a.not()).multiply(px).rename('new_m2' + tag),
    a.and(b.not()).multiply(px).rename('lost_m2' + tag)
  ));
});


// ---------- 6. ZONAL STATISTICS ---------------------------------------
// COUNT_FACTOR: fractional counts live on 0.5 m pixels. Reading them at
// 4 m and multiplying by 64 approximates the 0.5 m sum. Treat building
// counts as approximate; cross-check one small area at native scale.
var zones = ee.FeatureCollection([
  ee.Feature(fpGeom, {zone: 'floodplain_proxy'}),
  ee.Feature(district.difference(fpGeom, 100), {zone: 'rest_of_district'}),
  ee.Feature(district, {zone: 'lahore_district'})
]).map(function (f) {
  return f.set('zone_km2', f.geometry().area(100).divide(1e6));
});

print('Zone areas km2', zones.aggregate_array('zone'),
      zones.aggregate_array('zone_km2'));

var stats = stack.reduceRegions({
  collection: zones,
  reducer: ee.Reducer.sum(),
  scale: SCALE,
  crs: CRS,
  tileScale: 16
}).map(function (f) {
  var d = f.toDictionary().combine({
    buildings_A: ee.Number(f.get('count_A')).multiply(COUNT_FACTOR),
    buildings_B: ee.Number(f.get('count_B')).multiply(COUNT_FACTOR)
  });
  return ee.Feature(null, d);
});


// ---------- 7. YEARLY SERIES INSIDE THE FLOODPLAIN PROXY --------------
var series = ee.FeatureCollection(
  ee.List.sequence(2016, 2023).map(function (y) {
    var built = obYear(y).select('building_presence').gte(MAIN_THR)
      .multiply(px)
      .reduceRegion({
        reducer: ee.Reducer.sum(),
        geometry: fpGeom,
        scale: SCALE,
        crs: CRS,
        maxPixels: 1e12,
        tileScale: 16
      }).values().get(0);
    return ee.Feature(null, {
      year: y,
      threshold: MAIN_THR,
      built_km2_floodplain_proxy: ee.Number(built).divide(1e6)
    });
  })
);


// ---------- 8. CHANGE MAP (for QGIS / ArcGIS Pro checks) --------------
var a0 = A.select('building_presence').gte(MAIN_THR);
var b0 = B.select('building_presence').gte(MAIN_THR);
var change = ee.Image(0)
  .where(a0.and(b0), 1)          // 1 = built in both years
  .where(b0.and(a0.not()), 2)    // 2 = new since YEAR_A
  .where(a0.and(b0.not()), 3)    // 3 = "lost" (mostly noise)
  .rename('change')
  .toByte();


// ---------- 9. MAP LAYERS ---------------------------------------------
Map.setOptions('SATELLITE');
Map.centerObject(district, 10);
Map.addLayer(ee.Image().paint(ee.FeatureCollection([ee.Feature(district)]), 0, 2),
             {palette: ['ffff00']}, 'Lahore District');
Map.addLayer(rivers, {color: '00ffff'}, 'HydroSHEDS reaches kept');
Map.addLayer(fpMask, {palette: ['0044ff'], opacity: 0.35}, 'Floodplain proxy');
Map.addLayer(change.selfMask().clip(district),
             {min: 1, max: 3, palette: ['9e9e9e', 'ff0000', 'ffff00']},
             'Change ' + YEAR_A + '-' + YEAR_B + ' (grey stable, red new, yellow lost)');


// ---------- 10. EXPORTS (Tasks tab) -----------------------------------
var stamp = YEAR_A + '_' + YEAR_B;

Export.table.toDrive({
  collection: stats,
  description: 'zone_stats_' + stamp,
  folder: DRIVE_FOLDER,
  fileFormat: 'CSV'
});

Export.table.toDrive({
  collection: series,
  description: 'floodplain_series_2016_2023',
  folder: DRIVE_FOLDER,
  fileFormat: 'CSV'
});

Export.table.toDrive({
  collection: zones,
  description: 'zones_floodplain_proxy',
  folder: DRIVE_FOLDER,
  fileFormat: 'GeoJSON'
});

Export.image.toDrive({
  image: change.clip(fpGeom),
  description: 'change_map_floodplain_' + stamp,
  folder: DRIVE_FOLDER,
  region: fpGeom,
  scale: SCALE,
  crs: CRS,
  maxPixels: 1e10,
  fileFormat: 'GeoTIFF',
  formatOptions: {cloudOptimized: true}
});

// Provenance sidecar: everything needed to reproduce these numbers.
Export.table.toDrive({
  collection: ee.FeatureCollection([ee.Feature(null, {
    run_utc: new Date().toISOString(),
    buildings_collection: 'GOOGLE/Research/open-buildings-temporal/v1',
    hand_image: 'MERIT/Hydro/v1_0_1 (band hnd)',
    rivers_collection: 'WWF/HydroSHEDS/v1/FreeFlowingRivers',
    district_source: districtSource,
    years: YEAR_A + ',' + YEAR_B,
    thresholds: THRESHOLDS.join(','),
    main_threshold: MAIN_THR,
    river_buffer_m: RIVER_BUFFER_M,
    hand_max_m: HAND_MAX_M,
    min_upland_km2: MIN_UPLAND_KM2,
    scale_m: SCALE,
    crs: CRS,
    count_factor: COUNT_FACTOR,
    reducer: 'sum, tileScale 16, weighted at polygon edges',
    note: 'Raw pixel areas, not error-adjusted. Floodplain is a HAND proxy.'
  })]),
  description: 'provenance_' + stamp,
  folder: DRIVE_FOLDER,
  fileFormat: 'CSV'
});
