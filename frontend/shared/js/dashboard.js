/**
 * dashboard.js - Dashboard-Specific Logic
 * Smart Waste Segregator
 * 
 * Bin animation engine, real-time level monitoring,
 * quick stats, and recent activity feed.
 * (Most dashboard logic is inline in dashboard.html;
 *  this module provides reusable helpers imported by other pages.)
 */

// ==========================================
// Bin Animation Engine
// ==========================================

/**
 * Smoothly animate a bin fill level
 * @param {string} wasteContainerId - ID of .waste-container element
 * @param {string} percentId - ID of .percentage text element
 * @param {HTMLElement|null} valSpan - Optional info-card span to update
 * @param {string} statusId - ID of .status element
 * @param {number} target - Target fill level (0-100)
 */
export function animateBin(wasteContainerId, percentId, valSpan, statusId, target) {
  const wasteContainer = document.getElementById(wasteContainerId);
  const percentText = document.getElementById(percentId);
  if (!wasteContainer || !percentText) return;

  const bin = percentText.closest('.bin');
  const lid = bin ? bin.querySelector('.lid') : null;
  const status = document.getElementById(statusId);

  let current = parseInt(percentText.textContent) || 0;

  const interval = setInterval(() => {
    if (current === target) {
      clearInterval(interval);
      return;
    }

    current += current < target ? 1 : -1;

    wasteContainer.style.height = current + '%';
    percentText.textContent = current + '%';
    if (valSpan) valSpan.textContent = current + '%';
    if (lid) {
      lid.style.transform =
        'translateX(-50%) rotateX(' + Math.min(current / 2, 20) + 'deg)';
    }

    if (current >= 80) {
      if (bin) bin.classList.add('alert');
      if (status) status.textContent = '⚠️ Bin Full!';
    } else {
      if (bin) bin.classList.remove('alert');
      if (status) status.textContent = current >= 50 ? 'Half Full' : 'Normal';
    }
  }, 50);
}

// ==========================================
// Quick Stats Helpers
// ==========================================

/**
 * Calculate total collections from history data
 * @param {object} historyData - Firebase history snapshot val
 * @returns {number}
 */
export function countCollections(historyData) {
  if (!historyData) return 0;
  let count = 0;
  const entries = Object.values(historyData);
  for (let i = 1; i < entries.length; i++) {
    // A collection is when level drops significantly
    if (entries[i].level < entries[i - 1].level - 20) {
      count++;
    }
  }
  return count;
}

/**
 * Estimate CO2 saved based on total waste properly segregated (kg)
 * Rough estimate: 0.5 kg CO2 saved per kg of waste properly recycled
 * @param {number} totalWasteKg
 * @returns {string} formatted string e.g. "12.5kg"
 */
export function estimateCO2Saved(totalWasteKg) {
  const saved = (totalWasteKg * 0.5).toFixed(1);
  return saved + 'kg';
}

/**
 * Get status text for a fill level
 * @param {number} level
 * @returns {string}
 */
export function getStatusText(level) {
  if (level >= 90) return '🔴 Critical';
  if (level >= 80) return '🟠 Full';
  if (level >= 50) return '🟡 Half Full';
  if (level >= 20) return '🟢 Normal';
  return '⚪ Empty';
}

/**
 * Get status color class for a fill level
 * @param {number} level
 * @returns {string}
 */
export function getStatusColor(level) {
  if (level >= 80) return 'danger';
  if (level >= 50) return 'warning';
  return 'success';
}
