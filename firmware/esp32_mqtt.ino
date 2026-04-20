#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>
#include <PubSubClient.h>
#include <WiFi.h>
#include <WiFiClient.h>
#include <Wire.h>

#include <BLEAdvertisedDevice.h>
#include <BLEDevice.h>
#include <BLEScan.h>
#include <BLEUtils.h>

#include "soc/soc.h"
#include "soc/rtc_cntl_reg.h"

#define WIFI_SSID "loveyourahega"
#define WIFI_PASS "jfcFYuM5"
#define HOST "broker.hivemq.com"
#define PORT 1883
#define TOPIC "phantasm/iot/display"

Adafruit_SSD1306 display(128, 64, &Wire, -1);
WiFiClient wifiClient;
PubSubClient mqtt(wifiClient);

enum DisplayState { DS_BOOTING, DS_WIFI_CONNECTING, DS_MQTT_CONNECTING, DS_RUNNING };
DisplayState displayState = DS_BOOTING;
DisplayState lastDisplayState = DS_RUNNING;

bool isIdle = false;
bool mqttConnected = false;
unsigned long lastFrame = 0;
int frameCount = 0;
bool isVerified = false;
int tickFrame = 0;

bool isWaitingForBLE = false;
bool bleInitialized = false;
uint8_t imageBuffer[1024];

int maxRssi = -100;
BLEScan *pBLEScan = nullptr;

unsigned long lastMqttReconnect = 0;

class MyAdvertisedDeviceCallbacks : public BLEAdvertisedDeviceCallbacks {
  void onResult(BLEAdvertisedDevice advertisedDevice) {
    int rssi = advertisedDevice.getRSSI();
    bool isPhone = false;

    if (advertisedDevice.haveAppearance() && advertisedDevice.getAppearance() == 64) {
      isPhone = true;
    }

    if (advertisedDevice.getPayloadLength() > 0) {
      uint8_t* payload = advertisedDevice.getPayload();
      size_t payloadLength = advertisedDevice.getPayloadLength();
      for (size_t i = 0; i < payloadLength; ) {
        uint8_t len = payload[i];
        if (len == 0 || i + len >= payloadLength) break;
        uint8_t type = payload[i + 1];
        if (type == 0xFF && len >= 3) {
          uint16_t mfg_id = payload[i + 2] | (payload[i + 3] << 8);
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

    if (isPhone && rssi > maxRssi) {
      maxRssi = rssi;
    }
  }
};

void startBLE() {
  if (bleInitialized) return;
  Serial.print("Starting BLE, free heap: ");
  Serial.println(ESP.getFreeHeap());
  BLEDevice::init("");
  pBLEScan = BLEDevice::getScan();
  pBLEScan->setAdvertisedDeviceCallbacks(new MyAdvertisedDeviceCallbacks());
  pBLEScan->setActiveScan(true);
  bleInitialized = true;
}

void stopBLE() {
  if (!bleInitialized) return;
  pBLEScan->stop();
  pBLEScan = nullptr;
  BLEDevice::deinit(true);
  bleInitialized = false;
  Serial.print("BLE stopped, free heap: ");
  Serial.println(ESP.getFreeHeap());
}

// PubSubClient message callback
void onMessage(char* topic, byte* payload, unsigned int len) {
  // Handle 1024-byte image payload
  // PubSubClient delivers the full message in one call — no chunking
  if (len == 1024) {
    isIdle = false;
    display.clearDisplay();
    display.setCursor(0, 28);
    display.println(" LOADING SHARE...");
    display.display();
    memcpy(imageBuffer, payload, 1024);
    display.clearDisplay();
    display.setCursor(10, 28);
    display.println(" SHARE READY");
    display.println(" WAIT FOR PROMPT");
    display.display();
    return;
  }

  isIdle = false;
  isVerified = false;
  display.clearDisplay();

  if (len >= 8 && strncmp((char*)payload, "VERIFIED", 8) == 0) {
    isVerified = true;
    tickFrame = 0;
    return;
  }

  if (len >= 7 && strncmp((char*)payload, "PREPARE", 7) == 0) {
    isWaitingForBLE = true;
    startBLE();
    display.setTextSize(2);
    display.setCursor(0, 10);
    display.println("  BRING");
    display.println("  PHONE");
    display.println("  CLOSE");
    display.display();
    return;
  }

  if (len > 0 && len <= 10) {
    char message[len + 1];
    memcpy(message, payload, len);
    message[len] = '\0';
    display.setTextSize(2);
    display.setCursor(0, 0);
    display.println("SECURE PIN:");
    display.setTextSize(4);
    display.setCursor(15, 25);
    display.print(message);
    display.display();
  }
}

bool mqttReconnect() {
  Serial.print("Connecting to MQTT, free heap: ");
  Serial.println(ESP.getFreeHeap());
  // Use a unique client ID to avoid conflicts on the broker
  String clientId = "phantasm-" + String((uint32_t)ESP.getEfuseMac(), HEX);
  if (mqtt.connect(clientId.c_str())) {
    mqtt.subscribe(TOPIC);
    mqttConnected = true;
    isIdle = true;
    displayState = DS_RUNNING;
    Serial.println("MQTT connected!");
    return true;
  }
  Serial.print("MQTT failed, rc=");
  Serial.println(mqtt.state());
  return false;
}

void setup() {
  WRITE_PERI_REG(RTC_CNTL_BROWN_OUT_REG, 0);
  Serial.begin(115200);

  if (!display.begin(SSD1306_SWITCHCAPVCC, 0x3C)) { for (;;); }
  display.clearDisplay();
  display.setTextColor(WHITE);
  display.setTextSize(1);
  display.setCursor(0, 0);
  display.println("Booting System...");
  display.display();

  Serial.print("Free heap at start: ");
  Serial.println(ESP.getFreeHeap());

  // Set PubSubClient buffer large enough for the 1024-byte image payload
  mqtt.setBufferSize(1200);
  mqtt.setServer(HOST, PORT);
  mqtt.setCallback(onMessage);

  WiFi.mode(WIFI_STA);

  WiFi.onEvent([](WiFiEvent_t event, WiFiEventInfo_t info) {
    switch (event) {
      case ARDUINO_EVENT_WIFI_STA_START:
        Serial.println("WiFi STA started");
        displayState = DS_WIFI_CONNECTING;
        break;
      case ARDUINO_EVENT_WIFI_STA_CONNECTED:
        Serial.println("Associated to AP — waiting for IP...");
        break;
      case ARDUINO_EVENT_WIFI_STA_GOT_IP:
        Serial.print("Got IP: ");
        Serial.println(WiFi.localIP());
        displayState = DS_MQTT_CONNECTING;
        break;
      case ARDUINO_EVENT_WIFI_STA_DISCONNECTED:
        Serial.print("Disconnected, reason: ");
        Serial.println(info.wifi_sta_disconnected.reason);
        mqttConnected = false;
        isIdle = false;
        displayState = DS_WIFI_CONNECTING;
        break;
      default:
        break;
    }
  });

  WiFi.begin(WIFI_SSID, WIFI_PASS);

  Serial.println("Setup Complete.");
}

void loop() {
  // UI STATUS UPDATES — redraws only on state change
  if (displayState != lastDisplayState) {
    lastDisplayState = displayState;
    display.clearDisplay();
    display.setTextSize(1);
    display.setTextColor(WHITE);
    display.setCursor(0, 0);
    switch (displayState) {
      case DS_BOOTING:
        display.println(F("Booting System..."));
        break;
      case DS_WIFI_CONNECTING:
        display.println(F("Connecting WiFi..."));
        break;
      case DS_MQTT_CONNECTING:
        display.println(F("WiFi OK"));
        display.setCursor(0, 16);
        display.println(F("MQTT connecting..."));
        break;
      case DS_RUNNING:
        break;
    }
    display.display();
  }

  // MQTT CONNECTION MANAGEMENT
  // PubSubClient connect/reconnect runs safely from loop() — no threading needed
  if (WiFi.status() == WL_CONNECTED) {
    if (!mqtt.connected()) {
      mqttConnected = false;
      isIdle = false;
      displayState = DS_MQTT_CONNECTING;
      unsigned long now = millis();
      if (now - lastMqttReconnect > 5000) {
        lastMqttReconnect = now;
        mqttReconnect();
      }
    }
    mqtt.loop(); // Must be called every loop to process incoming messages
  }

  // PROXIMITY SCANNING
  if (isWaitingForBLE && bleInitialized && pBLEScan != nullptr) {
    maxRssi = -100;
    pBLEScan->start(1, false);
    pBLEScan->clearResults();

    if (maxRssi > -50) {
      isWaitingForBLE = false;
      stopBLE();
      display.clearDisplay();
      display.drawBitmap(0, 0, imageBuffer, 128, 64, WHITE);
      display.display();
    }
  }

  // ANIMATIONS (IDLE & SUCCESS)
  if (mqttConnected && isIdle && millis() - lastFrame > 60) {
    lastFrame = millis();
    display.clearDisplay();
    display.drawLine(0, 0, 128, 0, WHITE);
    display.drawLine(0, 63, 128, 63, WHITE);

    int scanLineX = (frameCount * 3) % 128;
    display.drawLine(scanLineX, 2, scanLineX, 61, WHITE);

    for (int i = 0; i < 15; i++) {
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
    display.setTextSize(1);
    display.setCursor(42, 6);
    display.print("SUCCESS");
    display.drawCircle(64, 38, 20, WHITE);

    if (tickFrame > 5)  display.drawLine(54, 38, 62, 46, WHITE);
    if (tickFrame > 10) display.drawLine(62, 46, 76, 30, WHITE);
    if (tickFrame > 15) {
      display.drawLine(54, 39, 62, 47, WHITE);
      display.drawLine(62, 47, 76, 31, WHITE);
    }
    display.display();
    tickFrame++;

    if (tickFrame > 80) {
      isVerified = false;
      isIdle = true;
      frameCount = 0;
    }
  }
}