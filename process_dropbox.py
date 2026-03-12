import os
import csv
import dropbox
from dropbox.exceptions import ApiError

DROPBOX_TOKEN = os.getenv("DROPBOX_ACCESS_TOKEN")
TARGET_FOLDER = "" # Leave empty ("") for root folder

def convert_txt_to_csv(local_txt_path, local_csv_path):
    with open(local_txt_path, "rb") as f:
        content = f.read()

    col1 =['Cell'+str(i+1) for i in range(14)]
    col2 =['Temp'+str(i+1)+' C' for i in range(5)]
    
    # FIXED: Removed the invalid backslash 
    col_names = ['Date','Time','Current','Mode','Voltage'] + col2 + col1 +['Max Cell','Min Cell','Cell Difference','State of Charge(SOC)','Fault','Charging','DisCharging']

    # Process chunks of 47 bytes safely
    with open(local_csv_path, 'w', newline='') as csvfile:
        csv_writer = csv.writer(csvfile)
        csv_writer.writerow(col_names)

        # Loop through content in exact 47-byte blocks
        for i in range(0, len(content) - 46, 47):
            d1 =[b for b in content[i:i + 47]]

            da = f"{d1[0]:02d}:{d1[1]:02d}:{d1[2]:02d}"
            tim = f"{d1[3]:02d}:{d1[4]:02d}:{d1[5]:02d}"
            
            state = int(format(d1[6], '08b')[5:], 2)
            fau = int(format(d1[6], '08b')[:5], 2)

            faul = 'ALL OK' if fau + d1[12] + d1[13] == 0 else 'Faults'
            charg = 'Off' if state in [1, 0, 3] else 'On'
            disch = 'Off' if state in [1, 0, 2] else 'On'
            mod = 'Idle' if state in [0, 1] else 'Charging' if state == 2 else 'Discharging'

            cell_va = [float(d1[14+j] + (d1[15+j] << 8)) / 10000 for j in range(0, 28, 2)]
            tem_val = d1[42:47] 
            
            min1_cel = min(cell_va)
            max1_cel = max(cell_va)

            datal1 = [
                da, tim,
                float(d1[8] + (d1[9] << 8)) / 10,
                mod,
                float(d1[10] + (d1[11] << 8)) / 100
            ] + tem_val + cell_va +[max1_cel, min1_cel, (max1_cel - min1_cel), d1[7], faul, charg, disch]

            if len(datal1) == 31:
                csv_writer.writerow(datal1)
                
    return True

def main():
    if not DROPBOX_TOKEN:
        print("Error: DROPBOX_ACCESS_TOKEN environment variable not set.")
        return

    dbx = dropbox.Dropbox(DROPBOX_TOKEN)
    
    try:
        # Get all files in the folder
        result = dbx.files_list_folder(TARGET_FOLDER)
        
        for entry in result.entries:
            # Look for ANY .TXT file
            if isinstance(entry, dropbox.files.FileMetadata) and entry.name.upper().endswith('.TXT'):
                txt_filename = entry.name
                # Keep exact same filename, just change .TXT to .csv
                csv_filename = txt_filename.rsplit('.', 1)[0] + '.csv'
                
                txt_path_lower = entry.path_lower
                csv_path_lower = txt_path_lower.rsplit('.', 1)[0] + '.csv'
                csv_path_display = entry.path_display.rsplit('.', 1)[0] + '.csv'
                
                # Check if this exact CSV already exists in Dropbox
                try:
                    dbx.files_get_metadata(csv_path_lower)
                    print(f"Skipping {txt_filename}... {csv_filename} already exists!")
                    continue # Skips to the next file if CSV is found
                except ApiError as e:
                    if e.error.is_path() and e.error.get_path().is_not_found():
                        pass # CSV doesn't exist, proceed to process
                    else:
                        raise

                print(f"Processing new file: {txt_filename}...")
                
                # Download TXT file to GitHub runner
                local_txt = f"./{txt_filename}"
                local_csv = f"./{csv_filename}"
                dbx.files_download_to_file(local_txt, txt_path_lower)

                # Convert binary TXT to CSV
                success = convert_txt_to_csv(local_txt, local_csv)
                
                if success:
                    # Upload newly created CSV back to Dropbox (Leaves original TXT untouched)
                    with open(local_csv, 'rb') as f:
                        dbx.files_upload(f.read(), csv_path_display, mode=dropbox.files.WriteMode.overwrite)
                    print(f"Successfully uploaded {csv_filename} to Dropbox!")
                
                # Clean up local temporary files from GitHub Server
                if os.path.exists(local_txt): os.remove(local_txt)
                if os.path.exists(local_csv): os.remove(local_csv)

    except Exception as e:
        print(f"An error occurred: {e}")

if __name__ == "__main__":
    main()
