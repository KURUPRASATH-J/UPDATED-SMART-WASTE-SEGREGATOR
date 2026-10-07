// Export data to CSV
export async function exportToCSV(dataType = 'all') {
  try {
    let csvContent = 'data:text/csv;charset=utf-8,';
    
    if (dataType === 'bins' || dataType === 'all') {
      csvContent += 'Bin Data Export\n';
      csvContent += 'Timestamp,Bin Type,Level,Status\n';
      
      const wetRef = ref(database, 'bins/wet/history');
      const dryRef = ref(database, 'bins/dry/history');
      
      const wetSnapshot = await get(wetRef);
      const drySnapshot = await get(dryRef);
      
      if (wetSnapshot.exists()) {
        wetSnapshot.forEach(child => {
          const data = child.val();
          csvContent += `${data.timestamp},Wet,${data.level},${data.status || 'Normal'}\n`;
        });
      }
      
      if (drySnapshot.exists()) {
        drySnapshot.forEach(child => {
          const data = child.val();
          csvContent += `${data.timestamp},Dry,${data.level},${data.status || 'Normal'}\n`;
        });
      }
    }
    
    const encodedUri = encodeURI(csvContent);
    const link = document.createElement('a');
    link.setAttribute('href', encodedUri);
    link.setAttribute('download', `waste-data-${new Date().toISOString().split('T')[0]}.csv`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    
    return true;
  } catch (error) {
    console.error('Export to CSV failed:', error);
    return false;
  }
}

// Export data to JSON
export async function exportToJSON(dataType = 'all') {
  try {
    const exportData = {};
    
    if (dataType === 'bins' || dataType === 'all') {
      const binsRef = ref(database, 'bins');
      const snapshot = await get(binsRef);
      if (snapshot.exists()) {
        exportData.bins = snapshot.val();
      }
    }
    
    if (dataType === 'users' || dataType === 'all') {
      const usersRef = ref(database, 'users');
      const snapshot = await get(usersRef);
      if (snapshot.exists()) {
        exportData.users = snapshot.val();
      }
    }
    
    if (dataType === 'notifications' || dataType === 'all') {
      const notificationsRef = ref(database, 'notifications');
      const snapshot = await get(notificationsRef);
      if (snapshot.exists()) {
        exportData.notifications = snapshot.val();
      }
    }
    
    exportData.exportDate = new Date().toISOString();
    exportData.exportType = dataType;
    
    const dataStr = JSON.stringify(exportData, null, 2);
    const dataBlob = new Blob([dataStr], { type: 'application/json' });
    const url = URL.createObjectURL(dataBlob);
    
    const link = document.createElement('a');
    link.href = url;
    link.download = `waste-data-backup-${new Date().toISOString().split('T')[0]}.json`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    
    URL.revokeObjectURL(url);
    return true;
  } catch (error) {
    console.error('Export to JSON failed:', error);
    return false;
  }
}

// Export to Excel (using SheetJS)
export async function exportToExcel() {
  try {
    // This requires SheetJS library
    const XLSX = window.XLSX;
    
    if (!XLSX) {
      console.error('SheetJS library not loaded');
      return false;
    }
    
    const workbook = XLSX.utils.book_new();
    
    // Bin History Sheet
    const binHistory = [];
    const wetRef = ref(database, 'bins/wet/history');
    const dryRef = ref(database, 'bins/dry/history');
    
    const wetSnapshot = await get(wetRef);
    const drySnapshot = await get(dryRef);
    
    if (wetSnapshot.exists()) {
      wetSnapshot.forEach(child => {
        const data = child.val();
        binHistory.push({
          Timestamp: data.timestamp,
          Type: 'Wet',
          Level: data.level,
          Status: data.status || 'Normal'
        });
      });
    }
    
    if (drySnapshot.exists()) {
      drySnapshot.forEach(child => {
        const data = child.val();
        binHistory.push({
          Timestamp: data.timestamp,
          Type: 'Dry',
          Level: data.level,
          Status: data.status || 'Normal'
        });
      });
    }
    
    const worksheet = XLSX.utils.json_to_sheet(binHistory);
    XLSX.utils.book_append_sheet(workbook, worksheet, 'Bin History');
    
    // Save file
    XLSX.writeFile(workbook, `waste-report-${new Date().toISOString().split('T')[0]}.xlsx`);
    
    return true;
  } catch (error) {
    console.error('Export to Excel failed:', error);
    return false;
  }
}

// Email report
export async function emailReport(recipientEmail, reportData) {
  try {
    const subject = `Waste Management Report - ${new Date().toLocaleDateString()}`;
    const body = `
Dear User,

Please find your waste management report below:

Total Collections: ${reportData.totalCollections}
Wet Waste: ${reportData.wetWaste}
Dry Waste: ${reportData.dryWaste}
CO₂ Saved: ${reportData.co2Saved}

Best regards,
Smart Waste Segregator Team
    `.trim();
    
    const mailtoLink = `mailto:${recipientEmail}?subject=${encodeURIComponent(subject)}&body=${encodeURIComponent(body)}`;
    window.location.href = mailtoLink;
    
    return true;
  } catch (error) {
    console.error('Email report failed:', error);
    return false;
  }
}

// Print report
export function printReport(elementId = 'reportPreview') {
  try {
    const printContent = document.getElementById(elementId);
    if (!printContent) {
      console.error('Element not found:', elementId);
      return false;
    }
    
    const originalContent = document.body.innerHTML;
    const printableContent = printContent.innerHTML;
    
    document.body.innerHTML = printableContent;
    window.print();
    document.body.innerHTML = originalContent;
    
    // Reload page to restore functionality
    window.location.reload();
    
    return true;
  } catch (error) {
    console.error('Print report failed:', error);
    return false;
  }
}

// Schedule automatic reports
export function scheduleAutoReports(frequency = 'weekly', email) {
  try {
    const schedule = {
      frequency: frequency,
      email: email,
      lastSent: new Date().toISOString(),
      active: true
    };
    
    localStorage.setItem('reportSchedule', JSON.stringify(schedule));
    
    console.log('Auto-reports scheduled:', schedule);
    return true;
  } catch (error) {
    console.error('Schedule auto-reports failed:', error);
    return false;
  }
}
