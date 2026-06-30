# ESPHome LiveState

HA Custom Integration that creates **Online/Offline binary_sensor** entities for all ESPHome devices, attached directly to the existing ESP device in HA — just like PowerCalc attaches power sensors.

## Voraussetzung

Das **MCP ESPHome Addon** muss installiert und gestartet sein. Ohne das Addon zeigt die Integration einen Konfigurationsfehler.

## Installation via HACS

1. HACS → Custom Repository hinzufügen: `https://github.com/eragon02424/Integation_EspHome_LiveState` (Kategorie: Integration)
2. Integration herunterladen
3. HA neu starten
4. `Einstellungen → Geräte & Dienste → Integration hinzufügen → ESPHome LiveState`
5. URL: `http://localhost:8090`, Bearer Token aus dem MCP ESPHome Addon

## Was passiert

- Alle vom MCP ESPHome Addon erkannten Geräte bekommen automatisch eine `binary_sensor.<name>_online` Entity
- Die Entity wird dem vorhandenen ESP-Gerät in HA zugeordnet (via MAC-Adresse)
- Neue Geräte werden automatisch erkannt (kein Neustart nötig)
- Wenn das Addon stoppt → Integration zeigt Fehler
