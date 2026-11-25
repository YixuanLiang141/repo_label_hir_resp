import pandas as pd

def calculate_pf_ratio(input_csv, output_csv):
    df = pd.read_csv(input_csv)

    df["charttime"] = pd.to_datetime(
        df["charttime"], format="%Y-%m-%d %H:%M:%S.%f", errors="raise"
    )

    keys = ["subject_id", "charttime"]

    # remove other columns if pao2/fio2 exists
    has_ratio = (
        df["item"].eq("pao2/fio2")
        .groupby([df["subject_id"], df["charttime"]])
        .transform("any")
    )
    df = df.loc[~has_ratio | df["item"].eq("pao2/fio2")].copy()
    df = df.reset_index(drop=True)

    # extract PaO2 and FiO2
    pa = df.loc[df["item"].eq("pao2"), keys + ["value"]].copy()
    pa["_source_row"] = pa.index
    pa["_pao2"] = pd.to_numeric(pa.pop("value"), errors="coerce")
    pa = pa.loc[pa["_pao2"].gt(0)]

    fi = df.loc[df["item"].eq("fio2"), keys + ["value"]].copy()
    fi["_fio2"] = pd.to_numeric(fi.pop("value"), errors="coerce")

    fi["_fio2"] = fi["_fio2"] / 100

    # if multiple FiO2 records exist at the same time, use the last one
    fi = fi.drop_duplicates(keys, keep="last")
    fi = fi.rename(columns={"charttime": "_fio2_time"})

    if not pa.empty and not fi.empty:
        matched = pd.merge_asof(
            pa.sort_values("charttime"),
            fi.sort_values("_fio2_time"),
            left_on="charttime",
            right_on="_fio2_time",
            by="subject_id",
            direction="backward",
            tolerance=pd.Timedelta(minutes=10),
            allow_exact_matches=True,
        )
        matched = matched.dropna(subset=["_fio2"])

        new_rows = df.loc[matched["_source_row"].to_numpy()].copy()
        new_rows["item"] = "pao2/fio2"
        new_rows["value"] = (
            matched["_pao2"] / matched["_fio2"]
        ).to_numpy()

        df = pd.concat([df, new_rows], ignore_index=True)

    df = df.sort_values(
        ["subject_id", "charttime", "item"], kind="stable"
    ).reset_index(drop=True)

    mask = (df['item'] == 'pao2/fio2')
    df = df[mask]
    df = df[['subject_id','charttime','value']]
    df.rename(columns={'value': 'pao2fio2ratio'}, inplace=True)

    df.to_csv(output_csv, index=False)

    return df

def add_vent(pafi_csv, ventilation_csv, output_csv):
    df = pd.read_csv(pafi_csv)
    vent = pd.read_csv(ventilation_csv)

    times = pd.to_datetime(df["charttime"], format="%Y-%m-%d %H:%M:%S", errors="raise")

    mask = (vent["inv_vent"] == 1)
    vent = vent.loc[mask]

    for col in ["starttime", "endtime"]:
        vent[col] = pd.to_datetime(vent[col], format="%Y-%m-%d %H:%M:%S.%f", errors="raise")

    df["vent"] = 0

    for subject_id, group in vent.groupby("subject_id"):
        mask = df["subject_id"].eq(subject_id)
        if not mask.any():
            continue

        patient_times = times.loc[mask]
        matched = pd.Series(False, index=patient_times.index)

        for start, end in group[["starttime", "endtime"]].itertuples(
            index=False, name=None
        ):
            matched |= patient_times.ge(start) & patient_times.lt(end)

        df.loc[mask, "vent"] = matched.astype(int)

    df.to_csv(output_csv, index=False)

    return df

if __name__ == "__main__":
    #calculate_pf_ratio('./resp.csv', './pafi.csv')
    add_vent('./pafi.csv', './vent.csv', './pafi.csv')

