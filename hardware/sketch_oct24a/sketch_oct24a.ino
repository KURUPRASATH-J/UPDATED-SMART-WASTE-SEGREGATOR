#include <Arduino.h>
#include <WiFi.h>
#include <HTTPClient.h>
#include <ESP32Servo.h>

// ============================================
// YOUR CREDENTIALS
// ============================================
#define WIFI_SSID "Galaxy M34 5G 47D7"
#define WIFI_PASSWORD "11111111"

// Flask server IP (your laptop's IP on the hotspot network)
// Find it by running 'ipconfig' on your laptop
#define SERVER_IP "192.168.43.100"
#define SERVER_PORT 5000

// ============================================
// CONFIGURATION
// ============================================
#define BIN_HEIGHT 50  // Your actual bin height in cm

// Hardware pins
#define PRESENCE_TRIG_PIN 13
#define PRESENCE_ECHO_PIN 12
#define WET_TRIG_PIN 5
#define WET_ECHO_PIN 18
#define DRY_TRIG_PIN 19
#define DRY_ECHO_PIN 21
#define SERVO_PIN 14

// System settings
#define PRESENCE_THRESHOLD 20
#define UPDATE_INTERVAL 5000
#define PRESENCE_CHECK_INTERVAL 500
#define LID_OPEN_DURATION 5000

// ============================================
// SYSTEM CODE
// ============================================

Servo lidServo;

unsigned long lastUpdate = 0;
unsigned long lastPresenceCheck = 0;
unsigned long lidOpenTime = 0;

bool lidOpen = false;
bool presenceDetected = false;
int consecutiveDetections = 0;

String serverBase;

void setup() {
  Serial.begin(115200);
  delay(1000);
  
  Serial.println("\n\n====================================");
  Serial.println("Smart Waste Bin System v2.0 (Flask)");
  Serial.println("====================================\n");
  
  // Build server URL
  serverBase = "http://" + String(SERVER_IP) + ":" + String(SERVER_PORT);
  
  pinMode(PRESENCE_TRIG_PIN, OUTPUT);
  pinMode(PRESENCE_ECHO_PIN, INPUT);
  pinMode(WET_TRIG_PIN, OUTPUT);
  pinMode(WET_ECHO_PIN, INPUT);
  pinMode(DRY_TRIG_PIN, OUTPUT);
  pinMode(DRY_ECHO_PIN, INPUT);
  
  Serial.println("OK Sensor pins configured");
  
  lidServo.attach(SERVO_PIN);
  lidServo.write(0);
  Serial.println("OK Servo motor initialized (lid closed)");
  
  Serial.print("\nConnecting to WiFi: ");
  Serial.println(WIFI_SSID);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  
  int wifiAttempts = 0;
  while (WiFi.status() != WL_CONNECTED && wifiAttempts < 30) {
    delay(500);
    Serial.print(".");
    wifiAttempts++;
  }
  
  if (WiFi.status() == WL_CONNECTED) {
    Serial.println("\nOK WiFi Connected!");
    Serial.print("IP Address: ");
    Serial.println(WiFi.localIP());
  } else {
    Serial.println("\nERROR WiFi Connection Failed!");
    Serial.println("Turn ON hotspot: Galaxy M34 5G 47D7");
    while(1) { delay(1000); }
  }
  
  Serial.println("\nServer: " + serverBase);
  Serial.println("\n====================================");
  Serial.println("System Ready!");
  Serial.println("Monitoring presence and bin levels...");
  Serial.println("====================================\n");
}

void loop() {
  if (millis() - lastPresenceCheck >= PRESENCE_CHECK_INTERVAL) {
    lastPresenceCheck = millis();
    checkPresence();
  }
  
  if (lidOpen && (millis() - lidOpenTime >= LID_OPEN_DURATION)) {
    float presenceDistance = getDistance(PRESENCE_TRIG_PIN, PRESENCE_ECHO_PIN);
    if (presenceDistance > PRESENCE_THRESHOLD || presenceDistance < 0) {
      closeLid();
    } else {
      lidOpenTime = millis();
    }
  }
  
  if (millis() - lastUpdate >= UPDATE_INTERVAL) {
    lastUpdate = millis();
    updateBinLevels();
  }
}

void checkPresence() {
  float distance = getDistance(PRESENCE_TRIG_PIN, PRESENCE_ECHO_PIN);
  
  if (distance > 0 && distance <= PRESENCE_THRESHOLD) {
    consecutiveDetections++;
    
    if (consecutiveDetections >= 2 && !presenceDetected) {
      presenceDetected = true;
      Serial.println("\nPRESENCE DETECTED!");
      Serial.print("Distance: ");
      Serial.print(distance);
      Serial.println(" cm");
      
      openLid();
      sendPresenceToServer(true, distance);
    }
  } else {
    consecutiveDetections = 0;
    if (presenceDetected) {
      presenceDetected = false;
      sendPresenceToServer(false, distance);
    }
  }
}

void openLid() {
  if (!lidOpen) {
    Serial.println("Opening lid...");
    lidServo.write(90);
    lidOpen = true;
    lidOpenTime = millis();
    sendLidToServer("open");
  } else {
    lidOpenTime = millis();
  }
}

void closeLid() {
  if (lidOpen) {
    Serial.println("Closing lid...");
    lidServo.write(0);
    lidOpen = false;
    sendLidToServer("closed");
  }
}

void updateBinLevels() {
  float wetDistance = getDistance(WET_TRIG_PIN, WET_ECHO_PIN);
  float dryDistance = getDistance(DRY_TRIG_PIN, DRY_ECHO_PIN);
  
  int wetLevel = calculateFillLevel(wetDistance);
  int dryLevel = calculateFillLevel(dryDistance);
  
  Serial.println("\n=== Bin Status Update ===");
  Serial.print("Wet Bin: ");
  Serial.print(wetLevel);
  Serial.print("% (");
  Serial.print(wetDistance);
  Serial.println(" cm)");
  Serial.print("Dry Bin: ");
  Serial.print(dryLevel);
  Serial.print("% (");
  Serial.print(dryDistance);
  Serial.println(" cm)");
  Serial.print("Lid: ");
  Serial.println(lidOpen ? "OPEN" : "CLOSED");
  Serial.println("========================\n");
  
  sendBinDataToServer(wetLevel, wetDistance, dryLevel, dryDistance);
}

float getDistance(int trigPin, int echoPin) {
  digitalWrite(trigPin, LOW);
  delayMicroseconds(2);
  digitalWrite(trigPin, HIGH);
  delayMicroseconds(10);
  digitalWrite(trigPin, LOW);
  
  long duration = pulseIn(echoPin, HIGH, 30000);
  float distance = duration * 0.034 / 2;
  
  if (distance == 0 || distance > 400) {
    return -1;
  }
  
  return distance;
}

int calculateFillLevel(float distance) {
  if (distance < 0) return 0;
  
  float fillHeight = BIN_HEIGHT - distance;
  int percentage = (fillHeight / BIN_HEIGHT) * 100;
  
  if (percentage < 0) percentage = 0;
  if (percentage > 100) percentage = 100;
  
  return percentage;
}

// ============================================
// HTTP POST Functions (replaces Firebase)
// ============================================

void sendBinDataToServer(int wetLevel, float wetDistance, int dryLevel, float dryDistance) {
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("ERROR: WiFi not connected");
    return;
  }
  
  HTTPClient http;
  http.begin(serverBase + "/api/sensor-data");
  http.addHeader("Content-Type", "application/json");
  
  String json = "{";
  json += "\"wetLevel\":" + String(wetLevel) + ",";
  json += "\"wetDistance\":" + String(wetDistance, 2) + ",";
  json += "\"dryLevel\":" + String(dryLevel) + ",";
  json += "\"dryDistance\":" + String(dryDistance, 2);
  json += "}";
  
  int code = http.POST(json);
  
  if (code == 200) {
    Serial.println("OK Data sent to server");
  } else {
    Serial.print("ERROR sending data: ");
    Serial.println(code);
  }
  
  http.end();
}

void sendPresenceToServer(bool detected, float distance) {
  if (WiFi.status() != WL_CONNECTED) return;
  
  HTTPClient http;
  http.begin(serverBase + "/api/presence");
  http.addHeader("Content-Type", "application/json");
  
  String json = "{\"detected\":" + String(detected ? "true" : "false") + 
                ",\"distance\":" + String(distance, 2) + "}";
  
  int code = http.POST(json);
  if (code == 200) {
    Serial.println("OK Presence sent");
  } else {
    Serial.print("ERROR presence: ");
    Serial.println(code);
  }
  
  http.end();
}

void sendLidToServer(String status) {
  if (WiFi.status() != WL_CONNECTED) return;
  
  HTTPClient http;
  http.begin(serverBase + "/api/lid");
  http.addHeader("Content-Type", "application/json");
  
  String json = "{\"status\":\"" + status + "\"}";
  
  int code = http.POST(json);
  if (code == 200) {
    Serial.println("OK Lid status sent");
  } else {
    Serial.print("ERROR lid: ");
    Serial.println(code);
  }
  
  http.end();
}
