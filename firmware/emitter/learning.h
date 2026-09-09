#pragma once
#include <WebServer.h>
#include <Preferences.h>
#include <ESPmDNS.h>
#include "learning_page.h"

// The final classic ESP32 carrier uses GPIO27 for the button and GPIO15 for RX.
// C3 support retains a buildable alternative; it requires its own wiring.
#if CONFIG_IDF_TARGET_ESP32C3
static const uint8_t LEARN_BUTTON_PIN = 1, LEARN_RX_PIN = 3;
#else
static const uint8_t LEARN_BUTTON_PIN = 27, LEARN_RX_PIN = 15;
#endif
static const char *TOPIC_LEARN = "revgen/emitter/learn";
static const char *TOPIC_LEARN_ACK = "revgen/emitter/learn_ack";
static constexpr size_t LEARN_SLOTS = 32;
static WebServer learnWeb(80);
static Preferences learnPrefs;
static String learnRecords[LEARN_SLOTS];
static bool learningActive = false, learnArmed = false, learnReady = false;
static bool learnStorage = false, learnHaveFirst = false;
static String learnSession, learnProducer, learnMessage = "Ready", firstCode, capturedCode;
static uint32_t learnTouched = 0, learnStarted = 0, learnSequence = 0, learnVersion = 0;
static uint32_t lastIrSeen = 0, lastUpload = 0, captureStarted = 0;

static String randomId() {
  char id[33]; snprintf(id, sizeof(id), "%08lx%08lx%08lx%08lx",
    (unsigned long)esp_random(), (unsigned long)esp_random(),
    (unsigned long)esp_random(), (unsigned long)esp_random()); return String(id);
}
static String recordKey(size_t i) { return "r" + String(i); }
static bool storeRecord(size_t i, const String &value) {
  if (!learnStorage || learnPrefs.putString(recordKey(i).c_str(), value) != value.length()) return false;
  learnRecords[i] = value; return true;
}
static void learnReply(int status, const String &message, bool error = false) {
  JsonDocument d; d[error ? "error" : "message"] = message;
  String s; serializeJson(d,s); learnWeb.send(status,"application/json",s);
}
static bool allowed() {
  // Host validation prevents DNS-rebinding; nonce prevents cross-origin forms/fetches.
  String host = learnWeb.hostHeader(); host.toLowerCase();
  bool hostOK = host == WiFi.localIP().toString() || host == "revgen-emitter.local" ||
                host == WiFi.localIP().toString()+":80" || host == "revgen-emitter.local:80";
  if (!learningActive || !hostOK || learnWeb.header("X-Learn-Token") != learnSession) {
    learnReply(403,"Open the page after holding the physical button for 5 seconds",true);return false;
  }
  learnWeb.sendHeader("Cache-Control","no-store");return true;
}
static bool requestBody(JsonDocument &d) {
  if (!allowed()) return false;
  String body=learnWeb.arg("plain");
  if (body.length()>1024 || deserializeJson(d,body) || !d.is<JsonObject>()) {
    learnReply(400,"Invalid request",true);return false;
  }
  learnTouched=millis();return true;
}
static bool slug(const String &s) {
  if (!s.length() || s.length()>32 || s[0]<'a' || s[0]>'z') return false;
  for (char c:s) if (!(c>='a'&&c<='z') && !(c>='0'&&c<='9') && c!='_') return false;
  return true;
}
static bool displayName(const String &s) {
  if (!s.length() || s.length()>64) return false;
  for(size_t i=0;i<s.length();i++) if((uint8_t)s[i]<32) return false;
  return true;
}
static void leaveLearning() {
  learningActive=false;learnArmed=false;learnReady=false;learnSession="";
  IrReceiver.stop();learnWeb.stop();led(false);Serial.println("learning mode closed");
}
static void enterLearning() {
  learningActive=true; learnSession=randomId();learnTouched=learnStarted=millis();
  learnArmed=learnReady=learnHaveFirst=false;capturedCode="";learnVersion++;
  learnMessage="Start capture, then press and release the remote button twice.";
  IrReceiver.begin(LEARN_RX_PIN, DISABLE_LED_FEEDBACK);learnWeb.begin();
  Serial.printf("Learning page: http://%s/ (or http://revgen-emitter.local/)\n",WiFi.localIP().toString().c_str());
}
static void saveMapping(bool channel) {
  JsonDocument req;if(!requestBody(req))return;
  if(!channel && (!learnReady || req["version"].as<uint32_t>()!=learnVersion)) {
    learnReply(409,"Capture the same button twice first",true);return;
  }
  String device=req["device"]|"", name=req["name"]|"", action=req["action"]|"";
  String deviceName=req["device_name"]|"", behavior=req["behavior"]|"button";
  if(!slug(device)||!slug(action)||!displayName(name)||!displayName(deviceName)||
    (behavior!="button"&&behavior!="power_toggle"&&behavior!="power_on"&&behavior!="power_off")) {
    learnReply(400,"Use lowercase IDs and names of 1-64 UTF-8 bytes",true);return;
  }
  if(!channel && ((action=="power"&&behavior!="power_toggle") ||
    ((action=="power_on"||action=="power_off")&&behavior!=action))) {
    learnReply(400,"Select the correct power behavior; ordinary power buttons toggle",true);return;
  }
  String number=req["channel_number"]|"";
  if(channel) {
    if(device!="stb"||!number.length()||number.length()>6){learnReply(400,"Channel requires stb and 1-6 digits",true);return;}
    for(char c:number)if(c<'0'||c>'9'){learnReply(400,"Channel must contain digits only",true);return;}
  }
  int slot=-1;
  for(size_t i=0;i<LEARN_SLOTS;i++) {
    if(!learnRecords[i].length()){if(slot<0)slot=i;continue;}
    JsonDocument old;deserializeJson(old,learnRecords[i]);JsonObject e=old["entry"];
    if(e["device"]==device && e["action"]==action && e["kind"]==(channel?"channel":"command")){slot=i;break;}
  }
  if(slot<0){learnReply(507,"Local mapping capacity reached (32 entries)",true);return;}
  if(!learnStorage || learnSequence==UINT32_MAX || !learnPrefs.putUInt("seq",learnSequence+1)) {
    learnReply(507,"Local storage unavailable; nothing uploaded",true);return;
  }
  learnSequence++;
  JsonDocument doc;JsonObject e=doc["entry"].to<JsonObject>();
  e["id"]=randomId();e["producer"]=learnProducer;e["sequence"]=learnSequence;
  e["kind"]=channel?"channel":"command";e["device"]=device;e["device_name"]=deviceName;
  e["action"]=action;e["name"]=name;e["behavior"]=behavior;
  if(channel)e["channel_number"]=number;
  else {JsonDocument code;deserializeJson(code,capturedCode);e["code"].set(code.as<JsonObject>());}
  doc["synced"]=false;
  String saved;serializeJson(doc,saved);
  if(!storeRecord(slot,saved)){learnReply(507,"Flash storage full; mapping was not saved",true);return;}
  learnReady=false;learnMessage="Saved locally. Waiting for backend upload acknowledgement.";
  learnReply(200,learnMessage);
}
static void learningAck(byte *payload,unsigned int length) {
  JsonDocument ack;if(deserializeJson(ack,payload,length))return;
  for(size_t i=0;i<LEARN_SLOTS;i++) {
    if(!learnRecords[i].length())continue;
    JsonDocument d;deserializeJson(d,learnRecords[i]);
    if(d["entry"]["id"]!=ack["id"] || d["synced"].as<bool>())continue;
    d["synced"]=ack["ok"]==true;d["error"]=ack["error"]|"";d["warning"]=ack["warning"]|"";
    String saved;serializeJson(d,saved);
    if(!storeRecord(i,saved))learnMessage="Backend received mapping; local ACK persistence failed, retry pending.";
    else learnMessage=ack["ok"]==true?"Mapping uploaded and available to the backend.":"Backend refused mapping. Check server configuration or edit and save again.";
    break;
  }
}
static void learningSetup() {
  pinMode(LEARN_BUTTON_PIN,INPUT_PULLUP);
  learnStorage=learnPrefs.begin("revgen-learn",false);
  if(learnStorage) {
    learnProducer=learnPrefs.getString("producer","");
    if(!learnProducer.length()){learnProducer=randomId();learnStorage=learnPrefs.putString("producer",learnProducer)==learnProducer.length();}
    learnSequence=learnPrefs.getUInt("seq",0);
    for(size_t i=0;i<LEARN_SLOTS;i++)learnRecords[i]=learnPrefs.getString(recordKey(i).c_str(),"");
  }
  if(MDNS.begin("revgen-emitter"))MDNS.addService("http","tcp",80);
  const char *headers[]={"X-Learn-Token"};learnWeb.collectHeaders(headers,1);
  learnWeb.on("/",HTTP_GET,[]{
    if(!learningActive){learnReply(403,"Learning mode closed",true);return;}
    learnWeb.sendHeader("Cache-Control","no-store");
    learnWeb.sendHeader("X-Frame-Options","DENY");
    String page=FPSTR(LEARNING_PAGE);page.replace("__SESSION__",learnSession);learnWeb.send(200,"text/html",page);
  });
  learnWeb.on("/api/status",HTTP_GET,[]{
    if(!allowed())return;
    JsonDocument d;d["message"]=learnMessage;d["ready"]=learnReady;d["version"]=learnVersion;
    if(capturedCode.length()){JsonDocument c;deserializeJson(c,capturedCode);d["code"].set(c.as<JsonObject>());}
    JsonArray entries=d["entries"].to<JsonArray>();
    for(const String &s:learnRecords)if(s.length()) {
      JsonDocument r;deserializeJson(r,s);JsonObject v=entries.add<JsonObject>();
      v["device_name"]=r["entry"]["device_name"];v["name"]=r["entry"]["name"];
      v["synced"]=r["synced"];v["error"]=r["error"]|"";v["warning"]=r["warning"]|"";
    }
    String response;serializeJson(d,response);learnWeb.send(200,"application/json",response);
  });
  learnWeb.on("/api/capture",HTTP_POST,[]{JsonDocument d;if(!requestBody(d))return;
    learnArmed=true;learnReady=learnHaveFirst=false;capturedCode="";learnVersion++;captureStarted=millis();lastIrSeen=millis();
    learnMessage="Press and release the original remote button once.";learnReply(200,learnMessage);
  });
  learnWeb.on("/api/test",HTTP_POST,[]{JsonDocument d;if(!requestBody(d))return;
    if(!learnReady || d["version"].as<uint32_t>()!=learnVersion){learnReply(409,"Capture twice first",true);return;}
    JsonDocument code;deserializeJson(code,capturedCode);IrReceiver.stop();
    if(code["protocol"]=="panasonic")IrSender.sendPanasonic(code["address"].as<uint16_t>(),code["command"].as<uint8_t>(),0);
    else IrSender.sendNECRaw(code["raw"].as<uint32_t>(),0);
    delay(100);IrReceiver.start();IrReceiver.resume();lastIrSeen=millis();
    learnMessage="Test sent. Confirm the appliance responded; reception alone cannot prove that.";learnReply(200,learnMessage);
  });
  learnWeb.on("/api/save",HTTP_POST,[]{saveMapping(false);});
  learnWeb.on("/api/channel",HTTP_POST,[]{saveMapping(true);});
  learnWeb.on("/api/retry",HTTP_POST,[]{JsonDocument d;if(!requestBody(d))return;
    for(size_t i=0;i<LEARN_SLOTS;i++)if(learnRecords[i].length()) {
      JsonDocument r;deserializeJson(r,learnRecords[i]);if(r["synced"].as<bool>())continue;
      r.remove("error");String s;serializeJson(r,s);storeRecord(i,s);
    }lastUpload=0;learnReply(200,"Pending uploads will retry");
  });
  learnWeb.on("/api/exit",HTTP_POST,[]{JsonDocument d;if(!requestBody(d))return;learnReply(200,"Learning mode closed");leaveLearning();});
}

static void learningLoop() {
  static bool rawLast=false,stable=false,held=false;static uint32_t changed=0,pressed=0;
  bool raw=digitalRead(LEARN_BUTTON_PIN)==LOW;uint32_t now=millis();
  if(raw!=rawLast){rawLast=raw;changed=now;}
  if(now-changed>=40 && raw!=stable){stable=raw;if(stable)pressed=now;else held=false;}
  if(stable&&!held&&now-pressed>=5000&&!hasPending) {
    held=true;if(learningActive)leaveLearning();else enterLearning();
  }
  if(learningActive) {
    learnWeb.handleClient();led((now/180)%2);
    if(now-learnTouched>300000UL||now-learnStarted>1800000UL){leaveLearning();return;}
    if(learnArmed&&now-captureStarted>60000){learnArmed=false;learnMessage="Capture timed out. Start capture again.";}
    if(IrReceiver.decode()) {
      auto data=IrReceiver.decodedIRData;uint32_t quiet=now-lastIrSeen;lastIrSeen=now;IrReceiver.resume();
      if(learnArmed&&!(data.flags&(IRDATA_FLAGS_IS_REPEAT|IRDATA_FLAGS_WAS_OVERFLOW|IRDATA_FLAGS_PARITY_FAILED))&&quiet>=250) {
        JsonDocument code;code["type"]="ir";code["repeat"]=0;
        bool supported=true;
        if(data.protocol==PANASONIC && data.numberOfBits==48 && data.address<=0xFFF && data.command<=0xFF) {
          code["protocol"]="panasonic";code["address"]=data.address;code["command"]=data.command;
        }else if((data.protocol==NEC||data.protocol==NEC2)&&data.numberOfBits==32) {
          code["protocol"]="nec_raw";code["raw"]=(uint32_t)data.decodedRawData;
        }else supported=false;
        if(!supported){learnMessage="Unsupported or incomplete protocol. This version learns NEC and Panasonic only (not AC state frames).";learnHaveFirst=false;}
        else {
          String fresh;serializeJson(code,fresh);
          if(!learnHaveFirst){firstCode=fresh;learnHaveFirst=true;learnMessage="First press captured. Release, wait a moment, then press the SAME button again.";}
          else if(firstCode!=fresh){learnHaveFirst=false;learnMessage="Signals differed. Start again with two separate presses of the same button.";}
          else {
            capturedCode=fresh;learnArmed=false;learnReady=true;learnTouched=now;learnVersion++;
            learnMessage="Two matching presses captured. Test, name and save.";
            for(const String &s:learnRecords)if(s.length()) {
              JsonDocument old;deserializeJson(old,s);String other;serializeJson(old["entry"]["code"],other);
              if(other==fresh){learnMessage="Duplicate signal already saved. Check the assigned action before saving another name.";break;}
            }
          }
        }
      }
    }
  }
  // One durable outbox record at a time, oldest first; updates cannot overtake each other.
  if(!mqtt.connected()||now-lastUpload<5000)return;
  int slot=-1;uint32_t seq=UINT32_MAX;
  for(size_t i=0;i<LEARN_SLOTS;i++)if(learnRecords[i].length()) {
    JsonDocument r;deserializeJson(r,learnRecords[i]);
    if(!r["synced"].as<bool>()&&!String(r["error"]|"").length()&&r["entry"]["sequence"].as<uint32_t>()<seq) {
      slot=i;seq=r["entry"]["sequence"].as<uint32_t>();
    }
  }
  if(slot>=0){JsonDocument r;deserializeJson(r,learnRecords[slot]);String payload;serializeJson(r["entry"],payload);
    if(payload.length()<=1536)mqtt.publish(TOPIC_LEARN,payload.c_str(),false);lastUpload=now;
  }
}
