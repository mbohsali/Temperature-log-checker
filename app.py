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
                lines = page.extract_text().split("\n")

                # Fix broken lines where °C / splits
                fixed_lines = []
                skip = False
                for i, line in enumerate(lines):
                    if skip:
                        skip = False
                        continue
                    if line.strip().endswith("°C /") and i+1 < len(lines):
                        fixed_lines.append(line + " " + lines[i+1])
                        skip = True
                    else:
                        fixed_lines.append(line)

                # Parse device ranges
                device_ranges = {}
                for line in fixed_lines:
                    if "Device:" in line and "°C" in line and "to" in line:
                        range_match = re.findall(r"([\-]?\d+\.\d+)\s*°C", line)
                        dev_match = re.search(r"(FAC-\d+)", line)
                        if range_match and dev_match:
                            low, high = map(float, range_match[:2])
                            device_ranges[dev_match.group(1)] = (low, high)

                # Parse records
                for line in fixed_lines:
                    if line.startswith("FAC-"):
                        parts = line.split()
                        if len(parts) >= 7:
                            device = parts[0]
                            date = " ".join(parts[1:4])   # e.g. "23 Mar 25"
                            time = parts[4]              # e.g. "08:03:01"
                            temp_match = re.search(r"([\-]?\d+\.\d+)\s*°C", line)
                            if temp_match:
                                temp = float(temp_match.group(1))
                                low, high = device_ranges.get(device, (None, None))
                                status = "OK"
                                if low is not None and (temp < low or temp > high):
                                    status = "❌ OUT OF RANGE"
                                all_records.append([
                                    uploaded_file.name, device, date, time, temp, low, high, status
                                ])

    # Convert to DataFrame
    df = pd.DataFrame(all_records, columns=[
        "File", "Device", "Date", "Time", "Temperature (°C)", "Low Limit", "High Limit", "Status"
    ])

    # Save to Excel in memory
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="All Records", index=False)
        # optional: separate sheet for only out-of-range
        df[df["Status"] == "❌ OUT OF RANGE"].to_excel(writer, sheet_name="Out of Range", index=False)

    st.success("✅ Processing complete!")
    st.download_button(
        label="📥 Download Excel Report",
        data=output.getvalue(),
        file_name="temperature_check.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
