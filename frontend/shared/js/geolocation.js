/**
 * geolocation.js - Location Features
 * Smart Waste Segregator
 * 
 * GPS helpers, distance calculation and nearest-bin finder.
 */

/**
 * Get user's current GPS coordinates
 * @returns {Promise<{lat:number, lng:number}>}
 */
export function getCurrentLocation() {
  return new Promise((resolve, reject) => {
    if (!navigator.geolocation) {
      reject(new Error('Geolocation is not supported by this browser'));
      return;
    }
    navigator.geolocation.getCurrentPosition(
      pos => resolve({ lat: pos.coords.latitude, lng: pos.coords.longitude }),
      err => reject(err),
      { enableHighAccuracy: true, timeout: 10000, maximumAge: 300000 }
    );
  });
}

/**
 * Calculate distance between two GPS coordinates using the Haversine formula
 * @param {number} lat1
 * @param {number} lng1
 * @param {number} lat2
 * @param {number} lng2
 * @returns {number} Distance in meters
 */
export function getDistance(lat1, lng1, lat2, lng2) {
  const R = 6371000; // Earth radius in metres
  const toRad = deg => (deg * Math.PI) / 180;
  const dLat = toRad(lat2 - lat1);
  const dLng = toRad(lng2 - lng1);
  const a =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) * Math.sin(dLng / 2) ** 2;
  return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
}

/**
 * Calculate distance from the user's current location to a point
 * @param {number} lat - Target latitude
 * @param {number} lng - Target longitude
 * @returns {Promise<number>} Distance in meters
 */
export async function getDistanceTo(lat, lng) {
  const pos = await getCurrentLocation();
  return getDistance(pos.lat, pos.lng, lat, lng);
}

/**
 * Find the nearest bin from an array of bin locations
 * @param {Array<{lat:number, lng:number, name:string}>} bins
 * @returns {Promise<{bin:object, distance:number}|null>}
 */
export async function getNearestBin(bins) {
  if (!bins || bins.length === 0) return null;
  try {
    const pos = await getCurrentLocation();
    let nearest = null;
    let minDist = Infinity;
    bins.forEach(bin => {
      const d = getDistance(pos.lat, pos.lng, bin.lat, bin.lng);
      if (d < minDist) {
        minDist = d;
        nearest = bin;
      }
    });
    return { bin: nearest, distance: minDist };
  } catch (e) {
    console.warn('Could not get location for nearest bin:', e.message);
    return null;
  }
}

/**
 * Format a distance in metres to a human-readable string
 * @param {number} meters
 * @returns {string} e.g. "350 m" or "1.2 km"
 */
export function formatDistance(meters) {
  if (meters < 1000) return Math.round(meters) + ' m';
  return (meters / 1000).toFixed(1) + ' km';
}
