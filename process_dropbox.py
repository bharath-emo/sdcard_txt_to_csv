import os
import csv
import dropbox
from dropbox.exceptions import ApiError

# Get Dropbox token from GitHub Secrets
DROPBOX_TOKEN = os.getenv("DROPBOX_ACCESS_TOKEN")
TARGET_FOLDER = "" # Leave empty ("") for root folder, or use "/YourFolderName"

def convert_txt_to_csv(local_txt_path, local_csv_path):
    """Your exact binary processing logic, optimized for file I/O"""
    with open(local_txt_path, "rb") as f:
        content = f.read()

    # Generate Headers
    col1 =['Cell'+str(i+1) for i in range(14)]
    col2 =['Temp'+str(i+1)+' C' for i in range(5)]
    col_names = ['Date','Time','Current','Mode','Voltage'] + col2 + col1 + \['Max Cell','Min Cell','Cell Difference','State of Charge(SOC)','Fault','Charging','DisCharging']

    if len(content) % 47 != 0:
        print(f"Warning: File {local_txt_path} is incomplete or corrupted (not a multiple of 47 bytes).")
        return False

    # Open CSV once for writing (Much faster than opening in 'a' mode inside the loop)
    with open(local_csv_path, 'w', newline='') as csvfile:
        csv_writer = csv.writer(csvfile)
        csv_writer.writerow(col_names)

        for i in range(0, len(content), 47):
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
        # List files in the Dropbox folder
        result = dbx.files_list_folder(TARGET_FOLDER)
        
        for entry in result.entries:
            if isinstance(entry, dropbox.files.FileMetadata) and entry.name.upper().endswith('.TXT'):
                txt_path_lower = entry.path_lower
                csv_path_lower = txt_path_lower.rsplit('.', 1)[0] + '.csv'
                
                # Check if CSV already exists to avoid reprocessing
                try:
                    dbx.files_get_metadata(csv_path_lower)
                    print(f"Skipping {entry.name}, CSV already exists.")
                    continue
                except ApiError as e:
                    if e.error.is_path() and e.error.get_path().is_not_found():
                        pass # CSV doesn't exist, proceed!
                    else:
                        raise

                print(f"Processing {entry.name}...")
                
                # Download TXT file from Dropbox
                local_txt = f"./{entry.name}"
                local_csv = local_txt.rsplit('.', 1)[0] + '.csv'
                dbx.files_download_to_file(local_txt, txt_path_lower)

                # Convert binary TXT to CSV using your logic
                success = convert_txt_to_csv(local_txt, local_csv)
                
                if success:
                    # Upload CSV back to Dropbox
                    with open(local_csv, 'rb') as f:
                        dbx.files_upload(f.read(), csv_path_lower, mode=dropbox.files.WriteMode.overwrite)
                    print(f"Successfully uploaded {local_csv} to Dropbox!")
                
                # Clean up local GitHub runner files
                if os.path.exists(local_txt): os.remove(local_txt)
                if os.path.exists(local_csv): os.remove(local_csv)

    except Exception as e:
        print(f"An error occurred: {e}")

if __name__ == "__main__":
    main()
