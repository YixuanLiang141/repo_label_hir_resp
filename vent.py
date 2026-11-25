import pandas as pd

def filter_large_csv_by_stay_ids(input_file, output_file, key_col, chunksize=100_000):
    valid_ids = [15001552, 3845]

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

    df = df[["observation_tables/", "patientid", "variableid", "value"]]
    df.rename(columns={'patientid': 'subject_id'}, inplace=True)
    df.rename(columns={'observation_tables/': 'charttime'}, inplace=True)
    df.rename(columns={'variableid': 'itemid'}, inplace=True)

    df = df.drop_duplicates(keep='first')

    df.sort_values(by=['subject_id', 'charttime'], inplace=True)

    df.to_csv(output_csv, index=False)
    print(f"Done, result save to: {output_csv}")

    return df

def build_vent_intervals(input_csv, output_csv, mode_minutes=30, airway_hours=16):
    """Build half-open ventilation intervals from the two HiRID variables.

    Input must be sorted by subject_id, charttime. Mode takes precedence over
    airway; identical observations refresh the corresponding expiry time.
    Conflicting values at the same timestamp make that channel unknown until
    its next update. Unrecognized codes also make that channel unknown.

    IMV inferred from airway alone is a proxy for ventilation, not proof of
    active ventilation. inv_vent is 1 only for IMV; UNKNOWN also receives 0,
    so retain vent_state to distinguish missing evidence from OFF.
    Coverage extends from each subject's first observation to the last expiry;
    no admission/discharge limits are available in this input.
    Writes the CSV and returns its DataFrame. Does not change the input file.
    """
    if mode_minutes <= 0 or airway_hours <= 0:
        raise ValueError("Both validity periods must be positive.")

    columns = ["subject_id", "starttime", "endtime", "vent_state", "source", "inv_vent"]
    df = pd.read_csv(input_csv, usecols=["subject_id", "charttime", "itemid", "value"])
    df["charttime"] = pd.to_datetime(df["charttime"], errors="raise")
    if df[["subject_id", "charttime", "itemid"]].isna().any().any():
        raise ValueError("subject_id, charttime and itemid cannot be missing.")
    order = pd.MultiIndex.from_frame(df[["subject_id", "charttime"]])
    if not order.is_monotonic_increasing:
        raise ValueError("Input must be sorted by subject_id, charttime.")
    df = df[df["itemid"].isin([3845, 15001552])].copy()

    # Identify conflicts without choosing an arbitrary row at the same time.
    keys = ["subject_id", "charttime", "itemid"]
    duplicated = df.duplicated(keys, keep=False)
    if duplicated.any():
        counts = df.loc[duplicated].groupby(keys)["value"].transform("nunique", dropna=False)
        df.loc[counts.index[counts > 1], "value"] = float("nan")
        df = df.drop_duplicates(keys, keep="last")

    mappings = {
        3845: {1: "OFF", **dict.fromkeys([2, 3, 4, 5, 6, 7, 8, 10, 11, 15], "IMV"),
               **dict.fromkeys([12, 13, 14, 17], "NIV_CPAP")},
        15001552: {1: "IMV", 2: "IMV", 3: "NIV_CPAP", 4: "NIV_CPAP", 5: "NIV_CPAP"},
    }
    validity = {3845: pd.Timedelta(minutes=mode_minutes),
                15001552: pd.Timedelta(hours=airway_hours)}
    rows = []
    for subject_id, patient in df.groupby("subject_id", sort=False):
        # Compress repeated readings into channel segments, still refreshing
        # expiry on every reading. This avoids a large fixed time grid.
        events = {patient["charttime"].iloc[0]: {}}
        for itemid, channel in patient.groupby("itemid", sort=False):
            states = channel["value"].map(mappings[itemid]).fillna("UNKNOWN")
            segments = []
            for time, state in zip(channel["charttime"], states):
                end = time + validity[itemid]
                if segments and time <= segments[-1][1] and state == segments[-1][2]:
                    segments[-1][1] = end
                else:
                    if segments and time < segments[-1][1]:
                        segments[-1][1] = time
                    segments.append([time, end, state])
            for start, end, state in segments:
                events.setdefault(start, {})[itemid] = state
                events.setdefault(end, {})[itemid] = "UNKNOWN"

        times = sorted(events)
        current = {3845: "UNKNOWN", 15001552: "UNKNOWN"}
        for index, start in enumerate(times[:-1]):
            current.update(events[start])
            end = times[index + 1]
            if current[3845] != "UNKNOWN":
                state, source = current[3845], "mode"
            elif current[15001552] != "UNKNOWN":
                state, source = current[15001552], "airway"
            else:
                state, source = "UNKNOWN", "unknown"
            if (rows and rows[-1][0] == subject_id and rows[-1][2] == start
                    and rows[-1][3:5] == [state, source]):
                rows[-1][2] = end
            else:
                rows.append([subject_id, start, end, state, source, int(state == "IMV")])

    result = pd.DataFrame(rows, columns=columns)
    result.to_csv(output_csv, index=False)
    return result

if __name__ == "__main__":

    #filter_large_csv_by_stay_ids('../../hirid/observation_tables.csv', './vent_set.csv', 'variableid')
    #merge_rename_converse('./vent_set.csv', './vent_set.csv')
    build_vent_intervals('./vent_set.csv', './vent.csv')