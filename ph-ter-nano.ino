// ===============================
// Arduino Nano - pH & Turbidity
// pH sensor -> A1
// Turbidity sensor -> A2
// ===============================

const int PH_PIN = A1;
const int TURB_PIN = A2;

// Calibration offset for pH
const float pH_Offset = 0.00;

// Convert raw ADC (0–1023) to voltage (0–5V range)
float rawToVoltage(int raw) {
  return (raw / 1023.0) * 5.0;
}

void setup() {
  Serial.begin(9600);
  pinMode(PH_PIN, INPUT);
  pinMode(TURB_PIN, INPUT);
}

void loop() {
  // === pH Sensor ===
  int ph_raw = analogRead(PH_PIN);
  float ph_voltage = rawToVoltage(ph_raw);

  // Calibration formula (adjust if needed)
  float ph_value = (11.09 * ph_voltage) - 15.22 + pH_Offset;
  ph_value = constrain(ph_value, 0, 14);

  // === Turbidity Sensor ===
  int turb_raw = analogRead(TURB_PIN);
  float turb_voltage = rawToVoltage(turb_raw);

  float turbidity;
  if (turb_voltage >= 4.14) {
    turbidity = map(turb_voltage * 100, 414, 500, 5, 0);  // clean water zone
  } else {
    turbidity = -1120.4 * turb_voltage * turb_voltage +
                 5742.3 * turb_voltage - 4352.9;
  }
  turbidity = constrain(turbidity, 0, 1000);

  // === Output ===
  Serial.print("pH Raw: ");
  Serial.print(ph_raw);
  Serial.print(" | Voltage: ");
  Serial.print(ph_voltage, 3);
  Serial.print(" V | pH: ");
  Serial.print(ph_value, 2);

  Serial.print(" || Turb Raw: ");
  Serial.print(turb_raw);
  Serial.print(" | Voltage: ");
  Serial.print(turb_voltage, 3);
  Serial.print(" V | NTU: ");
  Serial.println(turbidity, 2);

  delay(2000); // update every 2s
}
