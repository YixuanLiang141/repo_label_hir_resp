import pandas as pd

def filter_large_csv_by_stay_ids(input_file, output_file, key_col, chunksize=100_000):
    valid_ids = [20000200, 2010]

    reader = pd.read_csv(input_file, chunksize=chunksize)
    first_chunk = True

    total_rows_kept = 0
    for i, chunk in enumerate(reader):
        filtered_chunk = chunk[chunk[key_col].isin(valid_ids)]
        total_rows_kept += len(filtered_chunk)

        if first_chunk:
            filtered_chunk.to_csv(output_file, index=False, mode='w')
            first_chunk = False
        else:
            filtered_chunk.to_csv(output_file, index=False, mode='a', header=False)

        print(f"Chunk {i+1} done. {len(filtered_chunk)} rows kept.")

def merge_rename_converse(input_csv, output_csv):

    df = pd.read_csv(input_csv)
    
    # Handle rows with empty value but with stringvalue containing "mm Hg"
    mask = df['value'].isna()
    df.loc[mask, 'value'] = pd.to_numeric(
        df.loc[mask, 'stringvalue']
        .astype('string')
        .str.strip()
        .str.replace(r'\s*mm Hg$', '', regex=True),
        errors='coerce'
    )
    
    df = df.dropna(subset=['value'])

    df = df[["observation_tables/", "patientid", "variableid", "value"]]
    df.rename(columns={'patientid': 'subject_id'}, inplace=True)
    df.rename(columns={'observation_tables/': 'charttime'}, inplace=True)
    df.rename(columns={'variableid': 'item'}, inplace=True)

    df = df.drop_duplicates(keep='first')
    
    mapping = {20000200: 'pao2', 2010: 'fio2'}
    df["item"] = df["item"].replace(mapping)

    df.sort_values(by=['subject_id', 'charttime'], inplace=True)

    df.to_csv(output_csv, index=False)
    print(f"Done, result save to: {output_csv}")

    return df

if __name__ == "__main__":

    filter_large_csv_by_stay_ids('../../hirid/observation_tables.csv', './resp.csv', 'variableid')
    merge_rename_converse('./resp.csv', './resp.csv')