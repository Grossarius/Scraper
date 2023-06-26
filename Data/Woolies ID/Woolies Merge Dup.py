import pandas as pd

def merge_csv_files(file_names, output_file):
    merged_data = pd.DataFrame()

    for file_name in file_names:
        data = pd.read_csv(file_name)
        merged_data = merged_data.append(data)

    merged_data.drop_duplicates(inplace=True)
    merged_data.to_csv(output_file, index=True)

# Usage
file_names = ["Woolies 46 Pantry pantry.csv", "Woolies 56 Pantry pantry.csv", "Woolies 1 pantry.csv"]
output_file = "Woolies pantry.csv"

merge_csv_files(file_names, output_file)