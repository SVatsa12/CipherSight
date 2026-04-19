#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>
#include <AsyncMqttClient.h>
#include <WiFi.h>
#include <Wire.h>

#include <BLEAdvertisedDevice.h>
#include <BLEDevice.h>
#include <BLEScan.h>
#include <BLEUtils.h>

#define WIFI_SSID "loveyourahega"
#define WIFI_PASS "jfcFYuM5"
#define HOST "broker.hivemq.com"
#define TOPIC "phantasm/iot/display"
#define SERVICE_UUID "4fafc201-1fb5-459e-8bcc-c5c9c331914b"

Adafruit_SSD1306 display(128, 64, &Wire, -1);
AsyncMqttClient mqtt;

bool isIdle = false;
bool mqttConnected = false;
unsigned long lastFrame = 0;
unsigned long lastBootUi = 0;
int frameCount = 0;
bool isVerified = false;
int tickFrame = 0;

// Defer MQTT connect to loop(): calling mqtt.connect() from the WiFi event
// callback can crash or watchdog-reset the ESP32 (wrong task context).
volatile bool wifiReadyForMqtt = false;

// BLE Scanner State
bool isWaitingForBLE = false;
uint8_t imageBuffer[1024];

int maxRssi = -100;
BLEScan *pBLEScan;

class MyAdvertisedDeviceCallbacks : public BLEAdvertisedDeviceCallbacks {
  void onResult(BLEAdvertisedDevice advertisedDevice) {
    int rssi = advertisedDevice.getRSSI();

    // Discriminator: Is this a mobile phone?
    bool isPhone = false;

    // Method 1: Check Standard GATT Appearance (64 = Generic Phone)
    if (advertisedDevice.haveAppearance() &&
        advertisedDevice.getAppearance() == 64) {
      isPhone = true;
    }

    // Method 2: Manually parse the raw payload to bypass String length bugs with 0x00 bytes
    if (advertisedDevice.getPayloadLength() > 0) {
      uint8_t* payload = advertisedDevice.getPayload();
      size_t payloadLength = advertisedDevice.getPayloadLength();
      for (size_t i = 0; i < payloadLength; ) {
        uint8_t len = payload[i];
        if (len == 0 || i + len >= payloadLength) break;
        uint8_t type = payload[i + 1];
        
        if (type == 0xFF && len >= 3) { // 0xFF is Manufacturer Specific Data
          uint16_t mfg_id = payload[i + 2] | (payload[i + 3] << 8);
          // Apple(0x004C), Google(0x00E0), Samsung(0x0075), Sony(0x025A), Xiaomi(0x0118)
          // Huawei(0x012D, 0x027D), OnePlus(0x038F), Oppo(0x032D), Vivo(0x036F), Motorola(0x00A6)
          if (mfg_id == 0x004C || mfg_id == 0x00E0 || mfg_id == 0x0075 ||
              mfg_id == 0x025A || mfg_id == 0x0118 || mfg_id == 0x012D ||
              mfg_id == 0x027D || mfg_id == 0x038F || mfg_id == 0x032D ||
              mfg_id == 0x036F || mfg_id == 0x00A6) {
            isPhone = true;
          }
        }
        i += len + 1;
      }
    }

    // Only register the signal strength if we confirmed it is a mobile phone
    if (isPhone && rssi > maxRssi) {
      maxRssi = rssi;
    }
  }
};

void connectWifi() { WiFi.begin(WIFI_SSID, WIFI_PASS); }
void connectMqtt() { mqtt.connect(); }

void onConnect(bool session) {
  mqtt.subscribe(TOPIC, 1);
  mqttConnected = true;
  isIdle = true;
}

void onDisconnect(AsyncMqttClientDisconnectReason reason) {
  mqttConnected = false;
  isIdle = false;
  isVerified = false;
  isWaitingForBLE = false;
}

void onMessage(char *topic, char *payload,
               AsyncMqttClientMessageProperties prop, size_t len, size_t idx,
               size_t total) {
  // CACHE MODE: Visual Cryptography / QR Code matrix array
  if (total == 1024) {
    // Must clear idle: otherwise loop() keeps drawing "PHANTASM OS" every 60ms
    // and overwrites / hides QR flow and PIN until PREPARE runs.
    isIdle = false;
    if (idx == 0) {
      display.clearDisplay();
      display.setTextSize(1);
      display.setTextColor(WHITE);
      display.setCursor(0, 28);
      display.println(" LOADING SHARE...");
      display.display();
    }
    if (idx + len <= 1024) {
      memcpy(imageBuffer + idx, payload, len);
    }
    if (idx + len == total) {
      display.clearDisplay();
      display.setTextSize(1);
      display.setCursor(10, 28);
      display.println(" SHARE READY");
      display.println(" WAIT FOR PROMPT");
      display.display();
    }
    return;
  }

  isIdle = false;
  isVerified = false;
  display.clearDisplay();

  // SUCCESS STATUS MODE
  if (len >= 8 && strncmp(payload, "VERIFIED", 8) == 0) {
    isVerified = true;
    tickFrame = 0;
    return;
  }

  if (len >= 7 && strncmp(payload, "PREPARE", 7) == 0) {
    isWaitingForBLE = true;
    display.setTextSize(2);
    display.setTextColor(WHITE);
    display.setCursor(0, 10);
    display.println("  BRING");
    display.println("  PHONE");
    display.println("  CLOSE");
    display.display();
    return;
  }

  // PIN CHALLENGE MODE
  if (total > 0 && total <= 10) {
    char message[len + 1];
    memcpy(message, payload, len);
    message[len] = '\0';

    display.setTextSize(2);
    display.setTextColor(WHITE);
    display.setCursor(0, 0);
    display.println("SECURE PIN:");

    display.setTextSize(4);
    display.setCursor(15, 25);
    display.print(message);
    display.display();
  }
}



void setup() {
  Serial.begin(115200);
  display.begin(SSD1306_SWITCHCAPVCC, 0x3C);
  display.clearDisplay();
  display.setTextColor(WHITE);
  display.println("Booting System...");
  display.display();

  // Do not force isIdle here: if true before MQTT payload, loop() only runs the
  // PHANTASM animation and never yields to QR / PIN handlers that skip isIdle=false.

  WiFi.mode(WIFI_STA);
  WiFi.onEvent([](WiFiEvent_t event, WiFiEventInfo_t info) {
    if (event == ARDUINO_EVENT_WIFI_STA_GOT_IP) {
      Serial.println("WiFi Connected! MQTT will start from loop...");
      wifiReadyForMqtt = true;
    }
  });

  mqtt.onConnect(onConnect);
  mqtt.onDisconnect(onDisconnect);
  mqtt.onMessage(onMessage);
  mqtt.setServer(HOST, 1883);

  connectWifi();

  // Init BLE after WiFi starts so the radio is not contended during association
  // (WiFi + BLE share the 2.4 GHz RF; BLE-first init can worsen connect issues).
  BLEDevice::init("");
  pBLEScan = BLEDevice::getScan();
  pBLEScan->setAdvertisedDeviceCallbacks(new MyAdvertisedDeviceCallbacks());
  pBLEScan->setActiveScan(true);
}

void loop() {
  if (wifiReadyForMqtt && !mqttConnected) {
    wifiReadyForMqtt = false;
    Serial.println("Connecting to MQTT...");
    connectMqtt();
  }

  // Until MQTT is up, redraw status — otherwise "Booting System..." never updates
  // if WiFi or broker fails (wrong SSID, no internet, HiveMQ blocked, etc.).
  if (!mqttConnected && millis() - lastBootUi > 400) {
    lastBootUi = millis();
    display.clearDisplay();
    display.setTextSize(1);
    display.setTextColor(WHITE);
    display.setCursor(0, 0);
    wl_status_t ws = WiFi.status();
    if (ws == WL_CONNECTED) {
      display.println(F("WiFi OK"));
      display.setCursor(0, 16);
      display.println(F("MQTT connecting..."));
    } else if (ws == WL_IDLE_STATUS || ws == WL_DISCONNECTED) {
      display.println(F("Connecting WiFi..."));
    } else {
      display.println(F("WiFi error"));
      display.setCursor(0, 16);
      display.print(F("code "));
      display.println((int)ws);
    }
    display.display();
  }

  // Proximity Render Trigger
  if (isWaitingForBLE) {
    maxRssi = -100; // Reset threshold
    // Scan for 1 second. Blocks momentarily but ensures clean RSSI polling
    pBLEScan->start(1, false);
    pBLEScan->clearResults();

    // If a phone is very close, its RSSI will spike > -50
    if (maxRssi > -50) {
      isWaitingForBLE = false;
      display.clearDisplay();
      display.drawBitmap(0, 0, imageBuffer, 128, 64, WHITE);
      display.display();
    }
  }

  if (mqttConnected && isIdle && millis() - lastFrame > 60) {
    lastFrame = millis();
    display.clearDisplay();
    
    // Draw top and bottom "Data Rails"
    display.drawLine(0, 0, 128, 0, WHITE);
    display.drawLine(0, 63, 128, 63, WHITE);

    // The Scanning Line
    int scanLineX = (frameCount * 3) % 128;
    display.drawLine(scanLineX, 2, scanLineX, 61, WHITE);
    
    // Draw random "Data Fragments" behind the scan line
    for(int i = 0; i < 15; i++) {
      int x = (i * 17 + frameCount) % 128;
      int y = (i * 9) % 50 + 7;
      if (x < scanLineX) {
          display.drawPixel(x, y, WHITE);
          if (i % 3 == 0) display.drawRect(x, y, 2, 2, WHITE);
      }
    }

    display.setTextSize(1);
    display.setCursor(35, 28);
    display.print("PHANTASM OS");
    
    display.display();
    frameCount++;
  } else if (mqttConnected && isVerified && millis() - lastFrame > 35) {
    lastFrame = millis();
    display.clearDisplay();

    // Draw Success Status
    display.setTextSize(1);
    display.setTextColor(WHITE);
    display.setCursor(42, 6);
    display.print("SUCCESS");

    // Draw Animated Checkmark
    display.drawCircle(64, 38, 20, WHITE);

    if (tickFrame > 5)
      display.drawLine(54, 38, 62, 46, WHITE);
    if (tickFrame > 10)
      display.drawLine(62, 46, 76, 30, WHITE);
    if (tickFrame > 15) {
      display.drawLine(54, 39, 62, 47, WHITE);
      display.drawLine(62, 47, 76, 31, WHITE);
    }

    display.display();
    tickFrame++;

    // Auto reset back to idle
    if (tickFrame > 80) {
      isVerified = false;
      isIdle = true;
      frameCount = 0;
    }
  }
}
