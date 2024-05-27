import pandas as pd
import os


def read_and_modify_csv(file_path, custom_headers, new_data, skip_until=30, num_rows=8):
    # Read the specified rows of the CSV file, ignoring original headers
    df = pd.read_csv(file_path, skiprows=skip_until, nrows=num_rows, header=None)

    # Check if the DataFrame has at least eight columns
    if df.shape[1] >= 8:
        # Merge the second (index 1) and third (index 2) columns
        parameter = df.iloc[:, 1].astype(str) + df.iloc[:, 2].astype(str)

        # Drop the original second and third columns
        df.drop([1, 2], axis=1, inplace=True)

        # Insert the merged column at the second position (index 1)
        df.insert(1, 'parameter', parameter)

        # Assign your final custom headers after the structure has been modified
        df.columns = custom_headers

        # Replace the data in the second column with new, manually defined data
        df.iloc[:, 1] = new_data

    return df


def process_all_csv(data_directory, output_directory, custom_headers, new_data, skip_until=30, num_rows=8):
    all_dataframes = []  # List to hold all the dataframes

    # List all CSV files in the given directory
    for filename in os.listdir(data_directory):
        if filename.endswith('.csv'):
            file_path = os.path.join(data_directory, filename)
            # Process each file
            df = read_and_modify_csv(file_path, custom_headers, new_data, skip_until, num_rows)
            all_dataframes.append(df)

    # Concatenate all DataFrames into one
    final_dataframe = pd.concat(all_dataframes, ignore_index=True)
    # Sort the DataFrame by 'point_id' column in ascending order
    final_dataframe = final_dataframe.sort_values(by='point_id', ascending=True)

    # Save the final DataFrame to a CSV file
    output_path = os.path.join(output_directory, 'total_macroelements.csv')
    final_dataframe.to_csv(output_path, index=False)  # Set index=False to avoid writing row numbers to the file

    return output_path


# Usage
base_directory = os.path.dirname(os.path.realpath(__file__))
data_directory = os.path.join(base_directory, 'data')
output_directory = os.path.join(base_directory, 'output')  # Set up the output directory
custom_headers = ['point_id', 'parameter', '1995', '2000', '2005', '2010', '2015', '2020']
new_data = ['P [%]', 'Ca [%]', 'Mg [%]', 'K [%]', 'Na [%]', 'S [%]', 'Al [%]', 'Fe [%]']

# Call the function
output_file_path = process_all_csv(data_directory, output_directory, custom_headers, new_data)
print("Combined CSV saved to:", output_file_path)
