import streamlit as st
import pandas as pd
import numpy as np
import io

# Set page config
st.set_page_config(page_title="Water Quality Data Cleaner", layout="wide")

st.title("Water Quality Data Cleaner & Calibrator")
st.markdown("""
This tool processes raw sensor data for **pH** and **Turbidity (NTU)**.
1.  **Upload** your Excel or CSV file.
2.  **Auto-Correction**:
    *   **pH**: Applies formula `(11.09 * V - 15.22)` and adds a **-1.0 Offset**.
    *   **NTU**: Applies the correct piecewise formula (no negative values).
3.  **Filtering**: Removes rows where pH is outside the **6.0 - 9.0** range.
""")

# File Uploader
uploaded_file = st.file_uploader("Upload your file (Excel or CSV)", type=['xlsx', 'csv'])

def calculate_ntu(voltage):
    # Piecewise formula for DFRobot Turbidity Sensor
    if voltage >= 4.2:
        # Clean water zone (Linear)
        val = 5 - ((voltage * 100 - 414) / (500 - 414)) * 5
    else:
        # Dirty water zone (Polynomial)
        val = (-1120.4 * (voltage**2)) + (5742.3 * voltage) - 4352.9
    
    # Clamp between 0 and 1000
    return max(0, min(1000, val))

def calculate_ph(voltage, offset=0.0):
    # Linear formula with user-defined offset
    # Original: 11.09 * V - 15.22
    # With offset: (11.09 * V - 15.22) + offset
    return (11.09 * voltage - 15.22) + offset

if uploaded_file is not None:
    try:
        # Read file
        if uploaded_file.name.endswith('.csv'):
            df = pd.read_csv(uploaded_file)
        else:
            df = pd.read_excel(uploaded_file)
        
        st.write("### Raw Data Preview")
        st.dataframe(df.head())
        
        # Column Selection
        cols = df.columns.tolist()
        
        # Try to auto-select columns
        ph_volt_default = cols.index('pH_Voltage') if 'pH_Voltage' in cols else 0
        turb_volt_default = cols.index('Turb_Voltage') if 'Turb_Voltage' in cols else 0
        
        col1, col2 = st.columns(2)
        with col1:
            ph_col = st.selectbox("Select pH Voltage Column", cols, index=ph_volt_default)
        with col2:
            turb_col = st.selectbox("Select Turbidity Voltage Column", cols, index=turb_volt_default)
        
        # pH Offset Control
        ph_offset = st.number_input(
            "pH Offset (Calibration Adjustment)", 
            value=-1.0, 
            step=0.1, 
            format="%.2f",
            help="Adjust the pH calibration offset. Default is -1.0"
        )
        
        # NTU Range Control
        col_ntu1, col_ntu2 = st.columns(2)
        with col_ntu1:
            ntu_min = st.number_input(
                "NTU Minimum", 
                value=0.0, 
                step=1.0, 
                format="%.1f",
                help="Minimum NTU value to keep (default: 0)"
            )
        with col_ntu2:
            ntu_max = st.number_input(
                "NTU Maximum", 
                value=1000.0, 
                step=10.0, 
                format="%.1f",
                help="Maximum NTU value to keep (default: 1000)"
            )
            
        if st.button("Process Data"):
            # Process
            processed_df = df.copy()
            
            # Calculate pH with user-defined offset
            processed_df['pH'] = processed_df[ph_col].apply(lambda v: calculate_ph(v, ph_offset)).round(2)
            
            # Calculate NTU and track corrections
            # First calculate raw NTU without clamping to see what would happen
            def calculate_ntu_raw(voltage):
                if voltage >= 4.2:
                    return 5 - ((voltage * 100 - 414) / (500 - 414)) * 5
                else:
                    return (-1120.4 * (voltage**2)) + (5742.3 * voltage) - 4352.9
            
            processed_df['NTU_raw_calc'] = processed_df[turb_col].apply(calculate_ntu_raw)
            processed_df['NTU'] = processed_df[turb_col].apply(calculate_ntu).round(2)
            
            # Track NTU corrections
            ntu_negative_count = (processed_df['NTU_raw_calc'] < 0).sum()
            ntu_over1000_count = (processed_df['NTU_raw_calc'] > 1000).sum()
            ntu_corrected_count = ntu_negative_count + ntu_over1000_count
            
            # Filter by BOTH pH AND NTU ranges
            # Keep rows where: (6 <= pH <= 9) AND (ntu_min <= NTU <= ntu_max)
            filtered_df = processed_df[
                (processed_df['pH'] >= 6) & 
                (processed_df['pH'] <= 9) &
                (processed_df['NTU'] >= ntu_min) &
                (processed_df['NTU'] <= ntu_max)
            ].copy()
            
            # Count how many rows are in the NTU range BEFORE filtering
            ntu_in_range_before_filter = ((processed_df['NTU'] >= ntu_min) & 
                                          (processed_df['NTU'] <= ntu_max)).sum()
            
            # Track removal reasons
            # Create boolean masks for pH and NTU validity
            ph_valid = (processed_df['pH'] >= 6) & (processed_df['pH'] <= 9)
            ntu_valid = (processed_df['NTU'] >= ntu_min) & (processed_df['NTU'] <= ntu_max)
            
            # Count different removal scenarios
            ph_wrong_ntu_correct = (~ph_valid & ntu_valid).sum()  # pH bad, NTU good
            ntu_wrong_ph_correct = (ph_valid & ~ntu_valid).sum()  # NTU bad, pH good
            both_wrong = (~ph_valid & ~ntu_valid).sum()           # Both bad
            
            # Remove rows with missing timestamps (if Timestamp column exists)
            if 'Timestamp' in filtered_df.columns:
                filtered_df = filtered_df.dropna(subset=['Timestamp'])
                # Also remove rows where Timestamp is empty string
                filtered_df = filtered_df[filtered_df['Timestamp'].astype(str).str.strip() != '']
            
            # Drop rows where only timestamp exists but all other data columns are null
            # Check if at least one of the important columns has data
            important_cols = [col for col in ['pH_Raw', 'Turb_Raw', ph_col, turb_col, 'pH', 'NTU'] 
                            if col in filtered_df.columns]
            if important_cols:
                filtered_df = filtered_df.dropna(subset=important_cols, how='all')
            
            # Rename and Select Columns
            # User wants to keep original names but include new calculations
            # Final structure: Timestamp, pH_Raw, pH_Voltage, pH, Turb_Raw, Turb_Voltage, NTU
            
            final_columns = []
            
            # Timestamp
            if 'Timestamp' in filtered_df.columns:
                final_columns.append('Timestamp')
            
            # pH Raw
            if 'pH_Raw' in filtered_df.columns:
                final_columns.append('pH_Raw')
            
            # pH Voltage
            # We used 'ph_col' for calculation. Use the actual column name from the file.
            # If the user selected a different column, we keep that name.
            if ph_col not in final_columns:
                final_columns.append(ph_col)
                
            # pH (Calculated)
            final_columns.append('pH')
            
            # Turb Raw
            if 'Turb_Raw' in filtered_df.columns:
                final_columns.append('Turb_Raw')
            elif 'ntu raw' in filtered_df.columns: # In case input already had this
                final_columns.append('ntu raw')
                
            # Turb Voltage
            # We used 'turb_col' for calculation. Keep original name.
            if turb_col not in final_columns:
                final_columns.append(turb_col)
                
            # NTU (Calculated)
            final_columns.append('NTU')
            
            # Select only these columns if they exist
            existing_final_cols = [c for c in final_columns if c in filtered_df.columns]
            final_df = filtered_df[existing_final_cols]
            
            # Identify removed rows (for download option)
            # Get the indices that were removed
            removed_indices = processed_df.index.difference(filtered_df.index)
            removed_df = processed_df.loc[removed_indices].copy()
            
            # Apply same column selection to removed data
            if not removed_df.empty:
                removed_final_cols = [c for c in final_columns if c in removed_df.columns]
                removed_df = removed_df[removed_final_cols]
            
            # Statistics
            st.divider()
            st.write("### Processing Results")
            
            m1, m2, m3 = st.columns(3)
            m1.metric("Original Rows", len(df))
            m2.metric("Filtered Rows (pH 6-9 & NTU Range)", len(final_df))
            m3.metric("Removed Rows", len(removed_df))
            
            # NTU Correction Statistics
            st.write("### NTU Correction Statistics")
            col_ntu1, col_ntu2, col_ntu3, col_ntu4 = st.columns(4)
            
            with col_ntu1:
                st.metric(
                    "Negative Values Fixed", 
                    ntu_negative_count,
                    help="NTU values that were negative and got clamped to 0"
                )
            
            with col_ntu2:
                st.metric(
                    "Values Clamped (>1000)", 
                    ntu_over1000_count,
                    help="NTU values that were >1000 and got clamped to 1000"
                )
            
            with col_ntu3:
                st.metric(
                    "Total NTU Corrections", 
                    ntu_corrected_count,
                    help="Total number of NTU values that were corrected"
                )
            
            with col_ntu4:
                st.metric(
                    f"Rows in NTU Range ({ntu_min}-{ntu_max})", 
                    ntu_in_range_before_filter,
                    help="Rows with NTU in your specified range (before pH filtering)"
                )
            
            # Removal Reason Statistics
            st.write("### Removal Reason Breakdown")
            st.markdown("*Why were rows removed?*")
            
            col_r1, col_r2, col_r3 = st.columns(3)
            
            with col_r1:
                st.metric(
                    "❌ pH Wrong, ✅ NTU Correct", 
                    ph_wrong_ntu_correct,
                    help=f"Rows removed because pH was outside 6-9 range, but NTU was within {ntu_min}-{ntu_max}"
                )
            
            with col_r2:
                st.metric(
                    "✅ pH Correct, ❌ NTU Wrong", 
                    ntu_wrong_ph_correct,
                    help=f"Rows removed because NTU was outside {ntu_min}-{ntu_max} range, but pH was within 6-9"
                )
            
            with col_r3:
                st.metric(
                    "❌ Both Wrong", 
                    both_wrong,
                    help="Rows removed because BOTH pH and NTU were outside their acceptable ranges"
                )
            
            st.write("#### Filtered Data Preview")
            st.dataframe(final_df.head())
            
            # Download buttons
            col1, col2 = st.columns(2)
            
            with col1:
                csv = final_df.to_csv(index=False).encode('utf-8')
                st.download_button(
                    label="📥 Download Cleaned Data (CSV)",
                    data=csv,
                    file_name="cleaned_water_data.csv",
                    mime="text/csv",
                    type="primary"
                )
            
            with col2:
                if not removed_df.empty:
                    removed_csv = removed_df.to_csv(index=False).encode('utf-8')
                    st.download_button(
                        label="🗑️ Download Removed Rows (CSV)",
                        data=removed_csv,
                        file_name="removed_rows.csv",
                        mime="text/csv",
                        type="secondary"
                    )
                else:
                    st.info("No rows were removed")
            
            
            # Visualization
            st.divider()
            st.write("### Visualization (Cleaned Data)")
            chart_data = final_df[['pH', 'NTU']]
            st.scatter_chart(chart_data)

    except Exception as e:
        st.error(f"Error processing file: {e}")
