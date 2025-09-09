import streamlit as st
import pdfplumber
import pandas as pd
import re
import io

st.set_page_config(page_title="Temperature Checker", page_icon="🌡️", layout="centered")

st.title("🌡️ Temperature Range Checker")
st.write("Upload one or more PDF reports, and get an Excel summary showing whether all readings are in range.")

uploaded_files = st.file_uploader("📂 Upload PDF files", type=["pdf"], accept_multiple_files=True)

if uploaded_files:
    all_records = []

    for uploaded_file in uploaded_files:
        with pdfplumber.open(uploaded_file) as pdf:
            for page in pdf.pages:
                text = page.extract_text()
                if not text:
                    continue

                lines = text.split("\n")

                # --- Fix broken lines like "2.78 °C /" + "37.0 °F"
                fixed_lines = []
                skip = False
                for i, line in enumerate(lines):
                    if skip:
                        skip = False
                        continue
                    if line.strip().endswith("°C /") and i + 1 < len(lines):
                        fixed_lines.append(line + " " + lines[i + 1])
                        skip = True
                    else:
                        fixed_lines.append(line)

                # --- Parse device ranges from "nullRange"
                device_ranges = {}
                for i, line in enumerate(fixed_lines):
                    if "nullRange:" in line and "Device:" in fixed_lines[i + 1]:
                        range_match = re.findall(r"([\-]?\d+\.\d+)\s*°C", line)
                        dev_match = re.search(r"(FAC[0-9A-Z\-]+)", fixed_lines[i + 1])
                        if range_match and dev_match:
                            low, high = map(float, range_match[:2])
                            device_ranges[dev_match.group(1)] = (low, high)

                # --- Parse temperature records
                for line in fixed_lines:
                    if line.startswith("FAC-") or line.startswith("FAC"):
                        parts = line.split()
                        if len(parts) >= 7:
                            device = parts[0]
                            date = " ".join(parts[1:4])   # e.g. "04 Dec 22"
                            time = parts[4]              # e.g. "08:02:33"

                            temp_match = re.search(r"([\-]?\d+\.\d+)\s*°C", line)
                            if temp_match:
                                temp = float(temp_match.group(1))
                                low, high = device_ranges.get(device, (None, None))
                                status = "OK"

                                # --- Apply rules ---
                                if "AMB" in device:  # Ambient device
                                    low, high = 15.0, 30.0
                                    if 20.0 <= temp <= 25.0:
                                        status = "OK"
                                    elif 15.0 <= temp < 20.0 or 25.0 < temp <= 30.0:
                                        status = "⚠️ Excursion"
                                    else:
                                        status = "❌ Out of Range"

                                elif "REF" in device:  # Fridge
                                    if low is not None and (temp < low or temp > high):
                                        status = "❌ Out of Range"

                                else:  # Freezer or other devices
                                    if low is not None and (temp < low or temp > high):
                                        status = "❌ Out of Range"

                                all_records.append([
                                    uploaded_file.name, device, date, time, temp, low, high, status
                                ])

    # --- Convert to DataFrame ---
    df = pd.DataFrame(all_records, columns=[
        "File", "Device", "Date", "Time", "Temperature (°C)", "Low Limit", "High Limit", "Status"
    ])

    # --- Save to Excel in memory ---
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="All Records", index=False)
        df[df["Status"].str.contains("Out of Range|Excursion")].to_excel(
            writer, sheet_name="Alerts", index=False
        )

    st.success("✅ Processing complete!")
    st.download_button(
        label="📥 Download Excel Report",
        data=output.getvalue(),
        file_name="temperature_check.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
