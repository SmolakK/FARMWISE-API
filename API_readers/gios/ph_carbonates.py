import pandas as pd
import os


def read_and_modify_csv(file_path, custom_headers, new_data, skip_until=6, num_rows=3):
    df = pd.read_csv(file_path, skiprows=skip_until, nrows=num_rows, header=None)
    if df.shape[1] >= 8:
        parameter = df.iloc[:, 1].astype(str) + df.iloc[:, 2].astype(str)
        df.drop([1, 2], axis=1, inplace=True)
        df.insert(1, 'parameter', parameter)
        df.columns = custom_headers
        df.iloc[:, 1] = new_data
    return df


def process_all_csv(data_directory, output_directory, custom_headers, new_data, skip_until=7, num_rows=3):
    all_dataframes = []
    for filename in os.listdir(data_directory):
        if filename.endswith('.csv'):
            file_path = os.path.join(data_directory, filename)
            df = read_and_modify_csv(file_path, custom_headers, new_data, skip_until, num_rows)
            all_dataframes.append(df)
    final_dataframe = pd.concat(all_dataframes, ignore_index=True)
    final_dataframe = final_dataframe.sort_values(by='point_id', ascending=True)

    # Check if the output directory exists, create if not
    if not os.path.exists(output_directory):
        os.makedirs(output_directory)

    output_path = os.path.join(output_directory, 'ph_carbonates.csv')
    final_dataframe.to_csv(output_path, index=False)
    return output_path


# Usage
base_directory = os.path.dirname(os.path.realpath(__file__))
data_directory = os.path.join(base_directory, 'data')
output_directory = os.path.join(base_directory, 'output')  # Set up the output directory

custom_headers = ['point_id', 'parameter', '1995', '2000', '2005', '2010', '2015', '2020']
new_data = ['pH_H2O [pH]', 'pH_KCl [pH]', 'CaCo3 [%]']

# Call the function
output_file_path = process_all_csv(data_directory, output_directory, custom_headers, new_data)
print("Combined CSV saved to:", output_file_path)
